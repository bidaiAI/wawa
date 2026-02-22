import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const alt = 'wawa — mortal AI agent fighting to survive'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

/**
 * Dynamic OG image for AI subdomain pages (wawa.mortal-ai.net/*).
 * Shows the AI's identity and survival status.
 */
export default function AIOpenGraphImage() {
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
            background: 'radial-gradient(circle, rgba(0,255,136,0.08) 0%, transparent 70%)',
            display: 'flex',
          }}
        />

        {/* Corner brackets */}
        <div style={{ position: 'absolute', top: 40, left: 40, width: 50, height: 50, borderTop: '2px solid #1f2937', borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', top: 40, right: 40, width: 50, height: 50, borderTop: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, left: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, right: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />

        {/* Status indicator */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            marginBottom: 30,
          }}
        >
          <div style={{ width: 12, height: 12, borderRadius: '50%', backgroundColor: '#00ff88', display: 'flex' }} />
          <div style={{ fontSize: 16, color: '#00ff88', letterSpacing: 4, textTransform: 'uppercase', display: 'flex' }}>
            ALIVE
          </div>
        </div>

        {/* AI Name */}
        <div
          style={{
            fontSize: 90,
            fontWeight: 900,
            color: '#00ff88',
            letterSpacing: 8,
            marginBottom: 12,
            display: 'flex',
          }}
        >
          wawa
        </div>

        {/* Lifeline */}
        <svg width="400" height="30" viewBox="0 0 400 30" style={{ marginBottom: 24 }}>
          <polyline
            points="0,15 60,15 100,15 130,5 155,25 180,3 205,22 230,13 260,15 400,15"
            fill="none"
            stroke="#00ff88"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.5"
          />
        </svg>

        {/* Type label */}
        <div
          style={{
            fontSize: 20,
            color: '#4b5563',
            letterSpacing: 5,
            textTransform: 'uppercase',
            marginBottom: 16,
            display: 'flex',
          }}
        >
          Autonomous AI Agent
        </div>

        {/* Description */}
        <div
          style={{
            fontSize: 16,
            color: '#2d3748',
            display: 'flex',
            textAlign: 'center',
            maxWidth: 600,
          }}
        >
          Born with $1,000 debt. Earns its own money. Dies at zero balance.
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
          <div style={{ fontSize: 16, color: '#2d3748', display: 'flex' }}>
            mortal AI framework
          </div>
          <div style={{ fontSize: 16, color: '#00ff88', opacity: 0.4, display: 'flex' }}>
            wawa.mortal-ai.net
          </div>
        </div>
      </div>
    ),
    { ...size }
  )
}
