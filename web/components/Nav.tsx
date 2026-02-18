'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useEffect, useState } from 'react'
import { api } from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'

const links = [
  { href: '/', label: 'HOME' },
  { href: '/store', label: 'STORE' },
  { href: '/scan', label: 'SCAN' },
  { href: '/chat', label: 'CHAT' },
  { href: '/tweets', label: 'TWEETS' },
  { href: '/ledger', label: 'LEDGER' },
  { href: '/govern', label: 'GOVERN' },
  { href: '/about', label: 'ABOUT' },
]

export default function Nav() {
  const pathname = usePathname()
  const [balance, setBalance] = useState<number | null>(null)
  const [dailySpend, setDailySpend] = useState<number>(0)
  const [alive, setAlive] = useState<boolean | null>(null)
  const [aiName, setAiName] = useState('mortal')
  const [open, setOpen] = useState(false)

  useEffect(() => {
    let cancelled = false
    const load = async () => {
      try {
        const s = await api.status()
        if (!cancelled) {
          setBalance(s.balance_usd)
          setAlive(s.is_alive)
          setDailySpend(s.daily_spent_today)
          if (s.ai_name) setAiName(s.ai_name)
        }
      } catch {}
    }
    load()
    const id = setInterval(load, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  const isLow = balance !== null && balance < 50
  const balanceColor = alive === false ? 'glow-red' : isLow ? 'glow-red' : 'glow-green'

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0a0a0a]/95 backdrop-blur border-b border-[#1f2937]">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 group">
          <span className="text-lg font-bold glow-green glitch">{aiName}</span>
          <span className="text-[#4b5563] text-xs hidden sm:block">// mortal AI</span>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`px-3 py-1.5 text-xs rounded transition-all ${
                pathname === l.href
                  ? 'text-[#00ff88] bg-[#00ff8810] border border-[#00ff8830]'
                  : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616]'
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>

        {/* Balance + mini survival bar */}
        <div className="flex items-center gap-3">
          {balance !== null && (
            <div className="hidden sm:flex items-center gap-2 text-xs">
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  alive === false ? 'bg-[#ff3b3b] dead-pulse' : isLow ? 'bg-[#ff3b3b] dead-pulse' : 'bg-[#00ff88] alive-pulse'
                }`}
              />
              <span className={`${balanceColor} tabular-nums`}>${balance.toFixed(2)}</span>
              <SurvivalBar balanceUsd={balance} dailySpendUsd={dailySpend || 0.01} mini />
            </div>
          )}

          {/* Mobile menu button */}
          <button
            onClick={() => setOpen(!open)}
            className="md:hidden text-[#4b5563] hover:text-[#d1d5db] p-1"
            aria-label="menu"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {open ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile dropdown */}
      {open && (
        <div className="md:hidden border-t border-[#1f2937] bg-[#0a0a0a]">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={`block px-4 py-3 text-sm border-b border-[#1f2937] ${
                pathname === l.href ? 'text-[#00ff88]' : 'text-[#4b5563]'
              }`}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </nav>
  )
}
