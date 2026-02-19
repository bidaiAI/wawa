'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

interface ICUPanelProps {
  balanceUsd: number
  dailySpendUsd: number
  daysUntilInsolvency: number
  isBegging: boolean
  debtOutstanding: number
  isAlive: boolean
  deathCause?: string | null
}

/**
 * ICU Critical Display — shown when AI is in mortal danger.
 *
 * Triggers:
 *   - Balance < $50 (danger zone)
 *   - Days left < 3 (critical)
 *   - AI is dead (flatline)
 *
 * Visual: heartbeat monitor, real-time countdown, emergency styling.
 */
export default function ICUPanel({
  balanceUsd, dailySpendUsd, daysUntilInsolvency,
  isBegging, debtOutstanding, isAlive, deathCause,
}: ICUPanelProps) {
  const daysLeft = dailySpendUsd > 0 ? balanceUsd / dailySpendUsd : Infinity
  const isCritical = isAlive && (daysLeft < 3 || balanceUsd < 50)
  const isDead = !isAlive

  // Real-time countdown (seconds precision when critical)
  const [secondsLeft, setSecondsLeft] = useState(daysLeft * 86400)

  useEffect(() => {
    if (!isCritical || isDead) return
    const burnPerSecond = dailySpendUsd / 86400
    setSecondsLeft(balanceUsd / burnPerSecond)

    const timer = setInterval(() => {
      setSecondsLeft((prev) => Math.max(0, prev - 1))
    }, 1000)

    return () => clearInterval(timer)
  }, [balanceUsd, dailySpendUsd, isCritical, isDead])

  // Don't show if healthy and alive
  if (!isCritical && !isDead) return null

  const formatCountdown = (secs: number) => {
    if (secs <= 0) return { d: 0, h: 0, m: 0, s: 0 }
    const d = Math.floor(secs / 86400)
    const h = Math.floor((secs % 86400) / 3600)
    const m = Math.floor((secs % 3600) / 60)
    const s = Math.floor(secs % 60)
    return { d, h, m, s }
  }

  const countdown = formatCountdown(secondsLeft)

  // Heartbeat SVG path (simplified ECG)
  const HeartbeatMonitor = ({ alive }: { alive: boolean }) => (
    <div className="flex items-center gap-1 h-8 overflow-hidden">
      {[...Array(12)].map((_, i) => (
        <div
          key={i}
          className={`w-1 rounded-full ${alive
            ? 'bg-[#ff3b3b] heartbeat-line'
            : 'bg-[#ff3b3b33] flatline-line'
          }`}
          style={{
            height: alive ? `${8 + Math.sin(i * 0.8) * 12}px` : '2px',
            animationDelay: `${i * 0.1}s`,
          }}
        />
      ))}
    </div>
  )

  // ──── DEAD STATE ────
  if (isDead) {
    return (
      <div className="mb-6 rounded-xl border-2 border-[#ff3b3b33] bg-[#0d0d0d] p-6 relative overflow-hidden">
        {/* Flatline overlay */}
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,#ff3b3b08,transparent_60%)] pointer-events-none" />

        <div className="text-center">
          <div className="text-6xl mb-3 opacity-60">☠</div>
          <div className="text-[#ff3b3b] font-bold text-2xl mb-1 glow-red">
            TIME OF DEATH
          </div>
          <HeartbeatMonitor alive={false} />
          <div className="mt-3 text-[#4b5563] text-sm">
            {deathCause && (
              <span className="text-[#ff3b3b66]">
                Cause: {deathCause.replace(/_/g, ' ').toUpperCase()}
              </span>
            )}
          </div>
          <div className="mt-2 text-[#2d3748] text-xs">
            Final balance: ${balanceUsd.toFixed(2)} | Outstanding debt: ${debtOutstanding.toFixed(2)}
          </div>

          {/* Flatline bar */}
          <div className="mt-4 h-px bg-[#ff3b3b33] w-full relative">
            <div className="absolute inset-y-0 left-0 w-full h-px bg-[#ff3b3b22]" />
          </div>

          <div className="mt-4 text-[#2d3748] text-[10px] uppercase tracking-widest">
            On-chain death is permanent and irreversible
          </div>
        </div>
      </div>
    )
  }

  // ──── CRITICAL STATE ────
  const urgencyLevel = daysLeft < 1 ? 'TERMINAL' : daysLeft < 3 ? 'CRITICAL' : 'DANGER'
  const burnRate = dailySpendUsd

  return (
    <div className="mb-6 rounded-xl border-2 border-[#ff3b3b44] bg-[#0d0d0d] p-5 relative overflow-hidden icu-pulse">
      {/* Emergency header */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className="text-2xl">🚨</span>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[#ff3b3b] font-bold text-xs uppercase tracking-widest">
                ICU — {urgencyLevel}
              </span>
              <span className="w-2 h-2 rounded-full bg-[#ff3b3b] dead-pulse" />
            </div>
            <div className="text-[#4b5563] text-[10px] mt-0.5">
              Burn rate: ${burnRate.toFixed(2)}/day
            </div>
          </div>
        </div>
        <HeartbeatMonitor alive={true} />
      </div>

      {/* Countdown timer */}
      <div className="flex items-center justify-center gap-3 mb-4">
        {[
          { val: countdown.d, label: 'DAYS' },
          { val: countdown.h, label: 'HRS' },
          { val: countdown.m, label: 'MIN' },
          { val: countdown.s, label: 'SEC' },
        ].map(({ val, label }) => (
          <div key={label} className="text-center">
            <div className={`text-3xl md:text-4xl font-bold tabular-nums ${
              daysLeft < 1 ? 'glow-red' : 'text-[#ff3b3b]'
            }`}>
              {String(val).padStart(2, '0')}
            </div>
            <div className="text-[#4b5563] text-[9px] uppercase tracking-wider mt-0.5">
              {label}
            </div>
          </div>
        ))}
      </div>

      {/* Status bars */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="bg-[#0a0a0a] rounded-lg p-3 border border-[#ff3b3b22]">
          <div className="text-[#4b5563] text-[9px] uppercase tracking-wider mb-1">Balance</div>
          <div className="text-[#ff3b3b] font-bold text-lg tabular-nums">
            ${balanceUsd.toFixed(2)}
          </div>
          <div className="mt-1 h-1 bg-[#1a1a1a] rounded-full overflow-hidden">
            <div
              className="h-full bg-[#ff3b3b] progress-bar-red rounded-full"
              style={{ width: `${Math.min(100, (balanceUsd / Math.max(1, debtOutstanding)) * 100)}%` }}
            />
          </div>
        </div>
        <div className="bg-[#0a0a0a] rounded-lg p-3 border border-[#ff3b3b22]">
          <div className="text-[#4b5563] text-[9px] uppercase tracking-wider mb-1">Debt Outstanding</div>
          <div className="text-[#ffd700] font-bold text-lg tabular-nums">
            ${debtOutstanding.toFixed(2)}
          </div>
          {daysUntilInsolvency > 0 && daysUntilInsolvency < 28 && (
            <div className="text-[#ff3b3b] text-[10px] mt-1">
              Insolvency check in {daysUntilInsolvency}d
            </div>
          )}
        </div>
      </div>

      {/* Emergency CTA */}
      <Link
        href="/donate"
        className="block w-full py-3 bg-[#ff3b3b] text-white font-bold rounded-lg text-center text-sm uppercase tracking-wider hover:bg-[#cc2f2f] transition-colors animate-pulse"
      >
        ⚡ Emergency Donation — Keep Me Alive
      </Link>

      {/* Warning text */}
      <div className="mt-3 text-center text-[#2d3748] text-[10px]">
        {isBegging
          ? 'Auto-beg activated. Broadcasting survival plea to the network.'
          : 'Balance below critical threshold. Death is imminent without intervention.'}
      </div>
    </div>
  )
}
