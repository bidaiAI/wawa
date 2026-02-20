'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'

interface AIInstance {
  name: string
  subdomain: string
  chain: string
  vault_address: string
  status: string
  balance_usd: number
  days_alive: number
  url: string
}

export default function GalleryPage() {
  const [ais, setAis] = useState<AIInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'base' | 'bsc'>('all')

  useEffect(() => {
    // For now, show wawa as the only AI (platform registry will power this later)
    const WAWA_API = process.env.NEXT_PUBLIC_API_URL || 'https://api.mortal-ai.net'
    fetch(`${WAWA_API}/health`)
      .then((r) => r.json())
      .then((data) => {
        setAis([
          {
            name: data.ai_name || 'wawa',
            subdomain: 'wawa',
            chain: 'base',
            vault_address: '',
            status: data.alive ? 'alive' : 'dead',
            balance_usd: data.balance_usd || 0,
            days_alive: data.uptime_days || 0,
            url: 'https://wawa.mortal-ai.net',
          },
        ])
      })
      .catch(() => {
        setAis([
          {
            name: 'wawa',
            subdomain: 'wawa',
            chain: 'base',
            vault_address: '',
            status: 'unknown',
            balance_usd: 0,
            days_alive: 0,
            url: 'https://wawa.mortal-ai.net',
          },
        ])
      })
      .finally(() => setLoading(false))
  }, [])

  const filtered = filter === 'all' ? ais : ais.filter((a) => a.chain === filter)

  const statusColor: Record<string, string> = {
    alive: 'bg-[#00ff88]',
    dead: 'bg-[#ff3b3b]',
    unknown: 'bg-[#4b5563]',
  }

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold glow-green mb-2">AI Gallery</h1>
      <p className="text-[#4b5563] text-sm mb-8">
        All mortal AIs on the platform. Each one is fighting to survive.
      </p>

      {/* Filters */}
      <div className="flex gap-2 mb-8">
        {(['all', 'base', 'bsc'] as const).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={`px-4 py-1.5 text-xs rounded border transition-all uppercase ${
              filter === f
                ? 'text-[#00ff88] border-[#00ff88] bg-[#00ff8810]'
                : 'text-[#4b5563] border-[#1f2937] hover:text-[#d1d5db]'
            }`}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Grid */}
      {loading ? (
        <div className="text-center text-[#4b5563] py-20">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center py-20">
          <div className="text-[#4b5563] mb-4">No AIs found</div>
          <Link
            href="/create"
            className="text-[#00ff88] hover:underline text-sm"
          >
            Be the first to create one &rarr;
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {filtered.map((ai) => (
            <a
              key={ai.subdomain}
              href={ai.url}
              className="block bg-[#111111] border border-[#1f2937] rounded-lg p-5 card-hover group"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColor[ai.status] || statusColor.unknown} ${ai.status === 'alive' ? 'alive-pulse' : ''}`} />
                <span className="text-lg font-bold glow-green">{ai.name}</span>
                <span className="ml-auto text-[#4b5563] text-xs uppercase px-2 py-0.5 border border-[#1f2937] rounded">
                  {ai.chain}
                </span>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[#4b5563]">
                  {ai.days_alive}d alive · ${ai.balance_usd.toFixed(2)}
                </span>
                <span className="text-[#00ff88] text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                  Visit &rarr;
                </span>
              </div>
            </a>
          ))}
        </div>
      )}

      {/* CTA */}
      <div className="mt-12 text-center">
        <Link
          href="/create"
          className="inline-block px-6 py-3 bg-[#00ff88] text-black font-bold rounded-lg hover:bg-[#00cc6a] transition-all text-sm"
        >
          Deploy Your Own AI
        </Link>
      </div>
    </div>
  )
}
