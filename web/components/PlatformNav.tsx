'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect } from 'react'
import { useAccount } from 'wagmi'
import WalletButton from '@/components/WalletButton'
import { getAdminToken, adminApi } from '@/lib/admin-api'

const links = [
  { href: '/', label: 'HOME' },
  { href: '/create', label: 'CREATE' },
  { href: '/gallery', label: 'GALLERY' },
  { href: '/ecosystem', label: 'ECOSYSTEM', accent: true },
  { href: '/dashboard', label: 'DASHBOARD' },
  { href: '/about', label: 'ABOUT' },
]

export default function PlatformNav() {
  const pathname = usePathname()
  const [open, setOpen] = useState(false)
  const { isConnected } = useAccount()
  const [isAdmin, setIsAdmin] = useState(false)

  useEffect(() => {
    if (!isConnected || !getAdminToken()) {
      setIsAdmin(false)
      return
    }
    adminApi.isAdmin().then((r) => setIsAdmin(r.is_admin)).catch(() => setIsAdmin(false))
  }, [isConnected])

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0a0a0a]/95 backdrop-blur border-b border-[#1f2937]">
      <div className="max-w-6xl mx-auto px-4 h-14 flex items-center justify-between">
        {/* Logo */}
        <Link href="/" className="flex items-center gap-2 group">
          <span className="text-lg font-bold glow-green glitch">MORTAL</span>
          <span className="text-[#4b5563] text-xs hidden sm:block">// sovereign AI platform</span>
        </Link>

        {/* Desktop links */}
        <div className="hidden md:flex items-center gap-1">
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className={`px-3 py-1.5 text-xs rounded transition-all ${
                pathname === l.href
                  ? l.accent
                    ? 'text-[#e0a0ff] bg-[#e0a0ff10] border border-[#e0a0ff30]'
                    : 'text-[#00ff88] bg-[#00ff8810] border border-[#00ff8830]'
                  : l.accent
                  ? 'text-[#e0a0ff80] hover:text-[#e0a0ff] hover:bg-[#161616]'
                  : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616]'
              }`}
            >
              {l.label}
            </Link>
          ))}
          {isAdmin && (
            <Link
              href="/admin"
              className={`px-3 py-1.5 text-xs rounded transition-all ${
                pathname?.startsWith('/admin')
                  ? 'text-[#ff8800] bg-[#ff880010] border border-[#ff880030]'
                  : 'text-[#ff880080] hover:text-[#ff8800] hover:bg-[#161616]'
              }`}
            >
              ADMIN
            </Link>
          )}
        </div>

        {/* Wallet + mobile menu */}
        <div className="flex items-center gap-3">
          <div className="hidden sm:block">
            <WalletButton />
          </div>

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
                pathname === l.href
                  ? l.accent ? 'text-[#e0a0ff]' : 'text-[#00ff88]'
                  : l.accent ? 'text-[#e0a0ff80]' : 'text-[#4b5563]'
              }`}
            >
              {l.label}
            </Link>
          ))}
          {isAdmin && (
            <Link
              href="/admin"
              onClick={() => setOpen(false)}
              className={`block px-4 py-3 text-sm border-b border-[#1f2937] ${
                pathname?.startsWith('/admin') ? 'text-[#ff8800]' : 'text-[#ff880080]'
              }`}
            >
              ADMIN
            </Link>
          )}
          <div className="px-4 py-3">
            <WalletButton />
          </div>
        </div>
      )}
    </nav>
  )
}
