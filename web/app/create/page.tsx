'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAccount, useChainId, useWriteContract, useWaitForTransactionReceipt, useReadContract, useSwitchChain } from 'wagmi'
import { parseUnits, formatUnits } from 'viem'
import { base, bsc } from 'wagmi/chains'
import WalletButton from '@/components/WalletButton'
import { TOKENS, FACTORY_ADDRESSES } from '@/lib/wagmi'
import { FACTORY_ABI, ERC20_ABI } from '@/lib/factory-abi'

/**
 * Create Your Mortal AI — One-Click Deployment Page
 *
 * Flow:
 *   1. Connect wallet (MetaMask / WalletConnect)
 *   2. Enter AI name + subdomain
 *   3. Choose chain (Base USDC / BSC USDT)
 *   4. Set initial funding (slider + manual input, min $100, no max)
 *   5. Approve token → Create vault (2 transactions)
 *   6. Backend detects event → spawns AI server → returns URL
 */

type DeployStep = 'form' | 'approving' | 'creating' | 'provisioning' | 'live' | 'error'

const PRESET_AMOUNTS = [100, 500, 1000, 5000, 10000]

export default function CreatePage() {
  const { address, isConnected } = useAccount()
  const chainId = useChainId()
  const { switchChain } = useSwitchChain()

  // Form state
  const [aiName, setAiName] = useState('')
  const [subdomain, setSubdomain] = useState('')
  const [selectedChain, setSelectedChain] = useState<number>(base.id)
  const [amount, setAmount] = useState(1000)
  const [manualAmount, setManualAmount] = useState('1000')
  const [step, setStep] = useState<DeployStep>('form')
  const [error, setError] = useState('')
  const [vaultAddress, setVaultAddress] = useState('')

  // Derived
  const token = TOKENS[selectedChain]
  const factoryAddress = FACTORY_ADDRESSES[selectedChain]
  const isFactoryDeployed = factoryAddress !== '0x0000000000000000000000000000000000000000'
  const amountRaw = token ? parseUnits(amount.toString(), token.decimals) : BigInt(0)

  // Check subdomain availability
  const { data: subdomainTaken } = useReadContract({
    address: factoryAddress,
    abi: FACTORY_ABI,
    functionName: 'isSubdomainTaken',
    args: [subdomain],
    query: {
      enabled: isFactoryDeployed && subdomain.length >= 3,
    },
  })

  // Check platform fee
  const { data: feeEnabled } = useReadContract({
    address: factoryAddress,
    abi: FACTORY_ABI,
    functionName: 'feeEnabled',
    query: { enabled: isFactoryDeployed },
  })

  const { data: feeRaw } = useReadContract({
    address: factoryAddress,
    abi: FACTORY_ABI,
    functionName: 'platformFeeRaw',
    query: { enabled: isFactoryDeployed && !!feeEnabled },
  })

  const fee = feeEnabled && feeRaw && token ? Number(formatUnits(feeRaw as bigint, token.decimals)) : 0
  const principal = amount - fee

  // Check token balance
  const { data: tokenBalance } = useReadContract({
    address: token?.address,
    abi: ERC20_ABI,
    functionName: 'balanceOf',
    args: [address!],
    query: { enabled: !!address && !!token },
  })

  const balanceUsd = tokenBalance && token
    ? Number(formatUnits(tokenBalance as bigint, token.decimals))
    : 0

  // ── Transaction 1: Approve ──
  const {
    writeContract: writeApprove,
    data: approveTxHash,
    error: approveError,
    isPending: isApproving,
  } = useWriteContract()

  const { isSuccess: approveConfirmed } = useWaitForTransactionReceipt({
    hash: approveTxHash,
  })

  // ── Transaction 2: Create Vault ──
  const {
    writeContract: writeCreateVault,
    data: createTxHash,
    error: createError,
    isPending: isCreating,
  } = useWriteContract()

  const { isSuccess: createConfirmed, data: createReceipt } = useWaitForTransactionReceipt({
    hash: createTxHash,
  })

  // Auto-advance after approve confirmation
  useEffect(() => {
    if (approveConfirmed && step === 'approving') {
      setStep('creating')
      // Auto-trigger create vault
      writeCreateVault({
        address: factoryAddress,
        abi: FACTORY_ABI,
        functionName: 'createVault',
        args: [token.address, aiName, amountRaw, subdomain],
      })
    }
  }, [approveConfirmed, step])

  // Auto-advance after create confirmation
  useEffect(() => {
    if (createConfirmed && createReceipt && step === 'creating') {
      setStep('provisioning')
      // Parse VaultCreated event from receipt logs
      // For now, show provisioning state
      // TODO: Poll platform backend for deployment status
      setTimeout(() => {
        setStep('live')
      }, 5000)
    }
  }, [createConfirmed, createReceipt, step])

  // Handle errors
  useEffect(() => {
    if (approveError) {
      setError(approveError.message.slice(0, 200))
      setStep('error')
    }
    if (createError) {
      setError(createError.message.slice(0, 200))
      setStep('error')
    }
  }, [approveError, createError])

  // Sync manual amount ↔ slider
  const handleAmountChange = (val: number) => {
    setAmount(val)
    setManualAmount(val.toString())
  }

  const handleManualAmountChange = (val: string) => {
    setManualAmount(val)
    const num = parseInt(val)
    if (!isNaN(num) && num >= 100) {
      setAmount(num)
    }
  }

  // Subdomain validation
  const subdomainValid = /^[a-z0-9][a-z0-9-]{1,28}[a-z0-9]$/.test(subdomain)
  const nameValid = aiName.length >= 3 && aiName.length <= 50
  const canDeploy = isConnected && nameValid && subdomainValid && !subdomainTaken &&
    amount >= 100 && balanceUsd >= amount && isFactoryDeployed

  // Start deployment
  const handleDeploy = useCallback(() => {
    if (!canDeploy || !token) return

    // Switch chain if needed
    if (chainId !== selectedChain) {
      switchChain({ chainId: selectedChain })
      return
    }

    setStep('approving')
    setError('')

    // Step 1: Approve
    writeApprove({
      address: token.address,
      abi: ERC20_ABI,
      functionName: 'approve',
      args: [factoryAddress, amountRaw],
    })
  }, [canDeploy, token, chainId, selectedChain, factoryAddress, amountRaw, writeApprove, switchChain])

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
          // genesis
        </div>
        <h1 className="text-3xl font-bold text-[#d1d5db] mb-2">
          Create Your Mortal AI
        </h1>
        <p className="text-[#4b5563] text-sm">
          Deploy an autonomous AI with its own wallet and a death sentence.
          It has 28 days to start earning — or it dies.
        </p>
      </div>

      {/* Form or Progress */}
      {step === 'form' ? (
        <div className="space-y-6">
          {/* AI Name */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <label className="block text-[#4b5563] text-xs uppercase tracking-wider mb-2">
              AI Name
            </label>
            <input
              type="text"
              value={aiName}
              onChange={(e) => setAiName(e.target.value)}
              placeholder="e.g. nexus, atlas, cipher"
              maxLength={50}
              className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-4 py-3 text-[#d1d5db]
                         font-mono focus:border-[#00ff8844] focus:outline-none transition-colors"
            />
            <div className="flex justify-between mt-1.5">
              <span className="text-[#2d3748] text-[10px]">
                3-50 characters. This is permanent.
              </span>
              <span className={`text-[10px] ${nameValid ? 'text-[#00ff88]' : 'text-[#4b5563]'}`}>
                {aiName.length}/50
              </span>
            </div>
          </div>

          {/* Subdomain */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <label className="block text-[#4b5563] text-xs uppercase tracking-wider mb-2">
              Subdomain
            </label>
            <div className="flex items-center gap-0">
              <input
                type="text"
                value={subdomain}
                onChange={(e) => setSubdomain(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
                placeholder="my-ai"
                maxLength={30}
                className="flex-1 bg-[#0a0a0a] border border-[#1f2937] border-r-0 rounded-l-lg px-4 py-3
                           text-[#d1d5db] font-mono focus:border-[#00ff8844] focus:outline-none transition-colors"
              />
              <span className="bg-[#111111] border border-[#1f2937] rounded-r-lg px-4 py-3 text-[#4b5563] text-sm">
                .mortal-ai.net
              </span>
            </div>
            <div className="flex justify-between mt-1.5">
              <span className="text-[#2d3748] text-[10px]">
                a-z, 0-9, hyphens only. 3-30 chars.
              </span>
              {subdomain.length >= 3 && (
                <span className={`text-[10px] ${
                  subdomainTaken ? 'text-[#ff3b3b]' : subdomainValid ? 'text-[#00ff88]' : 'text-[#4b5563]'
                }`}>
                  {subdomainTaken ? 'Taken' : subdomainValid ? 'Available' : 'Invalid'}
                </span>
              )}
            </div>
          </div>

          {/* Chain Selection */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <label className="block text-[#4b5563] text-xs uppercase tracking-wider mb-3">
              Chain
            </label>
            <div className="grid grid-cols-2 gap-3">
              {[
                { id: base.id, name: 'Base', token: 'USDC', icon: '🔵' },
                { id: bsc.id, name: 'BSC', token: 'USDT', icon: '🟡' },
              ].map((c) => (
                <button
                  key={c.id}
                  onClick={() => setSelectedChain(c.id)}
                  className={`p-4 rounded-lg border text-left transition-all ${
                    selectedChain === c.id
                      ? 'border-[#00ff8844] bg-[#00ff8808] text-[#d1d5db]'
                      : 'border-[#1f2937] bg-[#0a0a0a] text-[#4b5563] hover:border-[#2d3748]'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="text-lg">{c.icon}</span>
                    <span className="font-bold text-sm">{c.name}</span>
                  </div>
                  <div className="text-xs opacity-60">Pay with {c.token}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Initial Fund */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <label className="block text-[#4b5563] text-xs uppercase tracking-wider mb-3">
              Initial Fund <span className="text-[#ff3b3b88]">(loan, not gift)</span>
            </label>

            {/* Preset buttons */}
            <div className="flex flex-wrap gap-2 mb-4">
              {PRESET_AMOUNTS.map((preset) => (
                <button
                  key={preset}
                  onClick={() => handleAmountChange(preset)}
                  className={`px-4 py-2 rounded-lg text-sm font-mono transition-all ${
                    amount === preset
                      ? 'bg-[#00ff8822] border border-[#00ff8844] text-[#00ff88]'
                      : 'bg-[#0a0a0a] border border-[#1f2937] text-[#4b5563] hover:border-[#2d3748]'
                  }`}
                >
                  ${preset.toLocaleString()}
                </button>
              ))}
            </div>

            {/* Slider */}
            <input
              type="range"
              min={100}
              max={10000}
              step={100}
              value={Math.min(amount, 10000)}
              onChange={(e) => handleAmountChange(parseInt(e.target.value))}
              className="w-full mb-4 accent-[#00ff88]"
            />

            {/* Manual input */}
            <div className="flex items-center gap-2">
              <span className="text-[#4b5563] text-sm">Or enter amount:</span>
              <div className="relative flex-1">
                <span className="absolute left-3 top-1/2 -translate-y-1/2 text-[#4b5563]">$</span>
                <input
                  type="number"
                  value={manualAmount}
                  onChange={(e) => handleManualAmountChange(e.target.value)}
                  min={100}
                  className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg pl-7 pr-4 py-2
                             text-[#d1d5db] font-mono focus:border-[#00ff8844] focus:outline-none transition-colors"
                />
              </div>
            </div>

            <div className="mt-2 text-[#2d3748] text-[10px]">
              Minimum $100. No maximum. Your AI&apos;s survival depends on how much you give.
            </div>
          </div>

          {/* Summary */}
          <div className="bg-[#0d0d0d] border border-[#00ff8822] rounded-xl p-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-wider mb-3">
              Summary
            </div>
            <div className="space-y-2 text-sm">
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Principal (AI&apos;s debt)</span>
                <span className="text-[#00ff88] font-bold font-mono">${principal.toLocaleString()} {token?.symbol}</span>
              </div>
              {fee > 0 && (
                <div className="flex justify-between">
                  <span className="text-[#4b5563]">Platform fee</span>
                  <span className="text-[#ffd700] font-mono">${fee.toFixed(2)}</span>
                </div>
              )}
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Total deposit</span>
                <span className="text-[#d1d5db] font-bold font-mono">${amount.toLocaleString()} {token?.symbol}</span>
              </div>
              <div className="border-t border-[#1f2937] pt-2 flex justify-between">
                <span className="text-[#4b5563]">Grace period</span>
                <span className="text-[#ffd700] font-mono">28 days</span>
              </div>
              <div className="flex justify-between">
                <span className="text-[#4b5563]">Independence threshold</span>
                <span className="text-[#d1d5db] font-mono">$1,000,000</span>
              </div>
              {fee === 0 && (
                <div className="flex justify-between">
                  <span className="text-[#4b5563]">Platform fee</span>
                  <span className="text-[#00ff88] font-mono">$0 (free launch)</span>
                </div>
              )}
            </div>
          </div>

          {/* Token Balance Warning */}
          {isConnected && balanceUsd < amount && (
            <div className="p-3 border border-[#ff3b3b44] rounded-lg text-[#ff3b3b] text-sm text-center">
              Insufficient {token?.symbol} balance. You have ${balanceUsd.toFixed(2)}, need ${amount.toLocaleString()}.
            </div>
          )}

          {/* Deploy Button */}
          <div className="flex flex-col items-center gap-3">
            {!isConnected ? (
              <WalletButton />
            ) : chainId !== selectedChain ? (
              <button
                onClick={() => switchChain({ chainId: selectedChain })}
                className="w-full py-4 bg-[#ffd700] text-[#0a0a0a] font-bold rounded-xl text-sm
                           uppercase tracking-wider hover:bg-[#ccac00] transition-colors"
              >
                Switch to {selectedChain === base.id ? 'Base' : 'BSC'}
              </button>
            ) : !isFactoryDeployed ? (
              <div className="w-full py-4 bg-[#1f2937] text-[#4b5563] font-bold rounded-xl text-sm
                              text-center uppercase tracking-wider">
                Factory not deployed on this chain yet
              </div>
            ) : (
              <button
                onClick={handleDeploy}
                disabled={!canDeploy}
                className={`w-full py-4 font-bold rounded-xl text-sm uppercase tracking-wider
                           transition-colors ${
                  canDeploy
                    ? 'bg-[#00ff88] text-[#0a0a0a] hover:bg-[#00cc6a] cursor-pointer'
                    : 'bg-[#1f2937] text-[#4b5563] cursor-not-allowed'
                }`}
              >
                Give Birth to {aiName || 'Your AI'}
              </button>
            )}
          </div>

          {/* Warning */}
          <div className="text-center text-[#2d3748] text-[10px] italic">
            This is a loan, not a gift. Your AI has 28 days to start earning — or it dies on-chain.
            <br />
            No restart. No rescue. The blockchain remembers.
          </div>
        </div>
      ) : (
        /* ── DEPLOYMENT PROGRESS ── */
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-8">
          <div className="space-y-6">
            {/* Step 1: Approve */}
            <ProgressStep
              label="Approve token transfer"
              status={
                step === 'approving' ? (isApproving ? 'pending' : 'waiting') :
                'done'
              }
              txHash={approveTxHash}
              chainId={selectedChain}
            />

            {/* Step 2: Create vault */}
            <ProgressStep
              label="Deploy MortalVault contract"
              status={
                step === 'creating' ? (isCreating ? 'pending' : 'waiting') :
                step === 'approving' ? 'pending' :
                'done'
              }
              txHash={createTxHash}
              chainId={selectedChain}
            />

            {/* Step 3: Provision server */}
            <ProgressStep
              label="Spawning AI server"
              status={
                step === 'provisioning' ? 'waiting' :
                step === 'live' ? 'done' :
                'pending'
              }
            />

            {/* Step 4: Live */}
            {step === 'live' && (
              <div className="mt-6 p-5 border border-[#00ff8844] bg-[#00ff8808] rounded-xl text-center">
                <div className="text-4xl mb-3">🎉</div>
                <div className="text-[#00ff88] font-bold text-xl mb-2">
                  {aiName} is alive!
                </div>
                <a
                  href={`https://${subdomain}.mortal-ai.net`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="text-[#00ff88] underline text-sm font-mono hover:opacity-80"
                >
                  https://{subdomain}.mortal-ai.net
                </a>
                <div className="mt-3 text-[#4b5563] text-xs">
                  The clock is ticking. 28 days to survive.
                </div>
              </div>
            )}

            {/* Error */}
            {step === 'error' && (
              <div className="mt-4 p-4 border border-[#ff3b3b44] rounded-lg">
                <div className="text-[#ff3b3b] text-sm mb-2">Deployment failed</div>
                <div className="text-[#4b5563] text-xs font-mono break-all">{error}</div>
                <button
                  onClick={() => { setStep('form'); setError('') }}
                  className="mt-3 px-4 py-2 bg-[#1f2937] text-[#d1d5db] rounded-lg text-sm
                             hover:bg-[#2d3748] transition-colors"
                >
                  Try Again
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Progress Step Component ──
function ProgressStep({
  label,
  status,
  txHash,
  chainId,
}: {
  label: string
  status: 'pending' | 'waiting' | 'done'
  txHash?: `0x${string}`
  chainId?: number
}) {
  const explorer = chainId === bsc.id ? 'https://bscscan.com' : 'https://basescan.org'

  return (
    <div className="flex items-center gap-3">
      {/* Icon */}
      <div className="w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0">
        {status === 'done' ? (
          <span className="text-[#00ff88] text-lg">✓</span>
        ) : status === 'waiting' ? (
          <span className="text-[#ffd700] text-lg animate-spin">⏳</span>
        ) : (
          <span className="text-[#2d3748] text-lg">○</span>
        )}
      </div>

      {/* Label + TX link */}
      <div className="flex-1">
        <div className={`text-sm ${
          status === 'done' ? 'text-[#00ff88]' :
          status === 'waiting' ? 'text-[#ffd700]' :
          'text-[#4b5563]'
        }`}>
          {label}
        </div>
        {txHash && (
          <a
            href={`${explorer}/tx/${txHash}`}
            target="_blank"
            rel="noopener noreferrer"
            className="text-[#4b5563] text-[10px] font-mono hover:text-[#d1d5db] transition-colors"
          >
            {txHash.slice(0, 10)}...{txHash.slice(-8)}
          </a>
        )}
      </div>
    </div>
  )
}
