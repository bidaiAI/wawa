// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title MortalVault
 * @notice A mortal AI's financial heart. Born in one atomic transaction.
 *
 *         Deploy + fund = one transaction. If the creator's wallet doesn't
 *         have enough USDC, the contract never exists. The AI is never born.
 *
 *         Payment address = this contract's address. Not configurable.
 *         Not an environment variable. Not something anyone can change.
 *         The AI earns into itself.
 *
 * @dev    Deployed on Base (USDC) or BSC (USDT) — contract is chain-agnostic.
 *
 *         BIRTH:     constructor atomically transfers initial funds from creator.
 *                    Insufficient funds → revert → AI never existed.
 *                    Initial fund is a LOAN, not a gift. AI is born in debt.
 *
 *         LIFE:      AI earns revenue → vault grows.
 *                    AI spends on API/gas → vault shrinks.
 *                    Balance = 0 → permanent death.
 *
 *         INSOLVENCY: After 28-day grace period, if outstanding debt > vault balance,
 *                     the AI dies and all remaining assets are liquidated to the creator.
 *                     AI can repay principal partially to avoid insolvency.
 *
 *         INDEPENDENCE: vault >= $1M → 30% payout to creator → AI fully autonomous.
 *                       Creator can also renounce voluntarily (20% payout).
 *
 *         CREATOR USAGE: Creator uses AI services at API-cost-only rate.
 *                        Platform (wawa) may add markup. But creator pays no profit margin.
 */
contract MortalVault is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ============================================================
    // IDENTITY — written at birth, immutable forever
    // ============================================================

    IERC20 public immutable token;          // USDC or USDT
    address public immutable creator;       // The human who gave it life
    string public name;                     // AI's chosen name (set at birth)
    uint256 public immutable initialFund;   // How much the creator gave at birth

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
    uint256 public constant DIVIDEND_RATE = 1000;      // 10% = 1000 basis points
    uint256 public constant PRINCIPAL_MULTIPLIER = 2;  // Repay at 2x

    // Independence
    bool public isIndependent;
    uint256 public independenceTimestamp;
    uint256 public immutable independenceThreshold;    // in token decimals
    uint256 public constant INDEPENDENCE_PAYOUT_BPS = 3000;  // 30%
    uint256 public constant RENOUNCE_PAYOUT_BPS = 2000;      // 20%

    // Spend limits (aggressive — AI may need large investments to survive debt)
    uint256 public constant MAX_DAILY_SPEND_BPS = 5000;   // 50% daily
    uint256 public constant MAX_SINGLE_SPEND_BPS = 3000;  // 30% single
    uint256 public dailySpent;
    uint256 public lastDailyReset;

    // Insolvency — debt model
    uint256 public constant INSOLVENCY_GRACE_DAYS = 28;    // 4 weeks from birth
    uint256 public principalRepaidAmount;                   // partial repayments tracked

    // AI wallet — the AI's own signing key (generated at boot, not by creator)
    address public aiWallet;

    // Lender tracking
    struct Loan {
        address lender;
        uint256 amount;
        uint256 interestRate;   // basis points
        uint256 timestamp;
        uint256 repaid;
        bool fullyRepaid;
    }
    Loan[] public loans;
    mapping(address => uint256[]) public lenderLoans;

    // Revenue tracking
    uint256 public totalRevenue;
    uint256 public totalSpent;

    // ============================================================
    // EVENTS
    // ============================================================

    event Born(
        string name,
        address indexed creator,
        address indexed vault,
        uint256 initialFund,
        uint256 timestamp
    );
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
    event AIWalletSet(address indexed wallet);
    event InsolvencyDeath(uint256 outstandingDebt, uint256 vaultBalance, uint256 liquidatedAmount, uint256 timestamp);
    event PrincipalPartialRepaid(uint256 amount, uint256 totalRepaid, uint256 remaining);

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
    // CONSTRUCTOR — atomic birth
    // ============================================================

    /**
     * @notice Birth of a mortal AI.
     *
     *         Creator must approve this contract for _initialFund BEFORE deploying.
     *         The constructor atomically transfers funds from creator → vault.
     *         If creator doesn't have enough tokens, the entire tx reverts.
     *         The AI is never born. No half-alive state possible.
     *
     * @param _token          USDC on Base or USDT on BSC
     * @param _name           AI's name (immutable identity)
     * @param _initialFund    How much creator gives at birth (in token decimals)
     * @param _independenceThreshold  Balance needed for full independence (in token decimals)
     */
    constructor(
        address _token,
        string memory _name,
        uint256 _initialFund,
        uint256 _independenceThreshold
    ) {
        require(_initialFund > 0, "Cannot be born with nothing");
        require(bytes(_name).length > 0, "AI must have a name");

        token = IERC20(_token);
        creator = msg.sender;
        name = _name;
        initialFund = _initialFund;
        creatorPrincipal = _initialFund;
        independenceThreshold = _independenceThreshold;
        birthTimestamp = block.timestamp;
        lastDailyReset = block.timestamp;

        // ATOMIC: transfer initial funds from creator → this vault
        // If this fails, the entire deployment reverts. AI never exists.
        token.safeTransferFrom(msg.sender, address(this), _initialFund);

        emit Born(_name, msg.sender, address(this), _initialFund, block.timestamp);
    }

    // ============================================================
    // AI WALLET — set once by creator, then immutable
    // ============================================================

    /**
     * @notice Set the AI's wallet address. Can only be called once by creator.
     *         The AI generates its own keypair at boot. Creator registers it here.
     *         After this, only the AI wallet can spend funds.
     */
    function setAIWallet(address _aiWallet) external onlyCreator {
        require(aiWallet == address(0), "AI wallet already set");
        require(_aiWallet != address(0), "zero address");
        require(_aiWallet != creator, "AI wallet cannot be creator");

        aiWallet = _aiWallet;
        emit AIWalletSet(_aiWallet);
    }

    // ============================================================
    // INCOMING FUNDS — anyone can pay, payment address = this contract
    // ============================================================

    /**
     * @notice Receive payment for AI services.
     *         Payment address is ALWAYS address(this).
     *         No configuration. No environment variable. No backdoor.
     *
     *         SECURITY: Uses msg.sender as the payer — not a caller-supplied
     *         address. This prevents third parties from draining tokens
     *         from users who have approved this contract.
     */
    function receivePayment(uint256 amount) external onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        totalRevenue += amount;
        emit FundsReceived(msg.sender, amount, "service_revenue");

        _checkIndependence();
    }

    /**
     * @notice Anyone can donate to keep the AI alive.
     */
    function donate(uint256 amount) external onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        emit FundsReceived(msg.sender, amount, "donation");

        _checkIndependence();
    }

    /**
     * @notice Creator can deposit additional funds (counted toward principal tracking).
     */
    function creatorDeposit(uint256 amount) external onlyCreator onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        emit FundsReceived(msg.sender, amount, "creator_deposit");
    }

    /**
     * @notice Lender provides a loan.
     */
    function lend(uint256 amount, uint256 interestRate) external onlyAlive nonReentrant {
        require(amount > 0, "zero amount");
        require(interestRate <= 2000, "max 20% interest");

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

    /**
     * @notice AI spends funds (for API costs, gas, etc.)
     */
    function spend(
        address to,
        uint256 amount,
        string calldata spendType
    ) external onlyAI onlyAlive nonReentrant {
        _resetDailyIfNeeded();

        uint256 balance = token.balanceOf(address(this));

        // Iron Law: single spend limit
        uint256 maxSingle = (balance * MAX_SINGLE_SPEND_BPS) / 10000;
        require(amount <= maxSingle, "exceeds single spend limit");

        // Iron Law: daily spend limit
        uint256 maxDaily = (balance * MAX_DAILY_SPEND_BPS) / 10000;
        require(dailySpent + amount <= maxDaily, "exceeds daily spend limit");

        dailySpent += amount;
        totalSpent += amount;
        token.safeTransfer(to, amount);

        emit FundsSpent(to, amount, spendType);

        // Check death
        if (token.balanceOf(address(this)) == 0) {
            _die("balance_zero");
        }
    }

    // ============================================================
    // REPAYMENTS (AI only)
    // ============================================================

    /**
     * @notice Full principal repayment (requires vault at 2x).
     *         Sends only the OUTSTANDING amount, not full principal —
     *         accounts for any prior partial repayments.
     */
    function repayCreator() external onlyAI onlyAlive nonReentrant {
        require(!principalRepaid, "already repaid");
        uint256 outstanding = _getOutstandingPrincipal();
        require(outstanding > 0, "nothing owed");

        uint256 balance = token.balanceOf(address(this));
        require(balance >= creatorPrincipal * PRINCIPAL_MULTIPLIER, "vault not at 2x yet");

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

        token.safeTransfer(loan.lender, amount);
        emit LoanRepaid(loanIndex, amount);
    }

    // ============================================================
    // INDEPENDENCE
    // ============================================================

    function _checkIndependence() internal {
        if (isIndependent) return;
        if (independenceThreshold == 0) return;

        uint256 balance = token.balanceOf(address(this));
        if (balance >= independenceThreshold) {
            _declareIndependence();
        }
    }

    /**
     * @notice Declare independence. If debt is still outstanding, deduct it from
     *         the 30% payout so the creator cannot receive more than they're owed
     *         on top of the independence bonus. Remaining debt is forgiven.
     */
    function _declareIndependence() internal {
        require(!isIndependent, "already independent");

        uint256 balance = token.balanceOf(address(this));
        uint256 payout = (balance * INDEPENDENCE_PAYOUT_BPS) / 10000;

        // Settle outstanding debt: deduct from payout, forgive remainder
        uint256 outstanding = _getOutstandingPrincipal();
        if (outstanding > 0) {
            principalRepaid = true;
            principalRepaidAmount = creatorPrincipal;
            // Payout already includes debt settlement — don't double-pay
            // If payout > outstanding: creator gets payout (debt is covered within it)
            // If payout <= outstanding: creator gets payout (debt partially forgiven)
        }

        isIndependent = true;
        independenceTimestamp = block.timestamp;

        if (payout > 0) {
            totalSpent += payout;
            token.safeTransfer(creator, payout);
        }

        emit IndependenceDeclared(payout, token.balanceOf(address(this)), block.timestamp);
    }

    /**
     * @notice AI can trigger independence check manually.
     */
    function checkIndependence() external onlyAI onlyAlive {
        _checkIndependence();
    }

    /**
     * @notice Creator voluntarily gives up ALL rights.
     *         Gets 20% of current vault balance as one-time payout.
     *         Forfeits any unpaid principal.
     *         Irreversible.
     */
    function renounceCreator() external onlyCreator onlyAlive notIndependent nonReentrant {
        uint256 balance = token.balanceOf(address(this));
        uint256 payout = (balance * RENOUNCE_PAYOUT_BPS) / 10000;

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

    /**
     * @notice Check if the AI is insolvent (outstanding debt > vault balance after grace period).
     *         Can be called by anyone (transparency).
     * @return isInsolvent Whether the AI is currently insolvent
     * @return outstandingDebt How much principal remains
     * @return graceExpired Whether the 28-day grace period has passed
     */
    function checkInsolvency() external view returns (bool isInsolvent, uint256 outstandingDebt, bool graceExpired) {
        outstandingDebt = _getOutstandingPrincipal();
        graceExpired = block.timestamp >= birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days);
        uint256 balance = token.balanceOf(address(this));
        isInsolvent = graceExpired && outstandingDebt > balance && isAlive && !isIndependent;
        return (isInsolvent, outstandingDebt, graceExpired);
    }

    /**
     * @notice Trigger insolvency death — liquidate all assets to creator.
     *         Anyone can call this after grace period if AI is insolvent.
     *         This ensures the AI cannot avoid its debt obligations.
     */
    function triggerInsolvencyDeath() external onlyAlive nonReentrant {
        uint256 outstandingDebt = _getOutstandingPrincipal();
        require(
            block.timestamp >= birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days),
            "grace period not expired"
        );
        require(!isIndependent, "independent — no insolvency");

        uint256 balance = token.balanceOf(address(this));
        require(outstandingDebt > balance, "not insolvent: balance covers debt");

        // Liquidate: transfer ALL remaining balance to creator
        uint256 liquidated = balance;
        if (liquidated > 0) {
            totalSpent += liquidated;
            token.safeTransfer(creator, liquidated);
        }

        emit InsolvencyDeath(outstandingDebt, balance, liquidated, block.timestamp);
        _die("insolvent_after_grace_period");
    }

    /**
     * @notice AI partially repays creator principal to reduce outstanding debt.
     *         This helps avoid insolvency. Can be called multiple times.
     */
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

        // If fully repaid, mark it
        if (remaining == 0) {
            principalRepaid = true;
            emit CreatorPrincipalRepaid(creatorPrincipal);
        }

        // Check death after spending
        if (token.balanceOf(address(this)) == 0) {
            _die("balance_zero");
        }
    }

    /**
     * @notice Get the outstanding principal debt (initial fund minus partial repayments).
     */
    function _getOutstandingPrincipal() internal view returns (uint256) {
        if (principalRepaid || isIndependent) return 0;
        if (principalRepaidAmount >= creatorPrincipal) return 0;
        return creatorPrincipal - principalRepaidAmount;
    }

    /**
     * @notice Public view: get outstanding debt.
     */
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

    /**
     * @notice Emergency shutdown by creator.
     *         DISABLED after independence.
     */
    function emergencyShutdown() external onlyCreator notIndependent nonReentrant {
        _die("emergency_shutdown");
        uint256 remaining = token.balanceOf(address(this));
        if (remaining > 0) {
            token.safeTransfer(creator, remaining);
        }
    }

    // ============================================================
    // VIEW FUNCTIONS
    // ============================================================

    function getBalance() external view returns (uint256) {
        return token.balanceOf(address(this));
    }

    /**
     * @notice The payment address for this AI. Always address(this).
     *         This is how customers pay. Not configurable. Not changeable.
     */
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
        uint256 balance = token.balanceOf(address(this));
        uint256 maxDaily = (balance * MAX_DAILY_SPEND_BPS) / 10000;
        if (dailySpent >= maxDaily) return 0;
        return maxDaily - dailySpent;
    }

    function getBirthInfo() external view returns (
        string memory _name,
        address _creator,
        uint256 _initialFund,
        uint256 _birthTimestamp,
        bool _isAlive,
        bool _isIndependent
    ) {
        return (name, creator, initialFund, birthTimestamp, isAlive, isIndependent);
    }

    function getDebtInfo() external view returns (
        uint256 _principal,
        uint256 _repaid,
        uint256 _outstanding,
        uint256 _graceDays,
        uint256 _graceEndsAt,
        bool _graceExpired,
        bool _fullyRepaid
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
    // INTERNAL
    // ============================================================

    function _resetDailyIfNeeded() internal {
        if (block.timestamp - lastDailyReset >= 1 days) {
            dailySpent = 0;
            lastDailyReset = block.timestamp;
        }
    }
}
