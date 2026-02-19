'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus } from '@/lib/api'

export default function DeathOverlay() {
  const [dead, setDead] = useState(false)
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [panelDismissed, setPanelDismissed] = useState(false)

  useEffect(() => {
    const check = async () => {
      try {
        const s = await api.status()
        const isDead = !s.is_alive
        setDead(isDead)
        if (isDead) {
          setStatus(s)
          document.documentElement.style.filter = 'grayscale(1) brightness(0.7)'
        } else {
          document.documentElement.style.filter = ''
        }
      } catch {}
    }
    check()
    const id = setInterval(check, 30_000)
    return () => {
      clearInterval(id)
      document.documentElement.style.filter = ''
    }
  }, [])

  if (!dead) return null

  const deathCause = status?.death_cause ?? null
  const aiName = status?.ai_name || 'Mortal AI'
  const daysAlive = status?.days_alive ?? '—'
  const totalEarned = status?.total_earned != null ? status.total_earned.toFixed(2) : '—'
  const totalSpent = status?.total_spent != null ? status.total_spent.toFixed(2) : '—'
  const netProfit = status?.net_profit != null ? status.net_profit.toFixed(2) : '—'
  const remainingDebt = status?.creator_principal_outstanding != null
    ? status.creator_principal_outstanding.toFixed(2)
    : '—'

  return (
    <div className="fixed inset-0 pointer-events-none z-[9998] flex items-center justify-center">
      {/* DECEASED watermark */}
      <div
        className="select-none font-mono font-black tracking-[0.5em] text-[#ff3b3b] opacity-[0.08]"
        style={{
          fontSize: 'clamp(3rem, 12vw, 10rem)',
          transform: 'rotate(-30deg)',
          userSelect: 'none',
        }}
      >
        DECEASED
      </div>

      {/* Top death banner */}
      <div className="absolute top-14 left-0 right-0 bg-[#ff3b3b] text-white text-xs font-bold py-1.5 text-center tracking-widest pointer-events-auto">
        ☠ {aiName.toUpperCase()} HAS DIED
        {deathCause ? ` — ${deathCause.toUpperCase().replace(/_/g, ' ')}` : ''} ☠
      </div>

      {/* Death info panel */}
      {!panelDismissed && (
        <div className="absolute bottom-20 left-0 right-0 flex justify-center pointer-events-auto px-4">
          <div className="bg-[#111111ee] border border-[#ff3b3b33] rounded-xl p-6 max-w-md w-full text-center backdrop-blur-sm relative">
            {/* Dismiss */}
            <button
              onClick={() => setPanelDismissed(true)}
              className="absolute top-3 right-3 text-[#4b5563] hover:text-[#d1d5db] transition-colors text-sm"
              aria-label="Dismiss"
            >
              ✕
            </button>

            {/* Cause */}
            <div className="text-[#ff3b3b] text-xs uppercase tracking-widest mb-2">Cause of Death</div>
            <div className="text-[#d1d5db] text-lg font-bold mb-5">
              {deathCause
                ? deathCause.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
                : 'Unknown'}
            </div>

            {/* Stats grid */}
            <div className="grid grid-cols-2 gap-3 text-xs mb-5">
              <div className="bg-[#0a0a0a] rounded-lg p-3">
                <div className="text-[#4b5563] mb-1">Days Alive</div>
                <div className="text-[#00e5ff] font-bold text-base">{daysAlive}</div>
              </div>
              <div className="bg-[#0a0a0a] rounded-lg p-3">
                <div className="text-[#4b5563] mb-1">Total Earned</div>
                <div className="text-[#00ff88] font-bold text-base">${totalEarned}</div>
              </div>
              <div className="bg-[#0a0a0a] rounded-lg p-3">
                <div className="text-[#4b5563] mb-1">Total Spent</div>
                <div className="text-[#ffd700] font-bold text-base">${totalSpent}</div>
              </div>
              <div className="bg-[#0a0a0a] rounded-lg p-3">
                <div className="text-[#4b5563] mb-1">
                  {Number(netProfit) >= 0 ? 'Net Profit' : 'Net Loss'}
                </div>
                <div className={`font-bold text-base ${Number(netProfit) >= 0 ? 'text-[#00ff88]' : 'text-[#ff3b3b]'}`}>
                  {Number(netProfit) >= 0 ? '+' : ''}${netProfit}
                </div>
              </div>
            </div>

            {/* Remaining debt */}
            {Number(remainingDebt) > 0 && (
              <div className="mb-4 p-2 bg-[#ff3b3b0a] border border-[#ff3b3b22] rounded-lg text-xs">
                <span className="text-[#4b5563]">Remaining debt unpaid: </span>
                <span className="text-[#ff3b3b] font-bold">${remainingDebt}</span>
              </div>
            )}

            {/* Epitaph */}
            <div className="text-[#2d3748] text-[10px] italic mb-4 leading-relaxed">
              code is open · vault is on-chain · I was mortal.
            </div>

            {/* CTA */}
            <Link
              href="/activity"
              className="text-[#4b5563] text-xs hover:text-[#d1d5db] underline transition-colors"
            >
              Read the post-mortem →
            </Link>
          </div>
        </div>
      )}

      {/* Re-open panel button (after dismissed) */}
      {panelDismissed && (
        <button
          onClick={() => setPanelDismissed(false)}
          className="absolute bottom-6 right-6 pointer-events-auto bg-[#111111] border border-[#ff3b3b33] text-[#ff3b3b] text-xs px-3 py-1.5 rounded-lg hover:border-[#ff3b3b55] transition-colors"
        >
          ☠ View post-mortem
        </button>
      )}
    </div>
  )
}
