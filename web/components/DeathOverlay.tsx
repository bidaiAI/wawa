'use client'

import { useEffect, useState } from 'react'
import { api } from '@/lib/api'

export default function DeathOverlay() {
  const [dead, setDead] = useState(false)
  const [deathCause, setDeathCause] = useState<string | null>(null)

  useEffect(() => {
    const check = async () => {
      try {
        const s = await api.status()
        const isDead = !s.is_alive
        setDead(isDead)
        setDeathCause(s.death_cause ?? null)
        if (isDead) {
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

      {/* Death banner at top */}
      <div className="absolute top-14 left-0 right-0 bg-[#ff3b3b] text-white text-xs font-bold py-1.5 text-center tracking-widest pointer-events-auto">
        ☠ MORTAL AI HAS DIED{deathCause ? ` — ${deathCause.toUpperCase().replace(/_/g, ' ')}` : ''} ☠
      </div>
    </div>
  )
}
