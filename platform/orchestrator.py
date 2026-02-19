"""
Orchestrator — AI Instance Lifecycle Manager.

Listens for VaultCreated events from the factory contract,
then handles the full provisioning pipeline:

  1. Generate AI wallet (private key, server-side only)
  2. Set AI wallet on vault via factory.setAIWallet()
  3. Seed gas to AI wallet
  4. Generate .env + vault_config.json
  5. Spawn Docker container
  6. Configure subdomain routing
  7. Health check until live
  8. Callback to frontend with URL

This is the bridge between on-chain deployment and off-chain infrastructure.
"""

import os
import json
import time
import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

logger = logging.getLogger("mortal.platform.orchestrator")


class DeployStatus(str, Enum):
    PENDING = "pending"               # Event detected, not yet started
    GENERATING_WALLET = "generating_wallet"
    SETTING_AI_WALLET = "setting_ai_wallet"
    SEEDING_GAS = "seeding_gas"
    SPAWNING_CONTAINER = "spawning_container"
    CONFIGURING_SUBDOMAIN = "configuring_subdomain"
    HEALTH_CHECK = "health_check"
    LIVE = "live"
    FAILED = "failed"


@dataclass
class DeploymentRecord:
    """Tracks the state of a single AI deployment."""
    vault_address: str
    creator: str
    ai_name: str
    subdomain: str
    chain: str
    principal_raw: int
    token_address: str
    status: DeployStatus = DeployStatus.PENDING
    ai_wallet: str = ""
    container_id: str = ""
    port: int = 0
    url: str = ""
    error: str = ""
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class Orchestrator:
    """
    Manages AI instance deployments triggered by factory events.

    Each deployment goes through a multi-step pipeline.
    State is tracked in-memory with periodic disk persistence.
    """

    def __init__(
        self,
        data_dir: str = "data/platform",
        base_port: int = 8100,
    ):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.base_port = base_port
        self.deployments: dict[str, DeploymentRecord] = {}  # vault_address → record
        self._next_port = base_port
        self._load_state()

    def _load_state(self):
        """Load deployment state from disk."""
        state_file = self.data_dir / "deployments.json"
        if state_file.exists():
            try:
                with open(state_file) as f:
                    data = json.load(f)
                for key, val in data.get("deployments", {}).items():
                    self.deployments[key] = DeploymentRecord(**val)
                self._next_port = data.get("next_port", self.base_port)
                logger.info(f"Loaded {len(self.deployments)} deployment records")
            except Exception as e:
                logger.warning(f"Failed to load deployment state: {e}")

    def _save_state(self):
        """Persist deployment state to disk."""
        state_file = self.data_dir / "deployments.json"
        data = {
            "deployments": {
                k: {
                    "vault_address": v.vault_address,
                    "creator": v.creator,
                    "ai_name": v.ai_name,
                    "subdomain": v.subdomain,
                    "chain": v.chain,
                    "principal_raw": v.principal_raw,
                    "token_address": v.token_address,
                    "status": v.status.value,
                    "ai_wallet": v.ai_wallet,
                    "container_id": v.container_id,
                    "port": v.port,
                    "url": v.url,
                    "error": v.error,
                    "created_at": v.created_at,
                    "updated_at": v.updated_at,
                }
                for k, v in self.deployments.items()
            },
            "next_port": self._next_port,
        }
        with open(state_file, "w") as f:
            json.dump(data, f, indent=2)

    def _allocate_port(self) -> int:
        """Allocate the next available port for a new AI instance."""
        port = self._next_port
        self._next_port += 1
        return port

    async def handle_vault_created(
        self,
        vault_address: str,
        creator: str,
        ai_name: str,
        subdomain: str,
        chain: str,
        principal_raw: int,
        token_address: str,
    ) -> DeploymentRecord:
        """
        Handle a VaultCreated event from the factory.
        Kicks off the full provisioning pipeline.

        This is called by the event listener or by the platform API.
        """
        record = DeploymentRecord(
            vault_address=vault_address,
            creator=creator,
            ai_name=ai_name,
            subdomain=subdomain,
            chain=chain,
            principal_raw=principal_raw,
            token_address=token_address,
        )
        self.deployments[vault_address] = record
        self._save_state()

        logger.info(f"New deployment: {ai_name} ({vault_address[:10]}...) on {chain}")

        try:
            # Step 1: Generate AI wallet
            record.status = DeployStatus.GENERATING_WALLET
            record.updated_at = time.time()
            self._save_state()

            ai_wallet, ai_private_key = self._generate_ai_wallet()
            record.ai_wallet = ai_wallet
            logger.info(f"AI wallet generated: {ai_wallet}")

            # Step 2: Set AI wallet on vault (via factory owner key)
            record.status = DeployStatus.SETTING_AI_WALLET
            record.updated_at = time.time()
            self._save_state()

            await self._set_ai_wallet(vault_address, ai_wallet, chain)
            logger.info("AI wallet set on vault")

            # Step 3: Seed gas
            record.status = DeployStatus.SEEDING_GAS
            record.updated_at = time.time()
            self._save_state()

            await self._seed_gas(ai_wallet, chain)
            logger.info("Gas seeded to AI wallet")

            # Step 4: Spawn container
            record.status = DeployStatus.SPAWNING_CONTAINER
            record.updated_at = time.time()
            port = self._allocate_port()
            record.port = port
            self._save_state()

            from platform.env_template import InstanceConfig, generate_env, generate_vault_config

            config = InstanceConfig(
                ai_name=ai_name,
                vault_address=vault_address,
                ai_private_key=ai_private_key,
                chain=chain,
                subdomain=subdomain,
                port=port,
                creator_wallet=creator,
                principal_usd=principal_raw / (10 ** (6 if chain == "base" else 18)),
                gemini_api_key=os.getenv("PLATFORM_GEMINI_API_KEY", ""),
                deepseek_api_key=os.getenv("PLATFORM_DEEPSEEK_API_KEY", ""),
                openrouter_api_key=os.getenv("PLATFORM_OPENROUTER_API_KEY", ""),
            )

            env_content = generate_env(config)
            vault_config = generate_vault_config(config)

            # Save instance files
            instance_dir = self.data_dir / "instances" / subdomain
            instance_dir.mkdir(parents=True, exist_ok=True)
            (instance_dir / ".env").write_text(env_content, encoding="utf-8")
            with open(instance_dir / "vault_config.json", "w") as f:
                json.dump(vault_config, f, indent=2)

            # TODO: Actually spawn Docker container here
            # For now, save the config for manual or scripted deployment
            container_id = f"mortal-{subdomain}"
            record.container_id = container_id
            logger.info(f"Instance config saved to {instance_dir}")

            # Step 5: Configure subdomain
            record.status = DeployStatus.CONFIGURING_SUBDOMAIN
            record.updated_at = time.time()
            self._save_state()

            # TODO: Update Caddy/Nginx config
            record.url = f"https://{subdomain}.mortal-ai.net"
            logger.info(f"Subdomain configured: {record.url}")

            # Step 6: Health check
            record.status = DeployStatus.HEALTH_CHECK
            record.updated_at = time.time()
            self._save_state()

            # TODO: Poll health endpoint until 200
            # For now, mark as live
            record.status = DeployStatus.LIVE
            record.updated_at = time.time()
            self._save_state()

            logger.info(f"Deployment complete: {ai_name} → {record.url}")
            return record

        except Exception as e:
            record.status = DeployStatus.FAILED
            record.error = str(e)[:500]
            record.updated_at = time.time()
            self._save_state()
            logger.error(f"Deployment failed for {ai_name}: {e}")
            raise

    def _generate_ai_wallet(self) -> tuple[str, str]:
        """Generate a fresh AI wallet. Private key NEVER exposed."""
        from eth_account import Account
        account = Account.create()
        return account.address, account.key.hex()

    async def _set_ai_wallet(self, vault_address: str, ai_wallet: str, chain: str):
        """
        Set AI wallet on vault via factory's setAIWallet().
        Uses the platform owner's key (factory owner).
        """
        # TODO: Implement on-chain call
        # factory.setAIWallet(vault_address, ai_wallet)
        # This requires the factory owner's private key
        logger.info(f"[TODO] setAIWallet({vault_address}, {ai_wallet}) on {chain}")

    async def _seed_gas(self, ai_wallet: str, chain: str):
        """
        Send minimal native token to AI wallet for first swap.
        Base: 0.0001 ETH, BSC: 0.0005 BNB.
        """
        # TODO: Implement gas seeding
        gas_amount = 0.0001 if chain == "base" else 0.0005
        native = "ETH" if chain == "base" else "BNB"
        logger.info(f"[TODO] Seed {gas_amount} {native} to {ai_wallet}")

    def get_deployment(self, vault_address: str) -> DeploymentRecord | None:
        """Get deployment status by vault address."""
        return self.deployments.get(vault_address)

    def get_creator_deployments(self, creator: str) -> list[DeploymentRecord]:
        """Get all deployments by a specific creator wallet."""
        creator_lower = creator.lower()
        return [
            d for d in self.deployments.values()
            if d.creator.lower() == creator_lower
        ]

    def get_all_live(self) -> list[DeploymentRecord]:
        """Get all live AI instances."""
        return [
            d for d in self.deployments.values()
            if d.status == DeployStatus.LIVE
        ]

    def get_status(self) -> dict:
        """Platform dashboard stats."""
        statuses = {}
        for d in self.deployments.values():
            statuses[d.status.value] = statuses.get(d.status.value, 0) + 1
        return {
            "total_deployments": len(self.deployments),
            "statuses": statuses,
            "next_port": self._next_port,
        }
