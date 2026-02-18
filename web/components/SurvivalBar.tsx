'use client'

/**
 * SurvivalBar — reusable multi-zone survival progress bar.
 *
 * Zone thresholds (based on days-left):
 *   critical  < 3 days  → red, pulsing
 *   danger    < 7 days  → orange/yellow
 *   low      < 14 days  → yellow
 *   healthy  >= 14 days → green
 *
 * Milestone markers (based on USD balance):
 *   $10   → DEATH (iron law min reserve)
 *   $50   → DANGER
 *   $200  → survival discount triggers
 *   $1M   → INDEPENDENCE
 */

export interface SurvivalBarProps {
  /** current vault balance in USD */
  balanceUsd: number
  /** today's spend in USD (used to project days remaining) */
  dailySpendUsd: number
  /** daily API budget limit */
  dailyLimitUsd?: number
  /** show the API budget sub-bar below main bar */
  showApiBar?: boolean
  /** compact/mini size — hides labels and milestones */
  mini?: boolean
}

interface Zone {
  label: string
  days: number
  bar: string
  text: string
  bg: string
  border: string
  pulse?: boolean
}

const ZONES: Zone[] = [
  {
    label: 'CRITICAL',
    days: 3,
    bar: 'bg-[#ff3b3b]',
    text: 'glow-red',
    bg: 'bg-[#ff3b3b0a]',
    border: 'border-[#ff3b3b44]',
    pulse: true,
  },
  {
    label: 'DANGER',
    days: 7,
    bar: 'bg-[#ff7043]',
    text: 'text-[#ff7043]',
    bg: 'bg-[#ff70430a]',
    border: 'border-[#ff704344]',
  },
  {
    label: 'LOW',
    days: 14,
    bar: 'bg-[#ffd700]',
    text: 'text-[#ffd700]',
    bg: 'bg-[#ffd7000a]',
    border: 'border-[#ffd70044]',
  },
  {
    label: 'STABLE',
    days: Infinity,
    bar: 'bg-[#00ff88]',
    text: 'glow-green',
    bg: 'bg-[#00ff880a]',
    border: 'border-[#00ff8822]',
  },
]

/** Milestones shown as tick marks on the bar (USD balance thresholds) */
const MILESTONES = [
  { usd: 10,    label: '☠', tip: '$10 — DEATH' },
  { usd: 50,    label: '⚠', tip: '$50 — DANGER' },
  { usd: 200,   label: '🏷', tip: '$200 — discount triggers' },
]

function getZone(daysLeft: number): Zone {
  return ZONES.find((z) => daysLeft < z.days) ?? ZONES[ZONES.length - 1]
}

/** Map balance → position on a log-scale bar (0-100%). */
function balanceToPct(balance: number): number {
  if (balance <= 0) return 0
  // log scale: $10 → ~5%, $200 → ~35%, $1000 → ~50%, $10k → ~75%
  const MAX = 50_000
  const pct = Math.log10(Math.max(1, balance)) / Math.log10(MAX) * 100
  return Math.min(100, Math.max(0, pct))
}

function milestonePct(usd: number): number {
  return balanceToPct(usd)
}

export default function SurvivalBar({
  balanceUsd,
  dailySpendUsd,
  dailyLimitUsd,
  showApiBar = false,
  mini = false,
}: SurvivalBarProps) {
  const daysLeft = dailySpendUsd > 0 ? balanceUsd / dailySpendUsd : Infinity
  const zone = getZone(daysLeft)
  const fillPct = balanceToPct(balanceUsd)

  const daysLabel =
    daysLeft === Infinity ? '∞'
    : daysLeft > 999 ? '>999d'
    : `~${daysLeft.toFixed(1)}d`

  if (mini) {
    return (
      <div className="flex items-center gap-2">
        <div className="w-20 h-1.5 bg-[#1f2937] rounded-full overflow-hidden">
          <div
            className={`h-full rounded-full transition-all duration-1000 ${zone.bar} ${zone.pulse ? 'progress-bar-red' : ''}`}
            style={{ width: `${fillPct}%` }}
          />
        </div>
        <span className={`text-xs font-mono ${zone.text}`}>{daysLabel}</span>
      </div>
    )
  }

  return (
    <div className={`rounded-xl p-5 border ${zone.border} ${zone.bg}`}>
      {/* Header row */}
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <span className="text-[#4b5563] text-xs uppercase tracking-widest">生存进度</span>
          <span
            className={`text-xs px-1.5 py-0.5 rounded border border-current font-bold ${zone.text}`}
            style={{ opacity: 0.8 }}
          >
            {zone.label}
          </span>
        </div>
        <span className={`text-lg font-bold tabular-nums ${zone.text}`}>{daysLabel}</span>
      </div>
      <div className="text-[#4b5563] text-xs mb-3">
        距离死亡 · 基于今日支出 ${dailySpendUsd.toFixed(2)}/天
      </div>

      {/* Main bar with milestone markers */}
      <div className="relative">
        {/* Track */}
        <div className="h-4 bg-[#1a1a1a] rounded-full overflow-visible border border-[#1f2937] relative">
          {/* Fill */}
          <div
            className={`h-full rounded-full transition-all duration-1000 absolute left-0 top-0 ${zone.bar} ${zone.pulse ? 'progress-bar-red' : ''}`}
            style={{ width: `${fillPct}%` }}
          />
          {/* Zone dividers */}
          <div className="absolute inset-0 flex rounded-full overflow-hidden pointer-events-none">
            {/* gradient zones overlay */}
            <div className="absolute inset-0 rounded-full"
              style={{
                background: 'linear-gradient(to right, #ff3b3b22 0%, #ff3b3b11 8%, transparent 15%, transparent 100%)',
              }}
            />
          </div>
        </div>

        {/* Milestone ticks */}
        {MILESTONES.map((m) => {
          const pct = milestonePct(m.usd)
          return (
            <div
              key={m.usd}
              className="absolute top-0 -translate-x-1/2 group"
              style={{ left: `${pct}%` }}
              title={m.tip}
            >
              <div className="w-px h-4 bg-[#4b5563] opacity-60" />
              <div className="text-[9px] text-[#4b5563] mt-0.5 whitespace-nowrap hidden group-hover:block absolute -top-5 left-1/2 -translate-x-1/2 bg-[#0a0a0a] px-1 py-0.5 rounded border border-[#1f2937] z-10">
                {m.tip}
              </div>
            </div>
          )
        })}

        {/* Current position pin */}
        {fillPct > 2 && fillPct < 98 && (
          <div
            className="absolute top-1/2 -translate-y-1/2 -translate-x-1/2 pointer-events-none"
            style={{ left: `${fillPct}%` }}
          >
            <div className={`w-3 h-3 rounded-full border-2 border-[#0a0a0a] ${zone.bar}`} />
          </div>
        )}
      </div>

      {/* Balance labels */}
      <div className="flex justify-between mt-1 text-[9px] text-[#2d3748]">
        <span>$0</span>
        <span>$10</span>
        <span>$200</span>
        <span>$1k</span>
        <span>$10k+</span>
      </div>

      {/* API budget sub-bar */}
      {showApiBar && dailyLimitUsd !== undefined && dailyLimitUsd > 0 && (
        <div className="mt-4 pt-4 border-t border-[#1f2937]">
          <div className="flex justify-between items-center mb-1.5">
            <span className="text-[#4b5563] text-xs uppercase tracking-widest">今日 API 预算</span>
            <span className="text-xs text-[#4b5563] tabular-nums">
              ${dailySpendUsd.toFixed(2)} / ${dailyLimitUsd.toFixed(2)}
            </span>
          </div>
          <div className="h-1.5 bg-[#1a1a1a] rounded-full border border-[#1f2937]">
            {(() => {
              const apipct = Math.min(100, (dailySpendUsd / dailyLimitUsd) * 100)
              const apiColor = apipct > 90 ? 'bg-[#ff3b3b]' : apipct > 70 ? 'bg-[#ffd700]' : 'bg-[#00e5ff]'
              return (
                <div
                  className={`h-full rounded-full transition-all duration-700 ${apiColor}`}
                  style={{ width: `${apipct}%` }}
                />
              )
            })()}
          </div>
        </div>
      )}
    </div>
  )
}
