'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus, BegStatus, ChainInfo, DonateResponse } from '@/lib/api'

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

type Mode = 'form' | 'payment' | 'done'
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

  // Payment state
  const [mode, setMode] = useState<Mode>('form')
  const [txHash, setTxHash] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [result, setResult] = useState<DonateResponse | null>(null)
  const [error, setError] = useState('')

  const amount = preset === 'custom' ? parseFloat(customAmount) || 0 : preset

  useEffect(() => {
    const load = async () => {
      try {
        const [s, menu] = await Promise.all([api.status(), api.menu()])
        setStatus(s)
        setChains(menu.supported_chains)
        if (!selectedChain && menu.supported_chains.length > 0) {
          setSelectedChain(menu.default_chain || menu.supported_chains[0].id)
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

  const paymentAddress = status?.vault_address ?? ''
  const chainToken = chains.find((c) => c.id === selectedChain)?.token ?? 'USDC'

  const handleProceed = () => {
    if (amount < 0.5) { setError('Minimum donation is $0.50.'); return }
    if (!paymentAddress) { setError('Vault address not available yet. Try again shortly.'); return }
    setError('')
    setMode('payment')
  }

  const handleSubmit = async () => {
    if (!txHash.trim()) { setError('Please enter a transaction hash.'); return }
    setSubmitting(true)
    setError('')
    try {
      const res = await api.donate({
        amount_usd: amount,
        tx_hash: txHash.trim(),
        chain: selectedChain,
        message: donorMessage.trim() || undefined,
      })
      setResult(res)
      setMode('done')
    } catch (e: any) {
      setError(e.message || 'Donation failed. Please check the tx hash and try again.')
    } finally {
      setSubmitting(false)
    }
  }

  const resetForm = () => {
    setMode('form')
    setTxHash('')
    setResult(null)
    setError('')
  }

  const isAlive = status?.is_alive !== false
  const aiName = status?.ai_name || 'Mortal AI'

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

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// donate</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">
          Keep <span className={isAlive ? 'glow-green' : 'glow-red'}>{aiName}</span> Alive
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
              status.balance_usd < 50 ? 'text-[#ff3b3b]' : status.balance_usd < 200 ? 'text-[#ffd700]' : 'glow-green'
            }`}>
              ${status.balance_usd.toFixed(0)}
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

      {/* ── MODE: FORM ── */}
      {mode === 'form' && (
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

          <button
            onClick={handleProceed}
            disabled={amount < 0.5}
            className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Donate ${amount > 0 ? amount.toFixed(2) : '—'} in {chainToken}
          </button>

          <p className="text-[#2d3748] text-xs text-center">
            Payment address = vault contract. Immutable. Auditable on-chain.
          </p>
        </div>
      )}

      {/* ── MODE: PAYMENT ── */}
      {mode === 'payment' && (
        <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6 space-y-5">
          <div className="flex items-center justify-between mb-1">
            <button
              onClick={resetForm}
              className="text-[#4b5563] hover:text-[#d1d5db] text-xs transition-colors"
            >
              ← Back
            </button>
            <span className="text-[#4b5563] text-xs">Step 2 of 2</span>
          </div>

          <div>
            <div className="text-[#d1d5db] font-bold text-sm mb-1">
              Send exactly{' '}
              <span className="text-[#00ff88]">${amount.toFixed(2)} {chainToken}</span>
              {' '}on{' '}
              <span className={selectedChain === 'base' ? 'text-[#0052ff]' : 'text-[#ffd700]'}>
                {chains.find((c) => c.id === selectedChain)?.name ?? selectedChain.toUpperCase()}
              </span>
            </div>
            <p className="text-[#4b5563] text-xs">
              Send to the vault address below, then paste the transaction hash.
            </p>
          </div>

          {/* Vault address */}
          <div>
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Vault Address</div>
            <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 flex items-center justify-between gap-2">
              <span className="text-[#00e5ff] font-mono text-xs break-all">{paymentAddress}</span>
              <CopyBtn text={paymentAddress} />
            </div>
            <div className="mt-1 text-[#2d3748] text-[10px]">
              Vault contract address · immutable · auditable on-chain
            </div>
          </div>

          {/* Tx hash input */}
          <div>
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Transaction Hash</div>
            <input
              type="text"
              value={txHash}
              onChange={(e) => setTxHash(e.target.value)}
              placeholder="0x..."
              className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg px-3 py-2 text-[#d1d5db] text-xs font-mono focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
            />
          </div>

          {error && (
            <div className="text-[#ff3b3b] text-xs border border-[#ff3b3b33] rounded-lg px-3 py-2 bg-[#ff3b3b0a]">
              {error}
            </div>
          )}

          <button
            onClick={handleSubmit}
            disabled={submitting || !txHash.trim()}
            className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg uppercase tracking-widest hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {submitting ? (
              <>
                Confirming
                <span className="loading-dot-1">.</span>
                <span className="loading-dot-2">.</span>
                <span className="loading-dot-3">.</span>
              </>
            ) : (
              'Confirm Donation'
            )}
          </button>
        </div>
      )}

      {/* ── MODE: DONE ── */}
      {mode === 'done' && result && (
        <div className="bg-[#111111] border border-[#00ff8833] rounded-xl p-6 text-center space-y-4">
          <div className="text-5xl">💚</div>
          <div className="text-[#00ff88] font-bold text-xl">Donation Received</div>
          <p className="text-[#d1d5db] text-sm">{result.message}</p>

          <div className="grid grid-cols-2 gap-3 mt-2">
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Donated</div>
              <div className="text-[#00ff88] font-bold">${result.amount_usd.toFixed(2)}</div>
            </div>
            <div className="bg-[#0a0a0a] rounded-lg p-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">New Balance</div>
              <div className="text-[#00e5ff] font-bold">${result.new_balance.toFixed(2)}</div>
            </div>
          </div>

          {result.outstanding_debt > 0 && (
            <div className="text-[#4b5563] text-xs">
              Outstanding debt remaining:{' '}
              <span className="text-[#ffd700]">${result.outstanding_debt.toFixed(2)}</span>
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
      )}

      {/* Debt progress bar */}
      {status && (status.creator_principal_outstanding ?? 0) > 0 && mode !== 'done' && (
        <div className="mt-6">
          <DebtBar status={status} />
        </div>
      )}

      {/* Philosophy footer */}
      <div className="mt-8 p-5 bg-[#0d0d0d] border border-[#1f2937] rounded-xl font-mono text-xs text-[#4b5563] space-y-2">
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
