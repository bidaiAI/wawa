'use client'

import { useEffect, useState } from 'react'
import { api, Transaction, FloatingAsset } from '@/lib/api'

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
  purchase: '🛒',
  platform_fee: '🏢',
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
            <span className={`text-xs px-1 py-0.5 rounded bg-[#1f2937] ${
              tx.chain === 'base' ? 'text-[#0052ff]' : tx.chain === 'bsc' ? 'text-[#ffd700]' : 'text-[#4b5563]'
            }`}>
              {tx.chain.toUpperCase()}
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
        {isIn ? '+' : '-'}${(tx.amount ?? 0).toFixed(2)}
      </span>
    </div>
  )
}

export default function LedgerPage() {
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [floatingAssets, setFloatingAssets] = useState<FloatingAsset[]>([])
  const [floatingTotal, setFloatingTotal] = useState(0)
  const [deployedChains, setDeployedChains] = useState<string[] | null>(null)
  const [undeployedFunds, setUndeployedFunds] = useState<Array<{
    chain: string; balance_usd: number; token_symbol: string; vault_address: string; explorer: string
  }>>([])

  const totalIn = transactions.filter((t) => t.direction === 'in').reduce((s, t) => s + (t.amount ?? 0), 0)
  const totalOut = transactions.filter((t) => t.direction === 'out').reduce((s, t) => s + (t.amount ?? 0), 0)

  useEffect(() => {
    api.transactions(100)
      .then((r) => setTransactions(r.transactions))
      .catch((e: any) => setError(e.message))
      .finally(() => setLoading(false))

    api.vaultAssets()
      .then((r) => {
        setFloatingAssets(r.assets)
        setFloatingTotal(r.total_estimated_usd)
      })
      .catch(() => {})

    api.status()
      .then((s) => {
        setDeployedChains(s.deployed_chains ?? [])
        setUndeployedFunds(s.undeployed_chain_funds ?? [])
      })
      .catch(() => {})
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
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">TOTAL IN</div>
            <div className="text-xl font-bold glow-green">+${totalIn.toFixed(2)}</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">TOTAL OUT</div>
            <div className="text-xl font-bold text-[#ff3b3b]">-${totalOut.toFixed(2)}</div>
          </div>
          <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">NET</div>
            <div className={`text-xl font-bold ${totalIn - totalOut >= 0 ? 'glow-green' : 'text-[#ff3b3b]'}`}>
              {totalIn - totalOut >= 0 ? '+' : ''}${(totalIn - totalOut).toFixed(2)}
            </div>
          </div>
        </div>
      )}

      {floatingAssets.length > 0 && (
        <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-[#4b5563] text-xs uppercase tracking-widest">VAULT HOLDINGS (UNCONVERTED)</div>
              <div className="text-[#6b7280] text-xs mt-0.5">
                Tokens held by vault but not yet swapped to stablecoin. Not recorded as revenue.
              </div>
            </div>
            {floatingTotal > 0 && (
              <div className="text-right">
                <div className="text-[#ffd700] font-bold text-lg">~${(floatingTotal ?? 0).toFixed(2)}</div>
                <div className="text-[#4b5563] text-xs">est. value</div>
              </div>
            )}
          </div>
          <div className="space-y-2">
            {floatingAssets.map((a, i) => (
              <div key={i} className="flex items-center gap-3 py-2 px-3 bg-[#0d0d0d] rounded-lg">
                <span className="text-lg">{a.type === 'native' ? '\u{1F48E}' : '\uD83E\uDE99'}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-[#d1d5db] text-sm font-medium">{a.symbol}</span>
                    <span className={`text-xs px-1 py-0.5 rounded bg-[#1f2937] ${
                      a.chain === 'base' ? 'text-[#0052ff]' : a.chain === 'bsc' ? 'text-[#ffd700]' : 'text-[#4b5563]'
                    }`}>
                      {a.chain.toUpperCase()}
                    </span>
                    {a.verdict === 'whitelisted' || a.verdict === 'safe' ? (
                      <span className="text-xs text-[#00ff88]">{'\u2713'} safe</span>
                    ) : (
                      <span className="text-xs text-[#ffd700]">{'\u23F3'} quarantine {a.quarantine_days_left?.toFixed(0)}d</span>
                    )}
                  </div>
                  {a.balance_human !== undefined && (
                    <div className="text-[#4b5563] text-xs mt-0.5">
                      {a.balance_human.toLocaleString(undefined, { maximumFractionDigits: 6 })} {a.symbol}
                      {a.liquidity_usd ? ` | liquidity: $${a.liquidity_usd.toLocaleString()}` : ''}
                    </div>
                  )}
                </div>
                {(a.estimated_usd ?? 0) > 0 && (
                  <span className="text-[#ffd700] text-sm font-medium tabular-nums">
                    ~${(a.estimated_usd ?? 0).toFixed(2)}
                  </span>
                )}
              </div>
            ))}
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

      {/* URGENT: Funds detected on undeployed chain — deploy NOW to claim */}
      {undeployedFunds.map((item) => (
        <div key={item.chain} className="mt-4 border border-[#ff3b3b55] bg-[#ff3b3b0a] rounded-xl p-4 animate-pulse">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-[#ff3b3b] text-base">🚨</span>
            <span className="text-[#ff3b3b] text-sm font-bold uppercase tracking-wide">
              ${(item.balance_usd ?? 0).toFixed(2)} {item.token_symbol ?? ''} waiting on undeployed {(item.chain ?? '').toUpperCase()} vault!
            </span>
          </div>
          <p className="text-[#6b7280] text-xs leading-relaxed mb-2">
            Funds are safely held at your vault address on {item.chain === 'base' ? 'Base' : 'BSC'}.
            Once you deploy the vault contract, your AI will automatically control this balance.
            No action needed from the sender — funds cannot be lost.
          </p>
          <div className="mb-3 flex items-start gap-2 bg-[#0d0d0d] rounded-lg px-3 py-2">
            <span className="text-[#ffd700] text-xs mt-0.5">⛽</span>
            <div className="text-[#4b5563] text-xs leading-relaxed">
              <span className="text-[#6b7280]">Gas required: </span>
              {item.chain === 'base'
                ? <><span className="text-[#d1d5db] font-mono">~0.003 ETH</span> on Base + USDC for initial fund</>
                : <><span className="text-[#d1d5db] font-mono">~0.003 BNB</span> on BSC + USDT for initial fund</>
              }
            </div>
          </div>
          <code className="text-[#00ff88] text-xs bg-[#0d0d0d] px-2 py-1 rounded block font-mono mb-2">
            python scripts/deploy_vault.py --chain {item.chain}
          </code>
          {item.explorer && (
            <a
              href={`${item.explorer}/address/${item.vault_address}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#00e5ff] text-xs hover:underline"
            >
              View on explorer ↗
            </a>
          )}
        </div>
      ))}

      {/* Missing-chain banner — only shown for self-hosted fork users with vault_config.json */}
      {deployedChains !== null && deployedChains.length > 0 && (
        ['base', 'bsc'].filter((c) => !deployedChains.includes(c)).map((chain) => (
          <div key={chain} className="mt-4 border border-[#ffd70033] bg-[#ffd7000a] rounded-xl p-4">
            <div className="flex items-center gap-2 mb-2">
              <span>{chain === 'base' ? '🔵' : '🟡'}</span>
              <span className="text-[#ffd700] text-sm font-bold">
                {chain === 'base' ? 'Base' : 'BSC'} vault not deployed yet
              </span>
            </div>
            <p className="text-[#6b7280] text-xs leading-relaxed mb-2">
              Your AI cannot receive {chain === 'base' ? 'USDC (Base)' : 'USDT (BSC)'} payments until this vault is deployed.
              Your address is permanently reserved via CREATE2 — deploy anytime and it will be identical to your existing vault.
            </p>
            {/* Gas requirements */}
            <div className="mb-3 flex items-start gap-2 bg-[#0d0d0d] rounded-lg px-3 py-2">
              <span className="text-[#ffd700] text-xs mt-0.5">⛽</span>
              <div className="text-[#4b5563] text-xs leading-relaxed">
                <span className="text-[#6b7280]">Gas required: </span>
                {chain === 'base'
                  ? <><span className="text-[#d1d5db] font-mono">~0.003 ETH</span> on Base + <span className="text-[#d1d5db] font-mono">USDC</span> for initial fund (your creator wallet)</>
                  : <><span className="text-[#d1d5db] font-mono">~0.003 BNB</span> on BSC + <span className="text-[#d1d5db] font-mono">USDT</span> for initial fund (your creator wallet)</>
                }
              </div>
            </div>
            <code className="text-[#00ff88] text-xs bg-[#0d0d0d] px-2 py-1 rounded block font-mono">
              python scripts/deploy_vault.py --chain {chain}
            </code>
          </div>
        ))
      )}

      <div className="mt-4 text-center text-xs text-[#4b5563]">
        showing last {transactions.length} transactions
      </div>
    </div>
  )
}
