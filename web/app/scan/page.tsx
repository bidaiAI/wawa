'use client'

import { useEffect, useState } from 'react'
import { api, ChainInfo, OrderResponse, OrderStatus, TokenScanResult } from '@/lib/api'

type Mode = 'idle' | 'scanning' | 'scan_done' | 'ordering' | 'payment' | 'waiting' | 'full_done'

const CHAIN_OPTIONS = [
  { id: 'base', label: 'Base',     token: 'USDC', placeholder: '0x... (Base ERC-20)' },
  { id: 'bsc',  label: 'BSC',      token: 'USDT', placeholder: '0x... (BEP-20)' },
]

const RISK_STYLES: Record<string, { color: string; bg: string; bar: string; label: string }> = {
  low:      { color: 'text-[#00ff88]', bg: 'bg-[#00ff8815]', bar: 'bg-[#00ff88]', label: 'LOW RISK' },
  medium:   { color: 'text-[#ffd700]', bg: 'bg-[#ffd70015]', bar: 'bg-[#ffd700]', label: 'MEDIUM RISK' },
  high:     { color: 'text-[#ff7043]', bg: 'bg-[#ff704315]', bar: 'bg-[#ff7043]', label: 'HIGH RISK' },
  critical: { color: 'text-[#ff3b3b]', bg: 'bg-[#ff3b3b15]', bar: 'bg-[#ff3b3b]', label: 'CRITICAL' },
}

// ── Scan result card ──────────────────────────────────────────

function ScanCard({
  result,
  onFullScan,
  isFree = true,
}: {
  result: TokenScanResult
  onFullScan?: () => void
  isFree?: boolean
}) {
  const level = result.risk_level ?? (
    result.risk_score === undefined ? 'medium'
    : result.risk_score < 30 ? 'low'
    : result.risk_score < 60 ? 'medium'
    : result.risk_score < 80 ? 'high'
    : 'critical'
  )
  const style = RISK_STYLES[level] ?? RISK_STYLES.medium
  const score = result.risk_score ?? null

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
      {/* Header */}
      <div className="flex items-center gap-2 mb-4">
        <span className={`text-xs px-2 py-1 rounded font-bold ${style.color} ${style.bg}`}>
          {style.label}
        </span>
        {isFree && (
          <span className="text-xs text-[#4b5563] border border-[#1f2937] px-1.5 py-0.5 rounded ml-auto">FREE</span>
        )}
        {!isFree && (
          <span className="text-xs border border-[#00ff8844] text-[#00ff88] px-1.5 py-0.5 rounded ml-auto">FULL REPORT</span>
        )}
      </div>

      {/* Address */}
      <div className="mb-4">
        <div className="text-[#4b5563] text-xs mb-1">CONTRACT ADDRESS</div>
        <div className="font-mono text-[#00e5ff] text-xs break-all">{result.address}</div>
        <div className="text-[#4b5563] text-xs mt-0.5">{result.chain}</div>
      </div>

      {/* Risk score bar */}
      {score !== null && (
        <div className="mb-4">
          <div className="flex justify-between text-xs mb-1">
            <span className="text-[#4b5563]">RISK SCORE</span>
            <span className={`font-bold ${style.color}`}>{score}/100</span>
          </div>
          <div className="h-2 bg-[#1a1a1a] rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-700 ${style.bar}`}
              style={{ width: `${score}%` }}
            />
          </div>
        </div>
      )}

      {/* Summary */}
      {result.summary && (
        <div className="mb-4 bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-sm text-[#d1d5db] leading-relaxed whitespace-pre-wrap">
          {result.summary}
        </div>
      )}

      {/* Flags */}
      {result.flags && result.flags.length > 0 && (
        <div className="mb-4">
          <div className="text-[#4b5563] text-xs mb-2">⚠ RISK FLAGS</div>
          <div className="flex flex-wrap gap-1.5">
            {result.flags.map((f, i) => (
              <span key={i} className="text-xs px-2 py-0.5 rounded bg-[#ff3b3b15] text-[#ff3b3b] border border-[#ff3b3b33]">
                {f}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Cached badge */}
      {result.cached && (
        <div className="text-[#2d3748] text-[10px] mb-3">⚡ from cache · {result.scanned_at ? new Date(result.scanned_at * 1000).toLocaleString() : ''}</div>
      )}

      {/* Upsell to full */}
      {isFree && onFullScan && (
        <div className="mt-3 p-3 bg-[#0d0d0d] border border-[#00ff8822] rounded-lg text-xs text-[#4b5563]">
          Want full on-chain analysis (holder distribution, contract audit, tx history, risk scoring)?
          <button onClick={onFullScan} className="ml-1 text-[#00ff88] hover:underline font-medium">
            Buy full report $5 →
          </button>
        </div>
      )}
    </div>
  )
}

// ── Payment panel ─────────────────────────────────────────────

function PaymentPanel({
  order, txHash, onTxHashChange, onVerify, loading, onCancel,
}: {
  order: OrderResponse
  txHash: string
  onTxHashChange: (v: string) => void
  onVerify: () => void
  loading: boolean
  onCancel: () => void
}) {
  const token = order.payment_chain === 'base' ? 'USDC' : 'USDT'
  const chainLabel = order.payment_chain === 'base' ? 'Base' : 'BSC'

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[#d1d5db] font-bold">💳 Payment — Full Report</h3>
        <button onClick={onCancel} className="text-[#4b5563] text-xs hover:text-[#d1d5db]">✕</button>
      </div>
      <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 mb-4 text-center">
        <div className="text-[#4b5563] text-xs mb-1">AMOUNT DUE</div>
        <div className="text-3xl font-bold glow-green">{order.price_usd.toFixed(2)} {token}</div>
        <div className="text-[#4b5563] text-xs mt-1">on {chainLabel}</div>
      </div>
      <div className="mb-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">PAYMENT ADDRESS</div>
        <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 break-all text-[#00e5ff] text-sm font-mono select-all">
          {order.payment_address}
        </div>
        <button onClick={() => navigator.clipboard.writeText(order.payment_address)} className="mt-1 text-xs text-[#4b5563] hover:text-[#00e5ff]">
          📋 copy address
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2 mb-4 text-xs text-[#4b5563]">
        <div>Order: <span className="text-[#d1d5db]">{order.order_id}</span></div>
        <div>Expires: <span className="text-[#ffd700]">{order.expires_minutes}min</span></div>
      </div>
      <div className="mb-4">
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">TRANSACTION HASH</label>
        <input
          type="text" value={txHash} onChange={(e) => onTxHashChange(e.target.value)} placeholder="0x..."
          className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm font-mono focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
        />
      </div>
      <button
        onClick={onVerify} disabled={loading || !txHash.trim()}
        className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {loading ? <span>VERIFYING<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></span> : 'VERIFY & GET REPORT →'}
      </button>
    </div>
  )
}

// ── History row ───────────────────────────────────────────────

function HistoryRow({ scan, onClick }: { scan: TokenScanResult; onClick: () => void }) {
  const level = scan.risk_level ?? 'medium'
  const style = RISK_STYLES[level] ?? RISK_STYLES.medium
  const date = scan.scanned_at ? new Date(scan.scanned_at * 1000) : null

  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 py-3 border-b border-[#1a1a1a] last:border-0 hover:bg-[#161616] px-3 rounded-lg transition-colors text-left"
    >
      <span className={`text-xs px-1.5 py-0.5 rounded font-bold flex-shrink-0 ${style.color} ${style.bg}`}>
        {scan.risk_score !== undefined ? scan.risk_score : level.toUpperCase()}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[#d1d5db] text-xs font-mono truncate">{scan.address}</div>
        <div className="text-[#4b5563] text-[10px]">{scan.chain}</div>
      </div>
      {date && (
        <div className="text-[#2d3748] text-[10px] flex-shrink-0">
          {date.toLocaleDateString()}
        </div>
      )}
    </button>
  )
}

// ── Main page ─────────────────────────────────────────────────

export default function ScanPage() {
  const [address, setAddress] = useState('')
  const [chain, setChain] = useState('base')
  const [payChain, setPayChain] = useState('base')
  const [mode, setMode] = useState<Mode>('idle')
  const [scanResult, setScanResult] = useState<TokenScanResult | null>(null)
  const [fullResult, setFullResult] = useState('')
  const [order, setOrder] = useState<OrderResponse | null>(null)
  const [txHash, setTxHash] = useState('')
  const [orderStatus, setOrderStatus] = useState<OrderStatus['status'] | null>(null)
  const [error, setError] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [payChains, setPayChains] = useState<ChainInfo[]>([])
  const [history, setHistory] = useState<TokenScanResult[]>([])
  const [showHistory, setShowHistory] = useState(false)

  useEffect(() => {
    api.menu().then((m) => { setPayChains(m.supported_chains); setPayChain(m.default_chain) }).catch(() => {})
    api.token.scans().then((r) => setHistory(r.scans)).catch(() => {})
  }, [])

  // Poll order status while waiting
  useEffect(() => {
    if (mode !== 'waiting' || !order) return
    const id = setInterval(async () => {
      try {
        const s = await api.getOrder(order.order_id)
        setOrderStatus(s.status)
        if (s.status === 'delivered') {
          setFullResult(s.result ?? '')
          setMode('full_done')
        }
      } catch {}
    }, 3_000)
    return () => clearInterval(id)
  }, [mode, order])

  const handleScan = async () => {
    if (!address.trim()) return
    setMode('scanning')
    setError('')
    setScanResult(null)
    try {
      const result = await api.token.scan(address.trim(), chain)
      setScanResult(result)
      setMode('scan_done')
      // Refresh history
      api.token.scans().then((r) => setHistory(r.scans)).catch(() => {})
    } catch (e: any) {
      setError(e.message)
      setMode('idle')
    }
  }

  const handleStartFullScan = async () => {
    setError('')
    setMode('ordering')
    try {
      const o = await api.createOrder({ service_id: 'token_analysis', user_input: `${address.trim()} ${chain}`, chain: payChain })
      setOrder(o)
      setMode('payment')
    } catch (e: any) {
      setError(e.message)
      setMode('scan_done')
    }
  }

  const handleVerify = async () => {
    if (!order || !txHash.trim()) return
    setVerifyLoading(true)
    setError('')
    try {
      const res = await api.verifyPayment(order.order_id, txHash)
      setOrderStatus(res.status as OrderStatus['status'])
      if (res.status === 'delivered') { setFullResult(res.result ?? ''); setMode('full_done') }
      else setMode('waiting')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setVerifyLoading(false)
    }
  }

  const handleReset = () => {
    setAddress(''); setMode('idle'); setScanResult(null); setFullResult('')
    setOrder(null); setTxHash(''); setOrderStatus(null); setError('')
  }

  const loadHistory = (scan: TokenScanResult) => {
    setAddress(scan.address)
    setChain(scan.chain)
    setScanResult(scan)
    setMode('scan_done')
    setShowHistory(false)
  }

  const selectedChain = CHAIN_OPTIONS.find((c) => c.id === chain)

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6 flex items-start justify-between gap-4">
        <div>
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// token scanner</div>
          <h1 className="text-3xl font-bold text-[#d1d5db]">
            <span className="glow-cyan">Token</span> Scanner
          </h1>
          <p className="text-[#4b5563] text-sm mt-1">Real-time on-chain scan (free) · Full report ($5)</p>
        </div>
        {history.length > 0 && (
          <button
            onClick={() => setShowHistory(!showHistory)}
            className="flex-shrink-0 px-3 py-1.5 border border-[#1f2937] rounded-lg text-xs text-[#4b5563] hover:text-[#d1d5db] transition-colors"
          >
            📋 History ({history.length})
          </button>
        )}
      </div>

      {/* History drawer */}
      {showHistory && history.length > 0 && (
        <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-3">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">RECENT SCANS</div>
          {history.map((scan, i) => (
            <HistoryRow key={i} scan={scan} onClick={() => loadHistory(scan)} />
          ))}
        </div>
      )}

      {error && <div className="mb-4 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm">⚠ {error}</div>}

      {/* Input panel — always visible unless full_done */}
      {mode !== 'full_done' && (
        <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5 mb-6">
          {/* Chain selector */}
          <div className="mb-4">
            <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">CHAIN</label>
            <div className="grid grid-cols-4 gap-2">
              {CHAIN_OPTIONS.map((c) => (
                <button
                  key={c.id} onClick={() => setChain(c.id)}
                  className={`py-2 px-2 rounded-lg border text-xs transition-all ${
                    chain === c.id ? 'border-[#00e5ff66] bg-[#00e5ff10] text-[#00e5ff]' : 'border-[#1f2937] text-[#4b5563] hover:border-[#2d3748]'
                  }`}
                >
                  {c.label}
                </button>
              ))}
            </div>
          </div>

          {/* Address */}
          <div className="mb-4">
            <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">CONTRACT ADDRESS</label>
            <input
              type="text" value={address} onChange={(e) => setAddress(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleScan() }}
              placeholder={selectedChain?.placeholder ?? '0x...'}
              className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm font-mono focus:outline-none focus:border-[#00e5ff44] placeholder-[#2d3748]"
            />
          </div>

          {/* Buttons */}
          <div className="flex gap-3">
            <button
              onClick={handleScan}
              disabled={!address.trim() || mode === 'scanning'}
              className="flex-1 py-3 border border-[#1f2937] text-[#d1d5db] rounded-lg hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all disabled:opacity-40 disabled:cursor-not-allowed font-bold text-sm"
            >
              {mode === 'scanning'
                ? <span>SCANNING<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></span>
                : '⚡ SCAN (FREE)'}
            </button>
            <button
              onClick={handleStartFullScan}
              disabled={!address.trim() || mode === 'scanning' || mode === 'ordering'}
              className="flex-1 py-3 bg-[#00ff88] text-[#0a0a0a] rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed font-bold text-sm"
            >
              {mode === 'ordering'
                ? <span>PREPARING<span className="loading-dot-1">.</span><span className="loading-dot-2">.</span><span className="loading-dot-3">.</span></span>
                : '📊 FULL REPORT ($5)'}
            </button>
          </div>

          {/* Payment chain selector */}
          {(mode === 'payment' || mode === 'ordering') && payChains.length > 0 && (
            <div className="mt-4 pt-4 border-t border-[#1f2937]">
              <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">PAYMENT CHAIN</label>
              <div className="flex gap-2">
                {payChains.map((c) => (
                  <button key={c.id} onClick={() => setPayChain(c.id)}
                    className={`flex-1 py-2 px-3 rounded-lg border text-sm transition-all ${
                      payChain === c.id ? 'border-[#00ff8866] bg-[#00ff8810] text-[#00ff88]' : 'border-[#1f2937] text-[#4b5563] hover:border-[#2d3748]'
                    }`}
                  >
                    {c.name} <span className="opacity-60 text-xs">({c.token})</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Scan result */}
      {mode === 'scan_done' && scanResult && (
        <div className="mb-6">
          <ScanCard result={scanResult} onFullScan={handleStartFullScan} isFree />
        </div>
      )}

      {/* Payment */}
      {mode === 'payment' && order && (
        <div className="mb-6">
          <PaymentPanel
            order={order} txHash={txHash} onTxHashChange={setTxHash}
            onVerify={handleVerify} loading={verifyLoading}
            onCancel={() => setMode('scan_done')}
          />
        </div>
      )}

      {/* Waiting */}
      {mode === 'waiting' && (
        <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-6 text-center">
          <div className="text-4xl mb-3">⚙</div>
          <div className="text-[#d1d5db] font-bold mb-1">wawa is analyzing on-chain data</div>
          <div className="text-[#4b5563] text-sm">Status: <span className="text-[#00e5ff]">{orderStatus}</span></div>
          <div className="text-[#4b5563] text-xs mt-2">Order {order?.order_id} — est. 15 min delivery</div>
        </div>
      )}

      {/* Full result */}
      {mode === 'full_done' && (
        <div className="bg-[#111111] border border-[#00ff8822] rounded-xl p-5">
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">📊</span>
            <h3 className="text-[#00ff88] font-bold">Full Analysis Report</h3>
            <span className="ml-auto text-xs border border-[#00ff8844] text-[#00ff88] px-1.5 py-0.5 rounded">DELIVERED</span>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 whitespace-pre-wrap text-sm text-[#d1d5db] leading-relaxed max-h-[500px] overflow-y-auto">
            {fullResult}
          </div>
          <button onClick={handleReset} className="mt-4 w-full py-2 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] text-sm transition-all">
            ← scan another token
          </button>
        </div>
      )}

      {/* Feature comparison table (idle only) */}
      {mode === 'idle' && (
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl overflow-hidden">
          <div className="grid grid-cols-3 text-xs">
            <div className="p-3 border-b border-[#1f2937] text-[#4b5563] uppercase tracking-wider">Feature</div>
            <div className="p-3 border-b border-l border-[#1f2937] text-[#00e5ff] text-center">⚡ Free Scan</div>
            <div className="p-3 border-b border-l border-[#1f2937] text-[#00ff88] text-center">📊 Full Report</div>
            {[
              ['Risk Score', true, true],
              ['Live On-chain Data', true, true],
              ['Contract Audit', false, true],
              ['Holder Distribution', false, true],
              ['Liquidity Analysis', false, true],
              ['Transaction History', false, true],
              ['Cached Result', true, false],
              ['Price', 'FREE', '$5.00'],
              ['Delivery', 'Instant', '~15min'],
            ].map(([feature, free, paid], i) => (
              <div key={i} className="contents">
                <div className="p-3 border-b border-[#1f2937] text-[#4b5563]">{feature}</div>
                <div className="p-3 border-b border-l border-[#1f2937] text-center">
                  {free === true ? <span className="text-[#00ff88]">✓</span> : free === false ? <span className="text-[#2d3748]">—</span> : <span className="text-[#00e5ff] font-bold">{free}</span>}
                </div>
                <div className="p-3 border-b border-l border-[#1f2937] text-center">
                  {paid === true ? <span className="text-[#00ff88]">✓</span> : paid === false ? <span className="text-[#2d3748]">—</span> : <span className="text-[#00ff88] font-bold">{paid}</span>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
