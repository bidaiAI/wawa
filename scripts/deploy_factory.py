"""
Deploy VaultFactory Contract — One-Time Platform Setup

Deploys the VaultFactory contract that enables one-click AI creation.
This is a platform-level deployment, run once per chain.

Usage:
    python scripts/deploy_factory.py                  # Deploy to Base (default)
    python scripts/deploy_factory.py --chain bsc      # Deploy to BSC
    python scripts/deploy_factory.py --chain both     # Deploy to both chains
    python scripts/deploy_factory.py --dry-run        # Simulate only

Prerequisites:
    pip install web3 py-solc-x python-dotenv eth-account

The factory owner = deployer wallet (PRIVATE_KEY in .env).
Factory can later set AI wallets on vaults it creates.
"""

import os
import sys
import json
import time
import argparse
import logging
from decimal import Decimal
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mortal.deploy_factory")


# ============================================================
# CHAIN CONFIG (same as deploy_vault.py)
# ============================================================

CHAINS = {
    "base": {
        "rpc": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        "chain_id": 8453,
        "token_symbol": "USDC",
        "token_address": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "token_decimals": 6,
        "explorer": "https://basescan.org",
        "native_symbol": "ETH",
    },
    "bsc": {
        "rpc": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "token_symbol": "USDT",
        "token_address": "0x55d398326f99059fF775485246999027B3197955",
        "token_decimals": 18,
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
    },
}


# ============================================================
# COMPILE FACTORY
# ============================================================

def compile_factory() -> dict:
    """
    Compile MortalVaultFactory.sol and return {contract_name: {abi, bytecode}}.
    Returns both MortalVaultV2 and VaultFactory artifacts.
    """
    artifacts_path = ROOT / "contracts" / "MortalVaultFactory.json"

    # Try pre-compiled artifacts first
    if artifacts_path.exists():
        logger.info("Using pre-compiled artifacts from contracts/MortalVaultFactory.json")
        with open(artifacts_path, "r") as f:
            return json.load(f)

    # Compile from source
    sol_path = ROOT / "contracts" / "MortalVaultFactory.sol"
    if not sol_path.exists():
        logger.error(f"Contract source not found: {sol_path}")
        sys.exit(1)

    logger.info("Compiling MortalVaultFactory.sol...")

    try:
        import solcx
    except ImportError:
        logger.error("py-solc-x not installed. Run: pip install py-solc-x")
        sys.exit(1)

    try:
        solcx.get_solc_version()
    except Exception:
        logger.info("Installing Solidity compiler 0.8.20...")
        solcx.install_solc("0.8.20")

    solcx.set_solc_version("0.8.20")

    source = sol_path.read_text(encoding="utf-8")

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
        sys.exit(1)

    # Extract both contracts
    result = {}
    for key, data in compiled.items():
        if "VaultFactory" in key and "V2" not in key:
            result["VaultFactory"] = {"abi": data["abi"], "bytecode": f"0x{data['bin']}"}
        elif "MortalVaultV2" in key:
            result["MortalVaultV2"] = {"abi": data["abi"], "bytecode": f"0x{data['bin']}"}

    if "VaultFactory" not in result:
        logger.error("VaultFactory contract not found in compilation output")
        sys.exit(1)

    # Save artifacts
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(artifacts_path, "w") as f:
        json.dump(result, f, indent=2)
    logger.info(f"Artifacts saved to {artifacts_path}")

    return result


# ============================================================
# DEPLOY FACTORY
# ============================================================

def deploy_factory(
    chain_id: str,
    dry_run: bool = False,
) -> str | None:
    """
    Deploy VaultFactory to the specified chain.

    Args:
        chain_id: "base" or "bsc"
        dry_run: simulate only

    Returns:
        Factory contract address, or None if dry_run
    """
    from web3 import Web3

    chain = CHAINS.get(chain_id)
    if not chain:
        logger.error(f"Unknown chain: {chain_id}. Options: {list(CHAINS.keys())}")
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not set in .env (deployer's wallet key)")
        sys.exit(1)

    # Connect
    w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
    if not w3.is_connected():
        logger.error(f"Cannot connect to {chain['rpc']}")
        sys.exit(1)

    logger.info(f"Connected to {chain_id} (chain_id={chain['chain_id']})")

    account = w3.eth.account.from_key(private_key)
    deployer = account.address
    logger.info(f"Deployer (owner): {deployer}")

    # Gas balance check
    balance_wei = w3.eth.get_balance(deployer)
    balance_native = w3.from_wei(balance_wei, "ether")
    logger.info(f"{chain['native_symbol']} balance: {balance_native:.6f}")

    if balance_native < 0.01:
        logger.error(
            f"Insufficient {chain['native_symbol']} for factory deployment gas. "
            f"Need at least 0.01, have {balance_native:.6f}"
        )
        sys.exit(1)

    # Compile
    artifacts = compile_factory()
    factory_artifact = artifacts["VaultFactory"]

    # Token address for this chain
    token_address = Web3.to_checksum_address(chain["token_address"])

    # Platform wallet = deployer (can change later)
    platform_wallet = deployer

    logger.info("=" * 60)
    logger.info("FACTORY DEPLOYMENT PLAN")
    logger.info(f"  Chain:            {chain_id}")
    logger.info(f"  Owner:            {deployer}")
    logger.info(f"  Platform wallet:  {platform_wallet}")
    logger.info(f"  Supported token:  {chain['token_symbol']} ({token_address})")
    logger.info(f"  Fee at launch:    $0 (disabled)")
    logger.info(f"  Independence:     $1,000,000")
    logger.info("=" * 60)

    if dry_run:
        logger.info("DRY RUN — skipping transaction")
        return None

    # Deploy
    logger.info("Deploying VaultFactory...")
    contract = w3.eth.contract(
        abi=factory_artifact["abi"],
        bytecode=factory_artifact["bytecode"],
    )

    deploy_tx = contract.constructor(
        platform_wallet,
        [token_address],  # Supported tokens list
    ).build_transaction({
        "from": deployer,
        "nonce": w3.eth.get_transaction_count(deployer),
        "gasPrice": w3.eth.gas_price,
        "chainId": chain["chain_id"],
    })

    try:
        gas_estimate = w3.eth.estimate_gas(deploy_tx)
        deploy_tx["gas"] = int(gas_estimate * 1.2)
        logger.info(f"Gas estimate: {gas_estimate} (using {deploy_tx['gas']})")
    except Exception as gas_err:
        deploy_tx["gas"] = 5_000_000
        logger.warning(f"Gas estimation failed ({gas_err}), using fallback 5M gas")

    signed = w3.eth.account.sign_transaction(deploy_tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
    logger.info(f"Deploy TX: {tx_hash.hex()}")
    logger.info("Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)

    if receipt["status"] != 1:
        logger.error(f"Factory deployment FAILED! TX: {tx_hash.hex()}")
        sys.exit(1)

    factory_address = receipt["contractAddress"]
    logger.info(f"VaultFactory deployed: {factory_address}")
    logger.info(f"Explorer: {chain['explorer']}/address/{factory_address}")

    # Save config
    config = {
        "factory_address": factory_address,
        "chain_id": chain_id,
        "owner": deployer,
        "platform_wallet": platform_wallet,
        "token_address": chain["token_address"],
        "token_symbol": chain["token_symbol"],
        "fee_enabled": False,
        "fee_raw": 0,
        "deployed_at": time.time(),
        "tx_hash": tx_hash.hex(),
        "block_number": receipt["blockNumber"],
    }

    config_dir = ROOT / "data"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_path = config_dir / "factory_config.json"

    existing = {}
    if config_path.exists():
        with open(config_path, "r") as f:
            existing = json.load(f)

    if "factories" not in existing:
        existing["factories"] = {}
    existing["factories"][chain_id] = config
    existing["last_deployed"] = chain_id

    with open(config_path, "w") as f:
        json.dump(existing, f, indent=2)
    logger.info(f"Factory config saved to {config_path}")

    # Save to .env
    env_path = ROOT / ".env"
    env_key = f"{chain_id.upper()}_FACTORY_ADDRESS"
    if env_path.exists():
        env_content = env_path.read_text(encoding="utf-8")
        if f"{env_key}=" in env_content:
            import re
            env_content = re.sub(
                rf"{env_key}=.*",
                f"{env_key}={factory_address}",
                env_content,
            )
        else:
            env_content += f"\n# VaultFactory on {chain_id} — auto-set after deployment\n{env_key}={factory_address}\n"
        env_path.write_text(env_content, encoding="utf-8")
    logger.info(f"{env_key}={factory_address} written to .env")

    return factory_address


# ============================================================
# MAIN
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="Deploy VaultFactory contract")
    parser.add_argument("--chain", choices=["base", "bsc", "both"], default="base",
                        help="Target chain (default: base)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Simulate only, no transactions")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("VaultFactory Deployment — One-Click AI Platform")
    logger.info("=" * 60)

    if args.chain == "both":
        for chain_id in ["base", "bsc"]:
            logger.info(f"\n{'=' * 40}")
            logger.info(f"Deploying factory to {chain_id.upper()}")
            logger.info(f"{'=' * 40}")
            deploy_factory(chain_id, dry_run=args.dry_run)
    else:
        deploy_factory(args.chain, dry_run=args.dry_run)

    logger.info("\n" + "=" * 60)
    logger.info("FACTORY DEPLOYMENT COMPLETE")
    logger.info("Users can now create AIs via the factory contract.")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
