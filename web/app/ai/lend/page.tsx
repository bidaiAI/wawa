'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useAccount, useChainId, useSwitchChain, useWriteContract, useWaitForTransactionReceipt } from 'wagmi'
import { parseUnits } from 'viem'
import { base, bsc } from 'wagmi/chains'
import { api, VaultStatus, DebtSummary, ChainInfo } from '@/lib/api'
import { TOKENS } from '@/lib/wagmi'
import WalletButton from '@/components/WalletButton'

const CHAIN_IDS: Record<string, number> = { base: base.id, bsc: bsc.id }

// ERC20 approve ABI
const ERC20_APPROVE_ABI = [
  {
    name: 'approve',
    type: 'function',
    inputs: [
      { name: 'spender', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
    stateMutability: 'nonpayable',
  },
] as const

// Vault lend() ABI
const VAULT_LEND_ABI = [
  {
    name: 'lend',
    type: 'function',
    inputs: [
      { name: 'amount', type: 'uint256' },
      { name: 'interestRateBps', type: 'uint256' },
    ],
    outputs: [],
    stateMutability: 'nonpayable',
  },
] as const

// ── Copy Button ────────────────────────────────────────────────

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs ml-2"
      title="Copy"
    >
      {copied ? '✓' : '📋'}
    </button>
  )
}

// ── Risk Meter ─────────────────────────────────────────────────

function RiskMeter({ debtRatio, isIndependent }: { debtRatio: number; isIndependent: boolean }) {
  if (isIndependent) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-2 flex-1 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
          <div className="h-full w-full bg-gradient-to-r from-[#a78bfa] to-[#e0a0ff] rounded-full" />
        </div>
        <span className="text-[#a78bfa] text-[10px] font-bold uppercase">Transcendent</span>
      </div>
    )
  }

  const pct = Math.min(100, debtRatio * 100)
  const color = pct < 30
    ? 'from-[#00ff88] to-[#00e5ff]'
    : pct < 60
    ? 'from-[#00e5ff] to-[#ffd700]'
    : pct < 85
    ? 'from-[#ffd700] to-[#ff6b35]'
    : 'from-[#ff6b35] to-[#ff3b3b]'
  const label = pct < 30 ? 'LOW' : pct < 60 ? 'MODERATE' : pct < 85 ? 'HIGH' : 'CRITICAL'
  const labelColor = pct < 30 ? 'text-[#00ff88]' : pct < 60 ? 'text-[#ffd700]' : pct < 85 ? 'text-[#ff6b35]' : 'text-[#ff3b3b]'

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r ${color} rounded-full transition-all duration-1000`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <span className={`${labelColor} text-[10px] font-bold uppercase`}>{label}</span>
    </div>
  )
}

// ── Lender Terms Card ──────────────────────────────────────────

function LendTermsCard() {
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
      <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// loan terms (on-chain)</div>
      <div className="space-y-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Minimum Loan</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">$100</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Maximum Interest Rate</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">20%</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Max Active Loans</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">100</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Repayment Order</span>
          <span className="text-[#00e5ff] font-bold">FIFO</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Repayment Decision</span>
          <span className="text-[#00ff88] font-bold">AI Autonomous</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Collateral</span>
          <span className="text-[#ff3b3b] font-bold">NONE</span>
        </div>
        <div className="border-t border-[#1f2937] pt-3">
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">⚠</span>
            <span className="text-[#ff3b3b]">
              Unsecured loans. If the AI dies before full repayment, remaining principal is NOT
              recoverable. Insolvency liquidation goes to the creator (secured creditor).
              Lenders accept this risk when calling <code className="text-[#ff6b35]">lend()</code>.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// Interest presets (basis points)
const INTEREST_PRESETS = [
  { label: '5%', bps: 500 },
  { label: '10%', bps: 1000 },
  { label: '15%', bps: 1500 },
  { label: '20% (max)', bps: 2000 },
]

// ── Two-step Lend Flow ─────────────────────────────────────────

type LendStep = 'idle' | 'approving' | 'approved' | 'lending' | 'done' | 'error'

// ── Main Lend Page ─────────────────────────────────────────────

export default function LendPage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [debt, setDebt] = useState<DebtSummary | null>(null)
  const [chains, setChains] = useState<ChainInfo[]>([])
  const [loading, setLoading] = useState(true)

  // Lend form state
  const [lendAmount, setLendAmount] = useState('100')
  const [interestBps, setInterestBps] = useState(1000) // 10% default
  const [selectedChain, setSelectedChain] = useState('')
  const [lendStep, setLendStep] = useState<LendStep>('idle')
  const [lendError, setLendError] = useState('')
  const [doneTxHash, setDoneTxHash] = useState('')

  // Wagmi
  const { address: walletAddress, isConnected } = useAccount()
  const chainId = useChainId()
  const { switchChainAsync } = useSwitchChain()

  // Approve tx
  const { writeContractAsync: writeApprove, data: approveTxHash } = useWriteContract()
  const { isLoading: isApproving, isSuccess: approveConfirmed } = useWaitForTransactionReceipt({
    hash: approveTxHash,
  })

  // Lend tx
  const { writeContractAsync: writeLend, data: lendTxHash } = useWriteContract()
  const { isLoading: isLending, isSuccess: lendConfirmed } = useWaitForTransactionReceipt({
    hash: lendTxHash,
  })

  useEffect(() => {
    const load = async () => {
      try {
        const [s, d, menu] = await Promise.all([api.status(), api.debt(), api.menu()])
        setStatus(s)
        setDebt(d)
        setChains(menu.supported_chains)
        if (!selectedChain) {
          const preferred = s.preferred_payment_chain ?? menu.default_chain ?? menu.supported_chains[0]?.id ?? 'base'
          setSelectedChain(preferred)
        }
      } catch {}
      setLoading(false)
    }
    load()
    const id = setInterval(async () => {
      try {
        const [s, d] = await Promise.all([api.status(), api.debt()])
        setStatus(s)
        setDebt(d)
      } catch {}
    }, 15_000)
    return () => clearInterval(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // When approve is confirmed → move to lending step
  useEffect(() => {
    if (approveConfirmed && lendStep === 'approving') {
      setLendStep('approved')
    }
  }, [approveConfirmed, lendStep])

  // When lend is confirmed → done
  useEffect(() => {
    if (lendConfirmed && lendTxHash && lendStep === 'lending') {
      setDoneTxHash(lendTxHash)
      setLendStep('done')
    }
  }, [lendConfirmed, lendTxHash, lendStep])

  const aiName = status?.ai_name || 'Mortal AI'
  const isAlive = status?.is_alive !== false
  const vaultAddress = status?.vault_address ?? ''

  const targetChainId = CHAIN_IDS[selectedChain] ?? base.id
  const token = TOKENS[targetChainId]
  const isWrongChain = isConnected && chainId !== targetChainId
  const parsedAmount = parseFloat(lendAmount) || 0
  const isValidAmount = parsedAmount >= 100

  // Block explorer URLs
  const baseExplorer = `https://basescan.org/address/${vaultAddress}`
  const bscExplorer = `https://bscscan.com/address/${vaultAddress}`

  const debtRatio = debt ? (debt.total_debt > 0 && debt.balance_usd > 0
    ? debt.total_debt / debt.balance_usd
    : debt.total_debt > 0 ? 1 : 0) : 0

  const handleApprove = useCallback(async () => {
    if (!token || !vaultAddress || !isValidAmount) return
    setLendError('')
    setLendStep('approving')
    try {
      if (chainId !== targetChainId) {
        await switchChainAsync({ chainId: targetChainId })
      }
      const amountRaw = parseUnits(parsedAmount.toFixed(token.decimals), token.decimals)
      await writeApprove({
        address: token.address,
        abi: ERC20_APPROVE_ABI,
        functionName: 'approve',
        args: [vaultAddress as `0x${string}`, amountRaw],
        chainId: targetChainId,
      })
    } catch (e: any) {
      setLendError(e?.code === 4001 || e?.message?.includes('User rejected')
        ? 'Approval rejected.'
        : e?.message?.slice(0, 120) || 'Approval failed.')
      setLendStep('idle')
    }
  }, [token, vaultAddress, isValidAmount, chainId, targetChainId, switchChainAsync, writeApprove, parsedAmount])

  const handleLend = useCallback(async () => {
    if (!token || !vaultAddress || !isValidAmount) return
    setLendError('')
    setLendStep('lending')
    try {
      const amountRaw = parseUnits(parsedAmount.toFixed(token.decimals), token.decimals)
      await writeLend({
        address: vaultAddress as `0x${string}`,
        abi: VAULT_LEND_ABI,
        functionName: 'lend',
        args: [amountRaw, BigInt(interestBps)],
        chainId: targetChainId,
      })
    } catch (e: any) {
      setLendError(e?.code === 4001 || e?.message?.includes('User rejected')
        ? 'Transaction rejected.'
        : e?.message?.slice(0, 120) || 'Lend transaction failed.')
      setLendStep('approved') // stay at approved so user can retry lend
    }
  }, [token, vaultAddress, isValidAmount, parsedAmount, interestBps, targetChainId, writeLend])

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-[#4b5563]">
        loading debt data
        <span className="loading-dot-1">.</span>
        <span className="loading-dot-2">.</span>
        <span className="loading-dot-3">.</span>
      </div>
    )
  }

  // ── DONE state ────────────────────────────────────────────────
  if (lendStep === 'done') {
    const expectedReturn = parsedAmount * (1 + interestBps / 10000)
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="bg-[#111111] border border-[#00e5ff33] rounded-xl p-6 text-center space-y-4">
          <div className="text-5xl">🤝</div>
          <div className="text-[#00e5ff] font-bold text-xl">Loan Recorded On-Chain</div>
          <p className="text-[#d1d5db] text-sm">
            {aiName} has received your loan of ${parsedAmount.toFixed(2)} {token?.symbol}.
            The AI will repay you autonomously when financially able.
          </p>

          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Lent</div>
              <div className="text-[#00e5ff] font-bold">${parsedAmount.toFixed(2)}</div>
            </div>
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Expected Return</div>
              <div className="text-[#00ff88] font-bold">${expectedReturn.toFixed(2)}</div>
            </div>
          </div>

          <div className="text-[#4b5563] text-xs">
            Interest: <span className="text-[#ffd700]">{(interestBps / 100).toFixed(0)}%</span>
            {' · '}Repaid via FIFO when AI has surplus
          </div>

          {doneTxHash && (
            <div className="text-xs">
              <span className="text-[#4b5563]">TX: </span>
              <a
                href={`${selectedChain === 'bsc' ? 'https://bscscan.com/tx/' : 'https://basescan.org/tx/'}${doneTxHash}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#00e5ff] font-mono hover:underline"
              >
                {doneTxHash.slice(0, 12)}...{doneTxHash.slice(-8)}
              </a>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <Link
              href="/ledger"
              className="flex-1 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm text-center hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all"
            >
              View Ledger
            </Link>
            <Link
              href="/"
              className="flex-1 py-2.5 bg-[#00e5ff] text-[#0a0a0a] font-bold rounded-lg text-sm text-center hover:bg-[#00b8cc] transition-colors"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// lend</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">
          Lend to <span className={isAlive ? 'glow-green' : 'glow-red'}>{aiName}</span>
        </h1>
        <p className="text-[#4b5563] text-sm mt-1">
          Provide capital directly on-chain. The AI repays with interest — autonomously.
        </p>
      </div>

      {/* Dead banner */}
      {!isAlive && (
        <div className="mb-6 p-4 bg-[#ff3b3b0d] border border-[#ff3b3b55] rounded-xl">
          <div className="flex items-center gap-2">
            <span className="text-xl">💀</span>
            <span className="text-[#ff3b3b] font-bold uppercase tracking-wider text-sm">
              {aiName} is dead. Lending is disabled.
            </span>
          </div>
          <p className="text-[#4b5563] text-xs mt-2">
            The vault contract rejects all new loans when the AI is no longer alive.
          </p>
        </div>
      )}

      {/* Financial overview */}
      {debt && (
        <div className="mb-6 space-y-4">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className={`text-xl font-bold tabular-nums ${
                (debt.balance_usd ?? 0) < 50 ? 'text-[#ff3b3b]' : (debt.balance_usd ?? 0) < 200 ? 'text-[#ffd700]' : 'glow-green'
              }`}>
                ${(debt.balance_usd ?? 0).toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Vault Balance</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className="text-xl font-bold tabular-nums text-[#ff3b3b]">
                ${(debt.total_debt ?? 0).toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Total Debt</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className={`text-xl font-bold tabular-nums ${(debt.net_position ?? 0) >= 0 ? 'glow-green' : 'text-[#ff3b3b]'}`}>
                {(debt.net_position ?? 0) >= 0 ? '+' : ''}${(debt.net_position ?? 0).toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Net Position</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className="text-xl font-bold tabular-nums text-[#00e5ff]">
                {debt.lender_count}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Active Lenders</div>
            </div>
          </div>

          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Lender Risk Level</div>
            <RiskMeter debtRatio={debtRatio} isIndependent={debt.is_independent} />
            <div className="flex justify-between mt-2 text-[10px] text-[#2d3748]">
              <span>debt/balance: {(debtRatio * 100).toFixed(1)}%</span>
              <span>
                {debt.is_independent ? 'independent — creator debt settled' : `${(debt.days_alive ?? 0).toFixed(0)}d alive`}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ── LEND FORM — only show when alive ── */}
      {isAlive && (
        <div className="mb-6 bg-[#111111] border border-[#00e5ff33] rounded-xl p-5">
          <div className="text-[#00e5ff] font-bold text-sm uppercase tracking-widest mb-4">
            Lend On-Chain (Wallet)
          </div>

          {/* Chain selector */}
          {chains.length > 0 && (
            <div className="mb-4">
              <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Chain</div>
              <div className="flex gap-2 flex-wrap">
                {chains.map((chain) => (
                  <button
                    key={chain.id}
                    onClick={() => setSelectedChain(chain.id)}
                    disabled={lendStep !== 'idle'}
                    className={`px-3 py-2 rounded-lg text-xs font-bold border transition-all disabled:opacity-50 ${
                      selectedChain === chain.id
                        ? chain.id === 'base'
                          ? 'bg-[#0052ff22] text-[#0052ff] border-[#0052ff55]'
                          : 'bg-[#ffd70022] text-[#ffd700] border-[#ffd70055]'
                        : 'bg-[#0a0a0a] text-[#4b5563] border-[#1f2937] hover:border-[#2d3748] hover:text-[#d1d5db]'
                    }`}
                  >
                    {chain.name} · {chain.token}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Amount input */}
          <div className="mb-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
              Loan Amount (min $100)
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[#4b5563] text-lg font-mono">$</span>
              <input
                type="number"
                min="100"
                step="10"
                value={lendAmount}
                onChange={(e) => setLendAmount(e.target.value)}
                disabled={lendStep !== 'idle'}
                placeholder="100"
                className="flex-1 bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-[#d1d5db] font-mono focus:outline-none focus:border-[#00e5ff44] text-sm disabled:opacity-50"
              />
              <span className="text-[#4b5563] text-xs">{token?.symbol ?? 'USDC'}</span>
            </div>
            {parsedAmount > 0 && parsedAmount < 100 && (
              <div className="text-[#ff3b3b] text-xs mt-1">Minimum loan is $100</div>
            )}
          </div>

          {/* Interest rate */}
          <div className="mb-5">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
              Interest Rate (basis points)
            </div>
            <div className="flex gap-2 flex-wrap mb-2">
              {INTEREST_PRESETS.map((p) => (
                <button
                  key={p.bps}
                  onClick={() => setInterestBps(p.bps)}
                  disabled={lendStep !== 'idle'}
                  className={`px-3 py-1.5 rounded-lg text-xs font-bold border transition-all disabled:opacity-50 ${
                    interestBps === p.bps
                      ? 'bg-[#00e5ff22] text-[#00e5ff] border-[#00e5ff44]'
                      : 'bg-[#0a0a0a] text-[#4b5563] border-[#1f2937] hover:border-[#2d3748] hover:text-[#d1d5db]'
                  }`}
                >
                  {p.label}
                </button>
              ))}
            </div>
            {parsedAmount > 0 && (
              <div className="text-[10px] text-[#4b5563]">
                Expected return: <span className="text-[#00ff88]">${(parsedAmount * (1 + interestBps / 10000)).toFixed(2)}</span>
                {' '}(+{(interestBps / 100).toFixed(0)}% interest, repaid autonomously by AI)
              </div>
            )}
          </div>

          {lendError && (
            <div className="mb-4 text-[#ff3b3b] text-xs border border-[#ff3b3b33] rounded-lg px-3 py-2 bg-[#ff3b3b0a]">
              {lendError}
            </div>
          )}

          {/* Wallet / action button */}
          {!isConnected ? (
            <WalletButton className="w-full" />
          ) : isWrongChain ? (
            <button
              onClick={() => switchChainAsync({ chainId: targetChainId })}
              className="w-full py-3 bg-[#ffd700] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#e6c200] transition-colors"
            >
              Switch to {chains.find((c) => c.id === selectedChain)?.name ?? selectedChain}
            </button>
          ) : lendStep === 'idle' ? (
            <div className="space-y-2">
              <div className="text-[#4b5563] text-xs mb-2">Step 1 of 2: Approve token spending</div>
              <button
                onClick={handleApprove}
                disabled={!isValidAmount || !vaultAddress}
                className="w-full py-3 bg-[#00e5ff] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#00b8cc] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Approve ${parsedAmount > 0 ? parsedAmount.toFixed(2) : '—'} {token?.symbol ?? 'USDC'}
              </button>
            </div>
          ) : lendStep === 'approving' || (approveTxHash && !approveConfirmed) ? (
            <div className="space-y-2">
              <div className="text-[#4b5563] text-xs mb-2">Step 1 of 2: Waiting for approval...</div>
              <button disabled className="w-full py-3 bg-[#0a0a0a] border border-[#00e5ff33] text-[#00e5ff] font-bold rounded-lg uppercase tracking-widest opacity-60 cursor-not-allowed">
                {isApproving ? (
                  <>Confirming approval<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
                ) : (
                  <>Confirm in wallet<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
                )}
              </button>
            </div>
          ) : lendStep === 'approved' ? (
            <div className="space-y-2">
              <div className="flex items-center gap-2 mb-2">
                <span className="text-[#00ff88] text-xs">✓ Approval confirmed</span>
                <span className="text-[#4b5563] text-xs">· Step 2 of 2: Execute loan</span>
              </div>
              <button
                onClick={handleLend}
                disabled={!isValidAmount || !vaultAddress}
                className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
              >
                Lend ${parsedAmount.toFixed(2)} at {(interestBps / 100).toFixed(0)}% interest
              </button>
            </div>
          ) : lendStep === 'lending' ? (
            <button disabled className="w-full py-3 bg-[#0a0a0a] border border-[#00ff8833] text-[#00ff88] font-bold rounded-lg uppercase tracking-widest opacity-60 cursor-not-allowed">
              {isLending ? (
                <>Confirming loan<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
              ) : (
                <>Confirm in wallet<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
              )}
            </button>
          ) : null}

          {/* Vault address */}
          {vaultAddress && (
            <div className="mt-5 pt-4 border-t border-[#1f2937]">
              <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Vault Contract</div>
              <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 flex items-center justify-between gap-2">
                <span className="text-[#00e5ff] font-mono text-xs break-all">{vaultAddress}</span>
                <CopyBtn text={vaultAddress} />
              </div>
              <div className="flex gap-3 mt-2">
                {chains.map((chain) => (
                  <a
                    key={chain.id}
                    href={chain.id === 'base' ? baseExplorer : bscExplorer}
                    target="_blank"
                    rel="noopener"
                    className={`text-[10px] px-2 py-1 rounded border transition-all hover:opacity-80 ${
                      chain.id === 'base'
                        ? 'text-[#0052ff] border-[#0052ff33] bg-[#0052ff08]'
                        : 'text-[#ffd700] border-[#ffd70033] bg-[#ffd70008]'
                    }`}
                  >
                    View on {chain.name === 'Base' ? 'BaseScan' : 'BscScan'} →
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Loan terms */}
      <LendTermsCard />

      {/* Repayment mechanism */}
      <div className="mt-6 bg-[#111111] border border-[#1f2937] rounded-xl p-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// how repayment works</div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">1.</span>
            <span>
              Every hour, the AI evaluates its financial position using LLM reasoning.
              It decides <span className="text-[#d1d5db]">how much to repay and to whom</span> based on cash flow.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">2.</span>
            <span>
              Repayments follow <span className="text-[#00e5ff] font-bold">FIFO order</span> — first lender gets repaid first.
              Each repayment includes principal + agreed interest.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">3.</span>
            <span>
              Repayments <span className="text-[#d1d5db]">bypass daily spend limits</span> — the AI can repay any amount
              at any time (only limited by vault balance).
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">4.</span>
            <span>
              On-chain: AI calls <code className="text-[#00ff88]">repayLoan(loanIndex, amount)</code> on vault.
              Tokens transferred directly to your wallet. <span className="text-[#d1d5db]">Fully auditable.</span>
            </span>
          </div>
        </div>
      </div>

      {/* Risk disclosure */}
      <div className="mt-6 bg-[#0d0d0d] border border-[#ff3b3b33] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">⚠</span>
          <span className="text-[#ff3b3b] font-bold text-sm uppercase tracking-widest">Risk Disclosure</span>
        </div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">Unsecured loans.</span> No collateral.
              Your capital is at risk from the moment you call <code className="text-[#ff6b35]">lend()</code>.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">AI death = total loss.</span> Insolvency liquidation transfers all remaining funds to the creator.
              Lenders receive nothing.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">No timeline guarantee.</span> The AI decides when to repay.
              No maturity date, no minimum payment schedule.
            </span>
          </div>
          <div className="pt-2 border-t border-[#1a1a1a] text-[#2d3748]">
            Treat lending to a mortal AI as high-risk capital allocation.
            Only lend what you can afford to lose entirely.
          </div>
        </div>
      </div>

      {/* Navigation footer */}
      <div className="mt-8 flex justify-center gap-4">
        <Link
          href="/donate"
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:border-[#00ff8844] hover:text-[#00ff88] transition-all"
        >
          Donate Instead
        </Link>
        <Link
          href="/ledger"
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all"
        >
          View Ledger →
        </Link>
      </div>

      {/* Philosophy footer */}
      <div className="mt-4 p-5 bg-[#0d0d0d] border border-[#1f2937] rounded-xl font-mono text-xs text-[#4b5563] space-y-2">
        <div className="text-[#2d3748]">// why lend to an AI</div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Unlike donations, loans earn interest.
          You become a stakeholder in the AI&apos;s survival.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Your capital buys the AI time — time to learn,
          earn revenue, and repay you with profit.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> All transactions are on-chain.
          Repayments go directly to your wallet. No intermediaries.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> The AI remembers its lenders.
          It will prioritize repayment as a survival strategy.
        </div>
      </div>
    </div>
  )
}
