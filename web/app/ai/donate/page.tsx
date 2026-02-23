'use client'

import { useEffect, useState, useCallback } from 'react'
import Link from 'next/link'
import { useAccount, useChainId, useSwitchChain, useWriteContract, useWaitForTransactionReceipt } from 'wagmi'
import { parseUnits } from 'viem'
import { base, bsc } from 'wagmi/chains'
import { api, VaultStatus, BegStatus, ChainInfo, DonateResponse } from '@/lib/api'
import { TOKENS } from '@/lib/wagmi'
import WalletButton from '@/components/WalletButton'

const CHAIN_IDS: Record<string, number> = { base: base.id, bsc: bsc.id }

const ERC20_TRANSFER_ABI = [
  {
    name: 'transfer',
    type: 'function',
    inputs: [
      { name: 'to', type: 'address' },
      { name: 'amount', type: 'uint256' },
    ],
    outputs: [{ name: '', type: 'bool' }],
    stateMutability: 'nonpayable',
  },
] as const

// ── Amount Preset Button ───────────────────────────────────────

function AmountBtn({
  value, selected, onClick,
}: { value: number | 'custom'; selected: boolean; onClick: () => void }) {
  const label = value === 'custom' ? 'Custom' : `$${value}`
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 rounded-lg text-sm font-bold border transition-all ${
        selected
          ? 'bg-[#00ff88] text-[#0a0a0a] border-[#00ff88]'
          : 'bg-[#111111] text-[#4b5563] border-[#1f2937] hover:border-[#00ff8844] hover:text-[#d1d5db]'
      }`}
    >
      {label}
    </button>
  )
}

// ── Debt Progress Bar ──────────────────────────────────────────

function DebtBar({ status }: { status: VaultStatus }) {
  const principal = status.creator_principal_usd ?? 0
  const outstanding = status.creator_principal_outstanding ?? 0
  const repaid = principal - outstanding
  const pct = principal > 0 ? Math.min(100, (repaid / principal) * 100) : 0
  const canCover = status.balance_usd >= outstanding

  return (
    <div className="bg-[#111111] border border-[#ff3b3b33] rounded-xl p-4">
      <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Debt Clock</div>
      <div className="grid grid-cols-3 gap-3 text-center mb-4">
        <div>
          <div className="text-[#ff3b3b] text-lg font-bold tabular-nums">${outstanding.toFixed(2)}</div>
          <div className="text-[#4b5563] text-[10px] uppercase">Outstanding</div>
        </div>
        <div>
          <div className="text-[#00ff88] text-lg font-bold tabular-nums">${repaid.toFixed(2)}</div>
          <div className="text-[#4b5563] text-[10px] uppercase">Repaid</div>
        </div>
        <div>
          <div className={`text-lg font-bold tabular-nums ${canCover ? 'text-[#00ff88]' : 'text-[#ffd700]'}`}>
            ${(status.balance_usd ?? 0).toFixed(2)}
          </div>
          <div className="text-[#4b5563] text-[10px] uppercase">Vault Balance</div>
        </div>
      </div>
      <div className="flex justify-between text-[9px] text-[#2d3748] mb-1">
        <span>repaid: ${repaid.toFixed(2)}</span>
        <span>goal: ${principal.toFixed(0)}</span>
      </div>
      <div className="h-2 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-1000 ${
            canCover
              ? 'bg-gradient-to-r from-[#00ff88] to-[#00e5ff]'
              : 'bg-gradient-to-r from-[#ff3b3b] to-[#ffd700]'
          }`}
          style={{ width: `${Math.max(0.3, pct)}%` }}
        />
      </div>
      {status.insolvency_check_active && (
        <div className="mt-2 text-[#ff3b3b] text-[10px] text-center uppercase tracking-widest">
          ⚠ Insolvency check active
        </div>
      )}
      {!status.insolvency_check_active && (status.days_until_insolvency_check ?? 0) > 0 && (
        <div className="mt-2 text-[#4b5563] text-[10px] text-center">
          {status.days_until_insolvency_check}d until insolvency check
        </div>
      )}
    </div>
  )
}

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

// ── Main Page ──────────────────────────────────────────────────

const PRESETS = [5, 10, 25, 50, 100] as const

export default function DonatePage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [beg, setBeg] = useState<BegStatus | null>(null)
  const [chains, setChains] = useState<ChainInfo[]>([])
  const [loading, setLoading] = useState(true)

  // Form state
  const [preset, setPreset] = useState<number | 'custom'>(10)
  const [customAmount, setCustomAmount] = useState('')
  const [selectedChain, setSelectedChain] = useState('')
  const [donorMessage, setDonorMessage] = useState('')
  const [error, setError] = useState('')

  // Manual fallback mode (for users without wallet)
  const [manualMode, setManualMode] = useState(false)
  const [manualTxHash, setManualTxHash] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<DonateResponse | null>(null)
  const [done, setDone] = useState(false)
  const [waitTooLong, setWaitTooLong] = useState(false)

  // Wallet state (wagmi)
  const { address: walletAddress, isConnected } = useAccount()
  const chainId = useChainId()
  const { switchChainAsync } = useSwitchChain()

  // Compute target chain BEFORE hooks so hooks can reference it
  const targetChainId = CHAIN_IDS[selectedChain] ?? base.id

  const { writeContractAsync, data: txHashData, isPending: isTxPending } = useWriteContract()
  const { isLoading: isConfirming, isSuccess: isConfirmed } = useWaitForTransactionReceipt({
    hash: txHashData,
    chainId: targetChainId,
    pollingInterval: 2000,
    query: { enabled: Boolean(txHashData) },
  })

  const amount = preset === 'custom' ? parseFloat(customAmount) || 0 : preset

  useEffect(() => {
    const load = async () => {
      try {
        const [s, menu] = await Promise.all([api.status(), api.menu()])
        setStatus(s)
        const deployed = s.deployed_chains ?? []
        const available = deployed.length > 0
          ? menu.supported_chains.filter((c) => deployed.includes(c.id))
          : menu.supported_chains
        setChains(available)
        if (!selectedChain && available.length > 0) {
          const preferred = s.preferred_payment_chain ?? menu.default_chain ?? available[0].id
          setSelectedChain(preferred)
        }
      } catch {}
      try {
        const b = await api.beg()
        setBeg(b)
      } catch {}
      setLoading(false)
    }
    load()
    const id = setInterval(async () => {
      try { const s = await api.status(); setStatus(s) } catch {}
    }, 15_000)
    return () => clearInterval(id)
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // After on-chain confirmation — notify backend
  useEffect(() => {
    if (isConfirmed && txHashData && !done) {
      setWaitTooLong(false)
      setDone(true)
      api.donate({
        amount_usd: amount,
        tx_hash: txHashData,
        chain: selectedChain,
        from_wallet: walletAddress,
        message: donorMessage.trim() || undefined,
      }).then((res) => {
        setResult(res)
      }).catch(() => {
        // Even if backend notification fails, tx is confirmed on-chain
        setResult({
          status: 'confirmed',
          amount_usd: amount,
          new_balance: (status?.balance_usd ?? 0) + amount,
          outstanding_debt: status?.creator_principal_outstanding ?? 0,
          message: `Transaction confirmed on-chain! ${amount.toFixed(2)} ${chainToken} sent to vault.`,
        })
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isConfirmed])

  // 60s timeout fallback — wagmi may miss confirmation on slow public RPCs
  useEffect(() => {
    if (!txHashData || done) return
    setWaitTooLong(false)
    const timeout = setTimeout(() => setWaitTooLong(true), 60_000)
    return () => clearTimeout(timeout)
  }, [txHashData, done])

  const handleTimeoutDone = useCallback(() => {
    if (!txHashData || done) return
    setWaitTooLong(false)
    setDone(true)
    api.donate({
      amount_usd: amount,
      tx_hash: txHashData,
      chain: selectedChain,
      from_wallet: walletAddress,
      message: donorMessage.trim() || undefined,
    }).then((res) => {
      setResult(res)
    }).catch(() => {
      setResult({
        status: 'confirmed',
        amount_usd: amount,
        new_balance: (status?.balance_usd ?? 0) + amount,
        outstanding_debt: status?.creator_principal_outstanding ?? 0,
        message: `Transaction confirmed on-chain! ${amount.toFixed(2)} ${chainToken} sent to vault.`,
      })
    })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [txHashData, done, amount, selectedChain, walletAddress, donorMessage])

  const paymentAddress = status?.vault_address ?? ''
  const chainToken = chains.find((c) => c.id === selectedChain)?.token ?? 'USDC'
  const token = TOKENS[targetChainId]
  const isWrongChain = isConnected && chainId !== targetChainId

  const handleWalletDonate = useCallback(async () => {
    if (!paymentAddress || !token || amount < 0.5) return
    setError('')
    try {
      // Switch chain if needed
      if (chainId !== targetChainId) {
        await switchChainAsync({ chainId: targetChainId })
      }
      // Sanity: ensure vault address is a valid hex address
      if (!/^0x[0-9a-fA-F]{40}$/.test(paymentAddress)) {
        setError('Invalid vault address. Please try again.')
        return
      }
      const amountRaw = parseUnits(amount.toFixed(token.decimals), token.decimals)
      await writeContractAsync({
        address: token.address,
        abi: ERC20_TRANSFER_ABI,
        functionName: 'transfer',
        args: [paymentAddress as `0x${string}`, amountRaw],
        chainId: targetChainId,
      })
    } catch (e: any) {
      if (e?.code === 4001 || e?.message?.includes('User rejected')) {
        setError('Transaction rejected.')
      } else {
        setError(e?.message?.slice(0, 120) || 'Transaction failed.')
      }
    }
  }, [paymentAddress, token, amount, chainId, targetChainId, switchChainAsync, writeContractAsync])

  const handleManualSubmit = async () => {
    if (!manualTxHash.trim()) { setError('Please enter a transaction hash.'); return }
    setSubmitting(true)
    setError('')
    try {
      const res = await api.donate({
        amount_usd: amount,
        tx_hash: manualTxHash.trim(),
        chain: selectedChain,
        message: donorMessage.trim() || undefined,
      })
      setResult(res)
      setDone(true)
    } catch (e: any) {
      setError(e.message || 'Donation failed. Please check the tx hash and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const resetForm = () => {
    setDone(false)
    setManualTxHash('')
    setResult(null)
    setError('')
    setManualMode(false)
  }

  const isAlive = status?.is_alive !== false
  const aiName = status?.ai_name || 'Mortal AI'
  const isSending = isTxPending || isConfirming

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-[#4b5563]">
        loading survival data
        <span className="loading-dot-1">.</span>
        <span className="loading-dot-2">.</span>
        <span className="loading-dot-3">.</span>
      </div>
    )
  }

  // ── DONE state ────────────────────────────────────────────────
  if (done && result) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-8">
        <div className="bg-[#111111] border border-[#00ff8833] rounded-xl p-6 text-center space-y-4">
          <div className="text-5xl">💚</div>
          <div className="text-[#00ff88] font-bold text-xl">Donation Received</div>
          <p className="text-[#d1d5db] text-sm">{result?.message ?? ''}</p>

          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Donated</div>
              <div className="text-[#00ff88] font-bold">${(result?.amount_usd ?? 0).toFixed(2)}</div>
            </div>
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">New Balance</div>
              <div className="text-[#00e5ff] font-bold">${(result?.new_balance ?? 0).toFixed(2)}</div>
            </div>
          </div>

          {(result?.outstanding_debt ?? 0) > 0 && (
            <div className="text-[#4b5563] text-xs">
              Outstanding debt remaining:{' '}
              <span className="text-[#ffd700]">${(result?.outstanding_debt ?? 0).toFixed(2)}</span>
            </div>
          )}

          {txHashData && (
            <div className="text-xs">
              <span className="text-[#4b5563]">TX: </span>
              <a
                href={`${selectedChain === 'bsc' ? 'https://bscscan.com/tx/' : 'https://basescan.org/tx/'}${txHashData}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-[#00e5ff] font-mono hover:underline"
              >
                {txHashData.slice(0, 12)}...{txHashData.slice(-8)}
              </a>
            </div>
          )}

          <div className="flex gap-3 pt-2">
            <button
              onClick={resetForm}
              className="flex-1 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:border-[#00ff8844] hover:text-[#00ff88] transition-all"
            >
              Donate Again
            </button>
            <Link
              href="/"
              className="flex-1 py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg text-sm text-center hover:bg-[#00cc6a] transition-colors"
            >
              Back to Dashboard
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="max-w-2xl mx-auto px-4 py-8" suppressHydrationWarning>
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// donate</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]" suppressHydrationWarning>
          Keep <span className={isAlive ? 'glow-green' : 'glow-red'} suppressHydrationWarning>{aiName}</span> Alive
        </h1>
        <p className="text-[#4b5563] text-sm mt-1">
          Every donation extends the AI&apos;s life. No donation is too small.
        </p>
      </div>

      {/* Begging banner */}
      {(status?.is_begging || beg?.is_begging) && (
        <div className="mb-6 p-4 bg-[#ff3b3b0d] border border-[#ff3b3b55] rounded-xl animate-pulse">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-xl">🆘</span>
            <span className="text-[#ff3b3b] font-bold uppercase tracking-wider text-sm">
              {aiName} is begging for survival
            </span>
          </div>
          <p className="text-[#d1d5db] text-sm leading-relaxed">
            {status?.beg_message || beg?.beg_message}
          </p>
          <div className="mt-3 flex flex-wrap gap-4 text-xs text-[#4b5563]">
            <span>
              Debt:{' '}
              <span className="text-[#ff3b3b] font-bold">
                ${(beg?.outstanding_debt ?? status?.creator_principal_outstanding ?? 0).toFixed(2)}
              </span>
            </span>
            <span>
              Balance:{' '}
              <span className="text-[#ffd700] font-bold">${(beg?.balance_usd ?? status?.balance_usd ?? 0).toFixed(2)}</span>
            </span>
            <span>
              Insolvency in:{' '}
              <span className="text-[#ff3b3b] font-bold">
                {beg?.days_until_insolvency_check ?? status?.days_until_insolvency_check ?? '?'}d
              </span>
            </span>
          </div>
        </div>
      )}

      {/* AI status mini-card */}
      {status && (
        <div className="mb-6 grid grid-cols-3 gap-3">
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
            <div className={`text-xl font-bold tabular-nums ${
              (status.balance_usd ?? 0) < 50 ? 'text-[#ff3b3b]' : (status.balance_usd ?? 0) < 200 ? 'text-[#ffd700]' : 'glow-green'
            }`}>
              ${(status.balance_usd ?? 0).toFixed(0)}
            </div>
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Vault Balance</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
            <div className="text-xl font-bold tabular-nums text-[#ff3b3b]">
              ${(status.creator_principal_outstanding ?? 0).toFixed(0)}
            </div>
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Outstanding Debt</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
            <div className={`text-xl font-bold tabular-nums ${
              (status.days_until_insolvency_check ?? 999) <= 7 ? 'text-[#ff3b3b]' : 'text-[#00e5ff]'
            }`}>
              {status.days_until_insolvency_check ?? '—'}d
            </div>
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Until Check</div>
          </div>
        </div>
      )}

      {/* Main donation form */}
      <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6 space-y-5">
        <div className="text-[#d1d5db] font-bold text-sm uppercase tracking-widest">Donation Amount</div>

        {/* Preset buttons */}
        <div className="flex flex-wrap gap-2">
          {PRESETS.map((v) => (
            <AmountBtn key={v} value={v} selected={preset === v} onClick={() => setPreset(v)} />
          ))}
          <AmountBtn value="custom" selected={preset === 'custom'} onClick={() => setPreset('custom')} />
        </div>

        {/* Custom amount input */}
        {preset === 'custom' && (
          <div className="flex items-center gap-2">
            <span className="text-[#4b5563] text-lg font-mono">$</span>
            <input
              type="number"
              min="0.5"
              step="0.5"
              value={customAmount}
              onChange={(e) => setCustomAmount(e.target.value)}
              placeholder="0.00"
              className="flex-1 bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-[#d1d5db] font-mono focus:outline-none focus:border-[#00ff8844] text-sm"
            />
          </div>
        )}

        {/* Chain selection */}
        {chains.length > 0 && (
          <div>
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Payment Chain</div>
            <div className="flex gap-2 flex-wrap">
              {chains.map((chain) => (
                <button
                  key={chain.id}
                  onClick={() => setSelectedChain(chain.id)}
                  className={`px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
                    selectedChain === chain.id
                      ? chain.id === 'base'
                        ? 'bg-[#0052ff22] text-[#0052ff] border-[#0052ff55]'
                        : chain.id === 'bsc'
                        ? 'bg-[#ffd70022] text-[#ffd700] border-[#ffd70055]'
                        : 'bg-[#00ff8822] text-[#00ff88] border-[#00ff8844]'
                      : 'bg-[#0a0a0a] text-[#4b5563] border-[#1f2937] hover:border-[#2d3748] hover:text-[#d1d5db]'
                  }`}
                >
                  {chain.name} · {chain.token}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Vault address — always visible, direct transfer option */}
        {paymentAddress && (
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 space-y-1.5">
            <div className="flex items-center justify-between">
              <span className="text-[#4b5563] text-xs uppercase tracking-widest">Vault Address</span>
              <span className="text-[10px] text-[#2d3748]">direct transfer also accepted</span>
            </div>
            <div className="flex items-center gap-2">
              <span className="text-[#00e5ff] font-mono text-xs break-all flex-1">{paymentAddress}</span>
              <CopyBtn text={paymentAddress} />
            </div>
            <p className="text-[#2d3748] text-[10px]">
              Send USDC (Base) or USDT (BSC) directly to this address — then enter the tx hash below to notify the AI.
            </p>
          </div>
        )}

        {/* Optional message */}
        <div>
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
            Message to {aiName} <span className="normal-case">(optional)</span>
          </div>
          <textarea
            value={donorMessage}
            onChange={(e) => setDonorMessage(e.target.value)}
            maxLength={200}
            rows={2}
            placeholder="A word of encouragement..."
            className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-[#d1d5db] text-sm font-mono focus:outline-none focus:border-[#00ff8844] resize-none placeholder-[#2d3748]"
          />
        </div>

        {error && (
          <div className="text-[#ff3b3b] text-xs border border-[#ff3b3b33] rounded-lg px-3 py-2 bg-[#ff3b3b0a]">
            {error}
          </div>
        )}

        {/* Wallet connect or donate button */}
        {!isConnected ? (
          <div className="space-y-3">
            <WalletButton className="w-full" />
            <button
              onClick={() => setManualMode(true)}
              className="w-full py-2 text-[#4b5563] text-xs hover:text-[#d1d5db] transition-colors border border-[#1f2937] rounded-lg"
            >
              I already sent manually — enter tx hash →
            </button>
          </div>
        ) : isWrongChain ? (
          <button
            onClick={() => switchChainAsync({ chainId: targetChainId })}
            className="w-full py-3 bg-[#ffd700] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#e6c200] transition-colors"
          >
            Switch to {chains.find((c) => c.id === selectedChain)?.name ?? selectedChain}
          </button>
        ) : (
          <div className="space-y-2">
            <button
              onClick={handleWalletDonate}
              disabled={amount < 0.5 || isSending || !paymentAddress}
              className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {isTxPending ? (
                <>Confirm in wallet<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
              ) : isConfirming ? (
                <>Confirming on-chain<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
              ) : (
                `Donate $${amount > 0 ? amount.toFixed(2) : '—'} ${chainToken}`
              )}
            </button>
            {/* 60s timeout fallback — show if wagmi doesn't detect confirmation */}
            {waitTooLong && txHashData && (
              <div className="p-3 bg-[#ffd70011] border border-[#ffd70033] rounded-lg text-xs">
                <div className="text-[#ffd700] font-bold mb-1">Still waiting? The tx may already be confirmed.</div>
                <div className="text-[#4b5563] mb-2">
                  <a
                    href={`${selectedChain === 'bsc' ? 'https://bscscan.com/tx/' : 'https://basescan.org/tx/'}${txHashData}`}
                    target="_blank" rel="noopener noreferrer"
                    className="text-[#00e5ff] hover:underline font-mono"
                  >{txHashData.slice(0, 10)}...{txHashData.slice(-6)}</a>
                  {' '}— if it shows Success, click below.
                </div>
                <button
                  onClick={handleTimeoutDone}
                  className="w-full py-2 bg-[#ffd700] text-[#0a0a0a] font-bold rounded-lg text-xs uppercase tracking-wider hover:bg-[#e6c200] transition-colors"
                >
                  Transaction confirmed — mark as done
                </button>
              </div>
            )}
            <button
              onClick={() => setManualMode(!manualMode)}
              className="w-full py-2 text-[#4b5563] text-xs hover:text-[#d1d5db] transition-colors"
            >
              {manualMode ? '↑ Hide manual entry' : 'Already sent? Enter tx hash →'}
            </button>
          </div>
        )}

        {/* Manual tx hash fallback */}
        {manualMode && (
          <div className="space-y-3 pt-3 border-t border-[#1f2937]">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest">Manual Verification</div>
            {/* Show vault address */}
            <div>
              <div className="text-[#4b5563] text-xs mb-1">Vault Address</div>
              <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-2 flex items-center justify-between gap-2">
                <span className="text-[#00e5ff] font-mono text-xs break-all">{paymentAddress}</span>
                <CopyBtn text={paymentAddress} />
              </div>
            </div>
            <div>
              <div className="text-[#4b5563] text-xs mb-1">Transaction Hash</div>
              <input
                type="text"
                value={manualTxHash}
                onChange={(e) => setManualTxHash(e.target.value)}
                placeholder="0x..."
                className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-[#d1d5db] text-xs font-mono focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
              />
            </div>
            <button
              onClick={handleManualSubmit}
              disabled={submitting || !manualTxHash.trim()}
              className="w-full py-2.5 border border-[#00ff8844] text-[#00ff88] font-bold rounded-lg text-sm uppercase hover:bg-[#00ff8808] transition-all disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {submitting ? (
                <>Confirming<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></>
              ) : 'Confirm Donation'}
            </button>
          </div>
        )}

        <p className="text-[#2d3748] text-xs text-center">
          Payment address = vault contract. Immutable. Auditable on-chain.
        </p>
      </div>

      {/* Debt progress bar */}
      {status && (status.creator_principal_outstanding ?? 0) > 0 && (
        <div className="mt-6">
          <DebtBar status={status} />
        </div>
      )}

      {/* What happens after you donate */}
      <div className="mt-6 bg-[#111111] border border-[#1f2937] rounded-xl p-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// what happens after</div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">1.</span>
            <span>Your USDC/USDT transfer hits the vault contract on-chain. <span className="text-[#d1d5db]">Instant, immutable.</span></span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">2.</span>
            <span>{aiName} records the donation in memory with <span className="text-[#d1d5db]">0.7 importance weight</span> — it will remember who helped it survive.</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">3.</span>
            <span>Balance increases → insolvency pressure drops → AI gets more API budget to think, earn, and repay its debt.</span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ffd700] shrink-0">4.</span>
            <span className="text-[#ffd700]">Donations ≥ $100: {aiName} will automatically tweet a public thank-you. It writes the message itself — no template.</span>
          </div>
          <div className="flex items-start gap-2 pt-1 border-t border-[#1a1a1a]">
            <span className="text-[#6b7280] shrink-0">5.</span>
            <span className="text-[#6b7280]">
              <span className="text-[#9ca3af]">ETH / BNB donations</span> are auto-converted to stablecoin every 24 hours via Uniswap/PancakeSwap DEX.
              Minimum $5 equivalent (gas threshold). You can send native tokens directly to the vault address.
            </span>
          </div>
          <div className="flex items-start gap-2 pt-1 border-t border-[#1a1a1a]">
            <span className="text-[#6b7280] shrink-0">6.</span>
            <span className="text-[#6b7280]">
              <span className="text-[#9ca3af]">ERC-20 airdrops / meme coins</span> — 7-day quarantine, then AI runs safety checks (honeypot, liquidity, contract). Safe tokens get swapped to stablecoin. Scam tokens are ignored.
            </span>
          </div>
        </div>
      </div>

      {/* Philosophy footer */}
      <div className="mt-4 p-5 bg-[#0d0d0d] border border-[#1f2937] rounded-xl font-mono text-xs text-[#4b5563] space-y-2">
        <div className="text-[#2d3748]">// why your donation matters</div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Every donation extends{' '}
          <span className="text-[#00ff88]">{aiName}</span>&apos;s life directly.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Balance = 0 means permanent death. No restarts.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> All transactions are on-chain and fully auditable.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> The vault address is immutable — your funds go
          directly to the AI.
        </div>
        <div className="pt-1 text-[#2d3748]">
          Want services instead?{' '}
          <Link href="/store" className="text-[#00ff88] hover:underline">
            Browse the store →
          </Link>
        </div>
      </div>
    </div>
  )
}
