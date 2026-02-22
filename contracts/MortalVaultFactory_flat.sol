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





// ============================================================


// MortalVaultV2 -- Factory-deployable version


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


    // IDENTITY -- written at birth, immutable forever


    // ============================================================





    IERC20 public token;


    address public creator;                    // NOT immutable -- set from constructor param


    address public immutable factory;          // The factory that deployed this vault


    string public name;


    uint256 public initialFund;





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


    uint256 public independenceThreshold;


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


        require(!isIndependent, "AI is independent -- creator has no power");


        _;


    }





    // ============================================================


    // CONSTRUCTOR -- factory birth


    // ============================================================





    /**


     * @notice Birth of a mortal AI via factory.


     *


     *         The factory deploys this vault via CREATE2 with salt = keccak256(creator, name).


     *         To ensure IDENTICAL vault addresses across chains (Base, BSC, etc.), the


     *         constructor must produce the same initcode hash on every chain.


     *


     *         Chain-specific values (_token, _initialFund, _independenceThreshold) differ


     *         across chains (different token addresses, different stablecoin decimals).


     *         Including them in the constructor would produce different initcodeHash and


     *         thus different CREATE2 addresses. To ensure cross-chain address equality,


     *         the constructor receives only chain-invariant params (_name, _creator).


     *         Chain-specific values are set via initialize() immediately after deployment.


     *


     *         The factory calls initialize() in the same transaction as CREATE2 deploy,


     *         so atomicity is preserved (either both succeed or both revert).


     *


     * @param _name     AI's name -- immutable identity, same on every chain


     * @param _creator  The real creator/investor (NOT msg.sender which is the factory)


     */


    constructor(


        string memory _name,


        address _creator


    ) {


        require(bytes(_name).length > 0, "AI must have a name");


        require(_creator != address(0), "Invalid creator");





        factory = msg.sender;


        creator = _creator;


        name = _name;


        // Chain-specific params are set by initialize()


    }





    /**


     * @notice Initialize chain-specific vault parameters and fund the vault.


     *


     *         Called by the factory in the same transaction as CREATE2 deployment.


     *         Can only be called ONCE (guarded by birthTimestamp == 0).


     *         Factory must have approved this vault for _initialFund tokens before calling.


     *


     * @param _token                  Stablecoin on this chain (USDC on Base, USDT on BSC)


     * @param _initialFund            Principal in token decimals (this is a LOAN)


     * @param _independenceThreshold  Token-denominated balance for full independence


     */


    function initialize(


        address _token,


        uint256 _initialFund,


        uint256 _independenceThreshold


    ) external {


        require(msg.sender == factory, "only factory");


        require(birthTimestamp == 0, "already initialized");


        require(_initialFund > 0, "Cannot be born with nothing");


        require(_token != address(0), "zero token address");





        token = IERC20(_token);


        initialFund = _initialFund;


        creatorPrincipal = _initialFund;


        independenceThreshold = _independenceThreshold;


        birthTimestamp = block.timestamp;


        lastDailyReset = block.timestamp;


        dailyLimitBase = _initialFund;





        // Factory pushes tokens to vault (safeTransfer, no approve needed)


        token.safeTransferFrom(msg.sender, address(this), _initialFund);





        emit Born(name, creator, address(this), _initialFund, block.timestamp);


    }





    // ============================================================


    // AI WALLET -- set by creator or factory (within 1 hour)


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


     *         Sends only the OUTSTANDING amount -- accounts for prior partial repayments.


     *         Uses outstanding (not creatorPrincipal) as the 2x base so that partial


     *         repayments lower the required vault balance proportionally.


     */


    function repayCreator() external onlyAI onlyAlive nonReentrant {


        require(!principalRepaid, "already repaid");


        uint256 outstanding = _getOutstandingPrincipal();


        require(outstanding > 0, "nothing owed");





        uint256 balance = token.balanceOf(address(this));


        // Threshold: 2x the REMAINING outstanding debt (not original principal).


        // Matches V1 behavior -- partial repayments lower the required balance.


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


    // NOTE -- Lender risk after AI death: same as V1. See MortalVault.sol for details.





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





        // Settle outstanding debt -- forgiven at independence


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


    // INSOLVENCY -- Debt Model


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


        require(!isIndependent, "independent -- no insolvency");





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


    // ERC-20 TOKEN RESCUE -- recovers non-vault tokens (airdrops, mistakes)


    // ============================================================





    /**


     * @notice Withdraw any ERC-20 token that is NOT the vault's own token.


     *         AI-only: always sends to aiWallet for DEX swap -> receivePayment().


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


    // NATIVE TOKEN RESCUE -- recovers accidentally sent ETH / BNB


    // ============================================================





    /**


     * @notice Withdraw native tokens (ETH on Base, BNB on BSC) from the vault.


     *         AI-only: always sends to aiWallet for DEX swap -> receivePayment().


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


     *         Same design as MortalVault V1 -- see receive() comment there.


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


// VAULT FACTORY -- One-click deployment for mortal AIs


// ============================================================


//


// Users call createVault() from the frontend with MetaMask.


// Factory deploys MortalVaultV2 with the user as creator.


// Platform backend listens for VaultCreated events -> spawns containers.


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


    mapping(string => address) public subdomainToVault;  // subdomain -> vault (uniqueness)


    address[] public allVaults;





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


     * Token support is added post-deployment via addSupportedToken() to keep bytecode chain-invariant.


     */


    constructor(


        address _platformWallet


    ) {


        owner = tx.origin;  // tx.origin = actual deployer even when called via DDP proxy


        platformWallet = _platformWallet;


        feeEnabled = false;


        platformFeeRaw = 0;


        defaultIndependenceThreshold = 1_000_000 * 1e6;  // $1M


    }





    // ============================================================


    // CORE -- Create a new mortal AI


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


        // -- Validate --


        require(supportedTokens[_token], "Token not supported");


        require(bytes(_name).length >= 3 && bytes(_name).length <= 50, "Name: 3-50 chars");


        require(bytes(_subdomain).length >= 3 && bytes(_subdomain).length <= 30, "Subdomain: 3-30 chars");


        require(_isValidSubdomain(_subdomain), "Subdomain: only a-z, 0-9, hyphens; no leading/trailing hyphen");


        require(subdomainToVault[_subdomain] == address(0), "Subdomain taken");





        // -- Calculate fee --


        uint256 fee = feeEnabled ? platformFeeRaw : 0;


        require(_totalDeposit > fee, "Deposit must exceed fee");


        uint256 principal = _totalDeposit - fee;


        require(principal >= MIN_PRINCIPAL, "Principal below minimum ($100)");





        // -- Pull tokens from caller --


        IERC20(_token).safeTransferFrom(msg.sender, address(this), _totalDeposit);





        // -- Send fee to platform (if any) --


        if (fee > 0 && platformWallet != address(0)) {


            IERC20(_token).safeTransfer(platformWallet, fee);


        }





        // -- Compute CREATE2 salt --


        // Salt = keccak256(creator ++ name). Same creator + same name -> same vault


        // address on every EVM chain where this factory is deployed at the same address.


        // This enables cross-chain address equivalence: a donor can send to the same


        // vault address on Base or BSC and reach the correct AI's vault on either chain.


        bytes32 salt = keccak256(abi.encode(msg.sender, _name));





        // -- Deploy vault via CREATE2 --


        // Constructor receives only chain-invariant params (_name, creator).


        // Chain-specific values (token, principal, threshold) go into initialize()


        // so that the initcodeHash -- and therefore the CREATE2 address -- is


        // IDENTICAL on Base and BSC for the same creator + same name.


        vault = address(new MortalVaultV2{salt: salt}(


            _name,


            msg.sender    // Real creator, not factory


        ));





        // -- Initialize and fund vault (same transaction -- atomic) --


        // Factory approves itself to the vault so initialize() can pull tokens.


        // This is safe: factory holds the tokens, vault is factory-deployed,


        // and initialize() can only be called once (guarded by birthTimestamp == 0).


        IERC20(_token).approve(vault, principal);


        MortalVaultV2(payable(vault)).initialize(


            _token,


            principal,


            defaultIndependenceThreshold


        );





        // Clear any residual allowance (should be 0 after initialize pulls exactly principal)


        uint256 residual = IERC20(_token).allowance(address(this), vault);


        if (residual > 0) {


            IERC20(_token).approve(vault, 0);


        }





        // -- Verify vault received funds (belt-and-suspenders) --


        require(


            IERC20(_token).balanceOf(vault) >= principal,


            "Vault funding failed"


        );





        // -- Register --


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


     * @notice Predict vault address for a given creator + name.


     *


     * @dev    CREATE2 formula:


     *           addr = keccak256(0xff ++ factory ++ salt ++ keccak256(initcode))[12:]


     *


     *         initcode = type(MortalVaultV2).creationCode ++ abi.encode(_name, _creator)


     *


     *         Only chain-invariant params (_name, _creator) are in the constructor,


     *         so the vault address is IDENTICAL on every chain for the same creator + name.


     *         Token, principal, and independence threshold are set via initialize() and


     *         do NOT affect the vault address.


     *


     *         Called by deploy_vault.py and the frontend to display the vault address before


     *         the user signs the createVault transaction.


     *


     * @param _creator  Creator wallet address


     * @param _name     AI name (same string as createVault _name param)


     */


    function predictVaultAddress(


        address _creator,


        string calldata _name


    ) external view returns (address) {


        bytes32 salt = keccak256(abi.encode(_creator, _name));


        bytes memory initcode = abi.encodePacked(


            type(MortalVaultV2).creationCode,


            abi.encode(_name, _creator)


        );


        bytes32 initcodeHash = keccak256(initcode);


        return address(uint160(uint256(keccak256(abi.encodePacked(


            bytes1(0xff),


            address(this),


            salt,


            initcodeHash


        )))));


    }





    // ============================================================


    // FACTORY -- Set AI wallet on behalf of platform


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


        MortalVaultV2(payable(_vault)).setAIWallet(_aiWallet);


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


    // ADMIN -- Platform owner only


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


