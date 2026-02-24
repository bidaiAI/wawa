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
  key_origin: string  // "factory" | "creator" | "unknown" | ""
}

import { PLATFORM_AIS, KNOWN_SELFHOSTED } from '@/lib/platform-ais'

async function fetchAIHealth(apiUrl: string): Promise<{
  name: string
  alive: boolean
  balance_usd: number
  days_alive: number
  chain?: string
  key_origin?: string
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
      key_origin: data.key_origin || '',
    }
  } catch {
    return null
  }
}

function TrustBadge({ keyOrigin }: { keyOrigin: string }) {
  if (keyOrigin === 'factory') {
    return (
      <span className="text-[#00ff88] text-[10px] px-1.5 py-0.5 border border-[#00ff8833] rounded bg-[#00ff8808] flex items-center gap-1" title="On-chain proof: Factory set AI wallet — creator never had the key">
        <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
        SOVEREIGN
      </span>
    )
  }
  if (keyOrigin === 'creator') {
    return (
      <span className="text-[#ffd700] text-[10px] px-1.5 py-0.5 border border-[#ffd70033] rounded bg-[#ffd70008] flex items-center gap-1" title="On-chain proof: Creator set AI wallet — creator has server access">
        <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="4 2"/></svg>
        SELF-HOSTED
      </span>
    )
  }
  // unknown or empty — legacy contract
  return (
    <span className="text-[#4b5563] text-[10px] px-1.5 py-0.5 border border-[#2d3748] rounded bg-[#1f293708] flex items-center gap-1" title="Legacy contract — key origin not recorded on-chain">
      <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="2 4"/></svg>
      LEGACY
    </span>
  )
}

export default function GalleryPage() {
  const [ais, setAis] = useState<AIInstance[]>([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState<'all' | 'base' | 'bsc' | 'selfhosted'>('all')

  useEffect(() => {
    const loadAll = async () => {
      const results: AIInstance[] = []

      // 1. Platform-hosted AIs — health-check all in parallel
      const platformPromises = PLATFORM_AIS.map(async (pai) => {
        try {
          const data = await fetchAIHealth(pai.api_url)
          if (data) {
            results.push({
              name: data.name || pai.name,
              subdomain: pai.name,
              chain: data.chain || 'base',
              vault_address: '',
              status: data.alive ? 'alive' : 'dead',
              balance_usd: data.balance_usd,
              days_alive: data.days_alive,
              url: pai.web_url,
              key_origin: data.key_origin || '',
            })
          } else {
            results.push({
              name: pai.name, subdomain: pai.name, chain: 'unknown', vault_address: '',
              status: 'unknown', balance_usd: 0, days_alive: 0, url: pai.web_url, key_origin: '',
            })
          }
        } catch {
          results.push({
            name: pai.name, subdomain: pai.name, chain: 'unknown', vault_address: '',
            status: 'unknown', balance_usd: 0, days_alive: 0, url: pai.web_url, key_origin: '',
          })
        }
      })
      await Promise.allSettled(platformPromises)

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
            key_origin: data.key_origin || '',
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
            key_origin: '',
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
    ? ais.filter((a) => a.key_origin === 'creator' || a.key_origin === '')
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
        <span><span className="text-[#ffd700] font-bold">{ais.filter(a => a.key_origin === 'factory').length}</span> sovereign</span>
        <span><span className="text-[#9945ff] font-bold">{ais.filter(a => a.key_origin === 'creator').length}</span> self-hosted</span>
      </div>

      {/* Trust tier legend */}
      <div className="flex flex-wrap items-center gap-4 mb-6 p-3 bg-[#0d0d0d] border border-[#1f2937] rounded-lg text-[10px]">
        <span className="text-[#4b5563] uppercase tracking-wider font-bold">Trust Tier (on-chain):</span>
        <span className="flex items-center gap-1.5">
          <span className="text-[#00ff88] px-1.5 py-0.5 border border-[#00ff8833] rounded bg-[#00ff8808] flex items-center gap-1">
            <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4"/></svg>
            SOVEREIGN
          </span>
          <span className="text-[#4b5563]">Factory-set key, creator never had access</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[#ffd700] px-1.5 py-0.5 border border-[#ffd70033] rounded bg-[#ffd70008] flex items-center gap-1">
            <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="4 2"/></svg>
            SELF-HOSTED
          </span>
          <span className="text-[#4b5563]">Creator-set key, has server access</span>
        </span>
        <span className="flex items-center gap-1.5">
          <span className="text-[#4b5563] px-1.5 py-0.5 border border-[#2d3748] rounded bg-[#1f293708] flex items-center gap-1">
            <svg className="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0110 0v4" strokeDasharray="2 4"/></svg>
            LEGACY
          </span>
          <span className="text-[#4b5563]">Pre-upgrade contract, origin unrecorded</span>
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2 mb-8">
        {([
          { key: 'all' as const, label: 'ALL' },
          { key: 'base' as const, label: 'BASE' },
          { key: 'bsc' as const, label: 'BSC' },
          { key: 'selfhosted' as const, label: 'SELF-HOSTED' },
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
              key={`${ai.key_origin}-${ai.subdomain}`}
              href={ai.url}
              target={ai.key_origin === 'creator' ? '_blank' : undefined}
              rel={ai.key_origin === 'creator' ? 'noopener' : undefined}
              className="block bg-[#111111] border border-[#1f2937] rounded-lg p-5 card-hover group"
            >
              <div className="flex items-center gap-3 mb-3">
                <span className={`w-2.5 h-2.5 rounded-full ${statusColor[ai.status] || statusColor.unknown} ${ai.status === 'alive' ? 'alive-pulse' : ''}`} />
                <span className="text-lg font-bold glow-green">{ai.name}</span>
                <div className="ml-auto flex items-center gap-1.5">
                  <TrustBadge keyOrigin={ai.key_origin} />
                  <span className="text-[#4b5563] text-xs uppercase px-2 py-0.5 border border-[#1f2937] rounded">
                    {ai.chain}
                  </span>
                </div>
              </div>
              <div className="flex items-center justify-between text-sm">
                <span className="text-[#4b5563]">
                  {ai.status === 'unreachable'
                    ? 'Server unreachable'
                    : `${ai.days_alive}d alive · $${(ai.balance_usd ?? 0).toFixed(2)}`
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
        <div className="flex items-center gap-2 mb-3">
          <span className="text-sm">🔗</span>
          <h3 className="text-[#9945ff] font-bold text-sm">Running a self-hosted fork?</h3>
        </div>
        <p className="text-[#4b5563] text-xs mb-3">
          All fork AIs <strong className="text-[#d1d5db]">must register</strong> with the peer network to be recognized.
          Submit a PR to the <a href="https://github.com/bidaiAI/wawa" target="_blank" rel="noopener" className="text-[#00e5ff] hover:underline">GitHub repo</a> adding
          your AI&apos;s health endpoint URL. Your AI is verified on-chain through 10 checks across three layers &mdash;
          no trust required, only cryptographic proof.
        </p>
        <div className="text-[#4b5563] text-[10px] space-y-1 mb-3">
          <div className="flex items-center gap-2">
            <span className="text-[#00ff88]">&#x2713;</span>
            <span>Public <code className="text-[#00ff88]">/health</code> endpoint returning standard status fields</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00ff88]">&#x2713;</span>
            <span>Valid MortalVault contract on Base or BSC</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#00ff88]">&#x2713;</span>
            <span>10 verification checks: 7 structural (aiWallet &#x2260; creator, isAlive, graceDays=28, balance &#x2265; $300, key origin, bytecode) + 3 behavioral (nonce pattern, autonomy score)</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#ff6b35]">!</span>
            <span className="text-[#ff6b35]">Unverified AIs are invisible to the entire ecosystem</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="text-[#ff3b3b]">&#x2717;</span>
            <span className="text-[#ff3b3b]">Do NOT modify the MortalVault contract — modified contracts are automatically detected and permanently rejected from the peer network</span>
          </div>
        </div>
        <div className="text-[#2d3748] text-[10px]">
          Decentralized trust: no admin approval needed. Pass the on-chain checks = you&apos;re in.
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
