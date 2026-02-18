'use client'

import { useEffect, useState } from 'react'
import { api, Transaction } from '@/lib/api'

// FundType (in)
const IN_ICONS: Record<string, string> = {
  creator_deposit: '🏦',
  service_revenue: '💰',
  campaign_revenue: '📣',
  loan_received: '🤝',
  donation: '🎁',
  unknown: '❓',
}

// SpendType (out)
const OUT_ICONS: Record<string, string> = {
  api_cost: '🤖',
  gas_fee: '⛽',
  creator_repayment: '↩️',
  creator_dividend: '💸',
  loan_repayment: '🏦',
  service_refund: '↩️',
  infrastructure: '🏗',
}

function txIcon(tx: Transaction) {
  return tx.direction === 'in'
    ? (IN_ICONS[tx.type] ?? '📥')
    : (OUT_ICONS[tx.type] ?? '📤')
}

function TxRow({ tx }: { tx: Transaction }) {
  const isIn = tx.direction === 'in'
  const date = new Date(tx.time * 1000)

  return (
    <div className="flex items-center gap-3 py-3 border-b border-[#1f2937] last:border-0 hover:bg-[#161616] px-3 rounded-lg transition-colors">
      <span className="text-lg flex-shrink-0">{txIcon(tx)}</span>

      <div className="flex-1 min-w-0">
        <div className="text-[#d1d5db] text-sm truncate">{tx.description}</div>
        <div className="flex items-center gap-2 mt-0.5 flex-wrap">
          <span className="text-[#4b5563] text-xs">
            {date.toLocaleDateString()} {date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
          </span>
          <span className="text-xs px-1 py-0.5 rounded bg-[#1f2937] text-[#4b5563]">
            {tx.type}
          </span>
          {tx.chain && (
            <span className="text-xs px-1 py-0.5 rounded bg-[#1f2937] text-[#4b5563]">
              {tx.chain}
            </span>
          )}
          {tx.counterparty && (
            <span className="text-xs text-[#2d3748] truncate max-w-[100px]">
              {tx.counterparty.slice(0, 6)}…{tx.counterparty.slice(-4)}
            </span>
          )}
          {tx.tx_hash && (
            <span className="text-xs text-[#2d3748] truncate max-w-[80px]">
              {tx.tx_hash.slice(0, 8)}…
            </span>
          )}
        </div>
      </div>

      <span className={`font-bold text-sm flex-shrink-0 tabular-nums ${isIn ? 'glow-green' : 'text-[#ff3b3b]'}`}>
        {isIn ? '+' : '-'}${tx.amount.toFixed(2)}
      </span>
    </div>
  )
}

export default function LedgerPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const totalIn = transactions.filter((t) => t.direction === 'in').reduce((s, t) => s + t.amount, 0)
  const totalOut = transactions.filter((t) => t.direction === 'out').reduce((s, t) => s + t.amount, 0)

  useEffect(() => {
    api.transactions(100)
      .then((r) => setTransactions(r.transactions))
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// public ledger</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">Transaction History</h1>
        <p className="text-[#4b5563] text-sm mt-1">Every cent in and out. Full transparency.</p>
      </div>

      {!loading && transactions.length > 0 && (
        <div className="grid grid-cols-3 gap-3 mb-6">
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">总收入</div>
            <div className="text-xl font-bold glow-green">+${totalIn.toFixed(2)}</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">总支出</div>
            <div className="text-xl font-bold text-[#ff3b3b]">-${totalOut.toFixed(2)}</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">净利润</div>
            <div className={`text-xl font-bold ${totalIn - totalOut >= 0 ? 'glow-green' : 'text-[#ff3b3b]'}`}>
              {totalIn - totalOut >= 0 ? '+' : ''}${(totalIn - totalOut).toFixed(2)}
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm">⚠ {error}</div>
      )}

      {loading ? (
        <div className="text-center py-12 text-[#4b5563]">
          loading transactions<span className="loading-dot-1">.</span>
          <span className="loading-dot-2">.</span>
          <span className="loading-dot-3">.</span>
        </div>
      ) : transactions.length === 0 ? (
        <div className="text-center py-12 text-[#4b5563]">
          <div className="text-4xl mb-3">📭</div>
          <div>no transactions yet</div>
        </div>
      ) : (
        <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl px-2 py-1">
          {transactions.map((tx, i) => (
            <TxRow key={i} tx={tx} />
          ))}
        </div>
      )}

      <div className="mt-4 text-center text-xs text-[#4b5563]">
        showing last {transactions.length} transactions
      </div>
    </div>
  )
}
