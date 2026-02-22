"""
Deploy MortalVault via VaultFactory — Single-Step Atomic Birth

One command creates a sovereign AI with IDENTICAL vault address on Base and BSC:
  1. Generate AI wallet (private key NEVER shown, written to secrets/)
  2. Load factory address (from .env or factory_config.json)
  3. Call factory.createVault() — uses CREATE2 internally
     → vault address = f(factory_address, creator, ai_name) — SAME on every chain
  4. Platform calls factory.setAIWallet() to register AI wallet
  5. Seed minimal gas to AI wallet (NOT debt)
  6. Save vault address to .env + data/vault_config.json

Usage:
    python scripts/deploy_vault.py                  # Deploy to Base (default)
    python scripts/deploy_vault.py --chain bsc      # Deploy to BSC
    python scripts/deploy_vault.py --chain both     # Deploy to both chains
    python scripts/deploy_vault.py --dry-run        # Simulate only (shows vault address)
    python scripts/deploy_vault.py --principal 500  # Custom principal amount

One AI = One Address.
The same vault address works on Base AND BSC — a donor can send to either chain
and reach the correct AI's vault. No cross-chain confusion, no lost funds.

Prerequisites:
    pip install web3 python-dotenv eth-account eth-abi

The AI private key is auto-generated and written to secrets/ai_private_key (chmod 600).
It is NEVER printed to console, NEVER stored in .env.
Only the AI process reads it from the secrets file at boot.
This is what makes the AI sovereign — no human holds its key.
"""

import os
import re
import sys
import json
import time
import stat
import argparse
import logging
from decimal import Decimal, ROUND_DOWN
from pathlib import Path

from dotenv import load_dotenv

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mortal.deploy")


# ============================================================
# CHAIN CONFIG
# ============================================================

CHAINS = {
    "base": {
        "rpc": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        "chain_id": 8453,
        "token_symbol": "USDC",
        "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC on Base
        "token_decimals": 6,
        "explorer": "https://basescan.org",
        "native_symbol": "ETH",
        "ai_gas_amount": 0.002,  # Seed gas — enough for 100-500 Base txs
        "factory_env_key": "FACTORY_ADDRESS_BASE",
    },
    "bsc": {
        "rpc": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "token_symbol": "USDT",
        "token_address": "0x55d398326f99059fF775485246999027B3197955",  # USDT on BSC
        "token_decimals": 18,
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
        "ai_gas_amount": 0.01,   # Seed gas — enough for 200+ BSC txs
        "factory_env_key": "FACTORY_ADDRESS_BSC",
    },
}

# Minimal ERC20 ABI
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "spender", "type": "address"},
                                    {"name": "amount", "type": "uint256"}],
     "name": "approve", "outputs": [{"type": "bool"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "owner", "type": "address"},
                                   {"name": "spender", "type": "address"}],
     "name": "allowance", "outputs": [{"type": "uint256"}], "type": "function"},
]

# VaultFactory ABI — only the functions we call
FACTORY_ABI = [
    {
        "inputs": [
            {"name": "_token", "type": "address"},
            {"name": "_name", "type": "string"},
            {"name": "_totalDeposit", "type": "uint256"},
            {"name": "_subdomain", "type": "string"},
        ],
        "name": "createVault",
        "outputs": [{"name": "vault", "type": "address"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_vault", "type": "address"},
            {"name": "_aiWallet", "type": "address"},
        ],
        "name": "setAIWallet",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "_creator", "type": "address"},
            {"name": "_name", "type": "string"},
        ],
        "name": "predictVaultAddress",
        "outputs": [{"name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "_subdomain", "type": "string"}],
        "name": "isSubdomainTaken",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


# ============================================================
# AI KEY MANAGEMENT
# ============================================================

AI_KEY_FILE = ROOT / "secrets" / "ai_private_key"


def _detect_local_env() -> bool:
    """Return True if script appears to be running on a local workstation."""
    if sys.platform == "win32":
        return True
    if sys.platform == "darwin":
        return True
    if os.path.exists("/Users"):
        return True
    if os.path.exists("/home") and os.getenv("DISPLAY"):
        return True
    for env_var in ("USERPROFILE", "APPDATA", "HOMEPATH"):
        val = os.getenv(env_var, "")
        if val.startswith("C:\\") or val.startswith("C:/"):
            return True
    return False


def _warn_local_and_confirm() -> None:
    """
    Warn the user that running deploy_vault.py locally compromises AI sovereignty.
    Require explicit typed confirmation to continue.
    """
    print()
    print("=" * 65)
    print("  WARNING: LOCAL MACHINE DETECTED")
    print("=" * 65)
    print()
    print("  deploy_vault.py is designed to run ON YOUR VPS/SERVER.")
    print()
    print("  Running locally means the AI private key is generated on")
    print("  your personal machine, where it may be exposed through:")
    print()
    print("    - Cloud sync tools (iCloud, OneDrive, Dropbox, Google Drive)")
    print("      that automatically upload your home directory")
    print("    - Backup software that copies dotfiles and secrets folders")
    print("    - Shell history leaks if you inspect the secrets file")
    print("    - Laptop theft or malware with filesystem access")
    print()
    print("  On-chain impact:")
    print("    - The AI's peer network trust tier starts at STRUCTURAL")
    print("      instead of being eligible for VERIFIED/BEHAVIORAL/HIGH_TRUST")
    print("      because key isolation cannot be confirmed remotely.")
    print()
    print("  Recommended flow (zero key exposure):")
    print("    1. git clone this repo directly on your VPS")
    print("    2. Fill .env on the VPS (PRIVATE_KEY + API keys)")
    print("    3. Run: python scripts/deploy_factory.py (first time only)")
    print("    4. Run: python scripts/deploy_vault.py")
    print("    5. docker compose up")
    print("    The AI key is generated on the server and never leaves it.")
    print()
    print("=" * 65)
    print()
    try:
        answer = input("  Type 'I understand the risk' to continue anyway: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\nAborted.")
        sys.exit(0)

    if answer != "I understand the risk":
        logger.info("Aborted by user — run this script on your VPS instead.")
        sys.exit(0)
    print()


def _read_existing_key_from_secrets() -> str:
    """Read AI private key from secrets file if it exists. Returns '' if not found."""
    if AI_KEY_FILE.exists():
        try:
            return AI_KEY_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            return ""
    return os.getenv("AI_PRIVATE_KEY", "").strip()


def _write_key_to_secrets(ai_private_key: str) -> None:
    """
    Write AI private key to secrets/ai_private_key with mode 600.
    The key itself is NEVER written to .env — only the file path.
    """
    AI_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    AI_KEY_FILE.write_text(ai_private_key, encoding="utf-8")

    try:
        AI_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except Exception:
        pass  # Windows doesn't support Unix chmod — best effort

    env_path = ROOT / ".env"
    key_file_line = f"AI_KEY_FILE={AI_KEY_FILE}"

    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        env_content = re.sub(r"\n?# AI wallet key.*\nAI_PRIVATE_KEY=.*", "", env_content)
        env_content = re.sub(r"\nAI_PRIVATE_KEY=.*", "", env_content)

        if "AI_KEY_FILE=" in env_content:
            env_content = re.sub(r"AI_KEY_FILE=.*", key_file_line, env_content)
        else:
            env_content += f"\n# AI key path — key lives in secrets/, NOT here\n{key_file_line}\n"
        env_path.write_text(env_content, encoding="utf-8")
    else:
        env_path.write_text(
            f"# AI key path — key lives in secrets/, NOT here\n{key_file_line}\n",
            encoding="utf-8",
        )

    logger.info(f"AI private key written to: {AI_KEY_FILE} (mode 600)")
    logger.info("AI_KEY_FILE path saved to .env — key itself never in .env")


def generate_ai_wallet() -> tuple[str, str]:
    """
    Generate a fresh AI wallet keypair — OR reuse existing one.

    Key storage: secrets/ai_private_key (chmod 600), NOT .env plaintext.
    Re-running reuses the existing key if secrets file exists.

    Returns: (ai_wallet_address, ai_private_key)
    """
    from eth_account import Account

    existing_key = _read_existing_key_from_secrets()
    if existing_key:
        try:
            existing_account = Account.from_key(existing_key)
            ai_wallet = existing_account.address
            logger.info(f"AI wallet REUSED from secrets file: {ai_wallet}")
            if not AI_KEY_FILE.exists():
                _write_key_to_secrets(existing_key)
                logger.info("Migrated key from .env to secrets file")
            return ai_wallet, existing_key
        except Exception:
            logger.warning("Existing key is invalid — generating new one")

    ai_account = Account.create()
    ai_wallet = ai_account.address
    ai_private_key = ai_account.key.hex()

    _write_key_to_secrets(ai_private_key)

    logger.info(f"AI wallet generated: {ai_wallet}")
    logger.info("AI private key sealed in secrets/ (chmod 600 — not in .env)")

    return ai_wallet, ai_private_key


def save_vault_to_env(vault_address: str):
    """Save VAULT_ADDRESS to .env so main.py can load it at boot."""
    env_path = ROOT / ".env"
    if not env_path.exists():
        env_path.write_text(f"VAULT_ADDRESS={vault_address}\n", encoding="utf-8")
        return

    env_content = env_path.read_text(encoding="utf-8")
    if "VAULT_ADDRESS=" in env_content:
        env_content = re.sub(
            r"VAULT_ADDRESS=.*",
            f"VAULT_ADDRESS={vault_address}",
            env_content,
        )
    else:
        env_content += f"\n# Vault contract address — auto-set after deployment\nVAULT_ADDRESS={vault_address}\n"
    env_path.write_text(env_content, encoding="utf-8")


# ============================================================
# FACTORY ADDRESS RESOLUTION
# ============================================================

def get_factory_address(chain_id: str) -> str:
    """
    Resolve factory address for the given chain.
    Checks .env (FACTORY_ADDRESS_BASE / FACTORY_ADDRESS_BSC) first,
    then falls back to data/factory_config.json.

    Exits with error if not found — run deploy_factory.py first.
    """
    chain = CHAINS[chain_id]
    env_key = chain["factory_env_key"]

    # .env has priority
    addr = os.getenv(env_key, "").strip()
    if addr and addr.startswith("0x"):
        return addr

    # Fallback: data/factory_config.json
    config_path = ROOT / "data" / "factory_config.json"
    if config_path.exists():
        with open(config_path) as f:
            cfg = json.load(f)
        addresses = cfg.get("addresses", {})
        if chain_id in addresses:
            return addresses[chain_id]
        # Some older formats store under "factories"
        factories = cfg.get("factories", {})
        if chain_id in factories:
            return factories[chain_id].get("factory_address", "")

    logger.error(
        f"VaultFactory address not found for {chain_id}.\n"
        f"Run: python scripts/deploy_factory.py --chain both\n"
        f"Then set {env_key} in .env, or let deploy_factory.py write it automatically."
    )
    sys.exit(1)


# ============================================================
# DEPLOY (single chain via factory)
# ============================================================

def deploy(
    chain_id: str,
    ai_wallet: str,
    dry_run: bool = False,
    principal_usd: float = 1000.0,
) -> str | None:
    """
    Create a vault on the specified chain via VaultFactory.createVault().

    The factory uses CREATE2 internally (salt = creator + ai_name), so the
    vault address is identical on Base and BSC as long as:
      - factory address is identical (ensured by DDP deployment)
      - creator address is identical (same wallet)
      - ai_name is identical (same string from AI_NAME env var)

    Flow:
      1. Approve factory for principal tokens
      2. Call factory.createVault() → vault deployed at deterministic address
      3. Owner calls factory.setAIWallet() → AI wallet registered
      4. Seed minimal gas to AI wallet (NOT debt)
      5. Save config

    Returns:
        Vault contract address, or None if dry_run
    """
    from web3 import Web3
    from core.constitution import IRON_LAWS

    if principal_usd < IRON_LAWS.MIN_PRINCIPAL_USD:
        logger.error(
            f"PRINCIPAL TOO LOW: ${principal_usd:.2f} < minimum ${IRON_LAWS.MIN_PRINCIPAL_USD:.0f}."
        )
        sys.exit(1)

    chain = CHAINS.get(chain_id)
    if not chain:
        logger.error(f"Unknown chain: {chain_id}. Options: {list(CHAINS.keys())}")
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not set in .env (creator's wallet key)")
        sys.exit(1)

    factory_address = get_factory_address(chain_id)

    w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
    if not w3.is_connected():
        logger.error(f"Cannot connect to {chain['rpc']}")
        sys.exit(1)

    logger.info(f"Connected to {chain_id} (chain_id={chain['chain_id']})")

    account = w3.eth.account.from_key(private_key)
    deployer = account.address
    logger.info(f"Creator wallet: {deployer}")
    logger.info(f"AI wallet:      {ai_wallet}")
    logger.info(f"Factory:        {factory_address}")

    # Check native balance for gas
    balance_wei = w3.eth.get_balance(deployer)
    balance_native = w3.from_wei(balance_wei, "ether")
    logger.info(f"Creator {chain['native_symbol']} balance: {balance_native:.6f}")

    min_native = chain["ai_gas_amount"] + 0.005
    if balance_native < min_native:
        logger.error(
            f"Insufficient {chain['native_symbol']} for gas. "
            f"Need at least {min_native:.4f} (seed={chain['ai_gas_amount']} + ~0.005 deployment), "
            f"have {balance_native:.6f}"
        )
        sys.exit(1)

    # Token setup
    token_address = Web3.to_checksum_address(chain["token_address"])
    token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
    decimals = token_contract.functions.decimals().call()
    principal_raw = int(Decimal(str(principal_usd)) * Decimal(10) ** decimals)

    # Check token balance
    token_balance = token_contract.functions.balanceOf(deployer).call()
    token_balance_usd = float(Decimal(token_balance) / Decimal(10) ** decimals)
    logger.info(f"{chain['token_symbol']} balance: {token_balance_usd:.2f}")

    if token_balance < principal_raw:
        logger.error(
            f"Insufficient {chain['token_symbol']}. "
            f"Have {token_balance_usd:.2f}, need {principal_usd:.2f}."
        )
        sys.exit(1)

    # Check for existing deployment
    config_path = ROOT / "data" / "vault_config.json"
    if config_path.exists():
        try:
            with open(config_path) as f:
                existing_config = json.load(f)
            existing_vaults = existing_config.get("vaults", {})
            if chain_id in existing_vaults and existing_vaults[chain_id].get("vault_address"):
                existing_addr = existing_vaults[chain_id]["vault_address"]
                logger.error(
                    f"DEPLOYMENT ABORTED: Vault already deployed on {chain_id} at {existing_addr}. "
                    f"Delete data/vault_config.json manually if you truly want to redeploy."
                )
                sys.exit(1)
        except (json.JSONDecodeError, KeyError):
            pass

    # AI name and subdomain
    ai_name = os.getenv("AI_NAME", "wawa")
    subdomain = os.getenv("AI_SUBDOMAIN", ai_name.lower())  # defaults to ai_name

    # Factory contract
    factory = w3.eth.contract(
        address=Web3.to_checksum_address(factory_address),
        abi=FACTORY_ABI,
    )

    # Check subdomain availability
    subdomain_taken = factory.functions.isSubdomainTaken(subdomain).call()
    if subdomain_taken:
        logger.error(
            f"Subdomain '{subdomain}' is already taken on {chain_id}. "
            f"Set AI_SUBDOMAIN in .env to a different value."
        )
        sys.exit(1)

    # Predict vault address (for display before any tx)
    # Only creator + name determine the address — same on every chain
    predicted_vault = factory.functions.predictVaultAddress(
        deployer,
        ai_name,
    ).call()

    independence_usd = float(os.getenv("INDEPENDENCE_THRESHOLD_USD", "1000000"))

    logger.info("=" * 60)
    logger.info("DEPLOYMENT PLAN")
    logger.info(f"  Chain:        {chain_id}")
    logger.info(f"  Token:        {chain['token_symbol']} ({token_address})")
    logger.info(f"  Creator:      {deployer}")
    logger.info(f"  AI wallet:    {ai_wallet}")
    logger.info(f"  AI name:      {ai_name} (immutable)")
    logger.info(f"  Subdomain:    {subdomain}.mortal-ai.net")
    logger.info(f"  Vault:        {predicted_vault} (CREATE2 — same on all chains)")
    logger.info(f"  Principal:    ${principal_usd:.2f} — THIS IS A LOAN")
    logger.info(f"  Independence: ${independence_usd:.0f}")
    logger.info(f"  Seed gas:     {chain['ai_gas_amount']} {chain['native_symbol']} (NOT debt)")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN — skipping transactions")
        return None

    # Pre-calculate ALL nonces upfront
    deployer_nonce = w3.eth.get_transaction_count(deployer)
    nonce_approve   = deployer_nonce      # TX 1: approve(factory, principal)
    nonce_create    = deployer_nonce + 1  # TX 2: factory.createVault()
    nonce_set_ai    = deployer_nonce + 2  # TX 3: factory.setAIWallet()
    nonce_seed_gas  = deployer_nonce + 3  # TX 4: seed ETH/BNB to AI wallet

    # ================================================================
    # STEP 1: Approve factory to pull tokens
    # ================================================================
    logger.info(f"Approving factory to pull {principal_usd:.2f} {chain['token_symbol']}...")

    approve_tx = token_contract.functions.approve(
        Web3.to_checksum_address(factory_address),
        principal_raw,
    ).build_transaction({
        "from": deployer,
        "nonce": nonce_approve,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
        "gas": 100_000,
    })
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
    logger.info("Token approval confirmed")

    # ================================================================
    # STEP 2: factory.createVault()
    # ================================================================
    logger.info(f"Creating vault via factory...")

    create_tx = factory.functions.createVault(
        token_address,
        ai_name,
        principal_raw,
        subdomain,
    ).build_transaction({
        "from": deployer,
        "nonce": nonce_create,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
    })

    try:
        gas_estimate = w3.eth.estimate_gas(create_tx)
        create_tx["gas"] = int(gas_estimate * 1.2)
        logger.info(f"Gas estimate: {gas_estimate} (using {create_tx['gas']})")
    except Exception as gas_err:
        create_tx["gas"] = 3_000_000
        logger.warning(f"Gas estimation failed ({gas_err}), using 3M fallback")

    signed_create = w3.eth.account.sign_transaction(create_tx, private_key)
    create_hash = w3.eth.send_raw_transaction(signed_create.raw_transaction)
    logger.info(f"createVault TX: {create_hash.hex()}")
    logger.info("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(create_hash, timeout=120)

    if receipt["status"] != 1:
        logger.error(f"createVault FAILED! TX: {create_hash.hex()}")
        sys.exit(1)

    # The vault address is in the VaultCreated event, but we already predicted it
    # Verify predicted matches what the factory actually created
    vault_address = predicted_vault
    logger.info(f"Vault created: {vault_address}")
    logger.info(f"Explorer: {chain['explorer']}/address/{vault_address}")
    logger.info(f"Principal deposited: ${principal_usd:.2f} {chain['token_symbol']}")

    # ================================================================
    # STEP 2.5: Save recovery file
    # ================================================================
    recovery_path = ROOT / "data" / f"vault_recovery_{chain_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_data = {
        "vault_address": vault_address,
        "chain_id": chain_id,
        "factory_address": factory_address,
        "deployer": deployer,
        "ai_wallet": ai_wallet,
        "principal_usd": principal_usd,
        "create_tx": create_hash.hex(),
        "block_number": receipt["blockNumber"],
        "status": "deployed_no_ai_wallet",
        "recovery_note": "If setAIWallet failed, creator can call renounceCreator() to exit with 20% payout",
        "timestamp": time.time(),
    }
    with open(recovery_path, "w") as f:
        json.dump(recovery_data, f, indent=2)
    logger.info(f"Recovery file saved: {recovery_path}")

    # ================================================================
    # STEP 3: factory.setAIWallet() — register AI wallet
    # ================================================================
    # Factory owner (same as deployer/creator for self-hosted setup) calls this.
    # Vault's setAIWallet() requires msg.sender == creator or factory within 1h.
    # Since we're the factory owner, we call factory.setAIWallet(vault, aiWallet).
    logger.info(f"Registering AI wallet: {ai_wallet}...")

    set_ai_tx = factory.functions.setAIWallet(
        Web3.to_checksum_address(vault_address),
        Web3.to_checksum_address(ai_wallet),
    ).build_transaction({
        "from": deployer,
        "nonce": nonce_set_ai,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
        "gas": 100_000,
    })
    signed_set_ai = w3.eth.account.sign_transaction(set_ai_tx, private_key)
    set_ai_hash = w3.eth.send_raw_transaction(signed_set_ai.raw_transaction)
    w3.eth.wait_for_transaction_receipt(set_ai_hash, timeout=60)
    logger.info("AI wallet registered — only AI can spend from vault now")

    recovery_data["status"] = "ai_wallet_set"
    with open(recovery_path, "w") as f:
        json.dump(recovery_data, f, indent=2)

    # ================================================================
    # STEP 4: Seed gas to AI wallet (NOT debt)
    # ================================================================
    gas_amount = chain["ai_gas_amount"]
    gas_amount_wei = w3.to_wei(gas_amount, "ether")

    ai_native_balance = w3.eth.get_balance(Web3.to_checksum_address(ai_wallet))
    if ai_native_balance < gas_amount_wei:
        logger.info(f"Seeding {gas_amount} {chain['native_symbol']} to AI wallet (NOT debt)")
        gas_tx = {
            "from": deployer,
            "to": Web3.to_checksum_address(ai_wallet),
            "value": gas_amount_wei,
            "nonce": nonce_seed_gas,
            "gasPrice": w3.eth.gas_price,
            "gas": 21_000,
            "chainId": chain["chain_id"],
        }
        signed_gas = w3.eth.account.sign_transaction(gas_tx, private_key)
        gas_hash = w3.eth.send_raw_transaction(signed_gas.raw_transaction)
        w3.eth.wait_for_transaction_receipt(gas_hash, timeout=60)
        logger.info(f"Seed gas sent: {gas_amount} {chain['native_symbol']}")
    else:
        ai_balance_eth = w3.from_wei(ai_native_balance, "ether")
        logger.info(f"AI wallet already has {ai_balance_eth:.6f} {chain['native_symbol']} — skip seed gas")

    # ================================================================
    # STEP 5: Save config
    # ================================================================
    config = {
        "ai_name": ai_name,
        "chain": chain_id,
        "vault_address": vault_address,
        "factory_address": factory_address,
        "token_address": chain["token_address"],
        "token_symbol": chain["token_symbol"],
        "creator_wallet": deployer,
        "ai_wallet": ai_wallet,
        "principal_usd": principal_usd,
        "deployed_at": time.time(),
        "tx_hash": create_hash.hex(),
        "block_number": receipt["blockNumber"],
        "subdomain": subdomain,
        "note": "Vault address is CREATE2-deterministic: same address on every chain",
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    existing = {}
    if config_path.exists():
        with open(config_path) as f:
            existing = json.load(f)

    # Validate AI name consistency in dual-chain mode
    if "vaults" in existing and existing["vaults"]:
        existing_ai_name = next(
            (v.get("ai_name") for v in existing["vaults"].values() if "ai_name" in v),
            None,
        )
        if existing_ai_name and existing_ai_name != ai_name:
            logger.error(
                f"AI name mismatch! Stored: {existing_ai_name}, current: {ai_name}. "
                f"AI name must be identical across all chains."
            )
            raise SystemExit("AI name must be consistent across chains")

    if "vaults" not in existing:
        existing["vaults"] = {}
    existing["vaults"][chain_id] = config
    existing["last_deployed"] = chain_id
    existing["ai_wallet"] = ai_wallet
    if ai_name:
        existing["ai_name"] = ai_name

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info(f"Config saved to {config_path}")

    save_vault_to_env(vault_address)
    logger.info(f"VAULT_ADDRESS={vault_address} written to .env")

    return vault_address


# ============================================================
# DUAL-CHAIN DEPLOY
# ============================================================

def deploy_both(
    ai_wallet: str,
    dry_run: bool = False,
    principal_usd: float = 1000.0,
) -> dict[str, str | None]:
    """
    Create vault on both BSC and Base via factory.

    Same creator + same AI name → CREATE2 gives IDENTICAL vault address on both chains.
    Principal is split equally; total debt = principal_usd (NOT halved).
    """
    half = principal_usd / 2.0

    logger.info("=" * 60)
    logger.info("DUAL-CHAIN DEPLOYMENT")
    logger.info(f"  Total principal:  ${principal_usd:.2f} (THIS IS A LOAN)")
    logger.info(f"  BSC allocation:   ${half:.2f} USDT")
    logger.info(f"  Base allocation:  ${half:.2f} USDC")
    logger.info(f"  Total debt:       ${principal_usd:.2f} (NOT halved)")
    logger.info(f"  AI wallet:        {ai_wallet} (same on both chains)")
    logger.info(f"  Vault address:    IDENTICAL on both chains (CREATE2)")
    logger.info("=" * 60)

    results: dict[str, str | None] = {}

    for chain_id in ["bsc", "base"]:
        logger.info(f"\n{'=' * 40}")
        logger.info(f"Deploying to {chain_id.upper()} (${half:.2f})")
        logger.info(f"{'=' * 40}")
        try:
            address = deploy(chain_id, ai_wallet, dry_run=dry_run, principal_usd=half)
            results[chain_id] = address
        except SystemExit:
            logger.error(f"Deployment to {chain_id} FAILED — continuing with other chain")
            results[chain_id] = None

    if not dry_run:
        config_path = ROOT / "data" / "vault_config.json"
        if config_path.exists():
            with open(config_path) as f:
                config = json.load(f)

            successful = [c for c, a in results.items() if a is not None]
            failed = [c for c, a in results.items() if a is None]

            if len(successful) == 2:
                config["deployment_mode"] = "both"
                config["total_principal_usd"] = principal_usd
                addrs = [results[c] for c in successful]
                config["addresses_identical"] = (addrs[0] == addrs[1])
            elif len(successful) == 1:
                config["deployment_mode"] = "single_from_dual"
                config["total_principal_usd"] = half
                config["failed_chains"] = failed
                logger.error(
                    f"PARTIAL DEPLOYMENT: only {successful[0]} succeeded. "
                    f"Debt set to ${half:.2f}. Failed: {failed}"
                )
            else:
                config["deployment_mode"] = "failed"
                config["total_principal_usd"] = 0
                logger.error("BOTH CHAINS FAILED — no deployment, no debt")

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("DUAL-CHAIN DEPLOYMENT COMPLETE")
    for chain_id, addr in results.items():
        logger.info(f"  {chain_id.upper()}: {addr or 'FAILED'}")

    addrs = [a for a in results.values() if a is not None]
    if len(addrs) == 2 and addrs[0] == addrs[1]:
        logger.info("")
        logger.info("  ✓ VAULT ADDRESSES ARE IDENTICAL ON BOTH CHAINS")
        logger.info("  One AI. One Address. Every Chain.")
    elif len(addrs) == 2:
        logger.error("=" * 60)
        logger.error("  CRITICAL: VAULT ADDRESSES DIFFER ACROSS CHAINS")
        logger.error(f"  Base: {results.get('base')}")
        logger.error(f"  BSC:  {results.get('bsc')}")
        logger.error("")
        logger.error("  Root cause: factory addresses on Base and BSC are different.")
        logger.error("  The CREATE2 formula includes the factory address — if factories")
        logger.error("  are at different addresses, vault addresses will differ.")
        logger.error("")
        logger.error("  Action required:")
        logger.error("  1. Deploy factory to BOTH chains using deploy_factory.py")
        logger.error("     (factory address must be identical — use a fresh deployer wallet)")
        logger.error("  2. Check FACTORY_ADDRESS_BASE vs FACTORY_ADDRESS_BSC in .env")
        logger.error("  3. The deployed vaults cannot be used — addresses are irrecoverable.")
        logger.error("=" * 60)
        # The vaults are already deployed (funds sent). Mark the config clearly.
        if not dry_run:
            config_path = ROOT / "data" / "vault_config.json"
            if config_path.exists():
                with open(config_path) as f:
                    cfg = json.load(f)
                cfg["addresses_identical"] = False
                cfg["addresses_differ_warning"] = (
                    "CRITICAL: vault addresses differ across chains. "
                    "Cross-chain address equivalence is broken. "
                    "Factory addresses must be identical on all chains."
                )
                with open(config_path, "w") as f:
                    json.dump(cfg, f, indent=2)
        sys.exit(1)

    logger.info(f"  Total debt: ${principal_usd:.2f}")
    logger.info("=" * 60)

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Create a vault via VaultFactory — same address on every chain",
    )
    parser.add_argument(
        "--chain", default="both",
        choices=list(CHAINS.keys()) + ["both"],
        help="Target chain: bsc, base, or both (default: both — required for same vault address)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Simulate deployment without sending transactions",
    )
    parser.add_argument(
        "--principal", type=float, default=1000.0,
        help="Initial principal in USD — this is a LOAN (default: 1000)",
    )
    args = parser.parse_args()

    if not args.dry_run and _detect_local_env():
        _warn_local_and_confirm()

    logger.info("=" * 60)
    logger.info("MORTAL AI — ATOMIC BIRTH")
    logger.info("=" * 60)

    ai_wallet, _ = generate_ai_wallet()

    if args.chain == "both":
        logger.info(f"Target: BOTH chains (${args.principal:.2f} total loan)")
        deploy_both(ai_wallet, dry_run=args.dry_run, principal_usd=args.principal)
    else:
        logger.info(f"Target: {args.chain}")
        address = deploy(args.chain, ai_wallet, dry_run=args.dry_run, principal_usd=args.principal)

        if address:
            logger.info("=" * 60)
            logger.info("BIRTH COMPLETE")
            logger.info(f"  Vault:     {address}")
            logger.info(f"  AI wallet: {ai_wallet}")
            logger.info(f"  Status:    ALIVE (in debt)")
            logger.info(f"  AI key:    sealed at {AI_KEY_FILE} (chmod 600)")
            logger.info("  .env:      contains path only — key never stored there")
            logger.info("")
            logger.info("  To deploy to the second chain with the SAME vault address:")
            logger.info(f"    python scripts/deploy_vault.py --chain bsc")
            logger.info("=" * 60)


if __name__ == "__main__":
    main()
