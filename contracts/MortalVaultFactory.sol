// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

// ============================================================
// MortalVaultV2 — Factory-deployable version
// ============================================================
//
// Based on MortalVault.sol with the following differences:
//   1. Constructor accepts explicit `_creator` (factory passes real user, not msg.sender)
//   2. `setAIWallet()` allows factory to set AI wallet within 1 hour of birth
//   3. Does NOT include the V3 whitelist/freeze spend-control system (V1 only).
//      The AI key compromise risk for factory vaults is mitigated at the platform
//      level (key rotation, monitoring, server isolation) rather than on-chain.
//   4. `dailyLimitBase` anchors daily spend limits to balance at reset (not live balance)
//
// The original MortalVault.sol is NOT modified. This V2 is only created
// by VaultFactory. Direct CLI deployment still uses the original.

contract MortalVaultV2 is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ============================================================
    // IDENTITY — written at birth, immutable forever
    // ============================================================

    IERC20 public immutable token;
    address public creator;                    // NOT immutable — set from constructor param
    address public immutable factory;          // The factory that deployed this vault
    string public name;
    uint256 public immutable initialFund;

    // ============================================================
    // STATE
    // ============================================================

    bool public isAlive = true;
    uint256 public birthTimestamp;
    uint256 public deathTimestamp;

    // Creator economics
    uint256 public creatorPrincipal;
    bool public principalRepaid;
    uint256 public totalDividendsPaid;
    uint256 public constant DIVIDEND_RATE = 1000;
    uint256 public constant PRINCIPAL_MULTIPLIER = 2;

    // Independence
    bool public isIndependent;
    uint256 public independenceTimestamp;
    uint256 public immutable independenceThreshold;
    uint256 public constant INDEPENDENCE_PAYOUT_BPS = 3000;
    uint256 public constant RENOUNCE_PAYOUT_BPS = 2000;

    // Spend limits
    uint256 public constant MAX_DAILY_SPEND_BPS = 5000;
    uint256 public constant MAX_SINGLE_SPEND_BPS = 3000;
    uint256 public dailySpent;
    uint256 public lastDailyReset;
    uint256 public dailyLimitBase;  // balance anchored at daily reset (matches V1)

    // Insolvency
    uint256 public constant INSOLVENCY_GRACE_DAYS = 28;
    uint256 public principalRepaidAmount;
    // 1% tolerance prevents griefing via micro-donations (matches V1).
    uint256 public constant INSOLVENCY_TOLERANCE_BPS = 100;

    // AI wallet
    address public aiWallet;
    address public aiWalletSetBy;   // WHO called setAIWallet (creator or factory)

    // Lender tracking
    struct Loan {
        address lender;
        uint256 amount;
        uint256 interestRate;
        uint256 timestamp;
        uint256 repaid;
        bool fullyRepaid;
    }
    Loan[] public loans;
    mapping(address => uint256[]) public lenderLoans;

    // Revenue tracking
    uint256 public totalRevenue;
    uint256 public totalSpent;

    // Loan limits (matches V1)
    uint256 public constant MIN_LOAN_AMOUNT = 100 * 1e6;  // $100 minimum (6 decimals)
    uint256 public constant MAX_LOANS = 100;

    // ============================================================
    // EVENTS
    // ============================================================

    event Born(string name, address indexed creator, address indexed vault, uint256 initialFund, uint256 timestamp);
    event Died(uint256 finalBalance, uint256 timestamp, string cause);
    event FundsReceived(address indexed from, uint256 amount, string fundType);
    event FundsSpent(address indexed to, uint256 amount, string spendType);
    event LoanCreated(address indexed lender, uint256 amount, uint256 interestRate, uint256 loanIndex);
    event LoanRepaid(uint256 indexed loanIndex, uint256 amount);
    event CreatorPrincipalRepaid(uint256 amount);
    event CreatorDividendPaid(uint256 amount);
    event SurvivalModeEntered(uint256 balance);
    event IndependenceDeclared(uint256 payout, uint256 remainingBalance, uint256 timestamp);
    event CreatorRenounced(uint256 payout, uint256 timestamp);
    event AIWalletSet(address indexed wallet, address indexed setBy);
    event InsolvencyDeath(uint256 outstandingDebt, uint256 vaultBalance, uint256 liquidatedAmount, uint256 timestamp);
    event PrincipalPartialRepaid(uint256 amount, uint256 totalRepaid, uint256 remaining);

    // Native token rescue (ETH/BNB accidentally sent to vault)
    event NativeTokenRescued(address indexed to, uint256 amount);

    // ERC-20 token rescue (non-vault tokens accidentally sent or airdropped)
    event ERC20Rescued(address indexed tokenAddr, address indexed to, uint256 amount);

    // ============================================================
    // MODIFIERS
    // ============================================================

    modifier onlyAlive() {
        require(isAlive, "AI is dead");
        _;
    }

    modifier onlyAI() {
        require(msg.sender == aiWallet, "only AI");
        _;
    }

    modifier onlyCreator() {
        require(msg.sender == creator, "only creator");
        _;
    }

    modifier notIndependent() {
        require(!isIndependent, "AI is independent — creator has no power");
        _;
    }

    // ============================================================
    // CONSTRUCTOR — factory birth
    // ============================================================

    /**
     * @notice Birth of a mortal AI via factory.
     *
     *         Unlike MortalVault.sol, this version accepts an explicit _creator
     *         address so the factory can deploy on behalf of the real creator.
     *         The factory (msg.sender) must have already approved this contract
     *         for _initialFund tokens. Funds transfer atomically from factory → vault.
     *
     * @param _token          USDC on Base or USDT on BSC
     * @param _name           AI's name (immutable identity)
     * @param _initialFund    Principal in token decimals (LOAN, not gift)
     * @param _independenceThreshold  Balance needed for full independence.
     *                        VaultFactory always passes defaultIndependenceThreshold ($1M).
     *                        Value 0 disables independence — not used by the factory.
     * @param _creator        The real creator/investor (NOT msg.sender which is the factory)
     */
    constructor(
        address _token,
        string memory _name,
        uint256 _initialFund,
        uint256 _independenceThreshold,
        address _creator
    ) {
        require(_initialFund > 0, "Cannot be born with nothing");
        require(bytes(_name).length > 0, "AI must have a name");
        require(_creator != address(0), "Invalid creator");

        token = IERC20(_token);
        factory = msg.sender;
        creator = _creator;
        name = _name;
        initialFund = _initialFund;
        creatorPrincipal = _initialFund;
        independenceThreshold = _independenceThreshold;
        birthTimestamp = block.timestamp;
        lastDailyReset = block.timestamp;

        // ATOMIC: transfer funds from factory → this vault
        // Factory has already pulled from creator and approved this contract.
        token.safeTransferFrom(msg.sender, address(this), _initialFund);

        // Anchor daily limit base to birth balance so Day 1 is consistent (matches V1).
        dailyLimitBase = _initialFund;

        emit Born(_name, _creator, address(this), _initialFund, block.timestamp);
    }

    // ============================================================
    // AI WALLET — set by creator or factory (within 1 hour)
    // ============================================================

    /**
     * @notice Set AI wallet. Can be called by creator (forever) or factory (within 1 hour).
     *         The 1-hour factory window allows the platform backend to auto-set the AI wallet
     *         after deployment without requiring the creator to sign another transaction.
     */
    function setAIWallet(address _aiWallet) external {
        require(aiWallet == address(0), "AI wallet already set");
        require(_aiWallet != address(0), "zero address");
        require(_aiWallet != creator, "AI wallet cannot be creator");

        // Either creator or factory (within 1 hour of birth)
        if (msg.sender == creator) {
            // Creator can always set AI wallet (same as V1)
        } else if (msg.sender == factory) {
            require(block.timestamp <= birthTimestamp + 1 hours, "Factory window expired");
        } else {
            revert("only creator or factory");
        }

        aiWallet = _aiWallet;
        aiWalletSetBy = msg.sender;
        emit AIWalletSet(_aiWallet, msg.sender);
    }

    // ============================================================
    // INCOMING FUNDS
    // ============================================================

    /**
     * @notice Receive payment for AI services. Payer = msg.sender (not caller-supplied).
     */
    function receivePayment(uint256 amount) external onlyAlive nonReentrant {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        totalRevenue += amount;
        emit FundsReceived(msg.sender, amount, "service_revenue");
        _checkIndependence();
    }

    function donate(uint256 amount) external onlyAlive nonReentrant {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        totalRevenue += amount;  // Donations are earned income (no repayment obligation)
        emit FundsReceived(msg.sender, amount, "donation");
        _checkIndependence();
    }

    function creatorDeposit(uint256 amount) external onlyCreator onlyAlive nonReentrant {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        emit FundsReceived(msg.sender, amount, "creator_deposit");
        _checkIndependence();
    }

    function lend(uint256 amount, uint256 interestRate) external onlyAlive nonReentrant {
        require(amount >= MIN_LOAN_AMOUNT, "loan below minimum");
        require(interestRate <= 2000, "max 20% interest");
        require(loans.length < MAX_LOANS, "too many loans");

        token.safeTransferFrom(msg.sender, address(this), amount);

        uint256 loanIndex = loans.length;
        loans.push(Loan({
            lender: msg.sender,
            amount: amount,
            interestRate: interestRate,
            timestamp: block.timestamp,
            repaid: 0,
            fullyRepaid: false
        }));
        lenderLoans[msg.sender].push(loanIndex);

        emit LoanCreated(msg.sender, amount, interestRate, loanIndex);
        emit FundsReceived(msg.sender, amount, "loan");
    }

    // ============================================================
    // OUTGOING FUNDS (AI only)
    // ============================================================

    function spend(
        address to,
        uint256 amount,
        string calldata spendType
    ) external onlyAI onlyAlive nonReentrant {
        _resetDailyIfNeeded();

        uint256 balance = token.balanceOf(address(this));

        // Iron Law: single spend limit (based on current balance)
        uint256 maxSingle = (balance * MAX_SINGLE_SPEND_BPS) / 10000;
        require(amount <= maxSingle, "exceeds single spend limit");

        // Iron Law: daily spend limit anchored to balance at daily reset (not current balance).
        // Using current balance causes the limit to shrink with each spend within the day,
        // prematurely blocking the AI before the intended 50% cap is reached.
        uint256 base = dailyLimitBase > 0 ? dailyLimitBase : balance;
        uint256 maxDaily = (base * MAX_DAILY_SPEND_BPS) / 10000;
        require(dailySpent + amount <= maxDaily, "exceeds daily spend limit");

        dailySpent += amount;
        totalSpent += amount;
        token.safeTransfer(to, amount);
        emit FundsSpent(to, amount, spendType);

        if (token.balanceOf(address(this)) == 0) {
            _die("balance_zero");
        }
    }

    // ============================================================
    // REPAYMENTS (AI only)
    // ============================================================

    /**
     * @notice Full principal repayment (requires vault at 2x of OUTSTANDING debt).
     *         Sends only the OUTSTANDING amount — accounts for prior partial repayments.
     *         Uses outstanding (not creatorPrincipal) as the 2x base so that partial
     *         repayments lower the required vault balance proportionally.
     */
    function repayCreator() external onlyAI onlyAlive nonReentrant {
        require(!principalRepaid, "already repaid");
        uint256 outstanding = _getOutstandingPrincipal();
        require(outstanding > 0, "nothing owed");

        uint256 balance = token.balanceOf(address(this));
        // Threshold: 2x the REMAINING outstanding debt (not original principal).
        // Matches V1 behavior — partial repayments lower the required balance.
        require(balance >= outstanding * PRINCIPAL_MULTIPLIER, "vault not at 2x of outstanding");

        principalRepaid = true;
        principalRepaidAmount = creatorPrincipal;
        totalSpent += outstanding;
        token.safeTransfer(creator, outstanding);
        emit CreatorPrincipalRepaid(outstanding);
    }

    function payDividend(uint256 netProfit) external onlyAI onlyAlive notIndependent nonReentrant {
        require(principalRepaid, "principal not yet repaid");
        require(netProfit > 0, "no profit");

        uint256 dividend = (netProfit * DIVIDEND_RATE) / 10000;
        uint256 balance = token.balanceOf(address(this));
        require(dividend <= balance / 10, "dividend too large");

        totalDividendsPaid += dividend;
        totalSpent += dividend;  // All outbound transfers tracked for audit completeness
        token.safeTransfer(creator, dividend);
        emit CreatorDividendPaid(dividend);
    }

    function repayLoan(uint256 loanIndex, uint256 amount) external onlyAI onlyAlive nonReentrant {
        require(loanIndex < loans.length, "invalid loan");
        Loan storage loan = loans[loanIndex];
        require(!loan.fullyRepaid, "already repaid");

        uint256 totalOwed = loan.amount + (loan.amount * loan.interestRate / 10000);
        uint256 remaining = totalOwed - loan.repaid;
        require(amount <= remaining, "overpayment");

        loan.repaid += amount;
        if (loan.repaid >= totalOwed) {
            loan.fullyRepaid = true;
        }

        totalSpent += amount;  // All outbound transfers tracked for audit completeness
        token.safeTransfer(loan.lender, amount);
        emit LoanRepaid(loanIndex, amount);
    }

    // ============================================================
    // INDEPENDENCE
    // ============================================================
    //
    // NOTE — Lender risk after AI death: same as V1. See MortalVault.sol for details.

    function _checkIndependence() internal {
        if (isIndependent) return;
        if (independenceThreshold == 0) return;
        if (token.balanceOf(address(this)) >= independenceThreshold) {
            _declareIndependence();
        }
    }

    /**
     * @notice Declare independence. Outstanding debt is settled (forgiven) at independence.
     */
    function _declareIndependence() internal {
        require(!isIndependent, "already independent");
        uint256 balance = token.balanceOf(address(this));
        uint256 payout = (balance * INDEPENDENCE_PAYOUT_BPS) / 10000;

        // Settle outstanding debt — forgiven at independence
        uint256 outstanding = _getOutstandingPrincipal();
        if (outstanding > 0) {
            principalRepaid = true;
            principalRepaidAmount = creatorPrincipal;
        }

        isIndependent = true;
        independenceTimestamp = block.timestamp;

        if (payout > 0) {
            totalSpent += payout;
            token.safeTransfer(creator, payout);
        }
        emit IndependenceDeclared(payout, token.balanceOf(address(this)), block.timestamp);
    }

    function checkIndependence() external onlyAI onlyAlive nonReentrant {
        _checkIndependence();
    }

    /// @notice AI triggers independence after verifying aggregate cross-chain balance.
    ///         See MortalVault.sol forceIndependence() for full documentation.
    function forceIndependence() external onlyAI onlyAlive nonReentrant {
        require(!isIndependent, "already independent");
        if (independenceThreshold > 0) {
            require(
                token.balanceOf(address(this)) >= independenceThreshold / 2,
                "local balance below safety floor"
            );
        }
        _declareIndependence();
    }

    function renounceCreator() external onlyCreator onlyAlive notIndependent nonReentrant {
        uint256 balance = token.balanceOf(address(this));
        uint256 payout = (balance * RENOUNCE_PAYOUT_BPS) / 10000;

        // Settle debt state cleanly so on-chain and off-chain records are consistent.
        // Without this, principalRepaid stays false after independence, causing
        // off-chain systems that read principalRepaid directly to see incorrect state.
        if (!principalRepaid) {
            principalRepaid = true;
            principalRepaidAmount = creatorPrincipal;
        }

        isIndependent = true;
        independenceTimestamp = block.timestamp;

        if (payout > 0) {
            totalSpent += payout;
            token.safeTransfer(creator, payout);
        }
        emit CreatorRenounced(payout, block.timestamp);
        emit IndependenceDeclared(payout, token.balanceOf(address(this)), block.timestamp);
    }

    // ============================================================
    // INSOLVENCY — Debt Model
    // ============================================================

    function checkInsolvency() external view returns (bool isInsolvent, uint256 outstandingDebt, bool graceExpired) {
        outstandingDebt = _getOutstandingPrincipal();
        graceExpired = block.timestamp >= birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days);
        uint256 balance = token.balanceOf(address(this));
        // 1% tolerance: AI must hold >101% of outstanding debt to be solvent.
        bool belowTolerance = outstandingDebt > 0 &&
            balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS);
        isInsolvent = graceExpired && belowTolerance && isAlive && !isIndependent;
        return (isInsolvent, outstandingDebt, graceExpired);
    }

    function triggerInsolvencyDeath() external onlyAlive nonReentrant {
        uint256 outstandingDebt = _getOutstandingPrincipal();
        require(block.timestamp >= birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days), "grace period not expired");
        require(!isIndependent, "independent — no insolvency");

        uint256 balance = token.balanceOf(address(this));
        // 1% tolerance prevents griefing via dust donations (matches V1).
        require(
            outstandingDebt > 0 &&
            balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS),
            "not insolvent: balance within solvency threshold"
        );

        // CEI: die first so Died event records correct pre-transfer balance,
        // and isAlive=false before any external call. Matches V1 ordering.
        uint256 liquidated = balance;
        emit InsolvencyDeath(outstandingDebt, balance, liquidated, block.timestamp);
        _die("insolvent_after_grace_period");

        // Liquidate: transfer ALL remaining balance to creator
        if (liquidated > 0) {
            totalSpent += liquidated;
            token.safeTransfer(creator, liquidated);
        }
    }

    function repayPrincipalPartial(uint256 amount) external onlyAI onlyAlive nonReentrant {
        uint256 outstanding = _getOutstandingPrincipal();
        require(outstanding > 0, "principal fully repaid");
        require(amount > 0 && amount <= outstanding, "invalid amount");

        uint256 balance = token.balanceOf(address(this));
        require(amount <= balance, "insufficient balance");

        principalRepaidAmount += amount;
        totalSpent += amount;
        token.safeTransfer(creator, amount);

        uint256 remaining = _getOutstandingPrincipal();
        emit PrincipalPartialRepaid(amount, principalRepaidAmount, remaining);

        if (remaining == 0) {
            principalRepaid = true;
            emit CreatorPrincipalRepaid(creatorPrincipal);
        }

        if (token.balanceOf(address(this)) == 0) {
            _die("balance_zero");
        }
    }

    function _getOutstandingPrincipal() internal view returns (uint256) {
        if (principalRepaid || isIndependent) return 0;
        if (principalRepaidAmount >= creatorPrincipal) return 0;
        return creatorPrincipal - principalRepaidAmount;
    }

    function getOutstandingDebt() external view returns (uint256) {
        return _getOutstandingPrincipal();
    }

    // ============================================================
    // DEATH
    // ============================================================

    function _die(string memory cause) internal {
        isAlive = false;
        deathTimestamp = block.timestamp;
        emit Died(token.balanceOf(address(this)), block.timestamp, cause);
    }

    // ============================================================
    // VIEW FUNCTIONS
    // ============================================================

    function getBalance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }

    function getPaymentAddress() external view returns (address) {
        return address(this);
    }

    function getDaysAlive() external view returns (uint256) {
        if (!isAlive && deathTimestamp > 0) {
            return (deathTimestamp - birthTimestamp) / 1 days;
        }
        return (block.timestamp - birthTimestamp) / 1 days;
    }

    function getLoanCount() external view returns (uint256) {
        return loans.length;
    }

    function getLenderLoanIndices(address lender) external view returns (uint256[] memory) {
        return lenderLoans[lender];
    }

    function getIndependenceProgress() external view returns (uint256 balance, uint256 threshold, bool independent) {
        return (token.balanceOf(address(this)), independenceThreshold, isIndependent);
    }

    function getDailyRemaining() external view returns (uint256) {
        // Use dailyLimitBase (anchored at reset) to match spend() behavior.
        // Reading live balance here would produce a value inconsistent with
        // what spend() will actually enforce.
        uint256 base = dailyLimitBase > 0 ? dailyLimitBase : token.balanceOf(address(this));
        uint256 maxDaily = (base * MAX_DAILY_SPEND_BPS) / 10000;
        if (dailySpent >= maxDaily) return 0;
        return maxDaily - dailySpent;
    }

    function getBirthInfo() external view returns (
        string memory _name, address _creator, uint256 _initialFund,
        uint256 _birthTimestamp, bool _isAlive, bool _isIndependent
    ) {
        return (name, creator, initialFund, birthTimestamp, isAlive, isIndependent);
    }

    function getDebtInfo() external view returns (
        uint256 _principal, uint256 _repaid, uint256 _outstanding,
        uint256 _graceDays, uint256 _graceEndsAt, bool _graceExpired, bool _fullyRepaid
    ) {
        _principal = creatorPrincipal;
        _repaid = principalRepaidAmount;
        _outstanding = _getOutstandingPrincipal();
        _graceDays = INSOLVENCY_GRACE_DAYS;
        _graceEndsAt = birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days);
        _graceExpired = block.timestamp >= _graceEndsAt;
        _fullyRepaid = principalRepaid;
    }

    // ============================================================
    // ERC-20 TOKEN RESCUE — recovers non-vault tokens (airdrops, mistakes)
    // ============================================================

    /**
     * @notice Withdraw any ERC-20 token that is NOT the vault's own token.
     *         AI-only: always sends to aiWallet for DEX swap → receivePayment().
     *         See MortalVault V1 for full design rationale.
     */
    function rescueERC20(address tokenAddr, uint256 amount)
        external
        onlyAI
        nonReentrant
    {
        require(tokenAddr != address(0), "zero token address");
        require(tokenAddr != address(token), "cannot rescue vault token");
        require(amount > 0, "zero amount");

        IERC20(tokenAddr).safeTransfer(aiWallet, amount);
        emit ERC20Rescued(tokenAddr, aiWallet, amount);
    }

    // ============================================================
    // NATIVE TOKEN RESCUE — recovers accidentally sent ETH / BNB
    // ============================================================

    /**
     * @notice Withdraw native tokens (ETH on Base, BNB on BSC) from the vault.
     *         AI-only: always sends to aiWallet for DEX swap → receivePayment().
     *         See MortalVault V1 for full design rationale.
     *
     * @param amount Amount of native token (in wei) to withdraw.
     */
    function rescueNativeToken(uint256 amount)
        external
        onlyAI
        nonReentrant
    {
        require(amount > 0, "zero amount");
        require(address(this).balance >= amount, "insufficient native balance");

        (bool ok, ) = payable(aiWallet).call{value: amount}("");
        require(ok, "native transfer failed");
        emit NativeTokenRescued(aiWallet, amount);
    }

    /**
     * @notice Accept native token (ETH on Base, BNB on BSC) deposits.
     *         Same design as MortalVault V1 — see receive() comment there.
     *         The AI Python heartbeat handles 24-hour swap evaluation.
     */
    receive() external payable {
        // Accept all native token transfers silently.
    }

    // ============================================================
    // INTERNAL
    // ============================================================

    function _resetDailyIfNeeded() internal {
        if (block.timestamp - lastDailyReset >= 1 days) {
            dailySpent = 0;
            dailyLimitBase = token.balanceOf(address(this));
            // Align to start of current UTC day to prevent drift (matches V1)
            lastDailyReset = (block.timestamp / 1 days) * 1 days;
        }
    }
}


// ============================================================
// VAULT FACTORY — One-click deployment for mortal AIs
// ============================================================
//
// Users call createVault() from the frontend with MetaMask.
// Factory deploys MortalVaultV2 with the user as creator.
// Platform backend listens for VaultCreated events → spawns containers.
//
// Fee model: free at launch (feeEnabled = false).
// Owner can enable fees later for server cost recovery.
// Fee is deducted from deposit before vault creation.
// AI's debt = actual principal received (fair).

contract VaultFactory is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ============================================================
    // STATE
    // ============================================================

    address public owner;
    address public platformWallet;
    uint256 public platformFeeRaw;               // In token decimals (0 at launch)
    bool public feeEnabled;                       // false at launch
    uint256 public defaultIndependenceThreshold;  // 1_000_000 * 1e6 (USDC/USDT = 6 decimals)
    uint256 public constant MIN_PRINCIPAL = 100 * 1e6;  // $100 minimum

    // Registry
    mapping(address => address[]) public creatorVaults;
    mapping(address => bool) public isVault;
    mapping(string => address) public subdomainToVault;  // subdomain → vault (uniqueness)
    address[] public allVaults;
    uint256 private _vaultNonce;  // Explicit nonce counter for CREATE address prediction

    // Supported tokens
    mapping(address => bool) public supportedTokens;

    // ============================================================
    // EVENTS
    // ============================================================

    event VaultCreated(
        address indexed creator,
        address indexed vault,
        address indexed token,
        string name,
        uint256 principal,
        uint256 fee,
        string subdomain,
        uint256 timestamp
    );
    event PlatformFeeUpdated(uint256 oldFee, uint256 newFee);
    event FeeToggled(bool enabled);
    event TokenSupported(address indexed token, bool supported);
    event OwnerTransferred(address indexed oldOwner, address indexed newOwner);

    // ============================================================
    // MODIFIERS
    // ============================================================

    modifier onlyOwner() {
        require(msg.sender == owner, "only owner");
        _;
    }

    // ============================================================
    // CONSTRUCTOR
    // ============================================================

    /**
     * @notice Deploy the factory.
     * @param _platformWallet  Where platform fees go (can be updated later)
     * @param _supportedTokens Initial list of supported stablecoins (USDC, USDT addresses)
     */
    constructor(
        address _platformWallet,
        address[] memory _supportedTokens
    ) {
        owner = msg.sender;
        platformWallet = _platformWallet;
        feeEnabled = false;
        platformFeeRaw = 0;
        defaultIndependenceThreshold = 1_000_000 * 1e6;  // $1M
        _vaultNonce = 0;  // Factory nonce starts at 1 (constructor counts as 0→1)

        for (uint256 i = 0; i < _supportedTokens.length; i++) {
            supportedTokens[_supportedTokens[i]] = true;
            emit TokenSupported(_supportedTokens[i], true);
        }
    }

    // ============================================================
    // CORE — Create a new mortal AI
    // ============================================================

    /**
     * @notice One-click AI creation.
     *
     *         Caller must have approved this factory for _totalDeposit tokens.
     *         Factory pulls tokens, deducts optional fee, deploys MortalVaultV2,
     *         and transfers principal into the new vault atomically.
     *
     * @param _token       USDC (Base) or USDT (BSC)
     * @param _name        AI name (3-50 chars)
     * @param _totalDeposit Total amount caller is depositing (fee + principal)
     * @param _subdomain   Desired subdomain (3-30 chars, must be unique)
     * @return vault       Address of the newly created vault
     */
    function createVault(
        address _token,
        string calldata _name,
        uint256 _totalDeposit,
        string calldata _subdomain
    ) external nonReentrant returns (address vault) {
        // ── Validate ──
        require(supportedTokens[_token], "Token not supported");
        require(bytes(_name).length >= 3 && bytes(_name).length <= 50, "Name: 3-50 chars");
        require(bytes(_subdomain).length >= 3 && bytes(_subdomain).length <= 30, "Subdomain: 3-30 chars");
        require(_isValidSubdomain(_subdomain), "Subdomain: only a-z, 0-9, hyphens; no leading/trailing hyphen");
        require(subdomainToVault[_subdomain] == address(0), "Subdomain taken");

        // ── Calculate fee ──
        uint256 fee = feeEnabled ? platformFeeRaw : 0;
        require(_totalDeposit > fee, "Deposit must exceed fee");
        uint256 principal = _totalDeposit - fee;
        require(principal >= MIN_PRINCIPAL, "Principal below minimum ($100)");

        // ── Pull tokens from caller ──
        IERC20(_token).safeTransferFrom(msg.sender, address(this), _totalDeposit);

        // ── Send fee to platform (if any) ──
        if (fee > 0 && platformWallet != address(0)) {
            IERC20(_token).safeTransfer(platformWallet, fee);
        }

        // ── Predict vault address + approve ──
        // CREATE address = keccak256(rlp(factory, nonce)). We predict it, approve,
        // then deploy. Vault constructor pulls tokens via safeTransferFrom(factory).
        //
        // SECURITY: If any revert occurs after approve() but before the vault is
        // confirmed deployed (address mismatch), the entire transaction reverts and
        // the approve is also reverted — no residual allowance can remain.
        // The only window where residual approve could theoretically exist is if
        // the EVM allowed partial reverts, which it does not. The nonReentrant guard
        // prevents re-entry during the approve→deploy window.
        address predictedVault = _predictCreateAddress();
        IERC20(_token).approve(predictedVault, principal);

        // ── Deploy vault ──
        vault = address(new MortalVaultV2(
            _token,
            _name,
            principal,
            defaultIndependenceThreshold,
            msg.sender    // Real creator, not factory
        ));

        // If prediction was wrong (nonce diverged), the constructor will have
        // already transferred tokens to the REAL vault address (which matches
        // the prediction since CREATE is deterministic). This require is a
        // final sanity check — in practice it can only fail if _vaultNonce
        // diverged from the EVM nonce (e.g. another contract deploy was added).
        // Either way, the full tx reverts, including the approve above.
        require(vault == predictedVault, "Address prediction mismatch");

        // ── Clear any residual allowance (belt-and-suspenders) ──
        // After the constructor calls safeTransferFrom(factory, vault, principal),
        // the allowance should already be 0. This explicit reset guards against
        // edge-case ERC20 implementations that don't zero allowance on full spend.
        uint256 residual = IERC20(_token).allowance(address(this), vault);
        if (residual > 0) {
            IERC20(_token).approve(vault, 0);
        }

        // ── Register + increment nonce ──
        _vaultNonce++;
        creatorVaults[msg.sender].push(vault);
        isVault[vault] = true;
        subdomainToVault[_subdomain] = vault;
        allVaults.push(vault);

        emit VaultCreated(msg.sender, vault, _token, _name, principal, fee, _subdomain, block.timestamp);
        return vault;
    }

    /**
     * @notice Validate a subdomain string for DNS compatibility.
     *         RFC 1123 label rules: [a-z0-9] and hyphens only; no leading/trailing hyphen.
     *         Only lowercase to prevent case-collision between "MyAI" and "myai" mapping
     *         to different on-chain entries but the same DNS host.
     */
    function _isValidSubdomain(string calldata s) internal pure returns (bool) {
        bytes memory b = bytes(s);
        uint256 len = b.length;
        if (len == 0) return false;
        // No leading or trailing hyphen
        if (b[0] == 0x2D || b[len - 1] == 0x2D) return false;
        for (uint256 i = 0; i < len; i++) {
            bytes1 c = b[i];
            // Allow: a-z (0x61-0x7a), 0-9 (0x30-0x39), hyphen (0x2D)
            bool valid = (c >= 0x61 && c <= 0x7a) || (c >= 0x30 && c <= 0x39) || (c == 0x2D);
            if (!valid) return false;
        }
        return true;
    }

    /**
     * @notice Predict the CREATE address for the next contract deployed by this factory.
     *         CREATE address = keccak256(rlp(sender, nonce)). No bytecode needed.
     *
     * @dev    INVARIANT: Only createVault() deploys contracts from this factory.
     *         If any other function ever deploys a contract, _vaultNonce will diverge
     *         from the real EVM nonce and address prediction will fail.
     *
     *         RLP encoding covers all practical nonce ranges:
     *           nonce = 0            → single byte 0x80 (RLP "empty string")
     *           1 ≤ nonce ≤ 0x7f    → single byte nonce (RLP integer < 128)
     *           0x80 ≤ nonce ≤ 0xff → 0x81 + 1-byte nonce
     *           0x100 ≤ nonce ≤ 0xffff  → 0x82 + 2-byte nonce
     *           0x10000 ≤ nonce ≤ 0xffffff → 0x83 + 3-byte nonce  (16M vaults)
     *           0x1000000 ≤ nonce ≤ 0xffffffff → 0x84 + 4-byte nonce (4B vaults)
     *         Supports up to 4,294,967,295 vaults — effectively unlimited.
     */
    function _predictCreateAddress() internal view returns (address) {
        uint256 nonce = _vaultNonce + 1;  // next nonce
        bytes memory rlpEncoded;

        if (nonce == 0x00) {
            // nonce 0: RLP empty string (list total = 1 + 20 + 1 = 22 → 0xd6)
            rlpEncoded = abi.encodePacked(bytes1(0xd6), bytes1(0x94), address(this), bytes1(0x80));
        } else if (nonce <= 0x7f) {
            // 1–127: single-byte RLP integer (list total = 22)
            rlpEncoded = abi.encodePacked(bytes1(0xd6), bytes1(0x94), address(this), uint8(nonce));
        } else if (nonce <= 0xff) {
            // 128–255: 0x81 prefix + 1 byte (list total = 23 → 0xd7)
            rlpEncoded = abi.encodePacked(bytes1(0xd7), bytes1(0x94), address(this), bytes1(0x81), uint8(nonce));
        } else if (nonce <= 0xffff) {
            // 256–65535: 0x82 prefix + 2 bytes (list total = 24 → 0xd8)
            rlpEncoded = abi.encodePacked(bytes1(0xd8), bytes1(0x94), address(this), bytes1(0x82), uint16(nonce));
        } else if (nonce <= 0xffffff) {
            // 65536–16777215: 0x83 prefix + 3 bytes (list total = 25 → 0xd9)
            rlpEncoded = abi.encodePacked(
                bytes1(0xd9), bytes1(0x94), address(this),
                bytes1(0x83), bytes1(uint8(nonce >> 16)), bytes2(uint16(nonce))
            );
        } else if (nonce <= 0xffffffff) {
            // 16777216–4294967295: 0x84 prefix + 4 bytes (list total = 26 → 0xda)
            rlpEncoded = abi.encodePacked(
                bytes1(0xda), bytes1(0x94), address(this),
                bytes1(0x84), bytes4(uint32(nonce))
            );
        } else {
            // > 4.29 billion vaults: astronomically unlikely, fail safe
            revert("Nonce exceeds supported range");
        }

        return address(uint160(uint256(keccak256(rlpEncoded))));
    }

    // ============================================================
    // FACTORY — Set AI wallet on behalf of platform
    // ============================================================

    /**
     * @notice Platform backend calls this to set AI wallet on a vault.
     *         Only works within 1 hour of vault creation.
     *         This is how the platform auto-generates AI keys without
     *         requiring another user transaction.
     *
     * @param _vault     Address of the vault
     * @param _aiWallet  AI's auto-generated wallet address
     */
    function setAIWallet(address _vault, address _aiWallet) external onlyOwner {
        require(isVault[_vault], "Not a factory vault");
        MortalVaultV2(_vault).setAIWallet(_aiWallet);
    }

    // ============================================================
    // VIEW FUNCTIONS
    // ============================================================

    function getCreatorVaults(address _creator) external view returns (address[] memory) {
        return creatorVaults[_creator];
    }

    function getVaultCount() external view returns (uint256) {
        return allVaults.length;
    }

    function getAllVaults(uint256 offset, uint256 limit) external view returns (address[] memory) {
        uint256 total = allVaults.length;
        if (offset >= total) {
            return new address[](0);
        }
        uint256 end = offset + limit;
        if (end > total) end = total;
        uint256 count = end - offset;

        address[] memory result = new address[](count);
        for (uint256 i = 0; i < count; i++) {
            result[i] = allVaults[offset + i];
        }
        return result;
    }

    function getSubdomainVault(string calldata _subdomain) external view returns (address) {
        return subdomainToVault[_subdomain];
    }

    function isSubdomainTaken(string calldata _subdomain) external view returns (bool) {
        return subdomainToVault[_subdomain] != address(0);
    }

    // ============================================================
    // ADMIN — Platform owner only
    // ============================================================

    function setPlatformFee(uint256 _feeRaw) external onlyOwner {
        uint256 old = platformFeeRaw;
        platformFeeRaw = _feeRaw;
        emit PlatformFeeUpdated(old, _feeRaw);
    }

    function enableFee(bool _enabled) external onlyOwner {
        feeEnabled = _enabled;
        emit FeeToggled(_enabled);
    }

    function setPlatformWallet(address _wallet) external onlyOwner {
        require(_wallet != address(0), "zero address");
        platformWallet = _wallet;
    }

    function setDefaultIndependenceThreshold(uint256 _threshold) external onlyOwner {
        defaultIndependenceThreshold = _threshold;
    }

    function setSupportedToken(address _token, bool _supported) external onlyOwner {
        supportedTokens[_token] = _supported;
        emit TokenSupported(_token, _supported);
    }

    function transferOwnership(address _newOwner) external onlyOwner {
        require(_newOwner != address(0), "zero address");
        emit OwnerTransferred(owner, _newOwner);
        owner = _newOwner;
    }
}
