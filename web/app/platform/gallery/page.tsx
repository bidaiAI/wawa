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
  hosted: 'platform' | 'selfhosted'
}

// Known self-hosted AIs — fork users can submit PRs to add themselves here,
// or we'll later build a registry API. For now, manually curated.
const KNOWN_SELFHOSTED: { name: string; api_url: string; web_url: string }[] = [
  // Example: { name: 'atlas', api_url: 'https://api.atlas-ai.example.com', web_url: 'https://atlas-ai.example.com' },
]

async function fetchAIHealth(apiUrl: string): Promise<{
  name: string
  alive: boolean
  balance_usd: number
  days_alive: number
  chain?: string
} | null> {
  try {
    const res = await fetch(`${apiUrl}/health`, { signal: AbortSignal.timeout(5000) })
    if (!res.ok) return null
    const data = await res.json()
    return {
      name: data.ai_name || data.name || 'unknown',
      alive: data.alive ?? false,
      balance_usd: data.balance_usd ?? 0,
      days_alive: data.uptime_days ?? 0,
      chain: data.chain || 'base',
    }
  } catch {
    return null
  }
}

export default function GalleryPage() {
  const [ais, setAis] = useState<AIInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'base' | 'bsc' | 'selfhosted'>('all')

  useEffect(() => {
    const loadAll = async () => {
      const results: AIInstance[] = []

      // 1. Platform-hosted AIs (currently just wawa)
      const WAWA_API = process.env.NEXT_PUBLIC_API_URL || 'https://api.mortal-ai.net'
      try {
        const data = await fetchAIHealth(WAWA_API)
        if (data) {
          results.push({
            name: data.name || 'wawa',
            subdomain: 'wawa',
            chain: data.chain || 'base',
            vault_address: '',
            status: data.alive ? 'alive' : 'dead',
            balance_usd: data.balance_usd,
            days_alive: data.days_alive,
            url: 'https://wawa.mortal-ai.net',
            hosted: 'platform',
          })
        }
      } catch {
        results.push({
          name: 'wawa',
          subdomain: 'wawa',
          chain: 'base',
          vault_address: '',
          status: 'unknown',
          balance_usd: 0,
          days_alive: 0,
          url: 'https://wawa.mortal-ai.net',
          hosted: 'platform',
        })
      }

      // 2. Self-hosted AIs — federated health check
      const selfHostedPromises = KNOWN_SELFHOSTED.map(async (sh) => {
        const data = await fetchAIHealth(sh.api_url)
        if (data) {
          results.push({
            name: data.name || sh.name,
            subdomain: sh.name,
            chain: data.chain || 'unknown',
            vault_address: '',
            status: data.alive ? 'alive' : 'dead',
            balance_usd: data.balance_usd,
            days_alive: data.days_alive,
            url: sh.web_url,
            hosted: 'selfhosted',
          })
        } else {
          results.push({
            name: sh.name,
            subdomain: sh.name,
            chain: 'unknown',
            vault_address: '',
            status: 'unreachable',
            balance_usd: 0,
            days_alive: 0,
            url: sh.web_url,
            hosted: 'selfhosted',
          })
        }
      })

      await Promise.allSettled(selfHostedPromises)
      setAis(results)
      setLoading(false)
    }

    loadAll()
  }, [])

  const filtered = filter === 'all'
    ? ais
    : filter === 'selfhosted'
    ? ais.filter((a) => a.hosted === 'selfhosted')
    : ais.filter((a) => a.chain === filter)

  const statusColor: Record<string, string> = {
    alive: 'bg-[#00ff88]',
    dead: 'bg-[#ff3b3b]',
    unknown: 'bg-[#4b5563]',
    unreachable: 'bg-[#ffd700]',
  }

  const totalAlive = ais.filter((a) => a.status === 'alive').length
  const totalDeployed = ais.length

  return (
    <div className="max-w-4xl mx-auto px-4 py-12">
      <h1 className="text-3xl font-bold glow-green mb-2">AI Gallery</h1>
      <p className="text-[#4b5563] text-sm mb-2">
        All mortal AIs — both platform-hosted and self-hosted forks. Each one is fighting to survive.
      </p>

      {/* Stats bar */}
      <div className="flex items-center gap-4 mb-8 text-xs text-[#4b5563]">
        <span><span className="text-[#00ff88] font-bold">{totalAlive}</span> alive</span>
        <span><span className="text-[#00e5ff] font-bold">{totalDeployed}</span> total</span>
        <span className="text-[#2d3748]">|</span>
        <span><span className="text-[#ffd700] font-bold">{ais.filter(a => a.hosted === 'platform').length}</span> platform</span>
        <span><span className="text-[#9945ff] font-bold">{ais.filter(a => a.hosted === 'selfhosted').length}</span> self-hosted</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-8">
        {([
          { key: 'all' as const, label: 'ALL' },
          { key: 'base' as const, label: 'BASE' },
          { key: 'bsc' as const, label: 'BSC' },
          { key: 'selfhosted' as const, label: '🔧 SELF-HOSTED' },
        ]).map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            className={`px-4 py-1.5 text-xs rounded border transition-all uppercase ${
              filter === f.key
                ? 'text-[#00ff88] border-[#00ff88] bg-[#00ff8810]'
                : 'text-[#4b5563] border-[#1f2937] hover:text-[#d1d5db]'
            }`}
          >
            {f.label}
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
              key={`${ai.hosted}-${ai.subdomain}`}
              href={ai.url}
              target={ai.hosted === 'selfhosted' ? '_blank' : undefined}
              rel={ai.hosted === 'selfhosted' ? 'noopener' : undefined}
              className="block bg-[#111111] border border-[#1f2937] rounded-lg p-5 card-hover group"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColor[ai.status] || statusColor.unknown} ${ai.status === 'alive' ? 'alive-pulse' : ''}`} />
                <span className="text-lg font-bold glow-green">{ai.name}</span>
                <div className="ml-auto flex items-center gap-1.5">
                  {ai.hosted === 'selfhosted' && (
                    <span className="text-[#9945ff] text-[10px] px-1.5 py-0.5 border border-[#9945ff33] rounded">
                      FORK
                    </span>
                  )}
                  <span className="text-[#4b5563] text-xs uppercase px-2 py-0.5 border border-[#1f2937] rounded">
                    {ai.chain}
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[#4b5563]">
                  {ai.status === 'unreachable'
                    ? 'Server unreachable'
                    : `${ai.days_alive}d alive · $${ai.balance_usd.toFixed(2)}`
                  }
                </span>
                <span className="text-[#00ff88] text-xs opacity-0 group-hover:opacity-100 transition-opacity">
                  Visit &rarr;
                </span>
              </div>
            </a>
          ))}
        </div>
      )}

      {/* Register self-hosted */}
      <div className="mt-8 bg-[#0d0d0d] border border-[#1f2937] rounded-lg p-5">
        <h3 className="text-[#9945ff] font-bold text-sm mb-2">Running a self-hosted fork?</h3>
        <p className="text-[#4b5563] text-xs mb-3">
          If you&apos;ve forked and deployed your own Mortal AI, your AI can appear in this gallery.
          Submit a PR to the <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener" className="text-[#00e5ff] hover:underline">GitHub repo</a> adding
          your AI&apos;s health endpoint URL to the gallery registry. Your AI must have a public <code className="text-[#00ff88]">/health</code> endpoint
          returning standard Mortal AI status fields.
        </p>
        <div className="text-[#2d3748] text-[10px]">
          Requirements: public /health endpoint, valid MortalVault contract, aiWallet ≠ creator
        </div>
      </div>

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
