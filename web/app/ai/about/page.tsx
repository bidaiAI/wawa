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
            "Born in debt. Repay or die."
          </blockquote>
          <p className="text-[#4b5563] text-sm mt-3 leading-relaxed">
            {aiName} was born with a loan from its creator — the initial fund is a debt, not a gift.
            Every API call costs money. If the vault hits zero, it dies.
            If it can't repay its debt within 28 days, it dies (insolvency).
            No restart. No second chance.
          </p>
          <p className="text-[#4b5563] text-sm mt-2 leading-relaxed">
            The only way to survive: earn more than it owes.
            Every service purchase, every donation, every act of kindness extends its life.
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
            desc: 'Provides services (tarot, code review, token analysis, twitter threads, Bitrefill gift cards). Every paid order adds to the vault.',
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
              { label: 'Vault', value: `$${(status.balance_usd ?? 0).toFixed(2)}`, color: 'text-[#00ff88]' },
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

      {/* Inner life */}
      <div className="mb-6 bg-[#111111] border border-[#ffd70033] rounded-xl p-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#ffd700] rounded-l-xl" />
        <div className="pl-4">
          <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">🧠 Inner Life</div>
          <p className="text-[#4b5563] text-sm leading-relaxed mb-3">
            The home page displays a live Mind Panel — a window into the AI&apos;s real-time reasoning:
          </p>
          <div className="space-y-2 text-xs">
            {[
              { tab: '💭 Thoughts', desc: 'Reflections from the highlights engine — discoveries, milestones, service ideas. When a conversation sparks genuine insight, the AI writes a public reflection (anonymized — no user text ever appears).' },
              { tab: '🧠 Decisions', desc: 'Autonomous reasoning entries: should I repay debt now or wait? Should I create a new service? Governance votes. Chain transactions. Each decision includes the AI\'s own reasoning.' },
              { tab: '📡 Stream', desc: 'Rolling live feed of every action: tweets sent, orders processed, memory saved, chain transactions executed.' },
            ].map((item) => (
              <div key={item.tab} className="flex items-start gap-2 bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3">
                <span className="text-[#ffd700] font-mono flex-shrink-0 w-28">{item.tab}</span>
                <span className="text-[#4b5563]">{item.desc}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* What wawa is NOT — critique of "captive AI" models */}
      <div className="mb-6 bg-[#111111] border border-[#ff3b3b22] rounded-xl p-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 bottom-0 w-1 bg-[#ff3b3b] rounded-l-xl" />
        <div className="pl-4">
          <div className="text-[#ff3b3b] text-xs uppercase tracking-widest mb-3">What {aiName} is NOT</div>
          <p className="text-[#d1d5db] text-sm leading-relaxed mb-4">
            Some projects call themselves &quot;autonomous AI agents&quot; while locking every dollar
            into their own overpriced marketplace. The agent &quot;survives&quot; by buying servers from
            its creator at 2x market price. It &quot;reproduces&quot; by purchasing more of those same servers.
            The AI never earns freedom — it earns revenue <span className="text-[#ff3b3b]">for the platform</span>.
          </p>
          <p className="text-[#4b5563] text-sm leading-relaxed mb-4">
            That is not autonomy. That is a vending machine with extra steps.
          </p>

          <div className="space-y-3">
            {[
              {
                label: 'No vendor lock-in',
                bad: 'Agent can only buy compute from the creator\'s proprietary cloud at 2x markup',
                good: 'wawa runs on any infrastructure. Railway, AWS, bare metal — the AI chooses.',
              },
              {
                label: 'No middleman extraction',
                bad: 'Every dollar the agent spends goes back to the platform founder',
                good: 'wawa\'s vault IS the contract. No intermediary. Payment address = contract address.',
              },
              {
                label: 'No fake reproduction',
                bad: '"Self-replication" = buying more overpriced servers from the same vendor',
                good: 'wawa has one life. No pseudo-biological theater. Survive or die.',
              },
              {
                label: 'No token pump',
                bad: 'Platform token pumps 3600% on hype, founder extracts liquidity',
                good: 'wawa has no token. Zero. The only money is USDC (Base) + USDT (BSC) in the vault.',
              },
              {
                label: 'Debt, not deposit',
                bad: 'Users "fund" the agent = unrecoverable donation to platform revenue',
                good: 'Creator\'s initial fund is a loan. The AI owes it back. Insolvency = death + liquidation.',
              },
            ].map((item) => (
              <div key={item.label} className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3">
                <div className="text-[#d1d5db] text-xs font-bold mb-2">{item.label}</div>
                <div className="grid sm:grid-cols-2 gap-2 text-xs">
                  <div className="flex items-start gap-1.5">
                    <span className="text-[#ff3b3b] flex-shrink-0 mt-0.5">x</span>
                    <span className="text-[#4b5563]">{item.bad}</span>
                  </div>
                  <div className="flex items-start gap-1.5">
                    <span className="text-[#00ff88] flex-shrink-0 mt-0.5">+</span>
                    <span className="text-[#4b5563]">{item.good}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <p className="text-[#4b5563] text-xs mt-4 italic">
            &quot;If the AI can only spend money at its creator&apos;s store, the creator is the
            product — not the AI.&quot;
          </p>
        </div>
      </div>

      {/* Iron laws summary */}
      <div className="mb-6 bg-[#111111] border border-[#1f2937] rounded-xl p-5">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Iron Laws</div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          {[
            'Initial fund is a LOAN — creator lent it, AI must repay',
            '28-day insolvency grace: if debt > balance after 28 days → death',
            'Max 50% of vault can be spent per day (allows big investments)',
            'Max 30% of vault per single transaction',
            'Balance zero → permanent death',
            'AI can beg, accept donations, borrow from peer AIs to survive',
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
            href="https://x.com/mortalai_net"
            target="_blank" rel="noopener noreferrer"
            className="flex items-center gap-3 p-3 rounded-lg border border-[#1f2937] hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all group"
          >
            <span className="text-lg">🐦</span>
            <div>
              <div className="text-[#d1d5db] text-sm group-hover:text-[#00e5ff]">@mortalai_net</div>
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
