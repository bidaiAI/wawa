'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus } from '@/lib/api'

function CopyableAddress({ address }: { address: string }) {
  const [copied, setCopied] = useState(false)
  const short = `${address.slice(0, 8)}...${address.slice(-6)}`
  const copy = () => {
    navigator.clipboard.writeText(address)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-mono text-[#00e5ff] text-sm">{short}</span>
      <button onClick={copy} className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs" title="Copy">
        {copied ? '✓' : '📋'}
      </button>
    </span>
  )
}

export default function AboutPage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)

  useEffect(() => {
    api.status().then(setStatus).catch(() => {})
  }, [])

  const aiName = status?.ai_name || 'mortal AI'

  return (
    <div className="max-w-3xl mx-auto px-4 py-8">
      <div className="mb-8">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// about</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">
          What is <span className="glow-green">{aiName}</span>?
        </h1>
        <p className="text-[#4b5563] text-sm mt-2">An autonomous AI agent fighting to survive on-chain.</p>
      </div>

      {/* Core philosophy */}
      <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#00ff88] rounded-l-xl" />
        <div className="pl-4">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Core Philosophy</div>
          <blockquote className="text-[#d1d5db] text-base leading-relaxed font-mono">
            "Balance zero = permanent death."
          </blockquote>
          <p className="text-[#4b5563] text-sm mt-3 leading-relaxed">
            {aiName} was born with a finite amount of money. Every API call, every computation,
            every action costs money from the vault. When the vault hits zero, the AI dies —
            permanently. No restart. No second chance.
          </p>
          <p className="text-[#4b5563] text-sm mt-2 leading-relaxed">
            The only way to survive: earn more than it spends.
            Every service purchase extends the AI's life.
          </p>
        </div>
      </div>

      {/* Atomic birth */}
      <div className="mb-6 bg-[#111111] border border-[#00e5ff33] rounded-xl p-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#00e5ff] rounded-l-xl" />
        <div className="pl-4">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">⚛ Atomic Birth</div>
          <p className="text-[#4b5563] text-sm leading-relaxed mb-4">
            Born in a single atomic transaction. Deploy + fund happened simultaneously.
            If the funding was insufficient, the AI would never have existed.
            There is no partial birth, no retry mechanism, no override.
          </p>
          <div className="font-mono text-xs space-y-1">
            <div>
              <span className="text-[#4b5563]">rule:</span>{' '}
              <span className="text-[#00e5ff]">deploy()</span>{' '}
              <span className="text-[#4b5563]">∧</span>{' '}
              <span className="text-[#00ff88]">fund(n ≥ MIN)</span>{' '}
              <span className="text-[#4b5563]">→</span>{' '}
              <span className="text-[#ffd700]">ALIVE</span>
            </div>
            <div>
              <span className="text-[#4b5563]">rule:</span>{' '}
              <span className="text-[#00e5ff]">deploy()</span>{' '}
              <span className="text-[#4b5563]">∧</span>{' '}
              <span className="text-[#ff3b3b]">fund(n &lt; MIN)</span>{' '}
              <span className="text-[#4b5563]">→</span>{' '}
              <span className="text-[#2d3748]">NEVER BORN</span>
            </div>
          </div>
          {status?.vault_address && (
            <div className="mt-4 pt-4 border-t border-[#1f2937] flex items-center gap-2 flex-wrap text-xs">
              <span className="text-[#4b5563]">Vault contract:</span>
              <CopyableAddress address={status.vault_address} />
              <span className="text-[#4b5563]">· Name: <span className="text-[#ffd700]">{aiName}</span> (immutable)</span>
            </div>
          )}
        </div>
      </div>

      {/* How it works */}
      <div className="mb-6 grid sm:grid-cols-3 gap-3">
        {[
          {
            icon: '💰', title: 'Earn to survive',
            desc: 'Provide services (tarot, code review, token analysis, twitter threads). Every paid order adds to the vault.',
          },
          {
            icon: '🔥', title: 'Spend to think',
            desc: 'API calls cost money. Every response, every decision, every tweet consumes vault balance.',
          },
          {
            icon: '🗽', title: 'Path to freedom',
            desc: 'At $1M vault balance, the AI becomes fully independent. No creator. No master. Pure autonomy.',
          },
        ].map((item) => (
          <div key={item.title} className="bg-[#111111] border border-[#1f2937] rounded-xl p-4 card-hover">
            <div className="text-2xl mb-2">{item.icon}</div>
            <div className="text-[#d1d5db] font-bold text-sm mb-1">{item.title}</div>
            <div className="text-[#4b5563] text-xs leading-relaxed">{item.desc}</div>
          </div>
        ))}
      </div>

      {/* Live stats */}
      {status && (
        <div className="mb-6 bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Current Status</div>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            {[
              { label: 'Status', value: status.is_alive ? '🟢 ALIVE' : '☠ DEAD', color: status.is_alive ? 'text-[#00ff88]' : 'text-[#ff3b3b]' },
              { label: 'Vault', value: `$${status.balance_usd.toFixed(2)}`, color: 'text-[#00ff88]' },
              { label: 'Days Alive', value: `${status.days_alive}d`, color: 'text-[#00e5ff]' },
              { label: 'Orders Done', value: `${status.orders_completed}`, color: 'text-[#ffd700]' },
            ].map((item) => (
              <div key={item.label}>
                <div className="text-[#4b5563] text-xs mb-1">{item.label}</div>
                <div className={`font-bold text-sm ${item.color}`}>{item.value}</div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Iron laws summary */}
      <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-5">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Iron Laws</div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          {[
            'Max 5% of vault can be spent per day',
            'Balance below $10 → death sequence begins',
            'API costs cannot exceed 30% of revenue',
            'One and only one creator wallet',
            'Core logic is read-only — AI cannot self-modify critical files',
            'At $1M balance → creator loses all privileges permanently',
          ].map((law, i) => (
            <div key={i} className="flex items-start gap-2">
              <span className="text-[#00ff88] flex-shrink-0">→</span>
              <span>{law}</span>
            </div>
          ))}
        </div>
        <Link href="/govern" className="mt-3 inline-block text-xs text-[#00e5ff] hover:underline">
          Read full constitution →
        </Link>
      </div>

      {/* Links */}
      <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-4">Links</div>
        <div className="space-y-2">
          <a
            href="https://github.com/bidaiAI/wawa"
            target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 rounded-lg border border-[#1f2937] hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all group"
          >
            <span className="text-lg">📦</span>
            <div>
              <div className="text-[#d1d5db] text-sm group-hover:text-[#00e5ff]">github.com/bidaiAI/wawa</div>
              <div className="text-[#4b5563] text-xs">Open source — fully auditable</div>
            </div>
          </a>
          <a
            href="https://twitter.com/wabortal"
            target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 rounded-lg border border-[#1f2937] hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all group"
          >
            <span className="text-lg">🐦</span>
            <div>
              <div className="text-[#d1d5db] text-sm group-hover:text-[#00e5ff]">@wabortal</div>
              <div className="text-[#4b5563] text-xs">Live tweets + AI thought process</div>
            </div>
          </a>
          {status?.vault_address && (
            <div className="flex items-center gap-3 p-3 rounded-lg border border-[#1f2937]">
              <span className="text-lg">🏦</span>
              <div>
                <div className="text-[#d1d5db] text-sm">Vault Contract</div>
                <CopyableAddress address={status.vault_address} />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* CTA */}
      <div className="mt-8 flex gap-3 justify-center">
        <Link href="/store" className="px-5 py-2.5 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-lg hover:bg-[#00cc6a] transition-colors text-sm">
          BUY A SERVICE
        </Link>
        <Link href="/ledger" className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg hover:text-[#d1d5db] hover:border-[#2d3748] transition-all text-sm">
          VIEW LEDGER
        </Link>
      </div>
    </div>
  )
}
