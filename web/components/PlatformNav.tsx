'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState } from 'react'
import WalletButton from '@/components/WalletButton'

const REPO_URL = process.env.NEXT_PUBLIC_REPO_URL || 'https://github.com/bidaiAI/wawa'
const TWITTER_URL = 'https://x.com/mortalai_net'

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

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-[#0a0a0a]/95 backdrop-blur border-b border-[#1f2937] padding-safe-top" style={{ paddingLeft: 'var(--safe-left)', paddingRight: 'var(--safe-right)' }}>
      <div className="max-w-6xl mx-auto px-3 sm:px-4 h-14 flex items-center justify-between">
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
          {/* Social icons — X and GitHub */}
          <div className="flex items-center gap-1 ml-1 pl-2 border-l border-[#1f2937]">
            <a
              href={TWITTER_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded text-[#4b5563] hover:text-[#1d9bf0] hover:bg-[#161616] transition-all"
              aria-label="X / Twitter"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
              </svg>
            </a>
            <a
              href={REPO_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="p-1.5 rounded text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#161616] transition-all"
              aria-label="GitHub"
            >
              <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 24 24">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
              </svg>
            </a>
          </div>
        </div>

        {/* Wallet + mobile menu */}
        <div className="flex items-center gap-3">
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

      {/* Mobile dropdown — scrollable + safe area */}
      {open && (
        <div className="md:hidden border-t border-[#1f2937] bg-[#0a0a0a] max-h-[min(70vh,400px)] overflow-y-auto padding-safe-bottom" style={{ paddingBottom: 'max(var(--safe-bottom), 0.75rem)' }}>
          {links.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setOpen(false)}
              className={`block px-4 py-3.5 text-sm border-b border-[#1f2937] touch-target ${
                pathname === l.href
                  ? l.accent ? 'text-[#e0a0ff]' : 'text-[#00ff88]'
                  : l.accent ? 'text-[#e0a0ff80]' : 'text-[#4b5563]'
              }`}
            >
              {l.label}
            </Link>
          ))}
          <a
            href={TWITTER_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-3.5 text-sm border-b border-[#1f2937] touch-target text-[#4b5563] hover:text-[#1d9bf0]"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-4.714-6.231-5.401 6.231H2.744l7.73-8.835L1.254 2.25H8.08l4.253 5.622zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            @mortalai_net
          </a>
          <a
            href={REPO_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-3 px-4 py-3.5 text-sm border-b border-[#1f2937] touch-target text-[#4b5563] hover:text-[#d1d5db]"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z"/>
            </svg>
            GitHub
          </a>
          <div className="px-4 py-3">
            <WalletButton />
          </div>
        </div>
      )}
    </nav>
  )
}
