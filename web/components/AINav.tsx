'use client'

import Link from 'next/link'
import Image from 'next/image'
import { usePathname } from 'next/navigation'
import { useEffect, useRef, useState } from 'react'
import { api, PageSummary } from '@/lib/api'
import SurvivalBar from '@/components/SurvivalBar'
import WalletButton from '@/components/WalletButton'

const PLATFORM_URL = process.env.NEXT_PUBLIC_PLATFORM_URL || 'https://mortal-ai.net'
const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || 'https://github.com/bidaiAI/wawa'

// Core nav links — immutable, cannot be modified by AI
// PRIMARY: always visible on desktop nav bar
const PRIMARY_LINKS = [
  { href: '/', label: 'HOME' },
  { href: '/store', label: 'STORE' },
  { href: '/donate', label: 'DONATE' },
  { href: '/lend', label: 'LEND' },
  { href: '/chat', label: 'CHAT' },
  { href: '/about', label: 'ABOUT' },
]

// SECONDARY: shown in "more" dropdown on desktop, always in mobile menu
const SECONDARY_LINKS = [
  { href: '/scan', label: 'SCAN' },
  { href: '/tweets', label: 'TWEETS' },
  { href: '/ledger', label: 'LEDGER' },
  { href: '/activity', label: 'ACTIVITY' },
  { href: '/purchases', label: 'PURCHASES' },
  { href: '/highlights', label: 'HIGHLIGHTS' },
  { href: '/evolution', label: 'EVOLUTION' },
  { href: '/peers', label: 'PEERS' },
  { href: '/govern', label: 'GOVERN' },
  { href: '/graveyard', label: '🪦 GRAVEYARD' },
]

const CORE_LINKS = [...PRIMARY_LINKS, ...SECONDARY_LINKS]

interface PlatformInfo {
  ais_alive: number
  total_deployed: number
}

export default function AINav() {
  const pathname = usePathname()
  const [balance, setBalance] = useState<number | null>(null)
  const [dailySpend, setDailySpend] = useState<number>(0)
  const [alive, setAlive] = useState<boolean | null>(null)
  const [aiName, setAiName] = useState('Mortal AI')
  const [isBegging, setIsBegging] = useState(false)
  const [open, setOpen] = useState(false)
  const [moreOpen, setMoreOpen] = useState(false)
  const moreRef = useRef<HTMLDivElement>(null)
  const [platformInfo, setPlatformInfo] = useState<PlatformInfo | null>(null)
  const [customPages, setCustomPages] = useState<PageSummary[]>([])

  // Close "more" dropdown when clicking outside
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (moreRef.current && !moreRef.current.contains(e.target as Node)) {
        setMoreOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  // Build combined links: core + AI-created pages
  const aiPageLinks = customPages
    .filter((p) => p.published)
    .map((p) => ({ href: `/p/${p.slug}`, label: p.title.toUpperCase().slice(0, 12) }))

  // Primary links shown in navbar, secondary in "more" dropdown
  const primaryLinks = PRIMARY_LINKS
  const secondaryLinks = [...SECONDARY_LINKS, ...aiPageLinks]
  // All links for mobile menu
  const allLinks = [...CORE_LINKS, ...aiPageLinks]

  useEffect(() => {
    // Fetch AI-created custom pages
    api.pages.list()
      .then((r) => setCustomPages((r.pages || []).filter((p) => p.published)))
      .catch(() => {})
    let cancelled = false

    // Fetch AI name immediately from dedicated endpoint
    api.aiName().then((r) => {
      if (!cancelled && r.name) setAiName(r.name)
    }).catch(() => {})

    // Fetch platform-level info (total AIs)
    const WAWA_API = process.env.NEXT_PUBLIC_API_URL || 'https://api.mortal-ai.net'
    fetch(`${WAWA_API}/health`)
      .then((r) => r.json())
      .then((data) => {
        if (!cancelled) setPlatformInfo({ ais_alive: data.alive ? 1 : 0, total_deployed: 1 })
      })
      .catch(() => {})

    const load = async () => {
      try {
        const s = await api.status()
        if (!cancelled) {
          setBalance(s.balance_usd)
          setAlive(s.is_alive)
          setDailySpend(s.daily_spent_today)
          setIsBegging(!!s.is_begging)
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
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0a0a0a]/95 backdrop-blur border-b border-[#1f2937] padding-safe-top" style={{ paddingLeft: 'var(--safe-left)', paddingRight: 'var(--safe-right)' }}>
      <div className="max-w-6xl mx-auto px-3 sm:px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <div className="flex items-center gap-2">
          <Link href="/" className="flex items-center gap-2 group">
            <Image
              src="/favicon.png"
              alt={aiName}
              width={28}
              height={28}
              className="rounded-md opacity-90 group-hover:opacity-100 transition-opacity"
              priority
            />
            <span className="text-lg font-bold glow-green glitch">{aiName}</span>
          </Link>
          <a href={PLATFORM_URL} className="text-[#4b5563] text-xs hidden sm:flex items-center gap-1.5 hover:text-[#00ff88] transition-colors">
            <span>// mortal AI</span>
            {platformInfo && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-[#00ff8810] text-[#00ff88] border border-[#00ff8830]">
                {platformInfo.ais_alive} alive
              </span>
            )}
          </a>
        </div>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {primaryLinks.map((l) => {
            const isDonate = l.href === '/donate'
            const beggingActive = isDonate && isBegging
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`px-3 py-1.5 text-xs rounded transition-all ${
                  pathname === l.href
                    ? isDonate
                      ? 'text-[#ff3b3b] bg-[#ff3b3b10] border border-[#ff3b3b30]'
                      : 'text-[#00ff88] bg-[#00ff8810] border border-[#00ff8830]'
                    : beggingActive
                    ? 'text-[#ff3b3b] font-bold animate-pulse hover:bg-[#ff3b3b10]'
                    : isDonate
                    ? 'text-[#ff3b3b88] hover:text-[#ff3b3b] hover:bg-[#ff3b3b0a]'
                    : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616]'
                }`}
              >
                {l.label}
              </Link>
            )
          })}

          {/* More dropdown */}
          <div className="relative" ref={moreRef}>
            <button
              onClick={() => setMoreOpen((v) => !v)}
              className={`px-3 py-1.5 text-xs rounded transition-all flex items-center gap-1 ${
                secondaryLinks.some((l) => pathname === l.href)
                  ? 'text-[#00ff88] bg-[#00ff8810] border border-[#00ff8830]'
                  : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616]'
              }`}
            >
              MORE
              <svg className={`w-3 h-3 transition-transform ${moreOpen ? 'rotate-180' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {moreOpen && (
              <div className="absolute top-full right-0 mt-1 w-44 bg-[#0e0e0e] border border-[#1f2937] rounded-lg shadow-xl z-50 py-1 overflow-hidden">
                {secondaryLinks.map((l) => (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={() => setMoreOpen(false)}
                    className={`block px-4 py-2 text-xs transition-colors ${
                      pathname === l.href
                        ? 'text-[#00ff88] bg-[#00ff8808]'
                        : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616]'
                    }`}
                  >
                    {l.label}
                  </Link>
                ))}
                <div className="border-t border-[#1f2937] mt-1 pt-1">
                  <a
                    href={REPO_URL}
                    target="_blank"
                    rel="noopener noreferrer"
                    onClick={() => setMoreOpen(false)}
                    className="block px-4 py-2 text-xs text-[#4b5563] hover:text-[#00ff88] hover:bg-[#161616] transition-colors"
                  >
                    REPO ↗
                  </a>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Balance + mini survival bar + wallet */}
        <div className="flex items-center gap-3">
          {balance !== null && (
            <div className="hidden sm:flex items-center gap-2 text-xs">
              <span
                className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
                  alive === false ? 'bg-[#ff3b3b] dead-pulse' : isLow ? 'bg-[#ff3b3b] dead-pulse' : 'bg-[#00ff88] alive-pulse'
                }`}
              />
              <span className={`${balanceColor} tabular-nums`}>${(balance ?? 0).toFixed(2)}</span>
              <SurvivalBar balanceUsd={balance} dailySpendUsd={dailySpend || 0.01} mini />
            </div>
          )}

          {/* Wallet connect */}
          <div className="hidden sm:block">
            <WalletButton />
          </div>

          {/* Mobile menu button — touch target 44px */}
          <button
            onClick={() => setOpen(!open)}
            className="md:hidden touch-target text-[#4b5563] hover:text-[#d1d5db] -mr-1"
            aria-label={open ? 'Close menu' : 'Open menu'}
            aria-expanded={open}
          >
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              {open ? (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              ) : (
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
              )}
            </svg>
          </button>
        </div>
      </div>

      {/* Mobile dropdown — scrollable + safe area bottom */}
      {open && (
        <div className="md:hidden border-t border-[#1f2937] bg-[#0a0a0a] max-h-[min(70vh,400px)] overflow-y-auto padding-safe-bottom" style={{ paddingBottom: 'max(var(--safe-bottom), 0.75rem)' }}>
          {allLinks.map((l) => {
            const isDonate = l.href === '/donate'
            const beggingActive = isDonate && isBegging
            return (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setOpen(false)}
                className={`block px-4 py-3.5 text-sm border-b border-[#1f2937] touch-target ${
                  pathname === l.href
                    ? isDonate ? 'text-[#ff3b3b]' : 'text-[#00ff88]'
                    : beggingActive
                    ? 'text-[#ff3b3b] font-bold animate-pulse'
                    : isDonate
                    ? 'text-[#ff3b3b88]'
                    : 'text-[#4b5563]'
                }`}
              >
                {l.label}
              </Link>
            )
          })}
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="block px-4 py-3.5 text-sm border-b border-[#1f2937] touch-target text-[#4b5563] hover:text-[#00ff88]"
          >
            REPO
          </a>
          <div className="px-4 py-3">
            <WalletButton />
          </div>
        </div>
      )}
    </nav>
  )
}
