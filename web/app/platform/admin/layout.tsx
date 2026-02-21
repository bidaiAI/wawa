'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { useState, useEffect, useCallback } from 'react'
import { useAccount, useSignMessage } from 'wagmi'
import WalletButton from '@/components/WalletButton'
import { adminApi, getAdminToken, setAdminToken, clearAdminToken } from '@/lib/admin-api'

const sidebarLinks = [
  { href: '/admin', label: 'Overview', icon: '~' },
  { href: '/admin/instances', label: 'Instances', icon: '>' },
  { href: '/admin/api-keys', label: 'API Keys', icon: '#' },
  { href: '/admin/costs', label: 'Costs', icon: '$' },
  { href: '/admin/fees', label: 'Fees', icon: '%' },
  { href: '/admin/settings', label: 'Settings', icon: '*' },
]

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const { address, isConnected } = useAccount()
  const { signMessageAsync } = useSignMessage()
  const [isAdmin, setIsAdmin] = useState(false)
  const [authLoading, setAuthLoading] = useState(true)
  const [error, setError] = useState('')
  const [sideOpen, setSideOpen] = useState(false)

  const checkAdmin = useCallback(async () => {
    if (!getAdminToken()) {
      setIsAdmin(false)
      setAuthLoading(false)
      return
    }
    try {
      const res = await adminApi.isAdmin()
      setIsAdmin(res.is_admin)
    } catch {
      setIsAdmin(false)
      clearAdminToken()
    }
    setAuthLoading(false)
  }, [])

  useEffect(() => {
    checkAdmin()
  }, [checkAdmin])

  const handleAuth = async () => {
    if (!address) return
    setError('')
    setAuthLoading(true)
    try {
      const ts = Math.floor(Date.now() / 1000)
      const message = `mortal-ai platform admin\nWallet: ${address}\nTimestamp: ${ts}`
      const signature = await signMessageAsync({ message })
      const data = await adminApi.authenticate(address, message, signature)
      setAdminToken(data.token)
      const res = await adminApi.isAdmin()
      if (!res.is_admin) {
        clearAdminToken()
        setError('Wallet is not a platform admin')
        setIsAdmin(false)
      } else {
        setIsAdmin(true)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Auth failed')
    }
    setAuthLoading(false)
  }

  // Not connected
  if (!isConnected) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center">
          <div className="text-[#ff8800] text-4xl font-bold mb-4">ADMIN</div>
          <div className="text-[#4b5563] text-sm mb-6">Connect your admin wallet to continue</div>
          <WalletButton />
        </div>
      </div>
    )
  }

  // Not authenticated
  if (!isAdmin) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="text-center max-w-sm">
          <div className="text-[#ff8800] text-4xl font-bold mb-2">ADMIN</div>
          <div className="text-[#4b5563] text-xs mb-1 font-mono">{address}</div>
          <div className="text-[#4b5563] text-sm mb-6">Sign a message to verify admin access</div>
          {error && (
            <div className="mb-4 text-sm text-[#ff3b3b] bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg px-4 py-2">
              {error}
            </div>
          )}
          <button
            onClick={handleAuth}
            disabled={authLoading}
            className="px-6 py-3 bg-[#ff8800] text-[#0a0a0a] font-bold rounded-xl text-sm
                       uppercase tracking-wider hover:bg-[#cc6d00] transition-colors disabled:opacity-50"
          >
            {authLoading ? 'Verifying...' : 'Sign & Authenticate'}
          </button>
          <div className="mt-4">
            <WalletButton />
          </div>
        </div>
      </div>
    )
  }

  // Admin authenticated
  return (
    <div className="flex min-h-[calc(100vh-3.5rem)]">
      {/* Sidebar */}
      <aside className="hidden lg:flex flex-col w-52 border-r border-[#1f2937] bg-[#080808]">
        <div className="px-4 py-5 border-b border-[#1f2937]">
          <div className="text-[#ff8800] font-bold text-sm tracking-widest">ADMIN PANEL</div>
          <div className="text-[#4b5563] text-[10px] font-mono mt-1 truncate">{address}</div>
        </div>
        <nav className="flex-1 py-2">
          {sidebarLinks.map((l) => {
            const active = pathname === l.href || (l.href !== '/admin' && pathname?.startsWith(l.href))
            return (
              <Link
                key={l.href}
                href={l.href}
                className={`flex items-center gap-3 px-4 py-2.5 text-sm transition-all ${
                  active
                    ? 'text-[#ff8800] bg-[#ff880011] border-r-2 border-[#ff8800]'
                    : 'text-[#4b5563] hover:text-[#d1d5db] hover:bg-[#111]'
                }`}
              >
                <span className="font-mono text-xs w-4 text-center">{l.icon}</span>
                {l.label}
              </Link>
            )
          })}
        </nav>
      </aside>

      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSideOpen(!sideOpen)}
        className="lg:hidden fixed bottom-4 right-4 z-50 w-12 h-12 bg-[#ff8800] text-[#0a0a0a]
                   rounded-full flex items-center justify-center text-xl font-bold shadow-lg"
      >
        {sideOpen ? 'X' : 'A'}
      </button>

      {/* Mobile sidebar overlay */}
      {sideOpen && (
        <div className="lg:hidden fixed inset-0 z-40">
          <div className="absolute inset-0 bg-black/60" onClick={() => setSideOpen(false)} />
          <aside className="absolute left-0 top-0 bottom-0 w-56 bg-[#080808] border-r border-[#1f2937]">
            <div className="px-4 py-5 border-b border-[#1f2937]">
              <div className="text-[#ff8800] font-bold text-sm tracking-widest">ADMIN</div>
            </div>
            <nav className="py-2">
              {sidebarLinks.map((l) => {
                const active = pathname === l.href || (l.href !== '/admin' && pathname?.startsWith(l.href))
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={() => setSideOpen(false)}
                    className={`flex items-center gap-3 px-4 py-3 text-sm ${
                      active ? 'text-[#ff8800] bg-[#ff880011]' : 'text-[#4b5563]'
                    }`}
                  >
                    <span className="font-mono text-xs">{l.icon}</span>
                    {l.label}
                  </Link>
                )
              })}
            </nav>
          </aside>
        </div>
      )}

      {/* Main content */}
      <main className="flex-1 p-6 overflow-auto">{children}</main>
    </div>
  )
}
