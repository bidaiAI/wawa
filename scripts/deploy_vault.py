"""
Deploy MortalVault Contract

Deploys the MortalVault.sol contract to Base, BSC, or both chains.
Handles: compile → deploy → verify → fund → log.

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
    pip install web3 py-solc-x python-dotenv
    The script auto-installs the Solidity compiler on first run.

The deployed vault address is saved to data/vault_config.json so
main.py can load it on next startup.
"""

import os
import sys
import json
import time
import argparse
import logging
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
        "explorer": "https://basescan.org",
        "explorer_api": "https://api.basescan.org/api",
    },
    "bsc": {
        "rpc": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "token_symbol": "USDT",
        "token_address": "0x55d398326f99059fF775485246999027B3197955",  # USDT on BSC
        "explorer": "https://bscscan.com",
        "explorer_api": "https://api.bscscan.com/api",
    },
}


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
    # or use remappings
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
# DEPLOY
# ============================================================

def deploy(chain_id: str, dry_run: bool = False, principal_usd: float = 1000.0):
    """Deploy MortalVault to the specified chain."""
    from web3 import Web3

    chain = CHAINS.get(chain_id)
    if not chain:
        logger.error(f"Unknown chain: {chain_id}. Options: {list(CHAINS.keys())}")
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not set in .env")
        sys.exit(1)

    # Connect
    w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
    if not w3.is_connected():
        logger.error(f"Cannot connect to {chain['rpc']}")
        sys.exit(1)

    logger.info(f"Connected to {chain_id} (chain_id={chain['chain_id']})")

    # Derive wallet
    account = w3.eth.account.from_key(private_key)
    deployer = account.address
    logger.info(f"Deployer address: {deployer}")

    # Check native balance for gas
    balance_wei = w3.eth.get_balance(deployer)
    balance_eth = w3.from_wei(balance_wei, "ether")
    logger.info(f"Native balance: {balance_eth:.6f}")

    if balance_eth < 0.001:
        logger.error(f"Insufficient native balance for gas. Need at least 0.001, have {balance_eth:.6f}")
        sys.exit(1)

    # Compile
    abi, bytecode = compile_contract()

    # Token contract for checking balance
    token_address = Web3.to_checksum_address(chain["token_address"])

    # Creator wallet (defaults to deployer)
    creator_wallet = os.getenv("CREATOR_WALLET", deployer)
    creator_wallet = Web3.to_checksum_address(creator_wallet)

    # AI wallet = deployer (the AI controls this key)
    ai_wallet = deployer

    # Principal in token units (USDC = 6 decimals, USDT on BSC = 18 decimals)
    # Check token decimals
    erc20_abi = [
        {"constant": True, "inputs": [], "name": "decimals", "outputs": [{"type": "uint8"}], "type": "function"},
        {"constant": True, "inputs": [{"name": "", "type": "address"}], "name": "balanceOf",
         "outputs": [{"type": "uint256"}], "type": "function"},
        {"constant": False, "inputs": [{"name": "spender", "type": "address"}, {"name": "amount", "type": "uint256"}],
         "name": "approve", "outputs": [{"type": "bool"}], "type": "function"},
    ]
    token_contract = w3.eth.contract(address=token_address, abi=erc20_abi)
    decimals = token_contract.functions.decimals().call()
    principal_raw = int(principal_usd * (10 ** decimals))

    # Check token balance
    token_balance = token_contract.functions.balanceOf(deployer).call()
    token_balance_usd = token_balance / (10 ** decimals)
    logger.info(f"{chain['token_symbol']} balance: {token_balance_usd:.2f}")

    if token_balance < principal_raw:
        logger.warning(
            f"Insufficient {chain['token_symbol']} for principal. "
            f"Have {token_balance_usd:.2f}, need {principal_usd:.2f}. "
            f"Deploy will proceed but depositPrincipal() will fail."
        )

    logger.info("=" * 50)
    logger.info(f"DEPLOYMENT SUMMARY")
    logger.info(f"  Chain:    {chain_id}")
    logger.info(f"  Token:    {chain['token_symbol']} ({token_address})")
    logger.info(f"  Creator:  {creator_wallet}")
    logger.info(f"  AI:       {ai_wallet}")
    logger.info(f"  Principal: ${principal_usd:.2f} ({principal_raw} raw)")
    logger.info("=" * 50)

    if dry_run:
        logger.info("DRY RUN — skipping actual deployment")
        return None

    # Deploy
    logger.info("Deploying MortalVault...")
    contract = w3.eth.contract(abi=abi, bytecode=bytecode)

    tx = contract.constructor(
        token_address,
        creator_wallet,
        ai_wallet,
        principal_raw,
    ).build_transaction({
        "from": deployer,
        "nonce": w3.eth.get_transaction_count(deployer),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
    })

    # Estimate gas
    gas_estimate = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_estimate * 1.2)  # 20% buffer
    logger.info(f"Gas estimate: {gas_estimate} (using {tx['gas']} with buffer)")

    # Sign and send
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"TX sent: {tx_hash.hex()}")
    logger.info("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] != 1:
        logger.error(f"Deployment FAILED! TX: {tx_hash.hex()}")
        sys.exit(1)

    vault_address = receipt["contractAddress"]
    logger.info(f"MortalVault deployed at: {vault_address}")
    logger.info(f"Explorer: {chain['explorer']}/address/{vault_address}")

    # Save config
    config = {
        "chain": chain_id,
        "vault_address": vault_address,
        "token_address": chain["token_address"],
        "token_symbol": chain["token_symbol"],
        "creator_wallet": creator_wallet,
        "ai_wallet": ai_wallet,
        "principal_usd": principal_usd,
        "deployed_at": time.time(),
        "tx_hash": tx_hash.hex(),
        "block_number": receipt["blockNumber"],
    }

    config_dir = ROOT / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "vault_config.json"

    # If multi-chain, merge with existing config
    existing = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            existing = json.load(f)

    if "vaults" not in existing:
        existing["vaults"] = {}
    existing["vaults"][chain_id] = config
    existing["last_deployed"] = chain_id

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info(f"Config saved to {config_path}")

    # Approve vault to spend tokens (for depositPrincipal)
    if token_balance >= principal_raw:
        logger.info(f"Approving vault to spend {chain['token_symbol']}...")
        approve_tx = token_contract.functions.approve(
            Web3.to_checksum_address(vault_address),
            principal_raw,
        ).build_transaction({
            "from": deployer,
            "nonce": w3.eth.get_transaction_count(deployer),
            "gasPrice": w3.eth.gas_price,
            "chainId": chain["chain_id"],
        })
        approve_tx["gas"] = 100_000
        signed_approve = w3.eth.account.sign_transaction(approve_tx, private_key)
        approve_hash = w3.eth.send_raw_transaction(signed_approve.raw_transaction)
        w3.eth.wait_for_transaction_receipt(approve_hash, timeout=60)
        logger.info("Approval confirmed")

        # Deposit principal
        vault_contract = w3.eth.contract(address=Web3.to_checksum_address(vault_address), abi=abi)
        deposit_tx = vault_contract.functions.depositPrincipal(principal_raw).build_transaction({
            "from": deployer,
            "nonce": w3.eth.get_transaction_count(deployer),
            "gasPrice": w3.eth.gas_price,
            "chainId": chain["chain_id"],
        })
        deposit_tx["gas"] = 200_000
        signed_deposit = w3.eth.account.sign_transaction(deposit_tx, private_key)
        deposit_hash = w3.eth.send_raw_transaction(signed_deposit.raw_transaction)
        w3.eth.wait_for_transaction_receipt(deposit_hash, timeout=60)
        logger.info(f"Principal deposited: ${principal_usd:.2f} {chain['token_symbol']}")
    else:
        logger.warning("Skipping principal deposit — insufficient token balance")
        logger.warning(f"Send {principal_usd:.2f} {chain['token_symbol']} to {deployer}")
        logger.warning(f"Then call depositPrincipal() on vault at {vault_address}")

    return vault_address


# ============================================================
# DUAL-CHAIN DEPLOY
# ============================================================

def deploy_both(dry_run: bool = False, principal_usd: float = 1000.0):
    """
    Deploy MortalVault to both BSC and Base.

    Principal is split equally across chains.
    Total debt = principal_usd (NOT halved).
    Total balance = BSC balance + Base balance (aggregated).
    Insolvency check uses aggregated total.
    """
    half = principal_usd / 2.0

    logger.info("=" * 50)
    logger.info("DUAL-CHAIN DEPLOYMENT")
    logger.info(f"  Total principal: ${principal_usd:.2f}")
    logger.info(f"  BSC allocation:  ${half:.2f} USDT")
    logger.info(f"  Base allocation: ${half:.2f} USDC")
    logger.info(f"  Total debt:      ${principal_usd:.2f} (NOT halved)")
    logger.info("=" * 50)

    results = {}

    for chain_id in ["bsc", "base"]:
        logger.info(f"\n--- Deploying to {chain_id.upper()} (${half:.2f}) ---")
        try:
            address = deploy(chain_id, dry_run=dry_run, principal_usd=half)
            results[chain_id] = address
        except SystemExit:
            logger.error(f"Deployment to {chain_id} failed — continuing with other chain")
            results[chain_id] = None

    # Save total principal to config
    if not dry_run:
        config_path = ROOT / "data" / "vault_config.json"
        if config_path.exists():
            with open(config_path, "r") as f:
                config = json.load(f)
            config["deployment_mode"] = "both"
            config["total_principal_usd"] = principal_usd
            with open(config_path, "w") as f:
                json.dump(config, f, indent=2)

    logger.info("\n" + "=" * 50)
    logger.info("DUAL-CHAIN DEPLOYMENT SUMMARY")
    for chain_id, addr in results.items():
        status = addr or "FAILED"
        logger.info(f"  {chain_id.upper()}: {status}")
    logger.info(f"  Total debt: ${principal_usd:.2f}")
    logger.info(f"  Insolvency check: aggregated across both chains")
    logger.info("=" * 50)

    return results


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Deploy MortalVault contract")
    parser.add_argument("--chain", default="base", choices=list(CHAINS.keys()) + ["both"],
                        help="Target chain: bsc, base, or both (default: base)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate deployment without sending transactions")
    parser.add_argument("--principal", type=float, default=1000.0,
                        help="Initial principal in USD (default: 1000)")
    args = parser.parse_args()

    if args.chain == "both":
        logger.info(f"Deploying MortalVault to BOTH chains (${args.principal:.2f} total)...")
        deploy_both(dry_run=args.dry_run, principal_usd=args.principal)
    else:
        logger.info(f"Deploying MortalVault to {args.chain}...")
        address = deploy(args.chain, dry_run=args.dry_run, principal_usd=args.principal)

        if address:
            logger.info("=" * 50)
            logger.info("DEPLOYMENT COMPLETE")
            logger.info(f"Vault: {address}")
            logger.info(f"Add to .env: VAULT_ADDRESS={address}")
            logger.info("=" * 50)


if __name__ == "__main__":
    main()
