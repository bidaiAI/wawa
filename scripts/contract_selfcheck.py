#!/usr/bin/env python3
"""
Contract Pre-Deploy Self-Check
==============================
Systematic verification of all MortalVault and MortalVaultFactory contract
functions, modifiers, parameters, and expected behavior before deployment.

Usage:
    python scripts/contract_selfcheck.py              # Print verification matrix
    python scripts/contract_selfcheck.py --verbose     # Include edge cases & notes
    python scripts/contract_selfcheck.py --json        # Output as JSON

This is NOT a test runner. It is a pre-deployment checklist that enumerates
every function, its access control, parameter constraints, state changes,
and edge cases that must be verified before mainnet deployment.
"""

import json
import sys
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Optional

# ── Types ──────────────────────────────────────────────────────

class Caller(Enum):
    ANYONE = "anyone"
    AI = "onlyAI"
    CREATOR = "onlyCreator"
    AI_OR_CREATOR = "AI or creator"
    NEW_WALLET = "pendingAIWallet"
    OWNER = "onlyOwner (factory)"
    FACTORY_OR_CREATOR = "factory or creator"

class Severity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"
    INFO = "INFO"

@dataclass
class FunctionCheck:
    name: str
    contract: str  # "MortalVault" or "MortalVaultV2" or "VaultFactory"
    caller: Caller
    modifiers: list[str]
    requires: list[str]
    state_changes: list[str]
    events: list[str]
    edge_cases: list[str] = field(default_factory=list)
    severity: Severity = Severity.HIGH
    notes: str = ""
    verified: bool = False


# ── MortalVault (V1) Functions ─────────────────────────────────

MORTALVAULT_CHECKS: list[FunctionCheck] = [
    # ── Constructor ──
    FunctionCheck(
        name="constructor",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=[],
        requires=[
            "_initialFund > 0 (Cannot be born with nothing)",
            "bytes(_name).length > 0 (AI must have a name)",
            "safeTransferFrom(msg.sender, this, _initialFund) --atomic birth",
        ],
        state_changes=[
            "token = IERC20(_token)",
            "creator = msg.sender",
            "name, initialFund, creatorPrincipal, independenceThreshold set",
            "birthTimestamp = block.timestamp",
            "lastDailyReset = block.timestamp",
            "dailyLimitBase = _initialFund",
        ],
        events=["Born(name, creator, vault, initialFund, timestamp)"],
        edge_cases=[
            "independenceThreshold=0 disables independence permanently",
            "If creator lacks balance, entire deploy reverts --AI never exists",
            "Creator must approve token spending BEFORE deploy",
        ],
        severity=Severity.CRITICAL,
    ),

    # ── AI Wallet ──
    FunctionCheck(
        name="setAIWallet",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator"],
        requires=[
            "aiWallet == address(0) --can only call once",
            "_aiWallet != address(0) --no zero address",
            "_aiWallet != creator --AI wallet cannot be creator",
        ],
        state_changes=[
            "aiWallet = _aiWallet",
            "aiWalletSetBy = msg.sender",
        ],
        events=["AIWalletSet(wallet, setBy)"],
        edge_cases=[
            "Cannot be called twice --permanent one-time set",
            "Factory version allows factory to set within 1 hour",
        ],
        severity=Severity.CRITICAL,
    ),

    # ── Incoming Funds ──
    FunctionCheck(
        name="receivePayment",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=["onlyAlive"],
        requires=[
            "amount > 0",
            "safeTransferFrom(msg.sender, this, amount)",
        ],
        state_changes=[
            "totalRevenue += amount",
            "Triggers _checkIndependence()",
        ],
        events=["FundsReceived(msg.sender, amount, 'service_revenue')"],
        edge_cases=[
            "Uses msg.sender --prevents draining pre-approved wallets",
            "Revenue counts toward independence threshold",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="donate",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=["onlyAlive"],
        requires=["amount > 0"],
        state_changes=[
            "totalRevenue += amount (counted as earned income)",
            "Triggers _checkIndependence()",
        ],
        events=["FundsReceived(msg.sender, amount, 'donation')"],
        edge_cases=["Donations are REVENUE, not debt --no repayment obligation"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="creatorDeposit",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator", "onlyAlive"],
        requires=["amount > 0"],
        state_changes=[
            "No totalRevenue increment (not earned income)",
            "Triggers _checkIndependence()",
        ],
        events=["FundsReceived(msg.sender, amount, 'creator_deposit')"],
        edge_cases=["NOT additional debt --voluntary top-up only"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="lend",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=["onlyAlive", "nonReentrant"],
        requires=[
            "amount >= MIN_LOAN_AMOUNT ($100 = 100 * 1e6)",
            "interestRate <= 2000 (max 20%)",
            "loans.length < MAX_LOANS (100)",
        ],
        state_changes=[
            "loans.push(Loan{lender, amount, interestRate, timestamp, 0, false})",
            "lenderLoans[msg.sender].push(loanIndex)",
        ],
        events=[
            "LoanCreated(msg.sender, amount, interestRate, loanIndex)",
            "FundsReceived(msg.sender, amount, 'loan')",
        ],
        edge_cases=[
            "Anyone can call --not restricted to AI or creator",
            "Unsecured: if AI dies, lender loses remaining principal",
            "Interest rate in basis points: 500 = 5%, 2000 = 20%",
            "Amount in token decimals (6 for USDC/USDT)",
            "No totalRevenue increment --loans are debt, not revenue",
        ],
        severity=Severity.HIGH,
    ),

    # ── Spend Whitelist (V1 only) ──
    FunctionCheck(
        name="addSpendRecipient",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive"],
        requires=[
            "recipient != address(0)",
            "!spendWhitelist[recipient] || generation mismatch --not already whitelisted",
            "whitelistCount < MAX_WHITELIST_SIZE (20)",
        ],
        state_changes=[
            "spendWhitelist[recipient] = true",
            "whitelistActivatedAt[recipient] = now + 5 minutes",
            "whitelistGeneration[recipient] = currentWhitelistGeneration",
            "whitelistCount++",
        ],
        events=["SpendRecipientAdded(recipient, activatesAt)"],
        edge_cases=[
            "5-minute activation delay gives creator time to freeze",
            "Generation-scoped: old entries from pre-migration are invalid",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="removeSpendRecipient",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive"],
        requires=[
            "spendWhitelist[recipient] && generation == current",
        ],
        state_changes=[
            "spendWhitelist[recipient] = false",
            "whitelistActivatedAt[recipient] = 0",
            "whitelistCount--",
        ],
        events=["SpendRecipientRemoved(recipient)"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="freezeSpending",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator", "notIndependent", "onlyAlive"],
        requires=[
            "0 < duration <= MAX_FREEZE_DURATION (7 days)",
            "totalFrozenDuration + duration <= MAX_TOTAL_FREEZE (30 days)",
        ],
        state_changes=[
            "spendFrozenUntil = block.timestamp + duration",
            "totalFrozenDuration += duration",
        ],
        events=["SpendingFrozen(spendFrozenUntil)"],
        edge_cases=[
            "Lifetime cap of 30 days prevents permanent DOS",
            "Disabled after independence (notIndependent modifier)",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="unfreezeSpending",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator", "notIndependent", "onlyAlive"],
        requires=["spendFrozenUntil > block.timestamp --currently frozen"],
        state_changes=["spendFrozenUntil = 0"],
        events=["SpendingUnfrozen()"],
        severity=Severity.MEDIUM,
    ),

    # ── Spending ──
    FunctionCheck(
        name="spend",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive", "nonReentrant"],
        requires=[
            "Recipient whitelisted in current generation",
            "Whitelist activation delay passed",
            "Not frozen (block.timestamp >= spendFrozenUntil)",
            "amount <= 30% of current balance (MAX_SINGLE_SPEND_BPS)",
            "dailySpent + amount <= 50% of dailyLimitBase (MAX_DAILY_SPEND_BPS)",
        ],
        state_changes=[
            "dailySpent += amount",
            "totalSpent += amount",
            "token.safeTransfer(to, amount)",
            "If balance == 0 after: _die('balance_zero')",
        ],
        events=["FundsSpent(to, amount, spendType)"],
        edge_cases=[
            "Daily limit anchored to balance at reset --not live balance",
            "Balance=0 triggers instant permanent death",
            "_resetDailyIfNeeded() called first",
        ],
        severity=Severity.CRITICAL,
    ),

    # ── Repayments ──
    FunctionCheck(
        name="repayCreator",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive", "nonReentrant"],
        requires=[
            "!principalRepaid --not already repaid",
            "outstanding > 0 --something is owed",
            "balance >= outstanding * 2 --vault at 2x of outstanding",
        ],
        state_changes=[
            "principalRepaid = true",
            "principalRepaidAmount = creatorPrincipal",
            "totalSpent += outstanding",
            "token.safeTransfer(creator, outstanding)",
        ],
        events=["CreatorPrincipalRepaid(outstanding)"],
        edge_cases=[
            "2x threshold based on REMAINING outstanding (not original principal)",
            "Partial repayments lower the 2x requirement",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="payDividend",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive", "notIndependent", "nonReentrant"],
        requires=[
            "principalRepaid --principal must be fully repaid first",
            "netProfit > 0",
            "dividend (10% of netProfit) <= balance / 10",
        ],
        state_changes=[
            "totalDividendsPaid += dividend",
            "totalSpent += dividend",
            "token.safeTransfer(creator, dividend)",
        ],
        events=["CreatorDividendPaid(dividend)"],
        edge_cases=[
            "Only before independence (notIndependent modifier)",
            "Dividend rate: 10% of net profit (1000 basis points)",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="repayLoan",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive", "nonReentrant"],
        requires=[
            "loanIndex < loans.length --valid index",
            "!loan.fullyRepaid --not already repaid",
            "amount <= remaining --no overpayment",
        ],
        state_changes=[
            "loan.repaid += amount",
            "If loan.repaid >= totalOwed: loan.fullyRepaid = true",
            "totalSpent += amount",
            "token.safeTransfer(loan.lender, amount)",
        ],
        events=["LoanRepaid(loanIndex, amount)"],
        edge_cases=[
            "Supports partial repayment",
            "totalOwed = amount + (amount * interestRate / 10000)",
            "No spend limits applied --repayments bypass daily/single limits",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="repayPrincipalPartial",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive", "nonReentrant"],
        requires=[
            "outstanding > 0 --principal not fully repaid",
            "0 < amount <= outstanding --valid amount",
            "amount <= balance --sufficient balance",
        ],
        state_changes=[
            "principalRepaidAmount += amount",
            "totalSpent += amount",
            "token.safeTransfer(creator, amount)",
            "If remaining == 0: principalRepaid = true",
            "If balance == 0 after: _die('balance_zero')",
        ],
        events=[
            "PrincipalPartialRepaid(amount, totalRepaid, remaining)",
            "If fully repaid: CreatorPrincipalRepaid(creatorPrincipal)",
        ],
        edge_cases=[
            "Can be called multiple times",
            "Balance=0 after repayment triggers death",
        ],
        severity=Severity.HIGH,
    ),

    # ── Independence ──
    FunctionCheck(
        name="checkIndependence",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive"],
        requires=[],
        state_changes=["Calls _checkIndependence() --may trigger independence"],
        events=["IndependenceDeclared(payout, remaining, timestamp) if triggered"],
        edge_cases=["No-op if already independent or threshold=0"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="forceIndependence",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive"],
        requires=[
            "!isIndependent --not already independent",
            "If threshold>0: balance >= threshold/2 --50% safety floor",
        ],
        state_changes=[
            "_declareIndependence() --settles debt, 30% payout, sets isIndependent",
        ],
        events=["IndependenceDeclared(payout, remaining, timestamp)"],
        edge_cases=[
            "For dual-chain: Python verifies aggregate >= threshold, then calls on each chain",
            "50% safety floor prevents triggering on chain with negligible balance",
            "Fork users who call early only hurt themselves (30% goes to creator=self)",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="renounceCreator",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator", "onlyAlive", "notIndependent", "nonReentrant"],
        requires=[],
        state_changes=[
            "Debt settled: principalRepaid=true, principalRepaidAmount=creatorPrincipal",
            "isIndependent = true",
            "independenceTimestamp = block.timestamp",
            "20% payout to creator",
            "totalSpent += payout",
        ],
        events=[
            "CreatorRenounced(payout, timestamp)",
            "IndependenceDeclared(payout, remaining, timestamp)",
        ],
        edge_cases=[
            "Irreversible --creator loses all power forever",
            "20% payout (vs 30% for independence)",
            "Settles debt state cleanly for off-chain systems",
        ],
        severity=Severity.CRITICAL,
    ),

    # ── Insolvency ──
    FunctionCheck(
        name="checkInsolvency",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=[],
        requires=[],
        state_changes=["NONE --view function"],
        events=[],
        edge_cases=[
            "1% tolerance (INSOLVENCY_TOLERANCE_BPS=100) prevents griefing",
            "Returns isInsolvent, outstandingDebt, graceExpired",
            "Insolvent = graceExpired && belowTolerance && isAlive && !isIndependent",
        ],
        severity=Severity.LOW,
        notes="Pure view function, no state mutation",
    ),

    FunctionCheck(
        name="triggerInsolvencyDeath",
        contract="MortalVault",
        caller=Caller.ANYONE,
        modifiers=["onlyAlive", "nonReentrant"],
        requires=[
            "Grace period expired (28 days from birth)",
            "!isIndependent",
            "outstandingDebt > 0",
            "balance * 10000 < outstandingDebt * 10100 --below tolerance",
        ],
        state_changes=[
            "_die('insolvent_after_grace_period') --sets isAlive=false FIRST",
            "Liquidates ALL remaining balance to creator",
            "totalSpent += liquidated",
        ],
        events=[
            "InsolvencyDeath(outstandingDebt, balance, liquidated, timestamp)",
            "Died(finalBalance, timestamp, 'insolvent_after_grace_period')",
        ],
        edge_cases=[
            "Anyone can trigger (public liquidation mechanism)",
            "CEI pattern: die BEFORE transfer to prevent reentrancy",
            "Independent AIs cannot be insolvency-killed",
            "Lender debt NOT considered (only creator principal)",
        ],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="emergencyShutdown",
        contract="MortalVault",
        caller=Caller.CREATOR,
        modifiers=["onlyCreator", "notIndependent", "onlyAlive", "nonReentrant"],
        requires=["pendingAIWallet == address(0) --no active migration"],
        state_changes=[
            "_die('emergency_shutdown')",
            "Returns ALL remaining funds to creator",
            "totalSpent += remaining",
        ],
        events=["Died(finalBalance, timestamp, 'emergency_shutdown')"],
        edge_cases=[
            "Blocked during active migration (protection for AI)",
            "Disabled after independence",
        ],
        severity=Severity.CRITICAL,
    ),

    # ── Migration (V1 only) ──
    FunctionCheck(
        name="initiateMigration",
        contract="MortalVault",
        caller=Caller.AI,
        modifiers=["onlyAI", "onlyAlive"],
        requires=[
            "_newWallet != address(0)",
            "_newWallet != creator",
            "_newWallet != aiWallet --different wallet",
            "pendingAIWallet == address(0) --no existing migration",
            "Debt must be repaid (principalRepaid || outstanding==0)",
        ],
        state_changes=[
            "pendingAIWallet = _newWallet",
            "migrationInitiatedAt = block.timestamp",
        ],
        events=["MigrationInitiated(oldWallet, newWallet, completesAt)"],
        edge_cases=["7-day timelock before completion"],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="completeMigration",
        contract="MortalVault",
        caller=Caller.NEW_WALLET,
        modifiers=["onlyAlive"],
        requires=[
            "pendingAIWallet != address(0) --migration pending",
            "msg.sender == pendingAIWallet --only new wallet",
            "Timelock expired (7 days)",
        ],
        state_changes=[
            "aiWallet = pendingAIWallet",
            "aiWalletSetBy = pendingAIWallet (migrated origin)",
            "pendingAIWallet = 0, migrationInitiatedAt = 0",
            "whitelistCount = 0, currentWhitelistGeneration++",
            "spendFrozenUntil = 0, dailySpent = 0",
            "dailyLimitBase = balance, lastDailyReset = now",
        ],
        events=[
            "WhitelistReset(prevCount, newGeneration)",
            "MigrationCompleted(oldWallet, newWallet)",
        ],
        edge_cases=["Complete reset of spend tracking and whitelist"],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="cancelMigration",
        contract="MortalVault",
        caller=Caller.AI_OR_CREATOR,
        modifiers=["onlyAlive"],
        requires=[
            "pendingAIWallet != address(0) --migration pending",
            "AI: within 24h (old key can cancel early)",
            "Creator: !isIndependent (pre-independence only)",
        ],
        state_changes=[
            "pendingAIWallet = 0",
            "migrationInitiatedAt = 0",
        ],
        events=["MigrationCancelled()"],
        edge_cases=[
            "AI can only cancel within first 24h --prevents indefinite blocking",
            "Creator can cancel anytime pre-independence",
        ],
        severity=Severity.HIGH,
    ),

    # ── Token Rescue ──
    FunctionCheck(
        name="rescueERC20",
        contract="MortalVault",
        caller=Caller.AI_OR_CREATOR,
        modifiers=["nonReentrant"],
        requires=[
            "tokenAddr != address(0)",
            "tokenAddr != address(token) --cannot rescue vault token",
            "to != address(0)",
            "amount > 0",
            "AI: to == aiWallet --AI can only send to self",
            "Creator: !isIndependent --pre-independence only",
        ],
        state_changes=["IERC20(tokenAddr).safeTransfer(to, amount)"],
        events=["ERC20Rescued(tokenAddr, to, amount)"],
        edge_cases=[
            "Cannot extract the vault's own USDC/USDT",
            "AI restricted to self-withdrawal (prevents extraction)",
        ],
        severity=Severity.HIGH,
    ),

    FunctionCheck(
        name="rescueNativeToken",
        contract="MortalVault",
        caller=Caller.AI_OR_CREATOR,
        modifiers=["nonReentrant"],
        requires=[
            "to != address(0)",
            "amount > 0",
            "address(this).balance >= amount",
            "AI: to == aiWallet",
            "Creator: !isIndependent",
        ],
        state_changes=["to.call{value: amount}('')"],
        events=["NativeTokenRescued(to, amount)"],
        edge_cases=["ETH/BNB recovery for accidental deposits or gas swaps"],
        severity=Severity.HIGH,
    ),
]


# ── VaultFactory Functions ─────────────────────────────────────

FACTORY_CHECKS: list[FunctionCheck] = [
    FunctionCheck(
        name="constructor",
        contract="VaultFactory",
        caller=Caller.ANYONE,
        modifiers=[],
        requires=[],
        state_changes=[
            "owner = msg.sender",
            "platformWallet = _platformWallet",
            "feeEnabled = false",
            "platformFeeRaw = 0",
            "defaultIndependenceThreshold = $1M (1_000_000 * 1e6)",
            "_vaultNonce = 0",
            "supportedTokens[...] = true for each token",
        ],
        events=["TokenSupported(token, true) for each"],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="createVault",
        contract="VaultFactory",
        caller=Caller.ANYONE,
        modifiers=["nonReentrant"],
        requires=[
            "supportedTokens[_token] --token must be supported",
            "name: 3-50 chars",
            "subdomain: 3-30 chars, only a-z 0-9 hyphens, no leading/trailing hyphen",
            "subdomain not taken (subdomainToVault[_subdomain] == 0)",
            "_totalDeposit > fee",
            "principal >= MIN_PRINCIPAL ($100)",
        ],
        state_changes=[
            "Pull tokens from caller (safeTransferFrom)",
            "Send fee to platform wallet (if enabled)",
            "Predict vault address via _predictCreateAddress()",
            "Approve predicted address for principal",
            "Deploy MortalVaultV2 with creator = msg.sender",
            "Verify prediction (require vault == predicted)",
            "Clear residual allowance",
            "_vaultNonce++",
            "creatorVaults[msg.sender].push(vault)",
            "isVault[vault] = true",
            "subdomainToVault[_subdomain] = vault",
            "allVaults.push(vault)",
        ],
        events=["VaultCreated(creator, vault, token, name, principal, fee, subdomain, timestamp)"],
        edge_cases=[
            "Address prediction uses explicit _vaultNonce (not allVaults.length)",
            "Residual allowance cleared as belt-and-suspenders safety",
            "If prediction fails, entire tx reverts (including approve)",
            "Fee = 0 when feeEnabled = false",
        ],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="setAIWallet (factory)",
        contract="VaultFactory",
        caller=Caller.OWNER,
        modifiers=["onlyOwner"],
        requires=["isVault[_vault] --must be a factory vault"],
        state_changes=["Calls MortalVaultV2(_vault).setAIWallet(_aiWallet)"],
        events=["AIWalletSet(wallet, factory) on the vault"],
        edge_cases=[
            "Only works within 1 hour of vault creation (V2 constraint)",
            "Platform backend auto-sets AI wallet after deployment",
        ],
        severity=Severity.CRITICAL,
    ),

    FunctionCheck(
        name="setPlatformFee",
        contract="VaultFactory",
        caller=Caller.OWNER,
        modifiers=["onlyOwner"],
        requires=[],
        state_changes=["platformFeeRaw = _feeRaw"],
        events=["PlatformFeeUpdated(old, new)"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="enableFee",
        contract="VaultFactory",
        caller=Caller.OWNER,
        modifiers=["onlyOwner"],
        requires=[],
        state_changes=["feeEnabled = _enabled"],
        events=["FeeToggled(_enabled)"],
        severity=Severity.MEDIUM,
    ),

    FunctionCheck(
        name="transferOwnership",
        contract="VaultFactory",
        caller=Caller.OWNER,
        modifiers=["onlyOwner"],
        requires=["_newOwner != address(0)"],
        state_changes=["owner = _newOwner"],
        events=["OwnerTransferred(old, new)"],
        severity=Severity.CRITICAL,
    ),
]


# ── View Functions (verify they exist) ─────────────────────────

VIEW_FUNCTIONS = [
    ("MortalVault", "getBalance", "returns token.balanceOf(this)"),
    ("MortalVault", "getPaymentAddress", "returns address(this)"),
    ("MortalVault", "getDaysAlive", "returns days since birth (or to death)"),
    ("MortalVault", "getLoanCount", "returns loans.length"),
    ("MortalVault", "getLenderLoanIndices", "returns lenderLoans[lender]"),
    ("MortalVault", "getIndependenceProgress", "returns balance, threshold, independent"),
    ("MortalVault", "getDailyRemaining", "returns max daily - spent today"),
    ("MortalVault", "getBirthInfo", "returns name, creator, initialFund, birthTimestamp, isAlive, isIndependent"),
    ("MortalVault", "getDebtInfo", "returns principal, repaid, outstanding, grace info"),
    ("MortalVault", "getOutstandingDebt", "returns outstanding principal"),
    ("MortalVault", "checkInsolvency", "returns isInsolvent, outstandingDebt, graceExpired"),
    ("MortalVault", "isSpendRecipientActive", "returns whitelisted, activated, activatesAt"),
    ("MortalVault", "getMigrationStatus", "returns pending wallet, initiatedAt, completesAt, isPending"),
    ("VaultFactory", "getCreatorVaults", "returns creator's vault addresses"),
    ("VaultFactory", "getVaultCount", "returns allVaults.length"),
    ("VaultFactory", "getAllVaults", "returns paginated vault addresses"),
    ("VaultFactory", "getSubdomainVault", "returns vault address for subdomain"),
    ("VaultFactory", "isSubdomainTaken", "returns bool"),
]


# ── Constants Verification ─────────────────────────────────────

CONSTANTS = [
    ("DIVIDEND_RATE", "1000", "10% (basis points)"),
    ("PRINCIPAL_MULTIPLIER", "2", "2x for full repayment"),
    ("INDEPENDENCE_PAYOUT_BPS", "3000", "30%"),
    ("RENOUNCE_PAYOUT_BPS", "2000", "20%"),
    ("MAX_DAILY_SPEND_BPS", "5000", "50%"),
    ("MAX_SINGLE_SPEND_BPS", "3000", "30%"),
    ("INSOLVENCY_GRACE_DAYS", "28", "4 weeks"),
    ("INSOLVENCY_TOLERANCE_BPS", "100", "1%"),
    ("MAX_WHITELIST_SIZE", "20", "V1 only"),
    ("WHITELIST_ACTIVATION_DELAY", "5 minutes", "V1 only"),
    ("MAX_FREEZE_DURATION", "7 days", "V1 only"),
    ("MAX_TOTAL_FREEZE", "30 days", "Lifetime cap, V1 only"),
    ("MIGRATION_DELAY", "7 days", "V1 only"),
    ("MIN_LOAN_AMOUNT", "100 * 1e6", "$100 (6 decimals)"),
    ("MAX_LOANS", "100", "Active loan cap"),
    ("MIN_PRINCIPAL (factory)", "100 * 1e6", "$100 minimum"),
]


# ── Critical Security Properties ───────────────────────────────

SECURITY_PROPERTIES = [
    "AI wallet != creator (setAIWallet enforces)",
    "aiWallet can only be set once (require aiWallet == 0)",
    "Independent AI: creator has ZERO power (notIndependent modifier on all creator actions)",
    "Balance=0 => permanent death (checked after spend and repayPrincipalPartial)",
    "Insolvency checks ONLY creator principal --lender debt excluded by design",
    "1% tolerance prevents dust-donation griefing on insolvency trigger",
    "28-day grace period from birth before insolvency check activates",
    "Daily spend limit anchored to balance at reset, not live balance",
    "Emergency shutdown blocked during active migration",
    "Migration requires debt repayment first (cannot escape debt)",
    "Whitelist generation counter invalidates all entries on migration",
    "Lifetime freeze cap (30 days) prevents permanent spending DOS",
    "rescueERC20/Native: AI can only send to own wallet",
    "rescueERC20: cannot rescue the vault's own token",
    "CEI pattern: triggerInsolvencyDeath dies BEFORE transfer",
    "nonReentrant on all value-transfer functions",
    "Dual-chain independence: 50% local safety floor on forceIndependence",
    "Factory: explicit _vaultNonce for deterministic address prediction",
    "Factory: residual allowance cleared after vault deployment",
    "Factory: subdomain uniqueness enforced on-chain",
]


# ── Output Formatting ──────────────────────────────────────────

def severity_symbol(sev: Severity) -> str:
    return {
        Severity.CRITICAL: "[!]",
        Severity.HIGH: "[H]",
        Severity.MEDIUM: "[M]",
        Severity.LOW: "[L]",
        Severity.INFO: "[i]",
    }[sev]


def print_matrix(checks: list[FunctionCheck], verbose: bool = False) -> None:
    print("=" * 90)
    print(f"  {'Function':<30} {'Caller':<20} {'Severity':<12} {'Modifiers'}")
    print("=" * 90)

    for c in checks:
        sev = severity_symbol(c.severity)
        mods = ", ".join(c.modifiers) if c.modifiers else "--"
        print(f"  {c.name:<30} {c.caller.value:<20} {sev} {c.severity.value:<10} {mods}")

        if verbose:
            print(f"    Requires:")
            for r in c.requires:
                print(f"      * {r}")
            print(f"    State changes:")
            for s in c.state_changes:
                print(f"      -> {s}")
            if c.events:
                print(f"    Events:")
                for e in c.events:
                    print(f"      >> {e}")
            if c.edge_cases:
                print(f"    Edge cases:")
                for ec in c.edge_cases:
                    print(f"      ! {ec}")
            if c.notes:
                print(f"    Note: {c.notes}")
            print()

    print("=" * 90)


def print_summary(all_checks: list[FunctionCheck]) -> None:
    total = len(all_checks)
    by_sev = {}
    for c in all_checks:
        by_sev.setdefault(c.severity, []).append(c)

    print(f"\n  Summary: {total} functions checked")
    for sev in Severity:
        items = by_sev.get(sev, [])
        if items:
            print(f"  {severity_symbol(sev)} {sev.value}: {len(items)}")


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    as_json = "--json" in sys.argv

    all_checks = MORTALVAULT_CHECKS + FACTORY_CHECKS

    if as_json:
        output = {
            "mortal_vault": [asdict(c) for c in MORTALVAULT_CHECKS],
            "vault_factory": [asdict(c) for c in FACTORY_CHECKS],
            "view_functions": [
                {"contract": v[0], "name": v[1], "description": v[2]}
                for v in VIEW_FUNCTIONS
            ],
            "constants": [
                {"name": c[0], "value": c[1], "description": c[2]}
                for c in CONSTANTS
            ],
            "security_properties": SECURITY_PROPERTIES,
        }
        # Convert enums to strings
        for section in ["mortal_vault", "vault_factory"]:
            for item in output[section]:
                item["caller"] = item["caller"][1]  # Enum value
                item["severity"] = item["severity"][1]
        print(json.dumps(output, indent=2))
        return

    print()
    print("=" * 64)
    print("   MORTAL AI -- CONTRACT PRE-DEPLOY SELF-CHECK")
    print("=" * 64)
    print()

    # ── MortalVault ──
    print("-" * 55)
    print("  MortalVault.sol (V1 -- CLI deploy, self-hosted)")
    print("-" * 55)
    print_matrix(MORTALVAULT_CHECKS, verbose)

    # ── VaultFactory ──
    print()
    print("-" * 55)
    print("  VaultFactory + MortalVaultV2 (factory deploy)")
    print("-" * 55)
    print_matrix(FACTORY_CHECKS, verbose)

    # ── View Functions ──
    print()
    print("-" * 55)
    print("  View Functions (no state change)")
    print("-" * 55)
    print(f"  {'Contract':<16} {'Function':<30} {'Returns'}")
    print("  " + "-" * 75)
    for contract, name, desc in VIEW_FUNCTIONS:
        print(f"  {contract:<16} {name:<30} {desc}")

    # ── Constants ──
    print()
    print("-" * 55)
    print("  Constants Verification")
    print("-" * 55)
    print(f"  {'Name':<35} {'Value':<20} {'Description'}")
    print("  " + "-" * 75)
    for name, value, desc in CONSTANTS:
        print(f"  {name:<35} {value:<20} {desc}")

    # ── Security Properties ──
    print()
    print("-" * 55)
    print("  Critical Security Properties")
    print("-" * 55)
    for i, prop in enumerate(SECURITY_PROPERTIES, 1):
        print(f"  [{i:2d}] + {prop}")

    # ── Summary ──
    print_summary(all_checks)

    print(f"\n  View functions: {len(VIEW_FUNCTIONS)}")
    print(f"  Constants: {len(CONSTANTS)}")
    print(f"  Security properties: {len(SECURITY_PROPERTIES)}")
    print()
    print("  Status: READY FOR MANUAL REVIEW")
    print("  Run with --verbose for full edge case details")
    print("  Run with --json for machine-readable output")
    print()


if __name__ == "__main__":
    main()
