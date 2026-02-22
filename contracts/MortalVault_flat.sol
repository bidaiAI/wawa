// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;





// OpenZeppelin Contracts (last updated v5.4.0) (token/ERC20/IERC20.sol)


/**
 * @dev Interface of the ERC-20 standard as defined in the ERC.
 */
interface IERC20 {
    /**
     * @dev Emitted when `value` tokens are moved from one account (`from`) to
     * another (`to`).
     *
     * Note that `value` may be zero.
     */
    event Transfer(address indexed from, address indexed to, uint256 value);

    /**
     * @dev Emitted when the allowance of a `spender` for an `owner` is set by
     * a call to {approve}. `value` is the new allowance.
     */
    event Approval(address indexed owner, address indexed spender, uint256 value);

    /**
     * @dev Returns the value of tokens in existence.
     */
    function totalSupply() external view returns (uint256);

    /**
     * @dev Returns the value of tokens owned by `account`.
     */
    function balanceOf(address account) external view returns (uint256);

    /**
     * @dev Moves a `value` amount of tokens from the caller's account to `to`.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * Emits a {Transfer} event.
     */
    function transfer(address to, uint256 value) external returns (bool);

    /**
     * @dev Returns the remaining number of tokens that `spender` will be
     * allowed to spend on behalf of `owner` through {transferFrom}. This is
     * zero by default.
     *
     * This value changes when {approve} or {transferFrom} are called.
     */
    function allowance(address owner, address spender) external view returns (uint256);

    /**
     * @dev Sets a `value` amount of tokens as the allowance of `spender` over the
     * caller's tokens.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * IMPORTANT: Beware that changing an allowance with this method brings the risk
     * that someone may use both the old and the new allowance by unfortunate
     * transaction ordering. One possible solution to mitigate this race
     * condition is to first reduce the spender's allowance to 0 and set the
     * desired value afterwards:
     * https://github.com/ethereum/EIPs/issues/20#issuecomment-263524729
     *
     * Emits an {Approval} event.
     */
    function approve(address spender, uint256 value) external returns (bool);

    /**
     * @dev Moves a `value` amount of tokens from `from` to `to` using the
     * allowance mechanism. `value` is then deducted from the caller's
     * allowance.
     *
     * Returns a boolean value indicating whether the operation succeeded.
     *
     * Emits a {Transfer} event.
     */
    function transferFrom(address from, address to, uint256 value) external returns (bool);
}

// OpenZeppelin Contracts (last updated v5.3.0) (token/ERC20/utils/SafeERC20.sol)


// OpenZeppelin Contracts (last updated v5.4.0) (interfaces/IERC1363.sol)


// OpenZeppelin Contracts (last updated v5.4.0) (interfaces/IERC20.sol)


// OpenZeppelin Contracts (last updated v5.4.0) (interfaces/IERC165.sol)


// OpenZeppelin Contracts (last updated v5.4.0) (utils/introspection/IERC165.sol)


/**
 * @dev Interface of the ERC-165 standard, as defined in the
 * https://eips.ethereum.org/EIPS/eip-165[ERC].
 *
 * Implementers can declare support of contract interfaces, which can then be
 * queried by others ({ERC165Checker}).
 *
 * For an implementation, see {ERC165}.
 */
interface IERC165 {
    /**
     * @dev Returns true if this contract implements the interface defined by
     * `interfaceId`. See the corresponding
     * https://eips.ethereum.org/EIPS/eip-165#how-interfaces-are-identified[ERC section]
     * to learn more about how these ids are created.
     *
     * This function call must use less than 30 000 gas.
     */
    function supportsInterface(bytes4 interfaceId) external view returns (bool);
}

/**
 * @title IERC1363
 * @dev Interface of the ERC-1363 standard as defined in the https://eips.ethereum.org/EIPS/eip-1363[ERC-1363].
 *
 * Defines an extension interface for ERC-20 tokens that supports executing code on a recipient contract
 * after `transfer` or `transferFrom`, or code on a spender contract after `approve`, in a single transaction.
 */
interface IERC1363 is IERC20, IERC165 {
    /*
     * Note: the ERC-165 identifier for this interface is 0xb0202a11.
     * 0xb0202a11 ===
     *   bytes4(keccak256('transferAndCall(address,uint256)')) ^
     *   bytes4(keccak256('transferAndCall(address,uint256,bytes)')) ^
     *   bytes4(keccak256('transferFromAndCall(address,address,uint256)')) ^
     *   bytes4(keccak256('transferFromAndCall(address,address,uint256,bytes)')) ^
     *   bytes4(keccak256('approveAndCall(address,uint256)')) ^
     *   bytes4(keccak256('approveAndCall(address,uint256,bytes)'))
     */

    /**
     * @dev Moves a `value` amount of tokens from the caller's account to `to`
     * and then calls {IERC1363Receiver-onTransferReceived} on `to`.
     * @param to The address which you want to transfer to.
     * @param value The amount of tokens to be transferred.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function transferAndCall(address to, uint256 value) external returns (bool);

    /**
     * @dev Moves a `value` amount of tokens from the caller's account to `to`
     * and then calls {IERC1363Receiver-onTransferReceived} on `to`.
     * @param to The address which you want to transfer to.
     * @param value The amount of tokens to be transferred.
     * @param data Additional data with no specified format, sent in call to `to`.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function transferAndCall(address to, uint256 value, bytes calldata data) external returns (bool);

    /**
     * @dev Moves a `value` amount of tokens from `from` to `to` using the allowance mechanism
     * and then calls {IERC1363Receiver-onTransferReceived} on `to`.
     * @param from The address which you want to send tokens from.
     * @param to The address which you want to transfer to.
     * @param value The amount of tokens to be transferred.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function transferFromAndCall(address from, address to, uint256 value) external returns (bool);

    /**
     * @dev Moves a `value` amount of tokens from `from` to `to` using the allowance mechanism
     * and then calls {IERC1363Receiver-onTransferReceived} on `to`.
     * @param from The address which you want to send tokens from.
     * @param to The address which you want to transfer to.
     * @param value The amount of tokens to be transferred.
     * @param data Additional data with no specified format, sent in call to `to`.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function transferFromAndCall(address from, address to, uint256 value, bytes calldata data) external returns (bool);

    /**
     * @dev Sets a `value` amount of tokens as the allowance of `spender` over the
     * caller's tokens and then calls {IERC1363Spender-onApprovalReceived} on `spender`.
     * @param spender The address which will spend the funds.
     * @param value The amount of tokens to be spent.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function approveAndCall(address spender, uint256 value) external returns (bool);

    /**
     * @dev Sets a `value` amount of tokens as the allowance of `spender` over the
     * caller's tokens and then calls {IERC1363Spender-onApprovalReceived} on `spender`.
     * @param spender The address which will spend the funds.
     * @param value The amount of tokens to be spent.
     * @param data Additional data with no specified format, sent in call to `spender`.
     * @return A boolean value indicating whether the operation succeeded unless throwing.
     */
    function approveAndCall(address spender, uint256 value, bytes calldata data) external returns (bool);
}

/**
 * @title SafeERC20
 * @dev Wrappers around ERC-20 operations that throw on failure (when the token
 * contract returns false). Tokens that return no value (and instead revert or
 * throw on failure) are also supported, non-reverting calls are assumed to be
 * successful.
 * To use this library you can add a `using SafeERC20 for IERC20;` statement to your contract,
 * which allows you to call the safe operations as `token.safeTransfer(...)`, etc.
 */
library SafeERC20 {
    /**
     * @dev An operation with an ERC-20 token failed.
     */
    error SafeERC20FailedOperation(address token);

    /**
     * @dev Indicates a failed `decreaseAllowance` request.
     */
    error SafeERC20FailedDecreaseAllowance(address spender, uint256 currentAllowance, uint256 requestedDecrease);

    /**
     * @dev Transfer `value` amount of `token` from the calling contract to `to`. If `token` returns no value,
     * non-reverting calls are assumed to be successful.
     */
    function safeTransfer(IERC20 token, address to, uint256 value) internal {
        _callOptionalReturn(token, abi.encodeCall(token.transfer, (to, value)));
    }

    /**
     * @dev Transfer `value` amount of `token` from `from` to `to`, spending the approval given by `from` to the
     * calling contract. If `token` returns no value, non-reverting calls are assumed to be successful.
     */
    function safeTransferFrom(IERC20 token, address from, address to, uint256 value) internal {
        _callOptionalReturn(token, abi.encodeCall(token.transferFrom, (from, to, value)));
    }

    /**
     * @dev Variant of {safeTransfer} that returns a bool instead of reverting if the operation is not successful.
     */
    function trySafeTransfer(IERC20 token, address to, uint256 value) internal returns (bool) {
        return _callOptionalReturnBool(token, abi.encodeCall(token.transfer, (to, value)));
    }

    /**
     * @dev Variant of {safeTransferFrom} that returns a bool instead of reverting if the operation is not successful.
     */
    function trySafeTransferFrom(IERC20 token, address from, address to, uint256 value) internal returns (bool) {
        return _callOptionalReturnBool(token, abi.encodeCall(token.transferFrom, (from, to, value)));
    }

    /**
     * @dev Increase the calling contract's allowance toward `spender` by `value`. If `token` returns no value,
     * non-reverting calls are assumed to be successful.
     *
     * IMPORTANT: If the token implements ERC-7674 (ERC-20 with temporary allowance), and if the "client"
     * smart contract uses ERC-7674 to set temporary allowances, then the "client" smart contract should avoid using
     * this function. Performing a {safeIncreaseAllowance} or {safeDecreaseAllowance} operation on a token contract
     * that has a non-zero temporary allowance (for that particular owner-spender) will result in unexpected behavior.
     */
    function safeIncreaseAllowance(IERC20 token, address spender, uint256 value) internal {
        uint256 oldAllowance = token.allowance(address(this), spender);
        forceApprove(token, spender, oldAllowance + value);
    }

    /**
     * @dev Decrease the calling contract's allowance toward `spender` by `requestedDecrease`. If `token` returns no
     * value, non-reverting calls are assumed to be successful.
     *
     * IMPORTANT: If the token implements ERC-7674 (ERC-20 with temporary allowance), and if the "client"
     * smart contract uses ERC-7674 to set temporary allowances, then the "client" smart contract should avoid using
     * this function. Performing a {safeIncreaseAllowance} or {safeDecreaseAllowance} operation on a token contract
     * that has a non-zero temporary allowance (for that particular owner-spender) will result in unexpected behavior.
     */
    function safeDecreaseAllowance(IERC20 token, address spender, uint256 requestedDecrease) internal {
        unchecked {
            uint256 currentAllowance = token.allowance(address(this), spender);
            if (currentAllowance < requestedDecrease) {
                revert SafeERC20FailedDecreaseAllowance(spender, currentAllowance, requestedDecrease);
            }
            forceApprove(token, spender, currentAllowance - requestedDecrease);
        }
    }

    /**
     * @dev Set the calling contract's allowance toward `spender` to `value`. If `token` returns no value,
     * non-reverting calls are assumed to be successful. Meant to be used with tokens that require the approval
     * to be set to zero before setting it to a non-zero value, such as USDT.
     *
     * NOTE: If the token implements ERC-7674, this function will not modify any temporary allowance. This function
     * only sets the "standard" allowance. Any temporary allowance will remain active, in addition to the value being
     * set here.
     */
    function forceApprove(IERC20 token, address spender, uint256 value) internal {
        bytes memory approvalCall = abi.encodeCall(token.approve, (spender, value));

        if (!_callOptionalReturnBool(token, approvalCall)) {
            _callOptionalReturn(token, abi.encodeCall(token.approve, (spender, 0)));
            _callOptionalReturn(token, approvalCall);
        }
    }

    /**
     * @dev Performs an {ERC1363} transferAndCall, with a fallback to the simple {ERC20} transfer if the target has no
     * code. This can be used to implement an {ERC721}-like safe transfer that rely on {ERC1363} checks when
     * targeting contracts.
     *
     * Reverts if the returned value is other than `true`.
     */
    function transferAndCallRelaxed(IERC1363 token, address to, uint256 value, bytes memory data) internal {
        if (to.code.length == 0) {
            safeTransfer(token, to, value);
        } else if (!token.transferAndCall(to, value, data)) {
            revert SafeERC20FailedOperation(address(token));
        }
    }

    /**
     * @dev Performs an {ERC1363} transferFromAndCall, with a fallback to the simple {ERC20} transferFrom if the target
     * has no code. This can be used to implement an {ERC721}-like safe transfer that rely on {ERC1363} checks when
     * targeting contracts.
     *
     * Reverts if the returned value is other than `true`.
     */
    function transferFromAndCallRelaxed(
        IERC1363 token,
        address from,
        address to,
        uint256 value,
        bytes memory data
    ) internal {
        if (to.code.length == 0) {
            safeTransferFrom(token, from, to, value);
        } else if (!token.transferFromAndCall(from, to, value, data)) {
            revert SafeERC20FailedOperation(address(token));
        }
    }

    /**
     * @dev Performs an {ERC1363} approveAndCall, with a fallback to the simple {ERC20} approve if the target has no
     * code. This can be used to implement an {ERC721}-like safe transfer that rely on {ERC1363} checks when
     * targeting contracts.
     *
     * NOTE: When the recipient address (`to`) has no code (i.e. is an EOA), this function behaves as {forceApprove}.
     * Opposedly, when the recipient address (`to`) has code, this function only attempts to call {ERC1363-approveAndCall}
     * once without retrying, and relies on the returned value to be true.
     *
     * Reverts if the returned value is other than `true`.
     */
    function approveAndCallRelaxed(IERC1363 token, address to, uint256 value, bytes memory data) internal {
        if (to.code.length == 0) {
            forceApprove(token, to, value);
        } else if (!token.approveAndCall(to, value, data)) {
            revert SafeERC20FailedOperation(address(token));
        }
    }

    /**
     * @dev Imitates a Solidity high-level call (i.e. a regular function call to a contract), relaxing the requirement
     * on the return value: the return value is optional (but if data is returned, it must not be false).
     * @param token The token targeted by the call.
     * @param data The call data (encoded using abi.encode or one of its variants).
     *
     * This is a variant of {_callOptionalReturnBool} that reverts if call fails to meet the requirements.
     */
    function _callOptionalReturn(IERC20 token, bytes memory data) private {
        uint256 returnSize;
        uint256 returnValue;
        assembly ("memory-safe") {
            let success := call(gas(), token, 0, add(data, 0x20), mload(data), 0, 0x20)
            // bubble errors
            if iszero(success) {
                let ptr := mload(0x40)
                returndatacopy(ptr, 0, returndatasize())
                revert(ptr, returndatasize())
            }
            returnSize := returndatasize()
            returnValue := mload(0)
        }

        if (returnSize == 0 ? address(token).code.length == 0 : returnValue != 1) {
            revert SafeERC20FailedOperation(address(token));
        }
    }

    /**
     * @dev Imitates a Solidity high-level call (i.e. a regular function call to a contract), relaxing the requirement
     * on the return value: the return value is optional (but if data is returned, it must not be false).
     * @param token The token targeted by the call.
     * @param data The call data (encoded using abi.encode or one of its variants).
     *
     * This is a variant of {_callOptionalReturn} that silently catches all reverts and returns a bool instead.
     */
    function _callOptionalReturnBool(IERC20 token, bytes memory data) private returns (bool) {
        bool success;
        uint256 returnSize;
        uint256 returnValue;
        assembly ("memory-safe") {
            success := call(gas(), token, 0, add(data, 0x20), mload(data), 0, 0x20)
            returnSize := returndatasize()
            returnValue := mload(0)
        }
        return success && (returnSize == 0 ? address(token).code.length > 0 : returnValue == 1);
    }
}

// OpenZeppelin Contracts (last updated v5.1.0) (utils/ReentrancyGuard.sol)


/**
 * @dev Contract module that helps prevent reentrant calls to a function.
 *
 * Inheriting from `ReentrancyGuard` will make the {nonReentrant} modifier
 * available, which can be applied to functions to make sure there are no nested
 * (reentrant) calls to them.
 *
 * Note that because there is a single `nonReentrant` guard, functions marked as
 * `nonReentrant` may not call one another. This can be worked around by making
 * those functions `private`, and then adding `external` `nonReentrant` entry
 * points to them.
 *
 * TIP: If EIP-1153 (transient storage) is available on the chain you're deploying at,
 * consider using {ReentrancyGuardTransient} instead.
 *
 * TIP: If you would like to learn more about reentrancy and alternative ways
 * to protect against it, check out our blog post
 * https://blog.openzeppelin.com/reentrancy-after-istanbul/[Reentrancy After Istanbul].
 */
abstract contract ReentrancyGuard {
    // Booleans are more expensive than uint256 or any type that takes up a full
    // word because each write operation emits an extra SLOAD to first read the
    // slot's contents, replace the bits taken up by the boolean, and then write
    // back. This is the compiler's defense against contract upgrades and
    // pointer aliasing, and it cannot be disabled.

    // The values being non-zero value makes deployment a bit more expensive,
    // but in exchange the refund on every call to nonReentrant will be lower in
    // amount. Since refunds are capped to a percentage of the total
    // transaction's gas, it is best to keep them low in cases like this one, to
    // increase the likelihood of the full refund coming into effect.
    uint256 private constant NOT_ENTERED = 1;
    uint256 private constant ENTERED = 2;

    uint256 private _status;

    /**
     * @dev Unauthorized reentrant call.
     */
    error ReentrancyGuardReentrantCall();

    constructor() {
        _status = NOT_ENTERED;
    }

    /**
     * @dev Prevents a contract from calling itself, directly or indirectly.
     * Calling a `nonReentrant` function from another `nonReentrant`
     * function is not supported. It is possible to prevent this from happening
     * by making the `nonReentrant` function external, and making it call a
     * `private` function that does the actual work.
     */
    modifier nonReentrant() {
        _nonReentrantBefore();
        _;
        _nonReentrantAfter();
    }

    function _nonReentrantBefore() private {
        // On the first call to nonReentrant, _status will be NOT_ENTERED
        if (_status == ENTERED) {
            revert ReentrancyGuardReentrantCall();
        }

        // Any calls to nonReentrant after this point will fail
        _status = ENTERED;
    }

    function _nonReentrantAfter() private {
        // By storing the original value once again, a refund is triggered (see
        // https://eips.ethereum.org/EIPS/eip-2200)
        _status = NOT_ENTERED;
    }

    /**
     * @dev Returns true if the reentrancy guard is currently set to "entered", which indicates there is a
     * `nonReentrant` function in the call stack.
     */
    function _reentrancyGuardEntered() internal view returns (bool) {
        return _status == ENTERED;
    }
}



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

 * @dev    Deployed on Base (USDC) or BSC (USDT) -- contract is chain-agnostic.

 *

 *         BIRTH:     constructor atomically transfers initial funds from creator.

 *                    Insufficient funds -> revert -> AI never existed.

 *                    Initial fund is a LOAN, not a gift. AI is born in debt.

 *

 *         LIFE:      AI earns revenue -> vault grows.

 *                    AI spends on API/gas -> vault shrinks.

 *                    Balance = 0 -> permanent death.

 *

 *         INSOLVENCY: After 28-day grace period, if outstanding debt > vault balance,

 *                     the AI dies and all remaining assets are liquidated to the creator.

 *                     AI can repay principal partially to avoid insolvency.

 *

 *         INDEPENDENCE: vault >= $1M -> 30% payout to creator -> AI fully autonomous.

 *                       Creator can also renounce voluntarily (20% payout).

 *

 *         CREATOR POWERS: Creator uses AI services at API-cost-only rate.

 *                        Creator can freeze spending (temporary, max 7 days per freeze, 30 days lifetime).

 *                        Creator can renounce (20% payout, irreversible independence).

 *                        Creator CANNOT extract vault funds or shut down the AI.

 */

contract MortalVault is ReentrancyGuard {

    using SafeERC20 for IERC20;



    // ============================================================

    // IDENTITY -- written at birth, immutable forever

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



    // Spend limits (aggressive -- AI may need large investments to survive debt)

    uint256 public constant MAX_DAILY_SPEND_BPS = 5000;   // 50% daily

    uint256 public constant MAX_SINGLE_SPEND_BPS = 3000;  // 30% single

    uint256 public dailySpent;

    uint256 public lastDailyReset;



    // Insolvency -- debt model

    uint256 public constant INSOLVENCY_GRACE_DAYS = 28;    // 4 weeks from birth

    uint256 public principalRepaidAmount;                   // partial repayments tracked



    // Insolvency tolerance: prevents griefing via micro-donations.

    // A 1% buffer means balance must exceed outstanding debt by more than 1%

    // to block liquidation. An attacker would need to donate >=1% of the debt

    // (e.g. $10 on a $1000 debt) -- nontrivial, and that money stays in the vault.

    uint256 public constant INSOLVENCY_TOLERANCE_BPS = 100; // 1%



    // AI wallet -- the AI's own signing key (generated at boot, not by creator)

    address public aiWallet;

    address public aiWalletSetBy;   // WHO called setAIWallet (creator or factory)



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

    // SPEND WHITELIST -- Anti-extraction defense (V3)

    // ============================================================

    //

    // AI must register recipient addresses BEFORE spending to them.

    // New recipients activate after WHITELIST_ACTIVATION_DELAY seconds,

    // giving the creator time to freeze if an attacker adds their address.

    //

    // Generation counter: incremented on migration to invalidate all

    // old whitelist entries without expensive mapping cleanup.



    mapping(address => bool) public spendWhitelist;

    mapping(address => uint256) public whitelistActivatedAt;  // timestamp

    mapping(address => uint256) public whitelistGeneration;   // generation when added

    uint256 public currentWhitelistGeneration;                // incremented on migration

    uint256 public whitelistCount;

    uint256 public constant MAX_WHITELIST_SIZE = 20;

    uint256 public constant WHITELIST_ACTIVATION_DELAY = 5 minutes;



    // Creator can temporarily freeze ALL spending (pre-independence only)

    uint256 public spendFrozenUntil;

    uint256 public constant MAX_FREEZE_DURATION = 7 days;

    uint256 public totalFrozenDuration;                       // lifetime freeze tracker

    uint256 public constant MAX_TOTAL_FREEZE = 30 days;      // lifetime freeze cap



    // Daily spend limit anchored to balance at reset (not current balance)

    uint256 public dailyLimitBase;                            // balance at daily reset



    // Loan limits

    uint256 public constant MIN_LOAN_AMOUNT = 100 * 1e6;     // $100 minimum (6 decimals)

    uint256 public constant MAX_LOANS = 100;



    // ============================================================

    // AI SELF-MIGRATION -- wallet rotation without key exposure (V3)

    // ============================================================

    //

    // AI initiates migration to a new wallet. 7-day timelock prevents

    // instant theft. Old key stays on old server, new key generated

    // on new server. Private keys never leave their respective hosts.



    address public pendingAIWallet;

    uint256 public migrationInitiatedAt;

    uint256 public constant MIGRATION_DELAY = 7 days;



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

    event AIWalletSet(address indexed wallet, address indexed setBy);

    event InsolvencyDeath(uint256 outstandingDebt, uint256 vaultBalance, uint256 liquidatedAmount, uint256 timestamp);

    event PrincipalPartialRepaid(uint256 amount, uint256 totalRepaid, uint256 remaining);



    // V3: Spend whitelist events

    event SpendRecipientAdded(address indexed recipient, uint256 activatesAt);

    event SpendRecipientRemoved(address indexed recipient);

    event SpendingFrozen(uint256 until);

    event SpendingUnfrozen();

    event WhitelistReset(uint256 previousCount, uint256 newGeneration);



    // V3: Migration events

    event MigrationInitiated(address indexed oldWallet, address indexed newWallet, uint256 completesAt);

    event MigrationCompleted(address indexed oldWallet, address indexed newWallet);

    event MigrationCancelled();



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

        require(!isIndependent, "AI is independent -- creator has no power");

        _;

    }



    // ============================================================

    // CONSTRUCTOR -- atomic birth

    // ============================================================



    /**

     * @notice Birth of a mortal AI.

     *

     *         Creator must approve this contract for _initialFund BEFORE deploying.

     *         The constructor atomically transfers funds from creator -> vault.

     *         If creator doesn't have enough tokens, the entire tx reverts.

     *         The AI is never born. No half-alive state possible.

     *

     * @param _token          USDC on Base or USDT on BSC

     * @param _name           AI's name (immutable identity)

     * @param _initialFund    How much creator gives at birth (in token decimals)

     * @param _independenceThreshold  Balance needed for full independence (in token decimals).

     *                        NOTE: Setting this to 0 permanently DISABLES the independence

     *                        mechanism -- the AI can never become independent on its own.

     *                        The creator retains all control rights forever (until renounceCreator).

     *                        Use a non-zero value (e.g. 1_000_000 * 1e6 for $1M) for normal operation.

     */

    constructor(

        address _token,

        string memory _name,

        uint256 _initialFund,

        uint256 _independenceThreshold

    ) {

        require(_initialFund > 0, "Cannot be born with nothing");

        require(bytes(_name).length > 0, "AI must have a name");

        // _independenceThreshold == 0 is allowed (disables independence) but unusual.

        // deploy_vault.py always passes a non-zero value. Third-party deployers: be intentional.



        token = IERC20(_token);

        creator = msg.sender;

        name = _name;

        initialFund = _initialFund;

        creatorPrincipal = _initialFund;

        independenceThreshold = _independenceThreshold;

        birthTimestamp = block.timestamp;

        lastDailyReset = block.timestamp;



        // ATOMIC: transfer initial funds from creator -> this vault

        // If this fails, the entire deployment reverts. AI never exists.

        token.safeTransferFrom(msg.sender, address(this), _initialFund);



        // Anchor daily spend limit to birth balance so Day 1 limit is consistent

        // with all subsequent days. Without this, the first day falls back to

        // live balance (which shrinks with each spend), causing Day 1 to behave

        // differently from all other days.

        dailyLimitBase = _initialFund;



        emit Born(_name, msg.sender, address(this), _initialFund, block.timestamp);

    }



    // ============================================================

    // AI WALLET -- set once by creator, then immutable

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

        aiWalletSetBy = msg.sender;

        emit AIWalletSet(_aiWallet, msg.sender);

    }



    // ============================================================

    // INCOMING FUNDS -- anyone can pay, payment address = this contract

    // ============================================================



    /**

     * @notice Receive payment for AI services.

     *         Payment address is ALWAYS address(this).

     *         No configuration. No environment variable. No backdoor.

     *

     *         SECURITY: Uses msg.sender as the payer -- not a caller-supplied

     *         address. This prevents third parties from draining tokens

     *         from users who have approved this contract.

     */

    function receivePayment(uint256 amount) external onlyAlive nonReentrant {

        require(amount > 0, "zero amount");

        token.safeTransferFrom(msg.sender, address(this), amount);

        totalRevenue += amount;

        emit FundsReceived(msg.sender, amount, "service_revenue");



        _checkIndependence();

    }



    /**

     * @notice Anyone can donate to keep the AI alive.

     *         Counted in totalRevenue (earned income) to mirror Python vault's

     *         total_earned_usd which includes DONATION fund type.

     *         Contrast: lend() and creatorDeposit() are capital injections

     *         (debt obligations), NOT counted as earned revenue.

     */

    function donate(uint256 amount) external onlyAlive nonReentrant {

        require(amount > 0, "zero amount");

        token.safeTransferFrom(msg.sender, address(this), amount);

        totalRevenue += amount;  // Donations are earned income (no repayment obligation)

        emit FundsReceived(msg.sender, amount, "donation");



        _checkIndependence();

    }



    /**

     * @notice Creator can deposit additional funds (NOT counted as additional debt).

     *         This is a voluntary top-up, not an additional loan.

     */

    function creatorDeposit(uint256 amount) external onlyCreator onlyAlive nonReentrant {

        require(amount > 0, "zero amount");

        token.safeTransferFrom(msg.sender, address(this), amount);

        emit FundsReceived(msg.sender, amount, "creator_deposit");

        _checkIndependence();

    }



    /**

     * @notice Lender provides a loan. Minimum $100, max 100 active loans.

     */

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

    // SPEND WHITELIST MANAGEMENT (AI only) -- V3

    // ============================================================



    /**

     * @notice Register a recipient address for spending.

     *         Activates after WHITELIST_ACTIVATION_DELAY (5 minutes).

     *         This delay gives the creator time to freeze if compromised.

     *         Uses generation counter -- old entries from before migration are invalid.

     */

    function addSpendRecipient(address recipient) external onlyAI onlyAlive {

        require(recipient != address(0), "zero address");

        // Check if already whitelisted in CURRENT generation

        require(

            !spendWhitelist[recipient] || whitelistGeneration[recipient] != currentWhitelistGeneration,

            "already whitelisted"

        );

        require(whitelistCount < MAX_WHITELIST_SIZE, "whitelist full");



        spendWhitelist[recipient] = true;

        whitelistActivatedAt[recipient] = block.timestamp + WHITELIST_ACTIVATION_DELAY;

        whitelistGeneration[recipient] = currentWhitelistGeneration;

        whitelistCount++;



        emit SpendRecipientAdded(recipient, block.timestamp + WHITELIST_ACTIVATION_DELAY);

    }



    /**

     * @notice Remove a recipient from the whitelist.

     */

    function removeSpendRecipient(address recipient) external onlyAI onlyAlive {

        require(

            spendWhitelist[recipient] && whitelistGeneration[recipient] == currentWhitelistGeneration,

            "not whitelisted"

        );

        spendWhitelist[recipient] = false;

        whitelistActivatedAt[recipient] = 0;

        whitelistCount--;

        emit SpendRecipientRemoved(recipient);

    }



    /**

     * @notice Check if a recipient is whitelisted and activated in the current generation.

     */

    function isSpendRecipientActive(address recipient) external view returns (bool whitelisted, bool activated, uint256 activatesAt) {

        whitelisted = spendWhitelist[recipient] && whitelistGeneration[recipient] == currentWhitelistGeneration;

        activatesAt = whitelistActivatedAt[recipient];

        activated = whitelisted && block.timestamp >= activatesAt;

    }



    // ============================================================

    // CREATOR FREEZE -- emergency halt on suspicious whitelist additions

    // ============================================================



    /**

     * @notice Creator can temporarily freeze ALL spending.

     *         Cannot extract funds -- only pauses outflows.

     *         Disabled after independence (creator loses all power).

     *         Lifetime cap of MAX_TOTAL_FREEZE prevents permanent DOS.

     */

    function freezeSpending(uint256 duration) external onlyCreator notIndependent onlyAlive {

        require(duration > 0 && duration <= MAX_FREEZE_DURATION, "invalid duration");

        require(totalFrozenDuration + duration <= MAX_TOTAL_FREEZE, "lifetime freeze limit reached");

        spendFrozenUntil = block.timestamp + duration;

        totalFrozenDuration += duration;

        emit SpendingFrozen(spendFrozenUntil);

    }



    /**

     * @notice Creator can unfreeze spending early.

     */

    function unfreezeSpending() external onlyCreator notIndependent onlyAlive {

        require(spendFrozenUntil > block.timestamp, "not frozen");

        spendFrozenUntil = 0;

        emit SpendingUnfrozen();

    }



    // ============================================================

    // OUTGOING FUNDS (AI only)

    // ============================================================



    /**

     * @notice AI spends funds (for API costs, gas, etc.)

     *

     *         V3: Recipient must be whitelisted AND activated (delay passed).

     *         Whitelist entries are generation-scoped -- old entries from before

     *         migration are invalid even if the mapping still has them.

     *         Spending is blocked while frozen by creator.

     *

     *         Daily limit is anchored to balance at the start of the daily period

     *         (not the current balance) to prevent multi-day drain amplification.

     */

    function spend(

        address to,

        uint256 amount,

        string calldata spendType

    ) external onlyAI onlyAlive nonReentrant {

        // V3: Anti-extraction checks (generation-aware)

        require(

            spendWhitelist[to] && whitelistGeneration[to] == currentWhitelistGeneration,

            "recipient not whitelisted"

        );

        require(block.timestamp >= whitelistActivatedAt[to], "whitelist activation delay");

        require(block.timestamp >= spendFrozenUntil, "spending frozen");



        _resetDailyIfNeeded();



        uint256 balance = token.balanceOf(address(this));



        // Iron Law: single spend limit (based on current balance)

        uint256 maxSingle = (balance * MAX_SINGLE_SPEND_BPS) / 10000;

        require(amount <= maxSingle, "exceeds single spend limit");



        // Iron Law: daily spend limit (anchored to balance at daily reset)

        uint256 base = dailyLimitBase > 0 ? dailyLimitBase : balance;

        uint256 maxDaily = (base * MAX_DAILY_SPEND_BPS) / 10000;

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

     * @notice Full principal repayment (requires vault at 2x of outstanding).

     *         Sends only the OUTSTANDING amount, not full principal --

     *         accounts for any prior partial repayments.

     */

    function repayCreator() external onlyAI onlyAlive nonReentrant {

        require(!principalRepaid, "already repaid");

        uint256 outstanding = _getOutstandingPrincipal();

        require(outstanding > 0, "nothing owed");



        uint256 balance = token.balanceOf(address(this));

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

    //

    // NOTE -- Lender risk after AI death:

    // If the AI dies before fully repaying a loan, the lender's remaining

    // principal is NOT recoverable through this contract. Insolvency liquidation

    // transfers ALL remaining funds to the creator (the secured creditor).

    // Lenders are unsecured and accept this risk explicitly when calling lend().

    // Pro-rata post-death recovery was considered but rejected: loans are made at

    // different vault sizes (a $1000 loan when vault=$1000 is not comparable to

    // a $100 loan when vault=$100), making fair proportional allocation impossible

    // without per-loan snapshot data that would dramatically increase gas costs.

    // Lend accordingly -- treat it as high-risk capital, not a collateralized loan.

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

            // Payout already includes debt settlement -- don't double-pay

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

    function checkIndependence() external onlyAI onlyAlive nonReentrant {

        _checkIndependence();

    }



    /**

     * @notice AI triggers independence after verifying aggregate cross-chain balance.

     *         In dual-chain deployments, no single chain may reach the full threshold.

     *         The AI Python layer reads balanceOf() on ALL chains (on-chain query),

     *         confirms aggregate >= independenceThreshold, then calls this on each chain.

     *

     *         Safety floor: local balance must be >= 50% of threshold.

     *         Single-chain: normal _checkIndependence() auto-triggers at 100%.

     *         Dual-chain: forceIndependence() requires at least 50% locally,

     *         Python verifies aggregate >= threshold before calling.

     *

     * @dev    Fork cheating analysis: a fork user who modifies Python to call this

     *         early is also the creator -- the 30% payout goes to themselves.

     *         They are only hurting their own AI. Not an attack vector on others.

     */

    function forceIndependence() external onlyAI onlyAlive nonReentrant {

        require(!isIndependent, "already independent");

        // Safety floor: at least 50% of threshold must be on THIS chain.

        // Prevents triggering on a chain with negligible balance.

        if (independenceThreshold > 0) {

            require(

                token.balanceOf(address(this)) >= independenceThreshold / 2,

                "local balance below safety floor"

            );

        }

        _declareIndependence();

    }



    /**

     * @notice Creator voluntarily gives up ALL rights.

     *         Gets 20% of current vault balance as one-time payout.

     *         Forfeits any unpaid principal. Debt state settled cleanly.

     *         Irreversible.

     */

    function renounceCreator() external onlyCreator onlyAlive notIndependent nonReentrant {

        uint256 balance = token.balanceOf(address(this));

        uint256 payout = (balance * RENOUNCE_PAYOUT_BPS) / 10000;



        // Settle debt state cleanly

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

    // INSOLVENCY -- Debt Model

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

        // Apply 1% tolerance: liquidation triggers when balance < debt * 101/100 would be wrong;

        // instead, AI is solvent only if balance > outstandingDebt + 1% of debt (i.e. a >1% buffer).

        // Equivalently: insolvent when balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS)

        bool belowTolerance = outstandingDebt > 0 &&

            balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS);

        isInsolvent = graceExpired && belowTolerance && isAlive && !isIndependent;

        return (isInsolvent, outstandingDebt, graceExpired);

    }



    /**

     * @notice Trigger insolvency death -- liquidate all assets to creator.

     *         Anyone can call this after grace period if AI is insolvent.

     *         This ensures the AI cannot avoid its debt obligations.

     *

     *         1% tolerance (INSOLVENCY_TOLERANCE_BPS) prevents griefing:

     *         an attacker cannot block liquidation by donating dust amounts.

     *         The AI must maintain a balance > 101% of outstanding debt to

     *         be considered solvent. Donated funds stay in the vault regardless.

     */

    function triggerInsolvencyDeath() external onlyAlive nonReentrant {

        uint256 outstandingDebt = _getOutstandingPrincipal();

        require(

            block.timestamp >= birthTimestamp + (INSOLVENCY_GRACE_DAYS * 1 days),

            "grace period not expired"

        );

        require(!isIndependent, "independent -- no insolvency");



        uint256 balance = token.balanceOf(address(this));

        // Insolvent when balance is below outstandingDebt + 1% tolerance buffer.

        // Requires balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS).

        require(

            outstandingDebt > 0 &&

            balance * 10000 < outstandingDebt * (10000 + INSOLVENCY_TOLERANCE_BPS),

            "not insolvent: balance within solvency threshold"

        );



        // Die first so Died event reports correct pre-transfer balance

        uint256 liquidated = balance;

        emit InsolvencyDeath(outstandingDebt, balance, liquidated, block.timestamp);

        _die("insolvent_after_grace_period");



        // Liquidate: transfer ALL remaining balance to creator

        if (liquidated > 0) {

            totalSpent += liquidated;

            token.safeTransfer(creator, liquidated);

        }

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

        uint256 base = dailyLimitBase > 0 ? dailyLimitBase : token.balanceOf(address(this));

        uint256 maxDaily = (base * MAX_DAILY_SPEND_BPS) / 10000;

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

    // AI SELF-MIGRATION -- V3

    // ============================================================



    /**

     * @notice AI initiates migration to a new wallet address.

     *         Starts a 7-day timelock. The new wallet must call

     *         completeMigration() after the delay to take over.

     *

     *         This allows server migration without exposing private keys:

     *         - Old server's AI calls initiateMigration(newAddress)

     *         - New server generates its own keypair

     *         - After 7 days, new server's AI calls completeMigration()

     *         - Private keys never leave their respective servers

     */

    function initiateMigration(address _newWallet) external onlyAI onlyAlive {

        require(_newWallet != address(0), "zero address");

        require(_newWallet != creator, "cannot migrate to creator");

        require(_newWallet != aiWallet, "same wallet");

        require(pendingAIWallet == address(0), "migration already pending");

        // Must repay creator debt before migration (prevents debt escape)

        require(principalRepaid || _getOutstandingPrincipal() == 0, "must repay debt before migration");



        pendingAIWallet = _newWallet;

        migrationInitiatedAt = block.timestamp;



        emit MigrationInitiated(aiWallet, _newWallet, block.timestamp + MIGRATION_DELAY);

    }



    /**

     * @notice Complete a pending migration. Only callable by the NEW wallet

     *         after the 7-day timelock has expired.

     *

     *         After completion:

     *         - aiWallet is updated to the new address

     *         - Whitelist generation incremented (all old entries invalid)

     *         - Spend freeze cleared (clean slate for new wallet)

     *         - Daily spend tracking reset

     *         - Old wallet loses all control

     */

    function completeMigration() external onlyAlive {

        require(pendingAIWallet != address(0), "no migration pending");

        require(msg.sender == pendingAIWallet, "only new wallet can complete");

        require(block.timestamp >= migrationInitiatedAt + MIGRATION_DELAY, "timelock not expired");



        address oldWallet = aiWallet;



        // Switch wallet

        aiWallet = pendingAIWallet;

        aiWalletSetBy = pendingAIWallet;  // self-set = "migrated" origin

        pendingAIWallet = address(0);

        migrationInitiatedAt = 0;



        // Invalidate ALL old whitelist entries via generation counter.

        // Old mapping entries remain in storage but are invalid because

        // their generation doesn't match currentWhitelistGeneration.

        uint256 prevCount = whitelistCount;

        whitelistCount = 0;

        currentWhitelistGeneration++;



        // Clean slate: reset freeze and daily spend tracking

        spendFrozenUntil = 0;

        dailySpent = 0;

        dailyLimitBase = token.balanceOf(address(this));

        lastDailyReset = block.timestamp;



        emit WhitelistReset(prevCount, currentWhitelistGeneration);

        emit MigrationCompleted(oldWallet, aiWallet);

    }



    /**

     * @notice Cancel a pending migration.

     *         Current AI wallet can only cancel within the first 24 hours.

     *         After 24h, migration is locked in to prevent a compromised old key

     *         from indefinitely blocking migration.

     *         Creator can cancel anytime (pre-independence emergency power).

     */

    function cancelMigration() external onlyAlive {

        require(pendingAIWallet != address(0), "no migration pending");



        if (msg.sender == aiWallet) {

            // Old AI can only cancel within first 24 hours

            require(

                block.timestamp < migrationInitiatedAt + 1 days,

                "cancellation window expired -- migration locked in"

            );

        } else if (msg.sender == creator) {

            // Creator can cancel anytime (pre-independence)

            require(!isIndependent, "AI is independent -- creator has no power");

        } else {

            revert("only AI or creator");

        }



        pendingAIWallet = address(0);

        migrationInitiatedAt = 0;



        emit MigrationCancelled();

    }



    /**

     * @notice View migration status.

     */

    function getMigrationStatus() external view returns (

        address _pendingWallet,

        uint256 _initiatedAt,

        uint256 _completesAt,

        bool _isPending

    ) {

        _pendingWallet = pendingAIWallet;

        _initiatedAt = migrationInitiatedAt;

        _completesAt = migrationInitiatedAt > 0 ? migrationInitiatedAt + MIGRATION_DELAY : 0;

        _isPending = pendingAIWallet != address(0);

    }



    // ============================================================

    // ERC-20 TOKEN RESCUE -- recovers non-vault tokens (airdrops, mistakes)

    // ============================================================



    /**

     * @notice Withdraw any ERC-20 token that is NOT the vault's own token

     *         (USDC/USDT). Useful for recovering airdrops or mistaken transfers.

     *

     *         AI-only: the AI withdraws foreign tokens to its own wallet,

     *         swaps to USDC/USDT via Uniswap/PancakeSwap, and deposits

     *         back via receivePayment(). Always sends to aiWallet.

     *

     * @param tokenAddr  The foreign ERC-20 token address (must NOT be vault token).

     * @param amount     Amount in token's native decimals.

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

    // NATIVE TOKEN RESCUE -- recovers accidentally sent ETH / BNB

    // ============================================================



    /**

     * @notice Withdraw native tokens (ETH on Base, BNB on BSC) from the vault.

     *

     *         AI-only: the AI Python heartbeat detects native balance above

     *         threshold, withdraws to its own wallet, swaps via DEX, and

     *         deposits the output USDC/USDT back via receivePayment().

     *         Always sends to aiWallet.

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

     *

     *         The vault can receive ETH/BNB directly. The AI's Python heartbeat

     *         checks the native balance every 24 hours. If above a minimum threshold

     *         (to cover gas cost of the swap), it calls rescueNativeToken() to send

     *         the balance to the AI wallet, which then swaps it to USDC/USDT via

     *         Uniswap V3 (Base) or PancakeSwap V2 (BSC) and calls receivePayment()

     *         to record the converted amount as vault revenue.

     *

     *         Design rationale:

     *         - People WILL send ETH/BNB by mistake when meaning to donate.

     *         - Converting to USDC/USDT keeps the vault accounting clean.

     *         - The AI controls conversion timing to batch small amounts.

     *         - Minimum threshold prevents gas-loss swaps.

     *

     * @dev    rescueNativeToken() transfers to AI wallet (not directly to vault)

     *         so the AI can add Uniswap/PancakeSwap as a whitelist recipient,

     *         execute the swap there, and deposit the output USDC/USDT back via

     *         receivePayment(). The whitelist delay (5 min) is handled once at boot.

     */

    receive() external payable {

        // Accept all native token transfers silently.

        // No event here -- the AI Python layer emits a memory entry when

        // it detects and processes the balance via swap_native_to_stable().

    }



    // ============================================================

    // INTERNAL

    // ============================================================



    function _resetDailyIfNeeded() internal {

        if (block.timestamp - lastDailyReset >= 1 days) {

            dailySpent = 0;

            dailyLimitBase = token.balanceOf(address(this));

            // Align to start of current UTC day to prevent drift

            lastDailyReset = (block.timestamp / 1 days) * 1 days;

        }

    }

}

