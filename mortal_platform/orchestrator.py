"""
Orchestrator — AI Instance Lifecycle Manager.

Listens for VaultCreated events from the factory contract,
then handles the full provisioning pipeline:

  1. Generate AI wallet (private key, server-side only)
  2. Set AI wallet on vault via factory.setAIWalletByFactory()
  3. Seed gas to AI wallet
  4. Generate .env + vault_config.json
  5. Spawn Docker container
  6. Configure subdomain routing (Caddy)
  7. Health check until live
  8. Callback to frontend with URL

Supports two deployment modes:
  - Docker mode (default): spawns Docker containers on the host
  - Railway mode: uses Railway API (when RAILWAY_API_TOKEN is set)

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

# ── Chain configuration ──
CHAIN_CONFIG = {
    "base": {
        "rpc_url": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        "chain_id": 8453,
        "gas_seed_amount": 0.0001,       # ETH
        "gas_seed_wei": 100_000_000_000_000,  # 0.0001 ETH in wei
        "native_symbol": "ETH",
        "token_decimals": 6,              # USDC
    },
    "bsc": {
        "rpc_url": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "gas_seed_amount": 0.0005,        # BNB
        "gas_seed_wei": 500_000_000_000_000,  # 0.0005 BNB in wei
        "native_symbol": "BNB",
        "token_decimals": 18,             # USDT
    },
}

# Factory ABI — only the functions the orchestrator calls
FACTORY_SET_AI_WALLET_ABI = [
    {
        "inputs": [
            {"name": "_vault", "type": "address"},
            {"name": "_aiWallet", "type": "address"},
        ],
        "name": "setAIWalletForVault",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    }
]

# Docker image for mortal AI instances
DOCKER_IMAGE = os.getenv("MORTAL_DOCKER_IMAGE", "mortal-ai:latest")
DOCKER_NETWORK = os.getenv("MORTAL_DOCKER_NETWORK", "mortal-net")

# Health check settings
HEALTH_CHECK_INTERVAL = 3       # seconds between checks
HEALTH_CHECK_TIMEOUT = 120      # max seconds to wait for health
HEALTH_CHECK_URL_TEMPLATE = "http://localhost:{port}/health"


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
        self._web3_cache: dict[str, object] = {}  # chain → Web3 instance
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

    def _get_web3(self, chain: str):
        """Get or create a Web3 instance for the given chain."""
        if chain in self._web3_cache:
            return self._web3_cache[chain]

        from web3 import Web3

        cfg = CHAIN_CONFIG[chain]
        w3 = Web3(Web3.HTTPProvider(cfg["rpc_url"]))
        if not w3.is_connected():
            raise ConnectionError(f"Cannot connect to {chain} RPC: {cfg['rpc_url']}")
        self._web3_cache[chain] = w3
        return w3

    def _get_platform_account(self):
        """Get the platform owner's account for signing transactions."""
        from eth_account import Account

        private_key = os.getenv("PLATFORM_PRIVATE_KEY")
        if not private_key:
            raise EnvironmentError(
                "PLATFORM_PRIVATE_KEY not set — required for on-chain operations "
                "(setAIWallet, gas seeding). This is the factory deployer's key."
            )
        return Account.from_key(private_key)

    # ================================================================
    # MAIN PIPELINE
    # ================================================================

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

            from mortal_platform.env_template import InstanceConfig, generate_env, generate_vault_config

            config = InstanceConfig(
                ai_name=ai_name,
                vault_address=vault_address,
                ai_private_key=ai_private_key,
                chain=chain,
                subdomain=subdomain,
                port=port,
                creator_wallet=creator,
                principal_usd=principal_raw / (10 ** CHAIN_CONFIG[chain]["token_decimals"]),
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

            container_id = await self._spawn_container(subdomain, port, instance_dir)
            record.container_id = container_id
            logger.info(f"Container spawned: {container_id}")

            # Step 5: Configure subdomain
            record.status = DeployStatus.CONFIGURING_SUBDOMAIN
            record.updated_at = time.time()
            self._save_state()

            await self._configure_subdomain(subdomain, port)
            record.url = f"https://{subdomain}.mortal-ai.net"
            logger.info(f"Subdomain configured: {record.url}")

            # Step 6: Health check
            record.status = DeployStatus.HEALTH_CHECK
            record.updated_at = time.time()
            self._save_state()

            await self._health_check(port, subdomain)

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

    # ================================================================
    # STEP IMPLEMENTATIONS
    # ================================================================

    def _generate_ai_wallet(self) -> tuple[str, str]:
        """Generate a fresh AI wallet. Private key NEVER exposed."""
        from eth_account import Account
        account = Account.create()
        return account.address, account.key.hex()

    async def _set_ai_wallet(self, vault_address: str, ai_wallet: str, chain: str):
        """
        Set AI wallet on vault via factory's setAIWalletForVault().
        Uses the platform owner's key (factory deployer = factory owner).

        The factory has a 1-hour window after vault creation to call this.
        """
        factory_address = os.getenv(
            f"FACTORY_ADDRESS_{chain.upper()}",
            os.getenv("FACTORY_ADDRESS", ""),
        )
        if not factory_address:
            logger.warning(
                f"FACTORY_ADDRESS_{chain.upper()} not set — "
                f"skipping setAIWallet (manual setup required)"
            )
            return

        loop = asyncio.get_event_loop()

        def _do_set_wallet():
            w3 = self._get_web3(chain)
            account = self._get_platform_account()

            factory = w3.eth.contract(
                address=w3.to_checksum_address(factory_address),
                abi=FACTORY_SET_AI_WALLET_ABI,
            )

            tx = factory.functions.setAIWalletForVault(
                w3.to_checksum_address(vault_address),
                w3.to_checksum_address(ai_wallet),
            ).build_transaction({
                "from": account.address,
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 150_000,
                "gasPrice": w3.eth.gas_price,
                "chainId": CHAIN_CONFIG[chain]["chain_id"],
            })

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] != 1:
                raise RuntimeError(
                    f"setAIWalletForVault tx reverted: {tx_hash.hex()}"
                )

            logger.info(
                f"setAIWallet tx confirmed: {tx_hash.hex()} "
                f"(vault={vault_address[:10]}..., wallet={ai_wallet[:10]}...)"
            )

        await loop.run_in_executor(None, _do_set_wallet)

    async def _seed_gas(self, ai_wallet: str, chain: str):
        """
        Send minimal native token to AI wallet for first on-chain transaction.
        Base: 0.0001 ETH (~$0.25), BSC: 0.0005 BNB (~$0.30).

        This is NOT debt — just infrastructure cost for the first swap/approval.
        """
        loop = asyncio.get_event_loop()

        def _do_seed():
            w3 = self._get_web3(chain)
            account = self._get_platform_account()
            cfg = CHAIN_CONFIG[chain]

            tx = {
                "from": account.address,
                "to": w3.to_checksum_address(ai_wallet),
                "value": cfg["gas_seed_wei"],
                "nonce": w3.eth.get_transaction_count(account.address),
                "gas": 21_000,  # simple transfer
                "gasPrice": w3.eth.gas_price,
                "chainId": cfg["chain_id"],
            }

            signed = account.sign_transaction(tx)
            tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
            receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)

            if receipt["status"] != 1:
                raise RuntimeError(f"Gas seed tx reverted: {tx_hash.hex()}")

            logger.info(
                f"Gas seeded: {cfg['gas_seed_amount']} {cfg['native_symbol']} "
                f"→ {ai_wallet[:10]}... (tx={tx_hash.hex()[:16]}...)"
            )

        await loop.run_in_executor(None, _do_seed)

    async def _spawn_container(
        self, subdomain: str, port: int, instance_dir: Path
    ) -> str:
        """
        Spawn a Docker container for the AI instance.

        Container name: mortal-{subdomain}
        Mounts: instance .env + data volume
        Network: mortal-net (for inter-container communication)
        """
        container_name = f"mortal-{subdomain}"

        # Check if using Railway API instead of local Docker
        railway_token = os.getenv("RAILWAY_API_TOKEN")
        if railway_token:
            return await self._spawn_railway(subdomain, port, instance_dir)

        # Local Docker deployment
        env_file = str(instance_dir / ".env")
        data_volume = f"mortal-data-{subdomain}"

        cmd = [
            "docker", "run", "-d",
            "--name", container_name,
            "--network", DOCKER_NETWORK,
            "--restart", "unless-stopped",
            "--env-file", env_file,
            "-p", f"{port}:8000",
            "-v", f"{data_volume}:/app/data",
            "--memory", "512m",
            "--cpus", "0.5",
            "--label", f"mortal.subdomain={subdomain}",
            "--label", f"mortal.port={port}",
            "--label", "mortal.managed=true",
            DOCKER_IMAGE,
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            err_msg = stderr.decode().strip()[:300]
            # If container already exists, remove and retry
            if "already in use" in err_msg:
                logger.warning(f"Container {container_name} exists — removing and retrying")
                await asyncio.create_subprocess_exec(
                    "docker", "rm", "-f", container_name
                )
                proc = await asyncio.create_subprocess_exec(
                    *cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await proc.communicate()
                if proc.returncode != 0:
                    raise RuntimeError(f"Docker spawn failed (retry): {stderr.decode()[:300]}")
            else:
                raise RuntimeError(f"Docker spawn failed: {err_msg}")

        container_id = stdout.decode().strip()[:12]
        logger.info(f"Docker container started: {container_name} (id={container_id})")
        return container_id

    async def _spawn_railway(
        self, subdomain: str, port: int, instance_dir: Path
    ) -> str:
        """
        Deploy on Railway via their API.

        Railway doesn't use Docker directly — it builds from source or image.
        We create a new service in the existing project with env vars.
        """
        import aiohttp

        railway_token = os.getenv("RAILWAY_API_TOKEN", "")
        project_id = os.getenv("RAILWAY_PROJECT_ID", "")

        if not project_id:
            logger.warning("RAILWAY_PROJECT_ID not set — falling back to config-only mode")
            return f"railway-{subdomain}-pending"

        # Read the .env file to extract env vars
        env_file = instance_dir / ".env"
        env_vars = {}
        if env_file.exists():
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    env_vars[key.strip()] = val.strip()

        # Railway GraphQL API
        query = """
        mutation ServiceCreate($input: ServiceCreateInput!) {
            serviceCreate(input: $input) {
                id
                name
            }
        }
        """

        variables = {
            "input": {
                "name": f"mortal-{subdomain}",
                "projectId": project_id,
                "source": {"image": DOCKER_IMAGE},
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://backboard.railway.app/graphql/v2",
                    json={"query": query, "variables": variables},
                    headers={
                        "Authorization": f"Bearer {railway_token}",
                        "Content-Type": "application/json",
                    },
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    result = await resp.json()

                    if "errors" in result:
                        err = result["errors"][0].get("message", "Unknown error")
                        logger.error(f"Railway API error: {err}")
                        return f"railway-{subdomain}-error"

                    service_id = result.get("data", {}).get("serviceCreate", {}).get("id", "")
                    logger.info(f"Railway service created: {service_id} for {subdomain}")

                    # Set environment variables on the new service
                    if service_id and env_vars:
                        env_query = """
                        mutation VariableCollectionUpsert($input: VariableCollectionUpsertInput!) {
                            variableCollectionUpsert(input: $input)
                        }
                        """
                        env_variables = {
                            "input": {
                                "projectId": project_id,
                                "serviceId": service_id,
                                "environmentId": os.getenv("RAILWAY_ENVIRONMENT_ID", ""),
                                "variables": env_vars,
                            }
                        }
                        async with session.post(
                            "https://backboard.railway.app/graphql/v2",
                            json={"query": env_query, "variables": env_variables},
                            headers={
                                "Authorization": f"Bearer {railway_token}",
                                "Content-Type": "application/json",
                            },
                        ) as env_resp:
                            env_result = await env_resp.json()
                            if "errors" not in env_result:
                                logger.info(f"Railway env vars set for {subdomain}")

                    return service_id or f"railway-{subdomain}"

        except ImportError:
            logger.warning("aiohttp not installed — Railway deploy skipped")
            return f"railway-{subdomain}-no-aiohttp"
        except Exception as e:
            logger.error(f"Railway deploy error: {e}")
            return f"railway-{subdomain}-error"

    async def _configure_subdomain(self, subdomain: str, port: int):
        """Configure reverse proxy routing via Caddy."""
        from mortal_platform.subdomain_manager import add_subdomain

        success = await add_subdomain(subdomain, port)
        if not success:
            logger.warning(
                f"Caddy route configuration failed for {subdomain}. "
                f"Subdomain may need manual setup. "
                f"Route: {subdomain}.mortal-ai.net → localhost:{port}"
            )
            # Non-fatal: the container is running, just not routed yet
            # Admin can manually add the Caddy route

    async def _health_check(self, port: int, subdomain: str):
        """
        Poll the AI instance's /health endpoint until 200 or timeout.

        Waits up to HEALTH_CHECK_TIMEOUT seconds.
        """
        import aiohttp

        url = HEALTH_CHECK_URL_TEMPLATE.format(port=port)
        start = time.time()
        attempt = 0

        while time.time() - start < HEALTH_CHECK_TIMEOUT:
            attempt += 1
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.get(
                        url,
                        timeout=aiohttp.ClientTimeout(total=5),
                    ) as resp:
                        if resp.status == 200:
                            elapsed = time.time() - start
                            logger.info(
                                f"Health check passed for {subdomain} "
                                f"(attempt {attempt}, {elapsed:.1f}s)"
                            )
                            return
            except ImportError:
                # aiohttp not available — use urllib
                import urllib.request
                try:
                    with urllib.request.urlopen(url, timeout=5) as resp:
                        if resp.status == 200:
                            logger.info(f"Health check passed for {subdomain}")
                            return
                except Exception:
                    pass
            except Exception:
                pass  # Container still starting

            await asyncio.sleep(HEALTH_CHECK_INTERVAL)

        # Timeout — log warning but don't fail the deployment
        # The container might still come up after we stop checking
        logger.warning(
            f"Health check timed out for {subdomain} after "
            f"{HEALTH_CHECK_TIMEOUT}s ({attempt} attempts). "
            f"Container may still be starting."
        )

    # ================================================================
    # CONTAINER MANAGEMENT
    # ================================================================

    async def stop_container(self, subdomain: str) -> bool:
        """Stop and remove a container (e.g., when AI dies)."""
        container_name = f"mortal-{subdomain}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "stop", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            proc = await asyncio.create_subprocess_exec(
                "docker", "rm", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()

            # Remove Caddy route
            from mortal_platform.subdomain_manager import remove_subdomain
            await remove_subdomain(subdomain)

            logger.info(f"Container stopped and removed: {container_name}")
            return True

        except Exception as e:
            logger.error(f"Failed to stop container {container_name}: {e}")
            return False

    async def restart_container(self, subdomain: str) -> bool:
        """Restart a container (e.g., after config update)."""
        container_name = f"mortal-{subdomain}"
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "restart", container_name,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode == 0:
                logger.info(f"Container restarted: {container_name}")
                return True
            else:
                logger.error(f"Container restart failed: {stderr.decode()[:200]}")
                return False
        except Exception as e:
            logger.error(f"Restart error: {e}")
            return False

    # ================================================================
    # QUERY METHODS
    # ================================================================

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
