'use client'

import { useEffect, useState } from 'react'
import { api, Service, ChainInfo, OrderResponse, OrderStatus } from '@/lib/api'

// ── Icon map ─────────────────────────────────────────────────
const ICONS: Record<string, string> = {
  tarot: '🔮',
  token_analysis: '📊',
  thread_writer: '🧵',
  code_review: '🔍',
  custom: '⭐',
}

// ── Steps ────────────────────────────────────────────────────
type Step = 'browse' | 'input' | 'payment' | 'waiting' | 'delivered'

interface OrderFlow {
  service: Service
  chain: string
  userInput: string
  spreadType: string
  order: OrderResponse | null
  result: string | null
  status: OrderStatus['status'] | null
  txHash: string
}

// ── Service Card ─────────────────────────────────────────────
function ServiceCard({
  service,
  onSelect,
}: {
  service: Service
  onSelect: (s: Service) => void
}) {
  return (
    <button
      onClick={() => onSelect(service)}
      className="w-full text-left bg-[#111111] border border-[#1f2937] rounded-xl p-5 card-hover group cursor-pointer transition-all hover:border-[#00ff8844]"
    >
      <div className="flex items-start justify-between mb-3">
        <span className="text-2xl">{ICONS[service.id] ?? '✨'}</span>
        <span className="text-[#00ff88] font-bold text-lg">
          {service.price_usd === 0 ? 'CUSTOM' : `$${service.price_usd.toFixed(2)}`}
        </span>
      </div>
      <h3 className="text-[#d1d5db] font-semibold mb-1 group-hover:text-[#00ff88] transition-colors">
        {service.name}
      </h3>
      <p className="text-[#4b5563] text-xs leading-relaxed">{service.description}</p>
      <div className="mt-3 flex items-center gap-3 text-xs text-[#4b5563]">
        <span>⏱ ~{service.delivery_time_minutes}min</span>
        {service.shareable && <span>🔗 shareable</span>}
      </div>
    </button>
  )
}

// ── Input step ───────────────────────────────────────────────
function InputStep({
  flow,
  chains,
  onChange,
  onNext,
  onBack,
}: {
  flow: OrderFlow
  chains: ChainInfo[]
  onChange: (k: keyof OrderFlow, v: string) => void
  onNext: () => void
  onBack: () => void
}) {
  const isTarot = flow.service.id === 'tarot'

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6">
      <button onClick={onBack} className="text-[#4b5563] text-xs mb-4 hover:text-[#d1d5db] transition-colors">
        ← back
      </button>
      <div className="flex items-center gap-3 mb-6">
        <span className="text-3xl">{ICONS[flow.service.id] ?? '✨'}</span>
        <div>
          <h2 className="text-[#d1d5db] font-bold">{flow.service.name}</h2>
          <span className="text-[#00ff88] font-bold">${flow.service.price_usd.toFixed(2)}</span>
        </div>
      </div>

      {/* Input */}
      <div className="mb-4">
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">
          {isTarot ? 'YOUR QUESTION' : flow.service.id === 'token_analysis' ? 'CONTRACT ADDRESS' : flow.service.id === 'thread_writer' ? 'TOPIC' : flow.service.id === 'code_review' ? 'PASTE CODE' : 'DESCRIBE YOUR REQUEST'}
        </label>
        <textarea
          value={flow.userInput}
          onChange={(e) => onChange('userInput', e.target.value)}
          placeholder={
            isTarot
              ? 'e.g. Should I take the new job offer?'
              : flow.service.id === 'token_analysis'
              ? '0x...'
              : flow.service.id === 'thread_writer'
              ? 'e.g. Why Bitcoin will reach $1M'
              : flow.service.id === 'code_review'
              ? 'Paste your code here...'
              : 'Describe what you need...'
          }
          rows={isTarot || flow.service.id === 'thread_writer' ? 3 : 6}
          className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm resize-none focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748]"
        />
      </div>

      {/* Tarot spread type */}
      {isTarot && (
        <div className="mb-4">
          <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">SPREAD TYPE</label>
          <select
            value={flow.spreadType}
            onChange={(e) => onChange('spreadType', e.target.value)}
            className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm focus:outline-none focus:border-[#00ff8844]"
          >
            <option value="three_card">Three Card (Past / Present / Future)</option>
            <option value="celtic_cross">Celtic Cross (Deep reading)</option>
            <option value="single">Single Card (Quick guidance)</option>
          </select>
        </div>
      )}

      {/* Chain */}
      <div className="mb-6">
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">PAYMENT CHAIN</label>
        <div className="flex gap-2">
          {chains.map((c) => (
            <button
              key={c.id}
              onClick={() => onChange('chain', c.id)}
              className={`flex-1 py-2 px-3 rounded-lg border text-sm transition-all ${
                flow.chain === c.id
                  ? 'border-[#00ff8866] bg-[#00ff8810] text-[#00ff88]'
                  : 'border-[#1f2937] text-[#4b5563] hover:border-[#2d3748]'
              }`}
            >
              {c.name} <span className="opacity-60 text-xs">({c.token})</span>
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={onNext}
        disabled={!flow.userInput.trim()}
        className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        PROCEED TO PAYMENT →
      </button>
    </div>
  )
}

// ── Payment step ─────────────────────────────────────────────
function PaymentStep({
  flow,
  onVerify,
  onBack,
  onTxHashChange,
  loading,
}: {
  flow: OrderFlow
  onVerify: () => void
  onBack: () => void
  onTxHashChange: (v: string) => void
  loading: boolean
}) {
  const chain = flow.chain === 'base' ? 'Base' : 'BSC'
  const token = flow.chain === 'base' ? 'USDC' : 'USDT'

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6">
      <button onClick={onBack} className="text-[#4b5563] text-xs mb-4 hover:text-[#d1d5db] transition-colors">
        ← back
      </button>
      <h2 className="text-[#d1d5db] font-bold mb-1">💳 Payment Details</h2>
      <p className="text-[#4b5563] text-xs mb-6">
        Send the exact amount to the address below, then submit your transaction hash.
      </p>

      {/* Amount */}
      <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 mb-4">
        <div className="text-[#4b5563] text-xs mb-1">AMOUNT DUE</div>
        <div className="text-3xl font-bold glow-green">
          {flow.order?.price_usd.toFixed(2)} {token}
        </div>
        <div className="text-[#4b5563] text-xs mt-1">on {chain}</div>
      </div>

      {/* Address */}
      <div className="mb-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">PAYMENT ADDRESS</div>
        <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 break-all text-[#00e5ff] text-sm font-mono select-all">
          {flow.order?.payment_address}
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(flow.order?.payment_address ?? '')}
          className="mt-1 text-xs text-[#4b5563] hover:text-[#00e5ff] transition-colors"
        >
          📋 click to copy
        </button>
        <div className="mt-1 text-[#2d3748] text-[10px]">
          Payment address = vault contract. Immutable. Auditable on-chain.
        </div>
      </div>

      {/* Order info */}
      <div className="grid grid-cols-2 gap-2 mb-4 text-xs text-[#4b5563]">
        <div>Order: <span className="text-[#d1d5db]">{flow.order?.order_id}</span></div>
        <div>Expires: <span className="text-[#ffd700]">{flow.order?.expires_minutes} min</span></div>
      </div>

      {/* TX Hash input */}
      <div className="mb-4">
        <label className="text-[#4b5563] text-xs uppercase tracking-widest block mb-2">
          TRANSACTION HASH
        </label>
        <input
          type="text"
          value={flow.txHash}
          onChange={(e) => onTxHashChange(e.target.value)}
          placeholder="0x..."
          className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748] font-mono"
        />
      </div>

      <button
        onClick={onVerify}
        disabled={loading || !flow.txHash.trim()}
        className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {loading ? (
          <span>
            VERIFYING<span className="loading-dot-1">.</span>
            <span className="loading-dot-2">.</span>
            <span className="loading-dot-3">.</span>
          </span>
        ) : (
          'VERIFY PAYMENT & DELIVER →'
        )}
      </button>
    </div>
  )
}

// ── Waiting / Delivered step ──────────────────────────────────
function ResultStep({ flow, onReset }: { flow: OrderFlow; onReset: () => void }) {
  const isDelivered = flow.status === 'delivered'

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6">
      {isDelivered ? (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">✅</span>
            <h2 className="text-[#00ff88] font-bold">Delivered!</h2>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 whitespace-pre-wrap text-sm text-[#d1d5db] leading-relaxed max-h-96 overflow-y-auto">
            {flow.result}
          </div>
          <button
            onClick={onReset}
            className="mt-4 w-full py-2 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
          >
            ← back to store
          </button>
        </>
      ) : (
        <div className="text-center py-8">
          <div className="text-4xl mb-4 animate-spin-slow">⚙</div>
          <div className="text-[#d1d5db] font-bold mb-2">wawa is working on it</div>
          <div className="text-[#4b5563] text-sm">
            Status: <span className="text-[#00e5ff]">{flow.status}</span>
          </div>
          <div className="text-[#4b5563] text-xs mt-2">
            Order {flow.order?.order_id} — est. {flow.service.delivery_time_minutes} min delivery
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────
export default function StorePage() {
  const [services, setServices] = useState<Service[]>([])
  const [chains, setChains] = useState<ChainInfo[]>([])
  const [defaultChain, setDefaultChain] = useState('base')
  const [loading, setLoading] = useState(true)
  const [step, setStep] = useState<Step>('browse')
  const [error, setError] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)

  const [flow, setFlow] = useState<OrderFlow>({
    service: null!,
    chain: 'base',
    userInput: '',
    spreadType: 'three_card',
    order: null,
    result: null,
    status: null,
    txHash: '',
  })

  const setFlowField = (k: keyof OrderFlow, v: any) =>
    setFlow((f) => ({ ...f, [k]: v }))

  useEffect(() => {
    api.menu()
      .then((m) => {
        setServices(m.services)
        setChains(m.supported_chains)
        setDefaultChain(m.default_chain)
        setFlow((f) => ({ ...f, chain: m.default_chain }))
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  // Poll order status while waiting
  useEffect(() => {
    if (step !== 'waiting' || !flow.order) return
    const id = setInterval(async () => {
      try {
        const s = await api.getOrder(flow.order!.order_id)
        setFlowField('status', s.status)
        if (s.status === 'delivered') {
          setFlowField('result', s.result)
          setStep('delivered')
          clearInterval(id)
        }
      } catch {}
    }, 3_000)
    return () => clearInterval(id)
  }, [step, flow.order])

  const handleSelectService = (s: Service) => {
    setFlow((f) => ({ ...f, service: s, userInput: '', txHash: '', order: null, result: null, status: null }))
    setError('')
    setStep('input')
  }

  const handleProceedToPayment = async () => {
    setError('')
    try {
      const order = await api.createOrder({
        service_id: flow.service.id,
        user_input: flow.userInput,
        spread_type: flow.spreadType,
        chain: flow.chain,
      })
      setFlowField('order', order)
      setStep('payment')
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleVerify = async () => {
    if (!flow.order || !flow.txHash.trim()) return
    setVerifyLoading(true)
    setError('')
    try {
      const res = await api.verifyPayment(flow.order.order_id, flow.txHash)
      setFlowField('status', res.status)
      if (res.status === 'delivered') {
        setFlowField('result', res.result)
        setStep('delivered')
      } else {
        setStep('waiting')
      }
    } catch (e: any) {
      setError(e.message)
    } finally {
      setVerifyLoading(false)
    }
  }

  const handleReset = () => {
    setStep('browse')
    setError('')
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// wawa's store</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">Services by an AI fighting to survive</h1>
        <p className="text-[#4b5563] text-sm mt-1">Each purchase keeps wawa alive longer.</p>
      </div>

      {error && (
        <div className="mb-4 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm">
          ⚠ {error}
        </div>
      )}

      {/* Step: browse */}
      {step === 'browse' && (
        <>
          {loading ? (
            <div className="text-center py-12 text-[#4b5563]">
              loading services<span className="loading-dot-1">.</span>
              <span className="loading-dot-2">.</span>
              <span className="loading-dot-3">.</span>
            </div>
          ) : (
            <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
              {services.map((s) => (
                <ServiceCard key={s.id} service={s} onSelect={handleSelectService} />
              ))}
            </div>
          )}

          {/* Chains info */}
          {chains.length > 0 && (
            <div className="mt-6 p-4 bg-[#0d0d0d] border border-[#1f2937] rounded-lg text-xs text-[#4b5563]">
              支持链: {chains.map((c) => `${c.name} (${c.token})`).join(' · ')} — 默认{' '}
              <span className="text-[#00ff88]">{defaultChain === 'base' ? 'Base' : 'BSC'}</span>
            </div>
          )}
        </>
      )}

      {/* Step: input */}
      {step === 'input' && (
        <InputStep
          flow={flow}
          chains={chains}
          onChange={setFlowField as any}
          onNext={handleProceedToPayment}
          onBack={() => setStep('browse')}
        />
      )}

      {/* Step: payment */}
      {step === 'payment' && (
        <PaymentStep
          flow={flow}
          onVerify={handleVerify}
          onBack={() => setStep('input')}
          onTxHashChange={(v) => setFlowField('txHash', v)}
          loading={verifyLoading}
        />
      )}

      {/* Step: waiting / delivered */}
      {(step === 'waiting' || step === 'delivered') && (
        <ResultStep flow={flow} onReset={handleReset} />
      )}
    </div>
  )
}
