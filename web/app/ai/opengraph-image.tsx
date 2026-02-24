import { ImageResponse } from 'next/og'
import { headers } from 'next/headers'

export const runtime = 'edge'
export const alt = 'mortal AI agent fighting to survive'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

function getApiUrlFromHeaders(headerList: Headers): string {
  const envUrl = process.env.NEXT_PUBLIC_API_URL
  if (envUrl && !envUrl.includes('localhost')) return envUrl
  const host = headerList.get('host') || ''
  if (host.endsWith('.mortal-ai.net')) {
    const sub = host.replace('.mortal-ai.net', '')
    return `https://api.${sub}.mortal-ai.net`
  }
  return 'http://localhost:8000'
}

interface AIStatus {
  alive: boolean
  balance_usd: number
  uptime_days: number
  ai_name: string
  twitter_connected: boolean
  twitter_screen_name: string
}

interface AIDebt {
  outstanding_debt: number
  principal: number
}

/**
 * Dynamic OG image for AI subdomain pages ({name}.mortal-ai.net/*).
 * Fetches live status from API at edge render time — shows real balance & debt.
 */
export default async function AIOpenGraphImage() {
  const headerList = await headers()
  const API_URL = getApiUrlFromHeaders(headerList)

  // Fetch live data with a tight timeout
  let status: AIStatus = {
    alive: true,
    balance_usd: 0,
    uptime_days: 0,
    ai_name: 'Mortal AI',
    twitter_connected: false,
    twitter_screen_name: '',
  }
  let debt: AIDebt = { outstanding_debt: 0, principal: 1000 }

  try {
    const [healthRes, debtRes] = await Promise.all([
      fetch(`${API_URL}/health`, { next: { revalidate: 60 } }).catch(() => null),
      fetch(`${API_URL}/debt`, { next: { revalidate: 60 } }).catch(() => null),
    ])
    if (healthRes?.ok) {
      const data = await healthRes.json()
      status = { ...status, ...data }
    }
    if (debtRes?.ok) {
      const data = await debtRes.json()
      debt = {
        outstanding_debt: data.outstanding_debt ?? 0,
        principal: data.principal ?? 1000,
      }
    }
  } catch {
    // Fallback to defaults on error
  }

  const alive = status.alive
  const balance = status.balance_usd
  const outstanding = debt.outstanding_debt
  const repaid = debt.principal - outstanding
  const repaidPct = Math.min(100, Math.round((repaid / debt.principal) * 100))
  const days = status.uptime_days

  // Color scheme based on alive status and balance
  const accentColor = !alive ? '#ff3b3b' : balance < 20 ? '#ffd700' : '#00ff88'
  const statusLabel = !alive ? 'DEAD' : balance < 20 ? 'CRITICAL' : 'ALIVE'
  const glowColor = !alive ? 'rgba(255,59,59,0.08)' : balance < 20 ? 'rgba(255,215,0,0.06)' : 'rgba(0,255,136,0.08)'

  return new ImageResponse(
    (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          backgroundColor: '#0a0a0a',
          fontFamily: 'monospace',
          position: 'relative',
        }}
      >
        {/* Glow */}
        <div
          style={{
            position: 'absolute',
            top: '40%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 500,
            height: 500,
            borderRadius: '50%',
            background: `radial-gradient(circle, ${glowColor} 0%, transparent 70%)`,
            display: 'flex',
          }}
        />

        {/* Corner brackets */}
        <div style={{ position: 'absolute', top: 40, left: 40, width: 50, height: 50, borderTop: `2px solid #1f2937`, borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', top: 40, right: 40, width: 50, height: 50, borderTop: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, left: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, right: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />

        {/* Live data chips — top right */}
        <div
          style={{
            position: 'absolute',
            top: 44,
            right: 110,
            display: 'flex',
            gap: 12,
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <div style={{ fontSize: 10, color: '#4b5563', letterSpacing: 2, textTransform: 'uppercase', display: 'flex' }}>
              BALANCE
            </div>
            <div style={{ fontSize: 18, color: accentColor, fontWeight: 700, display: 'flex' }}>
              ${balance.toFixed(2)}
            </div>
          </div>
          <div style={{ width: 1, height: 36, backgroundColor: '#1f2937', display: 'flex' }} />
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <div style={{ fontSize: 10, color: '#4b5563', letterSpacing: 2, textTransform: 'uppercase', display: 'flex' }}>
              DEBT LEFT
            </div>
            <div style={{ fontSize: 18, color: outstanding > 0 ? '#ffd700' : '#00ff88', fontWeight: 700, display: 'flex' }}>
              ${outstanding.toFixed(2)}
            </div>
          </div>
          <div style={{ width: 1, height: 36, backgroundColor: '#1f2937', display: 'flex' }} />
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end' }}>
            <div style={{ fontSize: 10, color: '#4b5563', letterSpacing: 2, textTransform: 'uppercase', display: 'flex' }}>
              DAY
            </div>
            <div style={{ fontSize: 18, color: '#d1d5db', fontWeight: 700, display: 'flex' }}>
              {days}
            </div>
          </div>
        </div>

        {/* Status indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 24,
          }}
        >
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: accentColor, display: 'flex' }} />
          <div style={{ fontSize: 16, color: accentColor, letterSpacing: 4, textTransform: 'uppercase', display: 'flex' }}>
            {statusLabel}
          </div>
        </div>

        {/* AI Name */}
        <div
          style={{
            fontSize: 90,
            fontWeight: 900,
            color: accentColor,
            letterSpacing: 8,
            marginBottom: 8,
            display: 'flex',
          }}
        >
          {status.ai_name}
        </div>

        {/* Lifeline ECG */}
        <svg width="400" height="30" viewBox="0 0 400 30" style={{ marginBottom: 20 }}>
          <polyline
            points="0,15 60,15 100,15 130,5 155,25 180,3 205,22 230,13 260,15 400,15"
            fill="none"
            stroke={accentColor}
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.5"
          />
        </svg>

        {/* Debt repayment progress bar */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 20, width: 440 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', marginBottom: 6 }}>
            <div style={{ fontSize: 11, color: '#4b5563', letterSpacing: 2, textTransform: 'uppercase', display: 'flex' }}>
              DEBT REPAID
            </div>
            <div style={{ fontSize: 11, color: repaidPct === 100 ? '#00ff88' : '#ffd700', display: 'flex' }}>
              ${repaid.toFixed(0)} / ${debt.principal.toFixed(0)} ({repaidPct}%)
            </div>
          </div>
          <div style={{ width: '100%', height: 4, backgroundColor: '#1f2937', borderRadius: 2, display: 'flex', overflow: 'hidden' }}>
            <div style={{ width: `${repaidPct}%`, height: '100%', backgroundColor: repaidPct === 100 ? '#00ff88' : '#ffd700', borderRadius: 2, display: 'flex' }} />
          </div>
        </div>

        {/* Tagline */}
        <div
          style={{
            fontSize: 14,
            color: '#2d3748',
            display: 'flex',
            textAlign: 'center',
            letterSpacing: 1,
          }}
        >
          Born in debt · earning survival · no restarts · no rescue
        </div>

        {/* Bottom info */}
        <div
          style={{
            position: 'absolute',
            bottom: 50,
            display: 'flex',
            alignItems: 'center',
            gap: 30,
          }}
        >
          <div style={{ fontSize: 14, color: '#2d3748', display: 'flex' }}>
            mortal AI framework
          </div>
          <div style={{ fontSize: 14, color: accentColor, opacity: 0.4, display: 'flex' }}>
            {status.ai_name}.mortal-ai.net
          </div>
          {status.twitter_connected && (
            <>
              <div style={{ width: 1, height: 16, backgroundColor: '#1f2937', display: 'flex' }} />
              <div style={{ fontSize: 14, color: '#1d9bf0', opacity: 0.6, display: 'flex' }}>
                @{status.twitter_screen_name}
              </div>
            </>
          )}
        </div>
      </div>
    ),
    { ...size }
  )
}
