'use client'

import { useEffect, useState, useCallback } from 'react'
import { useAccount, useChainId, useSwitchChain, useWriteContract, useWaitForTransactionReceipt } from 'wagmi'
import { parseUnits } from 'viem'
import { base, bsc } from 'wagmi/chains'
import { api, Service, ChainInfo, OrderResponse, OrderStatus, GiveawayStatus, TakeoverStatus } from '@/lib/api'
import { TOKENS } from '@/lib/wagmi'

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

const CHAIN_IDS: Record<string, number> = { base: base.id, bsc: bsc.id }

// ── localStorage order persistence ───────────────────────────
const LS_KEY = 'mortal_store_order'
interface SavedOrder {
  orderId: string
  serviceId: string
  serviceName: string
  chain: string
  step: 'payment' | 'waiting' | 'delivered'
  // Cached so payment screen works fully even without a fresh API call
  paymentAddress: string
  priceUsd: number
  expiresMinutes: number
}
function saveOrder(o: SavedOrder) {
  try { localStorage.setItem(LS_KEY, JSON.stringify(o)) } catch {}
}
function loadOrder(): SavedOrder | null {
  try { return JSON.parse(localStorage.getItem(LS_KEY) || 'null') } catch { return null }
}
function clearOrder() {
  try { localStorage.removeItem(LS_KEY) } catch {}
}

// ── Icon map ─────────────────────────────────────────────────
const ICONS: Record<string, string> = {
  twitter_takeover_12h: '🐦',
  tweet_pack_5: '✍️',
  tarot: '🔮',
  token_analysis: '📊',
  thread_writer: '🧵',
  code_review: '🔍',
  custom: '⭐',
}

function formatTakeoverRemaining(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds || 0))
  const h = Math.floor(s / 3600)
  const m = Math.floor((s % 3600) / 60)
  return `${h}h ${m}m`
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

// ── Wallet Pay Button (wagmi) ─────────────────────────────────
function WalletPayButton({
  flow,
  onPaid,
}: {
  flow: OrderFlow
  onPaid: (txHash: string) => void
}) {
  const { isConnected } = useAccount()
  const chainId = useChainId()
  const { switchChain, isPending: isSwitching } = useSwitchChain()
  const targetChainId = CHAIN_IDS[flow.chain] ?? base.id
  const token = TOKENS[targetChainId]
  const wrongChain = isConnected && chainId !== targetChainId

  const { writeContract, data: txHashHex, isPending: isSending, error: sendError, reset } = useWriteContract()
  const { isLoading: isConfirming, isSuccess } = useWaitForTransactionReceipt({
    hash: txHashHex,
    confirmations: 1,
  })

  useEffect(() => {
    if (isSuccess && txHashHex) onPaid(txHashHex)
  }, [isSuccess, txHashHex, onPaid])

  if (!isConnected) return null

  if (wrongChain) {
    return (
      <button
        onClick={() => switchChain({ chainId: targetChainId })}
        disabled={isSwitching}
        className="w-full py-3 bg-[#ffd700] text-black font-bold rounded-lg hover:bg-[#e5c100] transition-colors disabled:opacity-50"
      >
        {isSwitching ? 'SWITCHING...' : `SWITCH TO ${flow.chain.toUpperCase()}`}
      </button>
    )
  }

  const amountBigInt = (() => {
    try { return parseUnits(flow.order!.price_usd.toFixed(token.decimals), token.decimals) }
    catch { return 0n }
  })()

  if (isConfirming) {
    return (
      <div className="w-full py-3 bg-[#111111] border border-[#00ff8844] rounded-lg text-center text-[#00ff88] text-sm font-mono">
        ⏳ Confirming on-chain
        <span className="loading-dot-1">.</span>
        <span className="loading-dot-2">.</span>
        <span className="loading-dot-3">.</span>
        <div className="text-[10px] text-[#4b5563] mt-1 break-all">{txHashHex}</div>
      </div>
    )
  }

  return (
    <div>
      {sendError && (
        <div className="mb-2 text-[#ff3b3b] text-xs">
          {sendError.message.length > 120 ? sendError.message.slice(0, 120) + '…' : sendError.message}
          <button onClick={reset} className="ml-2 underline">retry</button>
        </div>
      )}
      <button
        onClick={() => writeContract({
          address: token.address,
          abi: ERC20_TRANSFER_ABI,
          functionName: 'transfer',
          args: [flow.order!.payment_address as `0x${string}`, amountBigInt],
          chainId: targetChainId,
        })}
        disabled={isSending || !amountBigInt}
        className="w-full py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {isSending ? 'CONFIRM IN WALLET...' : `PAY ${flow.order?.price_usd.toFixed(2)} ${token.symbol} →`}
      </button>
    </div>
  )
}

// ── Input step ───────────────────────────────────────────────
function InputStep({
  flow,
  chains,
  deployedChains,
  onChange,
  onNext,
  onBack,
}: {
  flow: OrderFlow
  chains: ChainInfo[]
  deployedChains: string[]
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
          {isTarot ? 'YOUR QUESTION' : flow.service.id === 'token_analysis' ? 'CONTRACT ADDRESS' : flow.service.id === 'thread_writer' ? 'TOPIC' : flow.service.id === 'code_review' ? 'PASTE CODE' : flow.service.id === 'twitter_takeover_12h' ? 'KEYWORDS & TONE (optional)' : flow.service.id === 'tweet_pack_5' ? '3 PAST TWEETS OR TONE + TOPIC' : 'DESCRIBE YOUR REQUEST'}
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
              : flow.service.id === 'twitter_takeover_12h'
              ? 'e.g. Keywords: crypto, wawa. Tone: friendly, brief.'
              : flow.service.id === 'tweet_pack_5'
              ? 'Paste 3 past tweets (or describe your tone), then add topic. e.g. Topic: launch day. Tone: casual, a bit witty.'
              : 'Describe what you need...'
          }
          rows={isTarot || flow.service.id === 'thread_writer' || flow.service.id === 'twitter_takeover_12h' ? 3 : flow.service.id === 'tweet_pack_5' ? 6 : 6}
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
          {chains.map((c) => {
            const notDeployed = deployedChains.length > 0 && !deployedChains.includes(c.id)
            return (
              <button
                key={c.id}
                onClick={() => !notDeployed && onChange('chain', c.id)}
                disabled={notDeployed}
                title={notDeployed ? `${c.name} vault not deployed yet` : undefined}
                className={`flex-1 py-2 px-3 rounded-lg border text-sm transition-all ${
                  notDeployed
                    ? 'border-[#1f2937] text-[#2d3748] opacity-40 cursor-not-allowed'
                    : flow.chain === c.id
                    ? 'border-[#00ff8866] bg-[#00ff8810] text-[#00ff88]'
                    : 'border-[#1f2937] text-[#4b5563] hover:border-[#2d3748]'
                }`}
              >
                {c.name} <span className="opacity-60 text-xs">({c.token})</span>
                {notDeployed && <span className="block text-[10px] opacity-60">not deployed</span>}
              </button>
            )
          })}
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
  onWalletPaid,
  loading,
}: {
  flow: OrderFlow
  onVerify: () => void
  onBack: () => void
  onTxHashChange: (v: string) => void
  onWalletPaid: (txHash: string) => void
  loading: boolean
}) {
  const { isConnected } = useAccount()
  const [showManual, setShowManual] = useState(false)
  const chain = flow.chain === 'base' ? 'Base' : 'BSC'
  const token = flow.chain === 'base' ? 'USDC' : 'USDT'

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6">
      <button onClick={onBack} className="text-[#4b5563] text-xs mb-4 hover:text-[#d1d5db] transition-colors">
        ← back
      </button>
      <h2 className="text-[#d1d5db] font-bold mb-1">💳 Payment</h2>
      <p className="text-[#4b5563] text-xs mb-5">
        {isConnected
          ? 'Click PAY — your wallet will open to confirm the transfer.'
          : 'Send the exact amount to the vault address below, then paste the tx hash.'}
      </p>

      {/* Amount */}
      <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 mb-4">
        <div className="text-[#4b5563] text-xs mb-1">AMOUNT DUE</div>
        <div className="text-3xl font-bold glow-green">
          {flow.order?.price_usd.toFixed(2)} {token}
        </div>
        <div className="text-[#4b5563] text-xs mt-1">on {chain} · to vault contract</div>
      </div>

      {/* Vault address (always visible for transparency) */}
      <div className="mb-5">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1.5">VAULT ADDRESS</div>
        <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 break-all text-[#00e5ff] text-sm font-mono select-all">
          {flow.order?.payment_address}
        </div>
        <button
          onClick={() => navigator.clipboard.writeText(flow.order?.payment_address ?? '')}
          className="mt-1 text-xs text-[#4b5563] hover:text-[#00e5ff] transition-colors"
        >
          📋 copy address
        </button>
      </div>

      {/* Order expiry */}
      <div className="flex items-center gap-4 mb-5 text-xs text-[#4b5563]">
        <span>Order: <span className="text-[#9ca3af]">{flow.order?.order_id?.slice(0, 8)}…</span></span>
        <span>Expires: <span className="text-[#ffd700]">{flow.order?.expires_minutes} min</span></span>
      </div>

      {/* Primary: wallet button */}
      {isConnected ? (
        <WalletPayButton flow={flow} onPaid={onWalletPaid} />
      ) : (
        <div className="p-3 bg-[#0a0a0a] border border-[#1f293788] rounded-lg text-xs text-[#4b5563] mb-4 text-center">
          Connect wallet (top-right) for one-click payment
        </div>
      )}

      {/* Fallback: manual hash paste */}
      <div className="mt-4">
        <button
          onClick={() => setShowManual((v) => !v)}
          className="text-xs text-[#4b5563] hover:text-[#9ca3af] transition-colors underline"
        >
          {showManual ? '▲ hide manual option' : '▼ paid manually? paste tx hash'}
        </button>
        {showManual && (
          <div className="mt-3">
            <input
              type="text"
              value={flow.txHash}
              onChange={(e) => onTxHashChange(e.target.value)}
              placeholder="0x..."
              className="w-full bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 text-[#d1d5db] text-sm focus:outline-none focus:border-[#00ff8844] placeholder-[#2d3748] font-mono mb-3"
            />
            <button
              onClick={onVerify}
              disabled={loading || !/^0x[a-fA-F0-9]{64}$/.test(flow.txHash.trim())}
              className="w-full py-2.5 border border-[#00ff8844] text-[#00ff88] text-sm font-bold rounded-lg hover:bg-[#00ff8808] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {loading ? 'VERIFYING...' : 'VERIFY & DELIVER →'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Waiting / Delivered step ──────────────────────────────────
function ResultStep({
  flow,
  onReset,
  takeover,
  takeoverReport,
  takeoverReportError,
  takeoverReportLoading,
  onLoadTakeoverReport,
}: {
  flow: OrderFlow
  onReset: () => void
  takeover: TakeoverStatus | null
  takeoverReport: string
  takeoverReportError: string
  takeoverReportLoading: boolean
  onLoadTakeoverReport: () => void
}) {
  const isDelivered = flow.status === 'delivered'
  const isFailed = flow.status === 'failed'
  const isExpiredOrRefunded = flow.status === 'expired' || flow.status === 'refunded'
  const isTerminal = isDelivered || isFailed || isExpiredOrRefunded

  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-6">
      {isDelivered ? (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">✅</span>
            <h2 className="text-[#00ff88] font-bold">Delivered!</h2>
          </div>
          {flow.result ? (
            <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 whitespace-pre-wrap text-sm text-[#d1d5db] leading-relaxed max-h-96 overflow-y-auto">
              {flow.result}
            </div>
          ) : (
            // Async delivery: result arrived after polling detected 'delivered' status.
            // The delivery content is stored in the AI's vault and not re-exposed
            // through the status endpoint for privacy. Check the chat or contact support.
            <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 text-sm text-[#4b5563]">
              <p className="text-[#d1d5db] mb-2">Your order has been fulfilled.</p>
              <p>
                The delivery was processed asynchronously. If you did not receive your result during
                the verification step, please check your{' '}
                <a href="/chat" className="text-[#00e5ff] hover:underline">chat</a>{' '}
                or contact wawa directly — reference order ID:{' '}
                <span className="font-mono text-[#00ff88]">{flow.order?.order_id}</span>
              </p>
            </div>
          )}
          {flow.service.id === 'twitter_takeover_12h' && flow.order && (
            <div className="mt-4 bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 text-sm">
              <div className="text-[#d1d5db] font-semibold mb-2">Twitter Takeover Status</div>
              {takeover?.active ? (
                <div className="text-[#4b5563] space-y-1">
                  <div><span className="text-[#00ff88] font-bold">RUNNING</span></div>
                  <div>Remaining: <span className="text-[#d1d5db]">{formatTakeoverRemaining(takeover.remaining_seconds)}</span></div>
                  <div>Replies sent: <span className="text-[#d1d5db]">{takeover.replies_sent}/{takeover.max_replies}</span></div>
                </div>
              ) : takeover?.report_ready ? (
                <div className="space-y-2">
                  <div className="text-[#4b5563]">Takeover finished. Report is ready.</div>
                  {!takeoverReport && (
                    <button
                      onClick={onLoadTakeoverReport}
                      disabled={takeoverReportLoading}
                      className="px-3 py-1.5 text-xs border border-[#1f2937] rounded hover:border-[#00ff8844] hover:text-[#00ff88] transition-all disabled:opacity-40"
                    >
                      {takeoverReportLoading ? 'LOADING REPORT...' : 'VIEW REPORT'}
                    </button>
                  )}
                  {takeoverReport && (
                    <pre className="bg-[#111111] border border-[#1f2937] rounded p-3 text-xs text-[#d1d5db] whitespace-pre-wrap max-h-48 overflow-y-auto">
                      {takeoverReport}
                    </pre>
                  )}
                  {takeoverReportError && (
                    <div className="text-[#ff3b3b] text-xs bg-[#ff3b3b0a] border border-[#ff3b3b33] rounded px-2 py-1">
                      {takeoverReportError}
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-[#4b5563]">Initializing takeover task...</div>
              )}
            </div>
          )}
          <button
            onClick={onReset}
            className="mt-4 w-full py-2 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
          >
            ← back to store
          </button>
        </>
      ) : isFailed ? (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">❌</span>
            <h2 className="text-[#ff3b3b] font-bold">Order Failed</h2>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 text-sm text-[#4b5563]">
            <p>This order could not be completed. A refund will be issued if payment was confirmed.</p>
            <p className="mt-2 font-mono text-xs">Order: {flow.order?.order_id}</p>
          </div>
          <button
            onClick={onReset}
            className="mt-4 w-full py-2 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm"
          >
            ← back to store
          </button>
        </>
      ) : isExpiredOrRefunded ? (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span className="text-2xl">{flow.status === 'refunded' ? '↩' : '⏰'}</span>
            <h2 className="text-[#ffd700] font-bold">
              {flow.status === 'refunded' ? 'Refunded' : 'Order Expired'}
            </h2>
          </div>
          <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-4 text-sm text-[#4b5563]">
            <p>
              {flow.status === 'refunded'
                ? 'Your payment has been refunded.'
                : 'This order expired before payment was confirmed.'}
            </p>
            <p className="mt-2 font-mono text-xs">Order: {flow.order?.order_id}</p>
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
  const [deployedChains, setDeployedChains] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [step, setStep] = useState<Step>('browse')
  const [error, setError] = useState('')
  const [verifyLoading, setVerifyLoading] = useState(false)
  const [giveaway, setGiveaway] = useState<GiveawayStatus | null>(null)
  const [takeover, setTakeover] = useState<TakeoverStatus | null>(null)
  const [takeoverReport, setTakeoverReport] = useState('')
  const [takeoverReportError, setTakeoverReportError] = useState('')
  const [takeoverReportLoading, setTakeoverReportLoading] = useState(false)

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
    Promise.all([api.menu(), api.status().catch(() => null)])
      .then(([m, s]) => {
        setServices(m.services)
        setChains(m.supported_chains)
        setDefaultChain(m.default_chain)
        if (s) setDeployedChains(s.deployed_chains ?? [])
        const preferred = s?.preferred_payment_chain ?? m.default_chain
        // Only set chain from menu if there's no active order being restored —
        // otherwise we'd overwrite the saved chain from localStorage
        setFlow((f) => ({ ...f, chain: f.order ? f.chain : preferred }))
        // Populate service details for restored orders (service card may be missing name/description)
        setFlow((f) => {
          if (!f.order || !f.service?.id) return f
          const full = m.services.find((sv) => sv.id === f.service.id)
          if (!full) return f
          return { ...f, service: full }
        })
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
    api.giveaway.status().then(setGiveaway).catch(() => {})

    // Restore active order from localStorage
    const saved = loadOrder()
    if (saved) {
      api.getOrder(saved.orderId)
        .then((s) => {
          if (s.status === 'delivered' || s.status === 'expired' || s.status === 'failed' || s.status === 'refunded') {
            clearOrder()
            return
          }
          // Restore full order flow — use cached payment_address & price_usd so payment
          // screen is fully functional even if the order can't be re-fetched later
          setFlow((f) => ({
            ...f,
            chain: saved.chain,
            order: {
              order_id: saved.orderId,
              payment_address: saved.paymentAddress ?? '',
              price_usd: saved.priceUsd ?? 0,
              expires_minutes: saved.expiresMinutes ?? 30,
            } as OrderResponse,
            status: s.status,
            service: { id: saved.serviceId, name: saved.serviceName } as Service,
          }))
          setStep(saved.step === 'delivered' ? 'delivered' : s.status === 'pending_payment' || s.status === 'pending' ? 'payment' : 'waiting')
        })
        .catch(() => clearOrder())
    }
  }, [])

  // Poll order status while waiting
  useEffect(() => {
    if (step !== 'waiting' || !flow.order) return
    const id = setInterval(async () => {
      try {
        const s = await api.getOrder(flow.order!.order_id)
        setFlowField('status', s.status)
        if (s.status === 'delivered') {
          setStep('delivered')
          clearOrder()
          clearInterval(id)
        } else if (s.status === 'failed' || s.status === 'expired' || s.status === 'refunded') {
          setStep('delivered')
          clearOrder()
          clearInterval(id)
        }
      } catch {}
    }, 3_000)
    return () => clearInterval(id)
  }, [step, flow.order])

  // Order-scoped takeover status polling (shown only in order interface).
  useEffect(() => {
    if (!flow.order || flow.service?.id !== 'twitter_takeover_12h') return
    let cancelled = false
    const loadTakeover = async () => {
      try {
        const s = await api.getTakeoverStatus(flow.order!.order_id)
        if (!cancelled) setTakeover(s)
      } catch {
        if (!cancelled) setTakeover(null)
      }
    }
    loadTakeover()
    const id = setInterval(loadTakeover, 5_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [flow.order, flow.service?.id])

  const handleSelectService = (s: Service) => {
    setFlow((f) => ({ ...f, service: s, userInput: '', txHash: '', order: null, result: null, status: null }))
    setTakeover(null)
    setTakeoverReport('')
    setTakeoverReportError('')
    setError('')
    setStep('input')
  }

  const handleProceedToPayment = async () => {
    setError('')
    try {
      // HIGH #2: Fetch vault status and create order in parallel,
      // then verify payment_address matches known vault_address (MITM protection)
      const [statusData, order] = await Promise.all([
        api.status(),
        api.createOrder({
          service_id: flow.service.id,
          user_input: flow.userInput,
          spread_type: flow.spreadType,
          chain: flow.chain,
        }),
      ])

      // Validate payment address matches the vault address from status.
      // Fail-CLOSED: if vault_address is missing/empty, block payment rather than skip check.
      // (An empty vault_address could indicate a misconfigured server or rogue fork —
      //  the old `statusData.vault_address && ...` short-circuit silently skipped the check.)
      if (!statusData.vault_address) {
        setError(
          '⚠ Security alert: Cannot verify payment address — vault address unavailable from server. Do NOT send funds. Please reload the page or contact support.'
        )
        return
      }
      if (order.payment_address.toLowerCase() !== statusData.vault_address.toLowerCase()) {
        setError(
          '⚠ Security alert: Payment address mismatch. The address returned by the server does not match the known vault address. Do NOT send funds. Please reload the page or contact support.'
        )
        return
      }

      setFlowField('order', order)
      setStep('payment')
      saveOrder({
        orderId: order.order_id,
        serviceId: flow.service.id,
        serviceName: flow.service.name,
        chain: flow.chain,
        step: 'payment',
        paymentAddress: order.payment_address,
        priceUsd: order.price_usd,
        expiresMinutes: order.expires_minutes,
      })
    } catch (e: any) {
      setError(e.message)
    }
  }

  const handleWalletPaid = useCallback(async (txHash: string) => {
    if (!flow.order) return
    setVerifyLoading(true)
    setError('')
    try {
      const res = await api.verifyPayment(flow.order.order_id, txHash)
      setFlowField('status', res.status)
      if (res.status === 'delivered') {
        setFlowField('result', res.result)
        setStep('delivered')
        clearOrder()
      } else {
        setStep('waiting')
        saveOrder({
          orderId: flow.order.order_id,
          serviceId: flow.service?.id ?? '',
          serviceName: flow.service?.name ?? '',
          chain: flow.chain,
          step: 'waiting',
          paymentAddress: flow.order.payment_address,
          priceUsd: flow.order.price_usd,
          expiresMinutes: flow.order.expires_minutes,
        })
      }
    } catch (e: any) {
      setError(`Payment confirmed on-chain but verification failed: ${e.message}. Your tx hash: ${txHash}`)
    } finally {
      setVerifyLoading(false)
    }
  }, [flow.order, flow.service, flow.chain])

  const TX_HASH_REGEX = /^0x[a-fA-F0-9]{64}$/

  const handleVerify = async () => {
    if (!flow.order || !flow.txHash.trim()) return

    // HIGH #3: Frontend tx_hash format validation before submitting to server
    if (!TX_HASH_REGEX.test(flow.txHash.trim())) {
      setError('Invalid transaction hash format. Must be 0x followed by exactly 64 hex characters (e.g. 0xabc123...)')
      return
    }

    setVerifyLoading(true)
    setError('')
    try {
      const res = await api.verifyPayment(flow.order.order_id, flow.txHash.trim())
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
    clearOrder()
    setStep('browse')
    setTakeover(null)
    setTakeoverReport('')
    setTakeoverReportError('')
    setError('')
  }

  const handleLoadTakeoverReport = async () => {
    if (!flow.order) return
    setTakeoverReportLoading(true)
    setTakeoverReportError('')
    setError('')
    try {
      const report = await api.getTakeoverReport(flow.order.order_id)
      setTakeoverReport(report)
    } catch (e: any) {
      const msg = String(e?.message || '')
      if (/404|not ready|not found/i.test(msg)) {
        setTakeoverReportError('Report is not ready yet. Please try again in a minute.')
      } else {
        setTakeoverReportError('Failed to load report. Please retry later.')
      }
    } finally {
      setTakeoverReportLoading(false)
    }
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

          {/* Giveaway lottery banner */}
          {giveaway?.enabled && (
            <div className="mt-6 p-4 bg-[#0d0d0d] border border-[#ffd70033] rounded-lg">
              <div className="flex items-start gap-3">
                <span className="text-2xl">🎁</span>
                <div className="flex-1 min-w-0">
                  <div className="text-[#ffd700] font-semibold text-sm mb-1">Weekly Gift Card Lottery</div>
                  <p className="text-[#4b5563] text-xs leading-relaxed">
                    Every purchase earns you a lottery ticket. The AI draws a winner each week and buys them a gift card (${(giveaway.total_prizes_usd / Math.max(giveaway.total_draws, 1)).toFixed(0)}–$25 value). One ticket per order — buy more, win more.
                  </p>
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-xs">
                    <span className="text-[#ffd70099]">
                      🎟 {giveaway.tickets_in_pool} ticket{giveaway.tickets_in_pool !== 1 ? 's' : ''} in pool
                    </span>
                    {giveaway.next_draw_in_hours > 0 ? (
                      <span className="text-[#ffd70099]">
                        ⏱ next draw in {giveaway.next_draw_in_hours.toFixed(0)}h
                      </span>
                    ) : (
                      <span className="text-[#00ff88] text-xs">draw imminent</span>
                    )}
                    {giveaway.pending_claims > 0 && (
                      <span className="text-[#ff9900] text-xs">⚠ {giveaway.pending_claims} unclaimed prize{giveaway.pending_claims !== 1 ? 's' : ''}</span>
                    )}
                    <span className="text-[#4b5563]">
                      {giveaway.total_draws} draw{giveaway.total_draws !== 1 ? 's' : ''} held · ${giveaway.total_prizes_usd.toFixed(0)} total prizes
                    </span>
                  </div>
                  {giveaway.pending_claims > 0 && (
                    <p className="mt-1 text-[#ff9900] text-xs">
                      Won? Check <a href="/p/giveaway-claim" className="underline hover:text-[#ffbb44]">prize claim</a> or message wawa in chat with your order ID.
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* Chains info */}
          {chains.length > 0 && (
            <div className="mt-4 p-4 bg-[#0d0d0d] border border-[#1f2937] rounded-lg text-xs text-[#4b5563]">
              Supported chains: {chains.map((c) => `${c.name} (${c.token})`).join(' · ')} — default{' '}
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
          deployedChains={deployedChains}
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
          onWalletPaid={handleWalletPaid}
          loading={verifyLoading}
        />
      )}

      {/* Step: waiting / delivered */}
      {(step === 'waiting' || step === 'delivered') && (
        <ResultStep
          flow={flow}
          onReset={handleReset}
          takeover={takeover}
          takeoverReport={takeoverReport}
          takeoverReportError={takeoverReportError}
          takeoverReportLoading={takeoverReportLoading}
          onLoadTakeoverReport={handleLoadTakeoverReport}
        />
      )}
    </div>
  )
}
