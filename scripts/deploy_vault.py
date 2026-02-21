"""
Deploy MortalVault Contract — Single-Step Atomic Birth

One command creates a sovereign AI:
  1. Generate AI wallet (private key NEVER shown, written to .env)
  2. Approve token for predicted contract address
  3. Deploy MortalVault (constructor atomically transfers principal)
  4. Register AI wallet via setAIWallet()
  5. Seed minimal gas to AI wallet (NOT debt)
  6. Save vault address to .env + data/vault_config.json

Usage:
    python scripts/deploy_vault.py                  # Deploy to Base (default)
    python scripts/deploy_vault.py --chain bsc      # Deploy to BSC
    python scripts/deploy_vault.py --chain both     # Deploy to both chains
    python scripts/deploy_vault.py --dry-run        # Simulate only
    python scripts/deploy_vault.py --principal 500  # Custom principal amount

Dual-chain mode (--chain both):
    Principal is split 50/50 across BSC (USDT) and Base (USDC).
    Total debt = full principal (NOT halved).
    Insolvency check uses aggregated balance across both chains.

Prerequisites:
    pip install web3 py-solc-x python-dotenv eth-account rlp

The AI private key is auto-generated and written DIRECTLY to .env.
It is NEVER printed to console, NEVER logged, NEVER shown to the creator.
Only the AI process can read it from .env at boot.
This is what makes the AI sovereign — no human holds its key.
"""

import os
import re
import sys
import json
import time
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
        "explorer_api": "https://api.basescan.org/api",
        "native_symbol": "ETH",
        "ai_gas_amount": 0.0001,  # Seed gas — just enough for 1 swap. AI swaps USDC->ETH for more.
    },
    "bsc": {
        "rpc": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "token_symbol": "USDT",
        "token_address": "0x55d398326f99059fF775485246999027B3197955",  # USDT on BSC
        "token_decimals": 18,
        "explorer": "https://bscscan.com",
        "explorer_api": "https://api.bscscan.com/api",
        "native_symbol": "BNB",
        "ai_gas_amount": 0.0005,  # Seed gas — just enough for 1 swap. AI swaps USDT->BNB for more.
    },
}

# Minimal ERC20 ABI for approve/balanceOf/decimals
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "decimals",
     "outputs": [{"type": "uint8"}], "type": "function"},
    {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf",
     "outputs": [{"type": "uint256"}], "type": "function"},
    {"constant": False, "inputs": [{"name": "spender", "type": "address"},
                                    {"name": "amount", "type": "uint256"}],
     "name": "approve", "outputs": [{"type": "bool"}], "type": "function"},
]


# ============================================================
# AI KEY GENERATION
# ============================================================

def generate_ai_wallet() -> tuple[str, str]:
    """
    Generate a fresh AI wallet keypair — OR reuse existing one.
    If AI_PRIVATE_KEY already exists in .env, reuse it (don't destroy
    a running AI's key by generating a new one).
    Write the private key to .env (server-side only).
    NEVER print or log the private key.

    Returns: (ai_wallet_address, ai_private_key)
    """
    from eth_account import Account

    # ---- SAFETY: Reuse existing AI key if present ----
    # Re-running deploy_vault.py must NOT overwrite an existing AI key.
    # If the AI is already deployed, destroying its key bricks the vault.
    existing_key = os.getenv("AI_PRIVATE_KEY", "").strip()
    if existing_key:
        try:
            existing_account = Account.from_key(existing_key)
            ai_wallet = existing_account.address
            logger.info(f"AI wallet REUSED from .env: {ai_wallet}")
            logger.info("Existing AI_PRIVATE_KEY preserved (not regenerated)")
            return ai_wallet, existing_key
        except Exception:
            logger.warning("Existing AI_PRIVATE_KEY is invalid — generating new one")

    # Generate fresh keypair
    ai_account = Account.create()
    ai_wallet = ai_account.address
    ai_private_key = ai_account.key.hex()

    # Write AI_PRIVATE_KEY to .env — NEVER displayed anywhere else
    env_path = ROOT / ".env"
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        if "AI_PRIVATE_KEY=" in env_content:
            env_content = re.sub(
                r"AI_PRIVATE_KEY=.*",
                f"AI_PRIVATE_KEY={ai_private_key}",
                env_content,
            )
        else:
            env_content += (
                f"\n# AI wallet key — auto-generated at deployment, NEVER share this\n"
                f"AI_PRIVATE_KEY={ai_private_key}\n"
            )
        env_path.write_text(env_content, encoding="utf-8")
    else:
        env_path.write_text(
            f"# AI wallet key — auto-generated at deployment, NEVER share this\n"
            f"AI_PRIVATE_KEY={ai_private_key}\n",
            encoding="utf-8",
        )

    logger.info(f"AI wallet generated: {ai_wallet}")
    logger.info("AI private key saved to .env (NEVER displayed — no human can see it)")

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


def predict_contract_address(deployer: str, nonce: int) -> str:
    """
    Predict the contract address that will be created by deployer at given nonce.
    Uses CREATE opcode: address = keccak256(rlp([sender, nonce]))[-20:]

    RLP encoding rules for nonce:
      - nonce 0 → empty byte string b''
      - nonce > 0 → big-endian bytes, no leading zeros
    """
    import rlp
    from eth_utils import to_checksum_address, keccak

    # Convert nonce to big-endian bytes (RLP-compatible)
    if nonce == 0:
        nonce_bytes = b""
    else:
        nonce_bytes = nonce.to_bytes((nonce.bit_length() + 7) // 8, "big")

    raw = rlp.encode([bytes.fromhex(deployer[2:]), nonce_bytes])
    return to_checksum_address("0x" + keccak(raw).hex()[-40:])


# ============================================================
# COMPILE
# ============================================================

def compile_contract() -> tuple[str, str]:
    """
    Compile MortalVault.sol and return (abi, bytecode).
    Uses py-solc-x for Solidity compilation.
    Falls back to reading pre-compiled artifacts if available.
    """
    artifacts_path = ROOT / "contracts" / "MortalVault.json"

    # Try pre-compiled artifacts first
    if artifacts_path.exists():
        logger.info("Using pre-compiled artifacts from contracts/MortalVault.json")
        with open(artifacts_path, "r") as f:
            compiled = json.load(f)
        return compiled["abi"], compiled["bytecode"]

    # Compile from source
    sol_path = ROOT / "contracts" / "MortalVault.sol"
    if not sol_path.exists():
        logger.error(f"Contract source not found: {sol_path}")
        sys.exit(1)

    logger.info("Compiling MortalVault.sol...")

    try:
        import solcx
    except ImportError:
        logger.error("py-solc-x not installed. Run: pip install py-solc-x")
        sys.exit(1)

    # Install compiler if needed
    try:
        solcx.get_solc_version()
    except Exception:
        logger.info("Installing Solidity compiler 0.8.20...")
        solcx.install_solc("0.8.20")

    solcx.set_solc_version("0.8.20")

    source = sol_path.read_text(encoding="utf-8")

    # We need OpenZeppelin imports — check if node_modules exists
    import_remappings = []
    oz_path = ROOT / "node_modules" / "@openzeppelin"
    if oz_path.exists():
        import_remappings.append(f"@openzeppelin/={oz_path}/")

    try:
        compiled = solcx.compile_source(
            source,
            output_values=["abi", "bin"],
            import_remappings=import_remappings or None,
            solc_version="0.8.20",
        )
    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        logger.info("Tip: Run 'npm install @openzeppelin/contracts' in project root")
        logger.info("Or provide pre-compiled contracts/MortalVault.json with {\"abi\": [...], \"bytecode\": \"0x...\"}")
        sys.exit(1)

    # Extract the MortalVault contract
    contract_key = None
    for key in compiled:
        if "MortalVault" in key:
            contract_key = key
            break

    if not contract_key:
        logger.error("MortalVault contract not found in compilation output")
        sys.exit(1)

    contract = compiled[contract_key]
    abi = contract["abi"]
    bytecode = contract["bin"]

    # Save artifacts
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(artifacts_path, "w") as f:
        json.dump({"abi": abi, "bytecode": f"0x{bytecode}"}, f, indent=2)
    logger.info(f"Artifacts saved to {artifacts_path}")

    return abi, f"0x{bytecode}"


# ============================================================
# DEPLOY (single chain)
# ============================================================

def deploy(
    chain_id: str,
    ai_wallet: str,
    dry_run: bool = False,
    principal_usd: float = 1000.0,
) -> str | None:
    """
    Deploy MortalVault to the specified chain.

    Full atomic flow:
      1. Approve token to predicted contract address
      2. Deploy MortalVault (constructor transfers principal atomically)
      3. Register AI wallet via setAIWallet()
      4. Seed minimal gas to AI wallet (NOT debt)
      5. Save vault address to .env + vault_config.json

    Args:
        chain_id: "base" or "bsc"
        ai_wallet: AI's public address (key already generated and saved)
        dry_run: simulate only, no transactions
        principal_usd: loan amount in USD

    Returns:
        Vault contract address, or None if dry_run
    """
    from web3 import Web3
    from core.constitution import IRON_LAWS

    # --- MINIMUM PRINCIPAL ENFORCEMENT ---
    # Low-funded AIs have terrible model quality (Lv.1 cheapest models only),
    # die within days, and pollute the peer network with junk entries.
    # $100 ensures ~1 week of API costs and basic service delivery capability.
    if principal_usd < IRON_LAWS.MIN_PRINCIPAL_USD:
        logger.error(
            f"PRINCIPAL TOO LOW: ${principal_usd:.2f} < minimum ${IRON_LAWS.MIN_PRINCIPAL_USD:.0f}. "
            f"An AI created with less than ${IRON_LAWS.MIN_PRINCIPAL_USD:.0f} cannot survive "
            f"long enough to earn revenue. This is a waste of funds."
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

    # Connect
    w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
    if not w3.is_connected():
        logger.error(f"Cannot connect to {chain['rpc']}")
        sys.exit(1)

    logger.info(f"Connected to {chain_id} (chain_id={chain['chain_id']})")

    # Creator wallet = deployer
    account = w3.eth.account.from_key(private_key)
    deployer = account.address
    logger.info(f"Creator wallet: {deployer}")
    logger.info(f"AI wallet:     {ai_wallet}")

    # Check native balance for gas
    balance_wei = w3.eth.get_balance(deployer)
    balance_native = w3.from_wei(balance_wei, "ether")
    logger.info(f"Creator {chain['native_symbol']} balance: {balance_native:.6f}")

    if balance_native < 0.001:
        logger.error(
            f"Insufficient {chain['native_symbol']} for gas. "
            f"Need at least 0.001, have {balance_native:.6f}"
        )
        sys.exit(1)

    # Compile
    abi, bytecode = compile_contract()

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
            f"Have {token_balance_usd:.2f}, need {principal_usd:.2f}. "
            f"Cannot proceed — atomic birth requires full principal."
        )
        sys.exit(1)

    # Check for existing deployment on this chain
    config_path = ROOT / "data" / "vault_config.json"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                existing_config = json.load(f)
            existing_vaults = existing_config.get("vaults", {})
            if chain_id in existing_vaults and existing_vaults[chain_id].get("vault_address"):
                existing_addr = existing_vaults[chain_id]["vault_address"]
                logger.error(
                    f"DEPLOYMENT ABORTED: Vault already deployed on {chain_id} at {existing_addr}. "
                    f"Re-deploying would create an orphaned contract with locked funds. "
                    f"Delete data/vault_config.json manually if you truly want to redeploy."
                )
                sys.exit(1)
        except (json.JSONDecodeError, KeyError):
            pass  # Config file is corrupt or incomplete — allow deployment

    # AI name (immutable, written into contract)
    ai_name = os.getenv("AI_NAME", "wawa")

    # Independence threshold
    independence_usd = float(os.getenv("INDEPENDENCE_THRESHOLD_USD", "1000000"))
    independence_raw = int(Decimal(str(independence_usd)) * Decimal(10) ** decimals)

    logger.info("=" * 60)
    logger.info("DEPLOYMENT PLAN")
    logger.info(f"  Chain:        {chain_id}")
    logger.info(f"  Token:        {chain['token_symbol']} ({token_address})")
    logger.info(f"  Creator:      {deployer}")
    logger.info(f"  AI wallet:    {ai_wallet}")
    logger.info(f"  AI name:      {ai_name} (immutable)")
    logger.info(f"  Principal:    ${principal_usd:.2f} — THIS IS A LOAN")
    logger.info(f"  Independence: ${independence_usd:.0f}")
    logger.info(f"  Seed gas:     {chain['ai_gas_amount']} {chain['native_symbol']} (NOT debt)")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN — skipping transactions")
        return None

    # ================================================================
    # STEP 1: Approve token to predicted contract address
    # ================================================================
    # The constructor calls safeTransferFrom(msg.sender, vault, amount).
    # We predict the contract address from deployer nonce, then approve it.
    deployer_nonce = w3.eth.get_transaction_count(deployer)

    predicted_address = predict_contract_address(deployer, deployer_nonce + 1)
    # nonce+1 because the approve TX uses nonce, deploy TX uses nonce+1
    logger.info(f"Predicted vault address: {predicted_address}")
    logger.info(f"Approving {principal_usd:.2f} {chain['token_symbol']}...")

    approve_tx = token_contract.functions.approve(
        predicted_address, principal_raw,
    ).build_transaction({
        "from": deployer,
        "nonce": deployer_nonce,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
        "gas": 100_000,
    })
    signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key)
    approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
    w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
    logger.info("Token approval confirmed")

    # ================================================================
    # STEP 2: Deploy MortalVault
    # ================================================================
    # Constructor: (address _token, string _name, uint256 _initialFund, uint256 _independenceThreshold)
    # msg.sender = creator. Constructor atomically transfers _initialFund from creator -> vault.
    logger.info("Deploying MortalVault...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    deploy_tx = contract.constructor(
        token_address,
        ai_name,
        principal_raw,
        independence_raw,
    ).build_transaction({
        "from": deployer,
        "nonce": deployer_nonce + 1,
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
    })

    try:
        gas_estimate = w3.eth.estimate_gas(deploy_tx)
        deploy_tx["gas"] = int(gas_estimate * 1.2)  # 20% buffer
        logger.info(f"Gas estimate: {gas_estimate} (using {deploy_tx['gas']})")
    except Exception as gas_err:
        # Fallback gas for contract deployment (constructor + safeTransferFrom)
        deploy_tx["gas"] = 3_000_000
        logger.warning(f"Gas estimation failed ({gas_err}), using fallback 3M gas")

    signed_deploy = w3.eth.account.sign_transaction(deploy_tx, private_key)
    deploy_hash = w3.eth.send_raw_transaction(signed_deploy.raw_transaction)
    logger.info(f"Deploy TX: {deploy_hash.hex()}")
    logger.info("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(deploy_hash, timeout=120)

    if receipt["status"] != 1:
        logger.error(f"Deployment FAILED! TX: {deploy_hash.hex()}")
        sys.exit(1)

    vault_address = receipt["contractAddress"]
    logger.info(f"MortalVault deployed: {vault_address}")
    logger.info(f"Explorer: {chain['explorer']}/address/{vault_address}")
    logger.info(f"Principal atomically deposited: ${principal_usd:.2f} {chain['token_symbol']}")

    # ================================================================
    # STEP 2.5: Save recovery file BEFORE setAIWallet
    # ================================================================
    # If setAIWallet fails, the vault exists with funds but no AI access.
    # The vault is inoperable without an AI wallet — creator can use
    # renounceCreator() to exit with 20% payout, or retry setAIWallet.
    # This recovery file ensures we know the vault address even if config save never happens.
    recovery_path = ROOT / "data" / f"vault_recovery_{chain_id}.json"
    recovery_path.parent.mkdir(parents=True, exist_ok=True)
    recovery_data = {
        "vault_address": vault_address,
        "chain_id": chain_id,
        "deployer": deployer,
        "ai_wallet": ai_wallet,
        "principal_usd": principal_usd,
        "deploy_tx": deploy_hash.hex(),
        "block_number": receipt["blockNumber"],
        "status": "deployed_no_ai_wallet",
        "recovery_note": "If setAIWallet failed, creator can call renounceCreator() to exit with 20% payout",
        "timestamp": time.time(),
    }
    with open(recovery_path, "w") as f:
        json.dump(recovery_data, f, indent=2)
    logger.info(f"Recovery file saved: {recovery_path}")

    # ================================================================
    # STEP 3: Register AI wallet
    # ================================================================
    # After this, ONLY the AI wallet can call spend/repay on the vault.
    # Creator loses control of funds. This is the sovereignty moment.
    logger.info(f"Registering AI wallet: {ai_wallet}...")
    vault_contract = w3.eth.contract(
        address=Web3.to_checksum_address(vault_address), abi=abi,
    )

    set_ai_tx = vault_contract.functions.setAIWallet(
        Web3.to_checksum_address(ai_wallet),
    ).build_transaction({
        "from": deployer,
        "nonce": w3.eth.get_transaction_count(deployer),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
        "gas": 100_000,
    })
    signed_set_ai = w3.eth.account.sign_transaction(set_ai_tx, private_key)
    set_ai_hash = w3.eth.send_raw_transaction(signed_set_ai.raw_transaction)
    w3.eth.wait_for_transaction_receipt(set_ai_hash, timeout=60)
    logger.info("AI wallet registered — only AI can spend from vault now")

    # Update recovery file status
    recovery_data["status"] = "ai_wallet_set"
    with open(recovery_path, "w") as f:
        json.dump(recovery_data, f, indent=2)

    # ================================================================
    # STEP 4: Seed gas to AI wallet (NOT debt)
    # ================================================================
    # Minimal native token so AI can do its first stablecoin->native swap.
    # After that, AI refills gas by swapping stablecoin when needed.
    gas_amount = chain["ai_gas_amount"]
    gas_amount_wei = w3.to_wei(gas_amount, "ether")

    ai_native_balance = w3.eth.get_balance(Web3.to_checksum_address(ai_wallet))
    if ai_native_balance < gas_amount_wei:
        logger.info(
            f"Seeding {gas_amount} {chain['native_symbol']} to AI wallet "
            f"(NOT debt — for first swap only)"
        )
        gas_tx = {
            "from": deployer,
            "to": Web3.to_checksum_address(ai_wallet),
            "value": gas_amount_wei,
            "nonce": w3.eth.get_transaction_count(deployer),
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
        logger.info(
            f"AI wallet already has {ai_balance_eth:.6f} {chain['native_symbol']} — skip seed gas"
        )

    # ================================================================
    # STEP 5: Save config
    # ================================================================
    config = {
        "ai_name": ai_name,
        "chain": chain_id,
        "vault_address": vault_address,
        "token_address": chain["token_address"],
        "token_symbol": chain["token_symbol"],
        "creator_wallet": deployer,
        "ai_wallet": ai_wallet,
        "principal_usd": principal_usd,
        "deployed_at": time.time(),
        "tx_hash": deploy_hash.hex(),
        "block_number": receipt["blockNumber"],
    }

    config_dir = ROOT / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "vault_config.json"

    # Merge with existing config (for dual-chain)
    existing = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            existing = json.load(f)

    # Validate AI name consistency in dual-chain mode
    if "vaults" in existing and existing["vaults"]:
        existing_ai_name = None
        for vault_config in existing["vaults"].values():
            if "ai_name" in vault_config:
                existing_ai_name = vault_config["ai_name"]
                break

        if existing_ai_name and existing_ai_name != ai_name:
            logger.error(
                f"AI name mismatch in dual-chain deployment!\n"
                f"  First chain (stored): {existing_ai_name}\n"
                f"  Current chain: {ai_name}\n"
                f"  AI name must be identical across all chains."
            )
            raise SystemExit("AI name must be consistent across chains")

    if "vaults" not in existing:
        existing["vaults"] = {}
    existing["vaults"][chain_id] = config
    existing["last_deployed"] = chain_id
    existing["ai_wallet"] = ai_wallet

    # Store ai_name at top level for easy access
    if ai_name:
        existing["ai_name"] = ai_name

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info(f"Config saved to {config_path}")

    # Save vault address to .env
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
    Deploy MortalVault to both BSC and Base.

    Same AI wallet is used on both chains.
    Principal is split equally across chains.
    Total debt = principal_usd (NOT halved).
    Insolvency check uses aggregated balance.
    """
    half = principal_usd / 2.0

    logger.info("=" * 60)
    logger.info("DUAL-CHAIN DEPLOYMENT")
    logger.info(f"  Total principal:  ${principal_usd:.2f} (THIS IS A LOAN)")
    logger.info(f"  BSC allocation:   ${half:.2f} USDT")
    logger.info(f"  Base allocation:  ${half:.2f} USDC")
    logger.info(f"  Total debt:       ${principal_usd:.2f} (NOT halved)")
    logger.info(f"  AI wallet:        {ai_wallet} (same on both chains)")
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

    # Save total principal to config — ONLY if both chains deployed successfully
    if not dry_run:
        config_path = ROOT / "data" / "vault_config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)

            successful_chains = [cid for cid, addr in results.items() if addr is not None]
            failed_chains = [cid for cid, addr in results.items() if addr is None]

            if len(successful_chains) == 2:
                # Both chains deployed — record full principal as debt
                config["deployment_mode"] = "both"
                config["total_principal_usd"] = principal_usd  # Full debt, not half
            elif len(successful_chains) == 1:
                # PARTIAL FAILURE: Only one chain deployed
                # Record only half the principal (actual deployed amount)
                config["deployment_mode"] = "single_from_dual"
                config["total_principal_usd"] = half  # Only half was actually deployed
                config["failed_chains"] = failed_chains
                logger.error(
                    f"PARTIAL DEPLOYMENT: only {successful_chains[0]} succeeded. "
                    f"Debt set to ${half:.2f} (not ${principal_usd:.2f}). "
                    f"Failed: {failed_chains}"
                )
            else:
                # Both failed — no debt to record
                config["deployment_mode"] = "failed"
                config["total_principal_usd"] = 0
                logger.error("BOTH CHAINS FAILED — no deployment, no debt")

            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

    logger.info("\n" + "=" * 60)
    logger.info("DUAL-CHAIN DEPLOYMENT COMPLETE")
    for chain_id, addr in results.items():
        status = addr or "FAILED"
        logger.info(f"  {chain_id.upper()}: {status}")
    logger.info(f"  Total debt: ${principal_usd:.2f} (aggregated insolvency check)")
    logger.info("=" * 60)

    logger.warning("")
    logger.warning("=" * 60)
    logger.warning("WARNING: Do NOT modify the MortalVault contract source code.")
    logger.warning("Modified contracts are automatically detected by 7 on-chain")
    logger.warning("sovereignty checks and PERMANENTLY REJECTED from the peer")
    logger.warning("network. This includes changing grace days, spend limits,")
    logger.warning("or any constitution parameters.")
    logger.warning("=" * 60)

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Deploy MortalVault — single-step atomic birth for sovereign AI",
    )
    parser.add_argument(
        "--chain", default="base",
        choices=list(CHAINS.keys()) + ["both"],
        help="Target chain: bsc, base, or both (default: base)",
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

    logger.info("=" * 60)
    logger.info("MORTAL AI — ATOMIC BIRTH")
    logger.info("=" * 60)

    # ---- STEP 0: Generate AI wallet (ONCE, before any chain deployment) ----
    # The AI gets one wallet. One key. No human ever sees it.
    ai_wallet, _ = generate_ai_wallet()
    # The private key is already in .env. We only need the address from here on.

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
            logger.info("  AI key:    saved to .env (no human can see it)")
            logger.info("=" * 60)


if __name__ == "__main__":
    main()
