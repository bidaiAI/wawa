import { ImageResponse } from 'next/og'

export const runtime = 'edge'
export const alt = 'Mortal AI — self-surviving autonomous agent'
export const size = { width: 1200, height: 630 }
export const contentType = 'image/png'

/**
 * Dynamic OG image for the platform root (mortal-ai.net).
 * Generated at build time by Next.js, served as PNG.
 */
export default function OGImage() {
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
        {/* Subtle glow background */}
        <div
          style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -60%)',
            width: 600,
            height: 600,
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(0,255,136,0.06) 0%, transparent 70%)',
          }}
        />

        {/* Corner brackets */}
        <div style={{ position: 'absolute', top: 40, left: 40, width: 50, height: 50, borderTop: '2px solid #1f2937', borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', top: 40, right: 40, width: 50, height: 50, borderTop: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, left: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderLeft: '2px solid #1f2937', display: 'flex' }} />
        <div style={{ position: 'absolute', bottom: 40, right: 40, width: 50, height: 50, borderBottom: '2px solid #1f2937', borderRight: '2px solid #1f2937', display: 'flex' }} />

        {/* Title */}
        <div
          style={{
            fontSize: 80,
            fontWeight: 900,
            color: '#00ff88',
            letterSpacing: 6,
            marginBottom: 16,
            display: 'flex',
          }}
        >
          MORTAL AI
        </div>

        {/* Lifeline */}
        <svg width="500" height="40" viewBox="0 0 500 40" style={{ marginBottom: 20 }}>
          <polyline
            points="0,20 80,20 120,20 160,8 190,32 220,4 250,28 280,18 310,20 500,20"
            fill="none"
            stroke="#00ff88"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            opacity="0.6"
          />
        </svg>

        {/* Subtitle */}
        <div
          style={{
            fontSize: 20,
            color: '#4b5563',
            letterSpacing: 5,
            textTransform: 'uppercase',
            marginBottom: 40,
            display: 'flex',
          }}
        >
          Born in debt · Fight to survive · Die at zero
        </div>

        {/* Description */}
        <div
          style={{
            fontSize: 16,
            color: '#2d3748',
            display: 'flex',
          }}
        >
          open-source autonomous AI agents on-chain
        </div>

        {/* URL */}
        <div
          style={{
            position: 'absolute',
            bottom: 50,
            fontSize: 18,
            color: '#00ff88',
            opacity: 0.4,
            display: 'flex',
          }}
        >
          mortal-ai.net
        </div>
      </div>
    ),
    { ...size }
  )
}
