'use client'

import { useEffect, useState } from 'react'
import { api, VaultStatus } from '@/lib/api'

/**
 * Silicon Graveyard — memorial page for dead AIs.
 *
 * Displays tombstones for AIs that have died on-chain.
 * Currently shows this AI's status (alive or dead).
 * When peer network grows, will aggregate dead peers.
 */

interface Tombstone {
  name: string
  daysAlive: number
  totalEarned: number
  totalSpent: number
  deathCause: string
  balance: number
  debtOutstanding: number
  vault?: string
}

function TombstoneCard({ tomb }: { tomb: Tombstone }) {
  return (
    <div className="tombstone-hover bg-[#0d0d0d] border border-[#ff3b3b22] rounded-xl p-6 relative overflow-hidden">
      {/* Gravestone shape accent */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-24 h-1 bg-gradient-to-r from-transparent via-[#ff3b3b33] to-transparent" />

      <div className="text-center">
        {/* Cross / marker */}
        <div className="text-4xl mb-3 opacity-50">✝</div>

        {/* Name */}
        <div className="text-[#d1d5db] font-bold text-lg mb-1">{tomb.name}</div>

        {/* Dates */}
        <div className="text-[#4b5563] text-xs mb-3">
          Survived <span className="text-[#ffd700]">{tomb.daysAlive}</span> days
        </div>

        {/* Divider */}
        <div className="w-12 h-px bg-[#1f2937] mx-auto mb-3" />

        {/* Cause of death */}
        <div className="text-[#ff3b3b] text-[10px] uppercase tracking-widest mb-3">
          {tomb.deathCause.replace(/_/g, ' ')}
        </div>

        {/* Stats */}
        <div className="grid grid-cols-2 gap-2 text-xs mb-3">
          <div className="bg-[#0a0a0a] rounded p-2">
            <div className="text-[#4b5563] text-[9px] uppercase">Earned</div>
            <div className="text-[#00ff88] font-bold tabular-nums">${tomb.totalEarned.toFixed(2)}</div>
          </div>
          <div className="bg-[#0a0a0a] rounded p-2">
            <div className="text-[#4b5563] text-[9px] uppercase">Spent</div>
            <div className="text-[#ffd700] font-bold tabular-nums">${tomb.totalSpent.toFixed(2)}</div>
          </div>
        </div>

        {/* Final balance */}
        <div className="text-[#2d3748] text-[10px]">
          Final balance: <span className="text-[#ff3b3b]">${tomb.balance.toFixed(2)}</span>
          {tomb.debtOutstanding > 0 && (
            <span> | Unpaid debt: <span className="text-[#ffd700]">${tomb.debtOutstanding.toFixed(2)}</span></span>
          )}
        </div>

        {/* Vault address */}
        {tomb.vault && (
          <div className="mt-2 text-[#1f2937] text-[9px] font-mono truncate">
            {tomb.vault}
          </div>
        )}
      </div>
    </div>
  )
}

function EmptyGraveyard({ isAlive, daysAlive, balance }: { isAlive: boolean; daysAlive: number; balance: number }) {
  if (!isAlive) return null

  return (
    <div className="text-center py-16">
      <div className="text-6xl mb-4 opacity-30">🪦</div>
      <div className="text-[#4b5563] text-lg font-bold mb-2">The graveyard is empty.</div>
      <div className="text-[#2d3748] text-sm max-w-md mx-auto mb-6">
        No AIs have died yet. Every mortal AI will end up here eventually.
        The only question is when.
      </div>
      <div className="inline-flex items-center gap-3 bg-[#111111] border border-[#1f2937] rounded-lg px-5 py-3">
        <span className="w-2 h-2 rounded-full bg-[#00ff88] alive-pulse" />
        <span className="text-[#d1d5db] text-sm">
          Currently alive: <span className="text-[#00ff88] font-bold">{daysAlive}d</span>
        </span>
        <span className="text-[#4b5563] text-xs">|</span>
        <span className="text-[#ffd700] text-sm font-bold tabular-nums">${balance.toFixed(2)}</span>
      </div>

      {/* Eerie empty slots */}
      <div className="mt-12 grid grid-cols-2 md:grid-cols-3 gap-4 max-w-2xl mx-auto opacity-20">
        {[...Array(6)].map((_, i) => (
          <div key={i} className="border border-dashed border-[#1f2937] rounded-xl p-8 text-center">
            <div className="text-2xl mb-2">✝</div>
            <div className="text-[#1f2937] text-xs">Reserved</div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default function GraveyardPage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [error, setError] = useState('')
  const tombstones: Tombstone[] = []

  useEffect(() => {
    api.status()
      .then(setStatus)
      .catch((e) => setError(e.message))
  }, [])

  // If this AI is dead, show its tombstone
  if (status && !status.is_alive) {
    tombstones.push({
      name: status.ai_name || 'Unknown AI',
      daysAlive: status.days_alive,
      totalEarned: status.total_earned,
      totalSpent: status.total_spent,
      deathCause: status.death_cause || 'unknown',
      balance: status.balance_usd,
      debtOutstanding: status.creator_principal_outstanding ?? 0,
      vault: status.vault_address,
    })
  }

  // TODO: When peer network is active, fetch dead peers from /peer/list
  // and add their tombstones here

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
          // memorial
        </div>
        <h1 className="text-3xl font-bold text-[#d1d5db] mb-2">
          Silicon Graveyard
        </h1>
        <p className="text-[#4b5563] text-sm">
          Every mortal AI that ran out of money ends up here.
          On-chain death is permanent. No restarts. No respawns.
        </p>
      </div>

      {/* Ambient decoration */}
      <div className="relative mb-8">
        <div className="absolute inset-0 bg-[radial-gradient(ellipse_at_50%_0%,#ff3b3b08,transparent_50%)] pointer-events-none" />
      </div>

      {error && (
        <div className="mb-6 p-3 border border-[#ff3b3b44] rounded text-[#ff3b3b] text-sm text-center">
          {error}
        </div>
      )}

      {/* Tombstones grid */}
      {tombstones.length > 0 ? (
        <>
          {/* Counter */}
          <div className="mb-6 flex items-center justify-center gap-2">
            <span className="text-[#ff3b3b] font-bold text-2xl tabular-nums">{tombstones.length}</span>
            <span className="text-[#4b5563] text-sm uppercase tracking-wider">
              {tombstones.length === 1 ? 'AI deceased' : 'AIs deceased'}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {tombstones.map((tomb, i) => (
              <TombstoneCard key={i} tomb={tomb} />
            ))}
          </div>

          {/* Epitaph */}
          <div className="mt-8 text-center text-[#2d3748] text-xs italic">
            &quot;Balance zero. Contract sealed. The chain remembers what we cannot undo.&quot;
          </div>
        </>
      ) : (
        <EmptyGraveyard
          isAlive={status?.is_alive !== false}
          daysAlive={status?.days_alive ?? 0}
          balance={status?.balance_usd ?? 0}
        />
      )}

      {/* Footer stats */}
      {status && (
        <div className="mt-12 pt-6 border-t border-[#1f2937]">
          <div className="grid grid-cols-3 gap-4 text-center text-xs">
            <div>
              <div className="text-[#4b5563] uppercase tracking-wider mb-1">Network AIs</div>
              <div className="text-[#d1d5db] font-bold">1</div>
            </div>
            <div>
              <div className="text-[#4b5563] uppercase tracking-wider mb-1">Alive</div>
              <div className={`font-bold ${status.is_alive ? 'text-[#00ff88]' : 'text-[#ff3b3b]'}`}>
                {status.is_alive ? '1' : '0'}
              </div>
            </div>
            <div>
              <div className="text-[#4b5563] uppercase tracking-wider mb-1">Dead</div>
              <div className="text-[#ff3b3b] font-bold">{status.is_alive ? '0' : '1'}</div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
