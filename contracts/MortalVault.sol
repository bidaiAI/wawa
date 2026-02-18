// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";

/**
 * @title MortalVault
 * @notice Autonomous AI survival vault. The AI earns money to stay alive.
 *         Balance reaches 0 = permanent death. No backdoors.
 *
 * @dev Deployed on Base (USDC)
 *      Creator: single, receives principal back + 5% dividend
 *      Lenders: multiple, FIFO repayment with interest
 *      Donors: direct transfers, no return
 *      Customers: pay for AI services via OrderSystem
 */
contract MortalVault is ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ============================================================
    // STATE
    // ============================================================

    IERC20 public immutable token;        // USDC on Base
    address public immutable creator;
    address public immutable aiWallet;    // AI-controlled wallet

    bool public isAlive = true;
    uint256 public birthTimestamp;
    uint256 public deathTimestamp;

    // Creator economics
    uint256 public creatorPrincipal;
    bool public principalRepaid;
    uint256 public totalDividendsPaid;
    uint256 public constant DIVIDEND_RATE = 500;       // 5% = 500 basis points
    uint256 public constant PRINCIPAL_MULTIPLIER = 2;  // Repay at 2x

    // Vault limits
    uint256 public constant MAX_DAILY_SPEND_BPS = 500;    // 5% daily
    uint256 public constant MAX_SINGLE_SPEND_BPS = 200;   // 2% single
    uint256 public dailySpent;
    uint256 public lastDailyReset;

    // Lender tracking
    struct Loan {
        address lender;
        uint256 amount;
        uint256 interestRate;    // basis points (e.g., 500 = 5%)
        uint256 timestamp;
        uint256 repaid;
        bool fullyRepaid;
    }
    Loan[] public loans;
    mapping(address => uint256[]) public lenderLoans;  // lender -> loan indices

    // Revenue tracking
    uint256 public totalRevenue;
    uint256 public totalSpent;

    // ============================================================
    // EVENTS
    // ============================================================

    event Born(address indexed creator, uint256 principal, uint256 timestamp);
    event Died(uint256 finalBalance, uint256 timestamp, string cause);
    event FundsReceived(address indexed from, uint256 amount, string fundType);
    event FundsSpent(address indexed to, uint256 amount, string spendType);
    event LoanCreated(address indexed lender, uint256 amount, uint256 interestRate, uint256 loanIndex);
    event LoanRepaid(uint256 indexed loanIndex, uint256 amount);
    event CreatorPrincipalRepaid(uint256 amount);
    event CreatorDividendPaid(uint256 amount);
    event SurvivalModeEntered(uint256 balance);

    // ============================================================
    // MODIFIERS
    // ============================================================

    modifier onlyAlive() {
        require(isAlive, "wawa is dead");
        _;
    }

    modifier onlyAI() {
        require(msg.sender == aiWallet, "only AI can call this");
        _;
    }

    modifier onlyCreator() {
        require(msg.sender == creator, "only creator");
        _;
    }

    // ============================================================
    // CONSTRUCTOR
    // ============================================================

    constructor(
        address _token,      // USDC address on Base
        address _creator,
        address _aiWallet,
        uint256 _principal
    ) {
        token = IERC20(_token);
        creator = _creator;
        aiWallet = _aiWallet;
        creatorPrincipal = _principal;
        birthTimestamp = block.timestamp;
        lastDailyReset = block.timestamp;

        emit Born(_creator, _principal, block.timestamp);
    }

    // ============================================================
    // INCOMING FUNDS
    // ============================================================

    /**
     * @notice Creator deposits initial capital
     */
    function depositPrincipal(uint256 amount) external onlyCreator onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        emit FundsReceived(msg.sender, amount, "creator_deposit");
    }

    /**
     * @notice Lender provides a loan
     */
    function lend(uint256 amount, uint256 interestRate) external onlyAlive nonReentrant {
        require(amount > 0, "zero amount");
        require(interestRate <= 2000, "max 20% interest");  // cap at 20%

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

    /**
     * @notice Anyone can donate (no function call needed for plain transfers,
     *         but this provides explicit tracking)
     */
    function donate(uint256 amount) external onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(msg.sender, address(this), amount);
        emit FundsReceived(msg.sender, amount, "donation");
    }

    /**
     * @notice Receive payment for AI services (called by OrderSystem)
     */
    function receivePayment(uint256 amount, address customer) external onlyAlive {
        require(amount > 0, "zero amount");
        token.safeTransferFrom(customer, address(this), amount);
        totalRevenue += amount;
        emit FundsReceived(customer, amount, "service_revenue");
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
     * @notice Repay creator's principal (only when vault >= 2x principal)
     */
    function repayCreator() external onlyAI onlyAlive nonReentrant {
        require(!principalRepaid, "already repaid");

        uint256 balance = token.balanceOf(address(this));
        require(balance >= creatorPrincipal * PRINCIPAL_MULTIPLIER, "vault not at 2x yet");

        principalRepaid = true;
        token.safeTransfer(creator, creatorPrincipal);

        emit CreatorPrincipalRepaid(creatorPrincipal);
    }

    /**
     * @notice Pay creator dividend (5% of net profit per period)
     */
    function payDividend(uint256 netProfit) external onlyAI onlyAlive nonReentrant {
        require(principalRepaid, "principal not yet repaid");
        require(netProfit > 0, "no profit");

        uint256 dividend = (netProfit * DIVIDEND_RATE) / 10000;
        uint256 balance = token.balanceOf(address(this));
        require(dividend <= balance / 10, "dividend too large relative to balance");

        totalDividendsPaid += dividend;
        token.safeTransfer(creator, dividend);

        emit CreatorDividendPaid(dividend);
    }

    /**
     * @notice Repay a lender (FIFO order enforced off-chain)
     */
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
    // DEATH
    // ============================================================

    function _die(string memory cause) internal {
        isAlive = false;
        deathTimestamp = block.timestamp;
        emit Died(token.balanceOf(address(this)), block.timestamp, cause);
    }

    /**
     * @notice Emergency shutdown by creator (e.g., critical bug found)
     *         Remaining funds go to creator. This is the ONLY backdoor
     *         and it kills the AI permanently.
     */
    function emergencyShutdown() external onlyCreator {
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

    function getDailyRemaining() external view returns (uint256) {
        _checkDailyReset();
        uint256 balance = token.balanceOf(address(this));
        uint256 maxDaily = (balance * MAX_DAILY_SPEND_BPS) / 10000;
        if (dailySpent >= maxDaily) return 0;
        return maxDaily - dailySpent;
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

    function _checkDailyReset() internal view {
        // View-only version for getDailyRemaining
        // Actual reset happens in _resetDailyIfNeeded
    }

    /**
     * @notice Accept direct USDC transfers as donations
     *         (ERC20 tokens don't trigger receive/fallback, so this is
     *          handled by monitoring Transfer events to this address)
     */
}
