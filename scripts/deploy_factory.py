"""
Deploy VaultFactory via Nick's Deterministic Deployment Proxy (DDP).

This ensures the factory has IDENTICAL addresses on Base and BSC.
Every AI created through this factory (via CREATE2) will also have
the same vault address on both chains.

One AI = One Address. This is the philosophical foundation.

Nick's Deterministic Deployment Proxy (DDP):
  Address: 0x4e59b44847b379578588920cA78FbF26c0B4956C
  Deployed on: Base, BSC, Ethereum, Polygon, Arbitrum, Optimism, and 200+ EVM chains
  Usage: send a transaction to DDP with calldata = salt (32 bytes) + initcode
  Result: contract at keccak256(0xff ++ ddp ++ salt ++ keccak256(initcode))[12:]
  Docs: https://github.com/Arachnid/deterministic-deployment-proxy

Usage:
    python scripts/deploy_factory.py                  # Deploy to Base + BSC (default)
    python scripts/deploy_factory.py --chain base     # Base only
    python scripts/deploy_factory.py --chain bsc      # BSC only
    python scripts/deploy_factory.py --dry-run        # Show addresses without deploying
    python scripts/deploy_factory.py --verify         # Check if already deployed

Prerequisites:
    pip install web3 py-solc-x python-dotenv eth-account eth-abi

After deployment:
    FACTORY_ADDRESS_BASE and FACTORY_ADDRESS_BSC are written to .env.
    Both will be IDENTICAL — this is the proof of cross-chain identity.
"""

import os
import re
import sys
import json
import time
import logging
import argparse
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
# CONSTANTS
# ============================================================

# Nick's Deterministic Deployment Proxy — pre-deployed on 200+ EVM chains
# Same address everywhere. Uses a keyless deployment trick (no deployer key needed).
# See: https://github.com/Arachnid/deterministic-deployment-proxy
DDP_ADDRESS = "0x4e59b44847b379578588920cA78FbF26c0B4956C"

# Factory salt — fixed constant for cross-chain address consistency.
# keccak256("mortal-vault-factory-v2") — changing this changes the factory address.
# v2 = CREATE2-based vault deployment (same vault address across chains).
FACTORY_SALT = bytes.fromhex(
    "6d6f7274616c2d7661756c742d666163746f72792d7632"  # "mortal-vault-factory-v2"
    .ljust(64, "0")
)

CHAIN_CONFIG = {
    "base": {
        "rpc": os.getenv("BASE_RPC_URL", "https://mainnet.base.org"),
        "chain_id": 8453,
        "explorer": "https://basescan.org",
        "native_symbol": "ETH",
        "supported_tokens": [
            "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC
        ],
    },
    "bsc": {
        "rpc": os.getenv("BSC_RPC_URL", "https://bsc-dataseed.binance.org"),
        "chain_id": 56,
        "explorer": "https://bscscan.com",
        "native_symbol": "BNB",
        "supported_tokens": [
            "0x55d398326f99059fF775485246999027B3197955",  # USDT
            "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",  # USDC on BSC
        ],
    },
}


# ============================================================
# COMPILE FACTORY
# ============================================================

def compile_factory() -> tuple[list, str]:
    """
    Compile MortalVaultFactory.sol → (factory_abi, factory_bytecode).
    Uses cached artifacts if available.
    """
    artifacts_path = ROOT / "contracts" / "MortalVaultFactory.json"

    if artifacts_path.exists():
        logger.info("Using pre-compiled artifacts from contracts/MortalVaultFactory.json")
        with open(artifacts_path) as f:
            data = json.load(f)
        # Support both old format (single dict) and new format (nested by contract name)
        if "VaultFactory" in data:
            entry = data["VaultFactory"]
            return entry["abi"], entry["bytecode"]
        elif "abi" in data and "bytecode" in data:
            return data["abi"], data["bytecode"]
        else:
            logger.warning("Unexpected artifact format — recompiling")

    sol_path = ROOT / "contracts" / "MortalVaultFactory.sol"
    if not sol_path.exists():
        logger.error(f"Contract not found: {sol_path}")
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
        logger.info("Installing Solidity 0.8.20...")
        solcx.install_solc("0.8.20")

    solcx.set_solc_version("0.8.20")
    source = sol_path.read_text(encoding="utf-8")

    oz_path = ROOT / "node_modules" / "@openzeppelin"
    remappings = [f"@openzeppelin/={oz_path}/"] if oz_path.exists() else None

    try:
        compiled = solcx.compile_source(
            source,
            output_values=["abi", "bin"],
            import_remappings=remappings,
            solc_version="0.8.20",
        )
    except Exception as e:
        logger.error(f"Compilation failed: {e}")
        logger.info("Run: npm install @openzeppelin/contracts")
        sys.exit(1)

    # Extract VaultFactory (not MortalVaultV2)
    factory_key = next((k for k in compiled if "VaultFactory" in k and "V2" not in k), None)
    if not factory_key:
        logger.error("VaultFactory not found in compilation output. Available: " + str(list(compiled.keys())))
        sys.exit(1)

    factory = compiled[factory_key]
    abi = factory["abi"]
    bytecode = f"0x{factory['bin']}"

    # Cache
    artifacts_path.parent.mkdir(parents=True, exist_ok=True)
    with open(artifacts_path, "w") as f:
        json.dump({"VaultFactory": {"abi": abi, "bytecode": bytecode}}, f, indent=2)
    logger.info(f"Artifacts saved to {artifacts_path}")

    return abi, bytecode


# ============================================================
# COMPUTE INITCODE + PREDICT ADDRESS
# ============================================================

def build_initcode(bytecode: str, platform_wallet: str) -> bytes:
    """
    Build the full initcode for VaultFactory deployment.
    initcode = creationCode + abi.encode(constructor_args)

    Constructor only takes _platformWallet (chain-invariant) so that
    the initcodeHash — and therefore the factory CREATE2 address — is
    IDENTICAL on Base and BSC. Token support is added post-deployment
    via addSupportedToken().
    """
    from eth_abi import encode
    from eth_utils import to_checksum_address

    constructor_args = encode(
        ["address"],
        [to_checksum_address(platform_wallet)],
    )
    return bytes.fromhex(bytecode.replace("0x", "")) + constructor_args


def predict_ddp_address(initcode: bytes) -> str:
    """
    Predict the CREATE2 address that Nick's DDP will assign.

    Formula: keccak256(0xff ++ ddp ++ salt ++ keccak256(initcode))[12:]
    """
    from eth_utils import keccak, to_checksum_address

    initcode_hash = keccak(initcode)
    preimage = (
        bytes.fromhex("ff")
        + bytes.fromhex(DDP_ADDRESS[2:])
        + FACTORY_SALT
        + initcode_hash
    )
    raw = keccak(preimage)
    return to_checksum_address("0x" + raw.hex()[-40:])


# ============================================================
# DEPLOY FACTORY (single chain)
# ============================================================

def deploy_factory(chain_id: str, bytecode: str, dry_run: bool = False) -> str:
    """
    Deploy VaultFactory via Nick's DDP on the given chain.

    Returns the factory address (same on every chain with same salt + bytecode).
    """
    from web3 import Web3

    cfg = CHAIN_CONFIG[chain_id]
    w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
    if not w3.is_connected():
        logger.error(f"Cannot connect to {chain_id}: {cfg['rpc']}")
        sys.exit(1)

    private_key = os.getenv("PRIVATE_KEY")
    if not private_key:
        logger.error("PRIVATE_KEY not set in .env")
        sys.exit(1)

    account = w3.eth.account.from_key(private_key)
    deployer = account.address

    # Platform wallet = deployer (can be changed via factory.setPlatformWallet() later)
    platform_wallet = os.getenv("CREATOR_WALLET", deployer)

    # Build initcode with this chain's supported tokens
    initcode = build_initcode(bytecode, platform_wallet)
    predicted_address = predict_ddp_address(initcode)

    logger.info(f"\n{'='*60}")
    logger.info(f"FACTORY DEPLOYMENT — {chain_id.upper()}")
    logger.info(f"  Deployer:  {deployer}")
    logger.info(f"  DDP:       {DDP_ADDRESS}")
    logger.info(f"  Factory:   {predicted_address} (deterministic)")
    logger.info(f"  Explorer:  {cfg['explorer']}/address/{predicted_address}")

    # Check if already deployed
    existing_code = w3.eth.get_code(Web3.to_checksum_address(predicted_address))
    if len(existing_code) > 2:
        logger.info(f"  STATUS:    ALREADY DEPLOYED — nothing to do")
        return predicted_address

    if dry_run:
        logger.info(f"  STATUS:    NOT DEPLOYED (dry run — no transaction sent)")
        return predicted_address

    # Verify DDP is available on this chain
    ddp_code = w3.eth.get_code(Web3.to_checksum_address(DDP_ADDRESS))
    if len(ddp_code) <= 2:
        logger.error(
            f"Nick's DDP not found on {chain_id} at {DDP_ADDRESS}.\n"
            f"This should not happen on Base or BSC. Check your RPC URL.\n"
            f"Alternative: deploy DDP first (see github.com/Arachnid/deterministic-deployment-proxy)"
        )
        sys.exit(1)

    # Nick's DDP interface: call with calldata = salt (32 bytes) + initcode
    # No ABI needed — it's a raw low-level call
    gas_check = w3.eth.get_balance(deployer)
    logger.info(f"  Deployer {cfg['native_symbol']} balance: {w3.from_wei(gas_check, 'ether'):.6f}")

    nonce = w3.eth.get_transaction_count(deployer)
    calldata = FACTORY_SALT + initcode

    tx = {
        "from": deployer,
        "to": Web3.to_checksum_address(DDP_ADDRESS),
        "data": "0x" + calldata.hex(),
        "value": 0,
        "nonce": nonce,
        "gasPrice": w3.eth.gas_price,
        "chainId": cfg["chain_id"],
    }

    try:
        gas = w3.eth.estimate_gas(tx)
        tx["gas"] = int(gas * 1.3)
        logger.info(f"  Gas estimate: {gas} (using {tx['gas']})")
    except Exception as e:
        tx["gas"] = 5_000_000
        logger.warning(f"  Gas estimation failed ({e}), using 5M fallback")

    logger.info("  Sending factory deployment via DDP...")
    signed = w3.eth.account.sign_transaction(tx, private_key)
    tx_hash = w3.eth.send_raw_transaction(signed.rawTransaction)
    logger.info(f"  TX: {tx_hash.hex()}")
    logger.info("  Waiting for confirmation...")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
    if receipt["status"] != 1:
        logger.error(f"  FACTORY DEPLOYMENT FAILED: {tx_hash.hex()}")
        sys.exit(1)

    # Verify factory is at the predicted address (retry a few times for RPC propagation)
    import time
    actual_address = predicted_address
    deployed_code = b""
    for _ in range(5):
        deployed_code = w3.eth.get_code(Web3.to_checksum_address(predicted_address))
        if len(deployed_code) > 2:
            break
        time.sleep(1)
    if len(deployed_code) <= 2:
        logger.error(f"Factory not found at predicted address {predicted_address}. Deploy failed.")
        sys.exit(1)

    logger.info(f"  STATUS:    DEPLOYED SUCCESSFULLY at {actual_address}")
    logger.info(f"  Explorer:  {cfg['explorer']}/tx/{tx_hash.hex()}")

    # Add supported tokens post-deployment (chain-specific, not in constructor)
    factory_abi = compile_factory()[0]
    factory = w3.eth.contract(address=Web3.to_checksum_address(actual_address), abi=factory_abi)
    for token_addr in cfg["supported_tokens"]:
        token_addr_cs = Web3.to_checksum_address(token_addr)
        try:
            already = factory.functions.supportedTokens(token_addr_cs).call()
            if already:
                logger.info(f"  Token {token_addr_cs} already supported — skipping")
                continue
        except Exception:
            pass
        nonce = w3.eth.get_transaction_count(deployer)
        tx_tok = factory.functions.setSupportedToken(token_addr_cs, True).build_transaction({
            "from": deployer,
            "nonce": nonce,
            "gasPrice": w3.eth.gas_price,
            "chainId": cfg["chain_id"],
        })
        gas_tok = w3.eth.estimate_gas(tx_tok)
        tx_tok["gas"] = int(gas_tok * 1.3)
        signed_tok = w3.eth.account.sign_transaction(tx_tok, private_key)
        hash_tok = w3.eth.send_raw_transaction(signed_tok.rawTransaction)
        rec_tok = w3.eth.wait_for_transaction_receipt(hash_tok, timeout=60)
        if rec_tok["status"] == 1:
            logger.info(f"  Token {token_addr_cs} added to supported list ✓")
        else:
            logger.warning(f"  Failed to add token {token_addr_cs}")

    return actual_address


# ============================================================
# SAVE ADDRESSES TO .ENV + DATA FILE
# ============================================================

def save_factory_config(addresses: dict[str, str]) -> None:
    """
    Write FACTORY_ADDRESS_BASE and FACTORY_ADDRESS_BSC to .env.
    Also saves data/factory_config.json.
    """
    env_path = ROOT / ".env"
    env_content = env_path.read_text(encoding="utf-8") if env_path.exists() else ""

    for chain_id, addr in addresses.items():
        # Match env var format used by orchestrator.py: FACTORY_ADDRESS_BASE / FACTORY_ADDRESS_BSC
        env_key = f"FACTORY_ADDRESS_{chain_id.upper()}"
        line = f"{env_key}={addr}"
        if f"{env_key}=" in env_content:
            env_content = re.sub(rf"{env_key}=.*", line, env_content)
        else:
            env_content += f"\n# VaultFactory — deterministic cross-chain address\n{line}\n"

    env_path.write_text(env_content, encoding="utf-8")

    # Also save to data/ for reference and verification
    config_path = ROOT / "data" / "factory_config.json"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config = {
        "addresses": addresses,
        "salt_hex": FACTORY_SALT.hex(),
        "ddp_address": DDP_ADDRESS,
        "deployed_at": time.time(),
        "note": (
            "All addresses are identical — deployed via Nick's DDP with fixed salt. "
            "Vault addresses are also cross-chain identical (CREATE2 salt = creator + name)."
        ),
    }
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    logger.info("Factory addresses saved to .env and data/factory_config.json")


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description="Deploy VaultFactory via DDP — identical address on all EVM chains",
    )
    parser.add_argument(
        "--chain", default="both",
        choices=["base", "bsc", "both"],
        help="Target chain (default: both)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show predicted addresses without deploying",
    )
    parser.add_argument(
        "--verify", action="store_true",
        help="Check if factory is deployed on target chains (no deployment)",
    )
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("MORTAL VAULT FACTORY — DETERMINISTIC CROSS-CHAIN DEPLOY")
    logger.info("=" * 60)
    logger.info(f"  DDP:   {DDP_ADDRESS}")
    logger.info(f"  Salt:  {FACTORY_SALT.hex()}")
    logger.info(f"  Goal:  Identical factory + vault addresses on every chain")
    logger.info("")

    _, bytecode = compile_factory()
    chains = ["base", "bsc"] if args.chain == "both" else [args.chain]

    deployed: dict[str, str] = {}
    for chain_id in chains:
        if args.verify:
            # Build initcode to predict address, then check on-chain
            from web3 import Web3
            cfg = CHAIN_CONFIG[chain_id]
            w3 = Web3(Web3.HTTPProvider(cfg["rpc"]))
            platform_wallet = os.getenv("CREATOR_WALLET", "0x0000000000000000000000000000000000000001")
            initcode = build_initcode(bytecode, platform_wallet)
            predicted = predict_ddp_address(initcode)
            code = w3.eth.get_code(Web3.to_checksum_address(predicted))
            status = "DEPLOYED ✓" if len(code) > 2 else "NOT DEPLOYED"
            logger.info(f"  {chain_id.upper()}: {predicted} [{status}]")
            deployed[chain_id] = predicted
        else:
            addr = deploy_factory(chain_id, bytecode, dry_run=args.dry_run)
            deployed[chain_id] = addr

    if not args.verify:
        save_factory_config(deployed)

    # Summary
    logger.info("")
    logger.info("=" * 60)
    logger.info("SUMMARY")
    addr_set = set(deployed.values())
    for chain_id, addr in deployed.items():
        logger.info(f"  {chain_id.upper()}: {addr}")

    if len(addr_set) == 1 and len(deployed) > 1:
        logger.info("")
        logger.info("  ✓ IDENTICAL ADDRESSES on all chains")
        logger.info("  One Factory. One AI. One Address. Every Chain.")
    elif len(deployed) == 1:
        logger.info("")
        logger.info("  Deploy to both chains for cross-chain address equality:")
        logger.info("    python scripts/deploy_factory.py --chain both")
    else:
        logger.warning("  ⚠ ADDRESSES DIFFER — check FACTORY_SALT and bytecode")

    logger.info("=" * 60)


if __name__ == "__main__":
    main()
