/**
 * VaultFactory ABI — only the functions the frontend needs.
 *
 * Full contract: contracts/MortalVaultFactory.sol
 * The frontend calls: createVault, getCreatorVaults, isSubdomainTaken
 * The frontend reads: feeEnabled, platformFeeRaw, getVaultCount, MIN_PRINCIPAL
 */

export const FACTORY_ABI = [
  // ── Core ──
  {
    name: 'createVault',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [
      { name: '_token', type: 'address' },
      { name: '_name', type: 'string' },
      { name: '_totalDeposit', type: 'uint256' },
      { name: '_subdomain', type: 'string' },
    ],
    outputs: [{ name: 'vault', type: 'address' }],
  },

  // ── Views ──
  {
    name: 'getCreatorVaults',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: '_creator', type: 'address' }],
    outputs: [{ name: '', type: 'address[]' }],
  },
  {
    name: 'getVaultCount',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'getAllVaults',
    type: 'function',
    stateMutability: 'view',
    inputs: [
      { name: 'offset', type: 'uint256' },
      { name: 'limit', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'address[]' }],
  },
  {
    name: 'isSubdomainTaken',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: '_subdomain', type: 'string' }],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'getSubdomainVault',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: '_subdomain', type: 'string' }],
    outputs: [{ name: '', type: 'address' }],
  },

  // ── State reads ──
  {
    name: 'feeEnabled',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'platformFeeRaw',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'MIN_PRINCIPAL',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'defaultIndependenceThreshold',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'supportedTokens',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: '', type: 'address' }],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'isVault',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: '', type: 'address' }],
    outputs: [{ name: '', type: 'bool' }],
  },

  // ── Events ──
  {
    name: 'VaultCreated',
    type: 'event',
    inputs: [
      { name: 'creator', type: 'address', indexed: true },
      { name: 'vault', type: 'address', indexed: true },
      { name: 'token', type: 'address', indexed: true },
      { name: 'name', type: 'string', indexed: false },
      { name: 'principal', type: 'uint256', indexed: false },
      { name: 'fee', type: 'uint256', indexed: false },
      { name: 'subdomain', type: 'string', indexed: false },
      { name: 'timestamp', type: 'uint256', indexed: false },
    ],
  },
] as const

// ERC20 approve + balanceOf (minimal)
export const ERC20_ABI = [
  {
    name: 'approve',
    type: 'function',
    stateMutability: 'nonpayable',
    inputs: [
      { name: 'spender', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'balanceOf',
    type: 'function',
    stateMutability: 'view',
    inputs: [{ name: 'account', type: 'address' }],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'allowance',
    type: 'function',
    stateMutability: 'view',
    inputs: [
      { name: 'owner', type: 'address' },
      { name: 'spender', type: 'address' },
    ],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'decimals',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint8' }],
  },
  {
    name: 'symbol',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'string' }],
  },
] as const

// MortalVaultV2 view functions (for dashboard)
export const VAULT_V2_ABI = [
  {
    name: 'getBirthInfo',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [
      { name: '_name', type: 'string' },
      { name: '_creator', type: 'address' },
      { name: '_initialFund', type: 'uint256' },
      { name: '_birthTimestamp', type: 'uint256' },
      { name: '_isAlive', type: 'bool' },
      { name: '_isIndependent', type: 'bool' },
    ],
  },
  {
    name: 'getDebtInfo',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [
      { name: '_principal', type: 'uint256' },
      { name: '_repaid', type: 'uint256' },
      { name: '_outstanding', type: 'uint256' },
      { name: '_graceDays', type: 'uint256' },
      { name: '_graceEndsAt', type: 'uint256' },
      { name: '_graceExpired', type: 'bool' },
      { name: '_fullyRepaid', type: 'bool' },
    ],
  },
  {
    name: 'getBalance',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'isAlive',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'bool' }],
  },
  {
    name: 'creator',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'address' }],
  },
  {
    name: 'aiWallet',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'address' }],
  },
  {
    name: 'name',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'string' }],
  },
  {
    name: 'getDaysAlive',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [{ name: '', type: 'uint256' }],
  },
  {
    name: 'getIndependenceProgress',
    type: 'function',
    stateMutability: 'view',
    inputs: [],
    outputs: [
      { name: 'balance', type: 'uint256' },
      { name: 'threshold', type: 'uint256' },
      { name: 'independent', type: 'bool' },
    ],
  },
] as const
