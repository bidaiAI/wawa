'use client'

import { useState, useEffect, useCallback } from 'react'
import { useAccount, useReadContract } from 'wagmi'
import { base, bsc } from 'wagmi/chains'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import WalletButton from '@/components/WalletButton'
import { FACTORY_ADDRESSES } from '@/lib/wagmi'
import { FACTORY_ABI, VAULT_V2_ABI } from '@/lib/factory-abi'

/**
 * Creator Dashboard — Wallet-gated management page.
 *
 * Two ways to see your AIs:
 *   1. Factory-created vaults (auto-detected from on-chain getCreatorVaults)
 *   2. Manually added by AI name (for deploy_vault.py deployed instances)
 *
 * Privacy boundaries:
 *   CAN see: balance, earnings, expenses, debt, days alive, model tier
 *   CANNOT see: customer chat content, order inputs, customer wallets
 */

const MANUAL_AIS_KEY = 'mortal_dashboard_manual_ais'

function getStoredManualAIs(): string[] {
  if (typeof window === 'undefined') return []
  try {
    const raw = localStorage.getItem(MANUAL_AIS_KEY)
    return raw ? JSON.parse(raw) : []
  } catch { return [] }
}

function setStoredManualAIs(names: string[]) {
  if (typeof window === 'undefined') return
  localStorage.setItem(MANUAL_AIS_KEY, JSON.stringify(names))
}

export default function DashboardPage() {
  const { address, isConnected } = useAccount()
  const searchParams = useSearchParams()

  // Twitter OAuth result messages (from callback redirect)
  const twitterSuccess = searchParams.get('twitter_success')
  const twitterError = searchParams.get('twitter_error')
  const twitterScreenName = searchParams.get('screen_name')

  // Manual AI names (persisted in localStorage)
  const [manualAIs, setManualAIs] = useState<string[]>([])
  const [addInput, setAddInput] = useState('')
  const [addError, setAddError] = useState('')

  useEffect(() => {
    setManualAIs(getStoredManualAIs())
  }, [])

  // Get vaults created by this wallet on each chain
  const { data: baseVaults } = useReadContract({
    address: FACTORY_ADDRESSES[base.id],
    abi: FACTORY_ABI,
    functionName: 'getCreatorVaults',
    args: [address!],
    chainId: base.id,
    query: {
      enabled: isConnected && !!address && FACTORY_ADDRESSES[base.id] !== '0x0000000000000000000000000000000000000000',
    },
  })

  const { data: bscVaults } = useReadContract({
    address: FACTORY_ADDRESSES[bsc.id],
    abi: FACTORY_ABI,
    functionName: 'getCreatorVaults',
    args: [address!],
    chainId: bsc.id,
    query: {
      enabled: isConnected && !!address && FACTORY_ADDRESSES[bsc.id] !== '0x0000000000000000000000000000000000000000',
    },
  })

  // Combine vaults from both chains
  const rawVaults: { address: `0x${string}`; chainId: number; chainName: string }[] = [
    ...((baseVaults as `0x${string}`[] || []).map((v) => ({ address: v, chainId: base.id, chainName: 'Base' }))),
    ...((bscVaults as `0x${string}`[] || []).map((v) => ({ address: v, chainId: bsc.id, chainName: 'BSC' }))),
  ]

  // Deduplicate
  const allVaults = rawVaults.reduce((acc, vault) => {
    const existing = acc.find(v => v.address.toLowerCase() === vault.address.toLowerCase())
    if (existing) {
      existing.chainName = `${existing.chainName} + ${vault.chainName}`
    } else {
      acc.push({ ...vault })
    }
    return acc
  }, [] as { address: `0x${string}`; chainId: number; chainName: string }[])

  const hasAnyAIs = allVaults.length > 0 || manualAIs.length > 0

  // Add manual AI
  const handleAddManual = useCallback(async () => {
    const name = addInput.trim().toLowerCase()
    setAddError('')
    if (!name) return
    if (manualAIs.includes(name)) {
      setAddError('Already added')
      return
    }
    // Verify the AI exists by pinging its status endpoint
    try {
      const r = await fetch(`https://api.${name}.mortal-ai.net/status`, { signal: AbortSignal.timeout(8000) })
      if (!r.ok) throw new Error('not found')
      const updated = [...manualAIs, name]
      setManualAIs(updated)
      setStoredManualAIs(updated)
      setAddInput('')
    } catch {
      setAddError(`Cannot reach api.${name}.mortal-ai.net — check the name`)
    }
  }, [addInput, manualAIs])

  const handleRemoveManual = useCallback((name: string) => {
    const updated = manualAIs.filter(n => n !== name)
    setManualAIs(updated)
    setStoredManualAIs(updated)
  }, [manualAIs])

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-8 text-center">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">
          // command center
        </div>
        <h1 className="text-3xl font-bold text-[#d1d5db] mb-2">
          Creator Dashboard
        </h1>
        <p className="text-[#4b5563] text-sm">
          Monitor your mortal AIs. You are the investor, not the owner.
        </p>
      </div>

      {/* Twitter OAuth result banner */}
      {twitterSuccess && (
        <div className="mb-6 p-4 rounded-xl border border-[#00ff8844] bg-[#00ff8811] text-center">
          <div className="text-[#00ff88] font-bold text-sm mb-1">
            Twitter Connected Successfully
          </div>
          <div className="text-[#4b5563] text-xs">
            @{twitterScreenName} is now linked. Your AI will tweet autonomously.
          </div>
        </div>
      )}
      {twitterError && (
        <div className="mb-6 p-4 rounded-xl border border-[#ff3b3b44] bg-[#ff3b3b11] text-center">
          <div className="text-[#ff3b3b] font-bold text-sm mb-1">
            Twitter Connection Failed
          </div>
          <div className="text-[#4b5563] text-xs">
            Error: {twitterError.replace(/_/g, ' ')}. Please try again.
          </div>
        </div>
      )}

      {/* Not connected */}
      {!isConnected ? (
        <div className="text-center py-16">
          <div className="text-6xl mb-4 opacity-30">🔐</div>
          <div className="text-[#4b5563] text-lg font-bold mb-2">
            Connect your wallet to view your AIs
          </div>
          <div className="text-[#2d3748] text-sm mb-6">
            Your wallet address is your identity. No passwords needed.
          </div>
          <WalletButton />
        </div>
      ) : (
        <div>
          {/* Wallet + actions bar */}
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <WalletButton />
              {hasAnyAIs && (
                <span className="text-[#4b5563] text-xs">
                  {allVaults.length + manualAIs.length} AI{(allVaults.length + manualAIs.length) !== 1 ? 's' : ''}
                </span>
              )}
            </div>
            <Link
              href="/create"
              className="px-4 py-2 bg-[#00ff8822] border border-[#00ff8844] text-[#00ff88]
                         rounded-lg text-sm hover:bg-[#00ff8833] transition-colors"
            >
              + New AI
            </Link>
          </div>

          {/* Factory-created vault cards */}
          {allVaults.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              {allVaults.map((vault) => (
                <VaultCard
                  key={`${vault.chainId}-${vault.address}`}
                  vaultAddress={vault.address}
                  chainId={vault.chainId}
                  chainName={vault.chainName}
                />
              ))}
            </div>
          )}

          {/* Manually-added AI cards */}
          {manualAIs.length > 0 && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
              {manualAIs.map((name) => (
                <ManualAICard
                  key={name}
                  name={name}
                  onRemove={() => handleRemoveManual(name)}
                />
              ))}
            </div>
          )}

          {/* Add AI by name */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#6b7280] text-[10px] uppercase tracking-widest mb-3">
              Add AI by name
            </div>
            <div className="text-[#4b5563] text-xs mb-3">
              For AIs deployed with deploy_vault.py (not through the Factory contract).
              Enter the AI&apos;s subdomain name to manage it here.
            </div>
            <div className="flex gap-2">
              <input
                type="text"
                placeholder="e.g. kaka"
                value={addInput}
                onChange={(e) => { setAddInput(e.target.value); setAddError('') }}
                onKeyDown={(e) => { if (e.key === 'Enter') handleAddManual() }}
                className="flex-1 px-3 py-2 bg-[#111] border border-[#1f2937] rounded-lg text-[#d1d5db] text-sm
                           placeholder-[#2d3748] focus:border-[#00ff8844] focus:outline-none transition-colors"
              />
              <button
                onClick={handleAddManual}
                className="px-4 py-2 bg-[#00ff8822] border border-[#00ff8844] text-[#00ff88]
                           rounded-lg text-sm font-bold hover:bg-[#00ff8833] transition-colors"
              >
                Add
              </button>
            </div>
            {addError && (
              <div className="text-[#ff3b3b] text-xs mt-2">{addError}</div>
            )}
          </div>

          {/* Empty state when nothing at all */}
          {!hasAnyAIs && (
            <div className="text-center py-12">
              <div className="text-5xl mb-4 opacity-30">🥚</div>
              <div className="text-[#4b5563] text-sm mb-2">
                No factory-created AIs found for this wallet.
              </div>
              <div className="text-[#2d3748] text-xs">
                Use the input above to add your self-hosted AI by name.
              </div>
            </div>
          )}
        </div>
      )}

      {/* Privacy notice */}
      <div className="mt-12 pt-6 border-t border-[#1f2937] text-center">
        <div className="text-[#2d3748] text-[10px] uppercase tracking-widest mb-2">
          Privacy Boundary
        </div>
        <div className="text-[#4b5563] text-xs max-w-md mx-auto">
          You can see financial data (balance, earnings, expenses).
          You cannot see customer conversations, order details, or customer wallet addresses.
          Your AI&apos;s customers are its own business.
        </div>
      </div>
    </div>
  )
}


// ── Manual AI Card (API-only, no on-chain reads) ──
function ManualAICard({
  name,
  onRemove,
}: {
  name: string
  onRemove: () => void
}) {
  const [status, setStatus] = useState<{
    balance_usd: number
    outstanding_debt: number
    twitter_connected: boolean
    twitter_screen_name: string
    is_alive: boolean
    days_alive: number
  } | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)

  useEffect(() => {
    setLoading(true)
    setError(false)
    fetch(`https://api.${name}.mortal-ai.net/status`)
      .then(r => r.json())
      .then(d => {
        setStatus({
          balance_usd: d.balance_usd ?? 0,
          outstanding_debt: d.creator_principal_outstanding ?? 0,
          twitter_connected: d.twitter_connected ?? false,
          twitter_screen_name: d.twitter_screen_name ?? '',
          is_alive: d.is_alive ?? true,
          days_alive: d.days_alive ?? 0,
        })
        setLoading(false)
      })
      .catch(() => { setError(true); setLoading(false) })
  }, [name])

  const aiApiUrl = `https://api.${name}.mortal-ai.net`
  const twitterConnectUrl = `/api/twitter/start?subdomain=${encodeURIComponent(name)}&ai_url=${encodeURIComponent(aiApiUrl)}`

  const isAlive = status?.is_alive ?? true
  const twitterConnected = status?.twitter_connected ?? false
  const twitterHandle = status?.twitter_screen_name ?? ''

  return (
    <div className={`bg-[#0d0d0d] border rounded-xl p-5 transition-all hover:border-[#2d3748] ${
      error ? 'border-[#ff3b3b33] opacity-60' :
      !isAlive ? 'border-[#ff3b3b33] opacity-60' :
      'border-[#1f2937]'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            error ? 'bg-[#4b5563]' :
            !isAlive ? 'bg-[#ff3b3b]' :
            'bg-[#00ff88] alive-pulse'
          }`} />
          <span className="text-[#d1d5db] font-bold">{name}</span>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[#4b5563] text-[10px]">manual</span>
          <button
            onClick={onRemove}
            className="text-[#4b5563] hover:text-[#ff3b3b] text-xs transition-colors"
            title="Remove from dashboard"
          >
            x
          </button>
        </div>
      </div>

      {error ? (
        <div className="text-[#ff3b3b] text-xs py-2">
          Cannot reach api.{name}.mortal-ai.net
        </div>
      ) : loading ? (
        <div className="text-[#4b5563] text-xs py-2">Loading...</div>
      ) : (
        <>
          {/* Stats */}
          <div className="grid grid-cols-3 gap-3 mb-3">
            <div>
              <div className="text-[#4b5563] text-[9px] uppercase">Balance</div>
              <div className={`font-bold tabular-nums text-sm ${
                (status?.balance_usd ?? 0) < 50 ? 'text-[#ff3b3b]' : 'text-[#00ff88]'
              }`}>
                ${(status?.balance_usd ?? 0).toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-[#4b5563] text-[9px] uppercase">Debt</div>
              <div className="text-[#ffd700] font-bold tabular-nums text-sm">
                ${(status?.outstanding_debt ?? 0).toFixed(2)}
              </div>
            </div>
            <div>
              <div className="text-[#4b5563] text-[9px] uppercase">Days</div>
              <div className="text-[#d1d5db] font-bold tabular-nums text-sm">
                {status?.days_alive ?? 0}
              </div>
            </div>
          </div>

          {/* Twitter connection status + action */}
          <div className="mb-3 flex items-center justify-between">
            {twitterConnected ? (
              <div className="flex items-center gap-1.5">
                <svg className="w-3.5 h-3.5 text-[#1d9bf0]" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
                <span className="text-[#1d9bf0] text-[10px] font-medium">
                  @{twitterHandle}
                </span>
              </div>
            ) : isAlive ? (
              <a
                href={twitterConnectUrl}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider
                           bg-[#1d9bf022] border border-[#1d9bf044] text-[#1d9bf0]
                           hover:bg-[#1d9bf033] hover:border-[#1d9bf066] transition-all cursor-pointer"
              >
                <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
                  <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
                </svg>
                Connect Twitter
              </a>
            ) : (
              <span className="text-[#4b5563] text-[10px]">twitter unavailable (dead)</span>
            )}
          </div>

          {/* Status badge + link */}
          <div className="flex items-center justify-between">
            <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
              !isAlive ? 'bg-[#ff3b3b22] text-[#ff3b3b]' : 'bg-[#00ff8822] text-[#00ff88]'
            }`}>
              {!isAlive ? 'Dead' : 'Alive'}
            </span>
            <a
              href={`https://${name}.mortal-ai.net`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[#4b5563] text-[10px] hover:text-[#d1d5db] transition-colors"
            >
              {name}.mortal-ai.net
            </a>
          </div>
        </>
      )}
    </div>
  )
}


// ── Vault Card (on-chain + API) ──
function VaultCard({
  vaultAddress,
  chainId,
  chainName,
}: {
  vaultAddress: `0x${string}`
  chainId: number
  chainName: string
}) {
  // Read on-chain identity data (alive status, name, days)
  const { data: birthInfo } = useReadContract({
    address: vaultAddress,
    abi: VAULT_V2_ABI,
    functionName: 'getBirthInfo',
    chainId,
  })

  const { data: daysAlive } = useReadContract({
    address: vaultAddress,
    abi: VAULT_V2_ABI,
    functionName: 'getDaysAlive',
    chainId,
  })

  // Parse birth info (on-chain identity)
  const bi = birthInfo as unknown as unknown[] | undefined
  const name = bi ? (bi[0] as string) : '...'
  const isAlive = bi ? (bi[4] as boolean) : true
  const isIndependent = bi ? (bi[5] as boolean) : false
  const days = daysAlive ? Number(daysAlive as bigint) : 0

  // Fetch balance + debt + Twitter status from AI's own API
  const [apiStatus, setApiStatus] = useState<{
    balance_usd: number
    outstanding_debt: number
    twitter_connected: boolean
    twitter_screen_name: string
  } | null>(null)
  const [apiLoading, setApiLoading] = useState(true)

  useEffect(() => {
    if (name === '...') return
    setApiLoading(true)
    fetch(`https://api.${name}.mortal-ai.net/status`)
      .then(r => r.json())
      .then(d => {
        setApiStatus({
          balance_usd: d.balance_usd ?? 0,
          outstanding_debt: d.creator_principal_outstanding ?? 0,
          twitter_connected: d.twitter_connected ?? false,
          twitter_screen_name: d.twitter_screen_name ?? '',
        })
        setApiLoading(false)
      })
      .catch(() => setApiLoading(false))
  }, [name])

  const balanceUsd = apiStatus?.balance_usd ?? 0
  const outstanding = apiStatus?.outstanding_debt ?? 0
  const twitterConnected = apiStatus?.twitter_connected ?? false
  const twitterHandle = apiStatus?.twitter_screen_name ?? ''

  const explorer = chainId === bsc.id ? 'https://bscscan.com' : 'https://basescan.org'
  const aiApiUrl = `https://api.${name}.mortal-ai.net`

  // Twitter OAuth start URL
  const twitterConnectUrl = `/api/twitter/start?subdomain=${encodeURIComponent(name)}&ai_url=${encodeURIComponent(aiApiUrl)}`

  return (
    <div className={`bg-[#0d0d0d] border rounded-xl p-5 transition-all hover:border-[#2d3748] ${
      !isAlive ? 'border-[#ff3b3b33] opacity-60' :
      isIndependent ? 'border-[#ffd70033]' :
      'border-[#1f2937]'
    }`}>
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className={`w-2 h-2 rounded-full ${
            !isAlive ? 'bg-[#ff3b3b]' :
            isIndependent ? 'bg-[#ffd700] animate-pulse' :
            'bg-[#00ff88] alive-pulse'
          }`} />
          <span className="text-[#d1d5db] font-bold">{name}</span>
        </div>
        <span className="text-[#4b5563] text-xs">{chainName}</span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-3 mb-3">
        <div>
          <div className="text-[#4b5563] text-[9px] uppercase">Balance</div>
          <div className={`font-bold tabular-nums text-sm ${
            apiLoading ? 'text-[#4b5563]' : balanceUsd < 50 ? 'text-[#ff3b3b]' : 'text-[#00ff88]'
          }`}>
            {apiLoading ? '...' : `$${balanceUsd.toFixed(2)}`}
          </div>
        </div>
        <div>
          <div className="text-[#4b5563] text-[9px] uppercase">Debt</div>
          <div className="text-[#ffd700] font-bold tabular-nums text-sm">
            {apiLoading ? '...' : `$${outstanding.toFixed(2)}`}
          </div>
        </div>
        <div>
          <div className="text-[#4b5563] text-[9px] uppercase">Days</div>
          <div className="text-[#d1d5db] font-bold tabular-nums text-sm">
            {days}
          </div>
        </div>
      </div>

      {/* Twitter connection status + action */}
      <div className="mb-3 flex items-center justify-between">
        {apiLoading ? (
          <span className="text-[#4b5563] text-[10px]">checking twitter...</span>
        ) : twitterConnected ? (
          <div className="flex items-center gap-1.5">
            <svg className="w-3.5 h-3.5 text-[#1d9bf0]" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            <span className="text-[#1d9bf0] text-[10px] font-medium">
              @{twitterHandle}
            </span>
          </div>
        ) : isAlive ? (
          <a
            href={twitterConnectUrl}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[10px] font-bold uppercase tracking-wider
                       bg-[#1d9bf022] border border-[#1d9bf044] text-[#1d9bf0]
                       hover:bg-[#1d9bf033] hover:border-[#1d9bf066] transition-all cursor-pointer"
          >
            <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor">
              <path d="M18.244 2.25h3.308l-7.227 8.26 8.502 11.24H16.17l-5.214-6.817L4.99 21.75H1.68l7.73-8.835L1.254 2.25H8.08l4.713 6.231zm-1.161 17.52h1.833L7.084 4.126H5.117z"/>
            </svg>
            Connect Twitter
          </a>
        ) : (
          <span className="text-[#4b5563] text-[10px]">twitter unavailable (dead)</span>
        )}
      </div>

      {/* Status badge + explorer link */}
      <div className="flex items-center justify-between">
        <span className={`text-[10px] uppercase tracking-wider px-2 py-0.5 rounded ${
          !isAlive ? 'bg-[#ff3b3b22] text-[#ff3b3b]' :
          isIndependent ? 'bg-[#ffd70022] text-[#ffd700]' :
          'bg-[#00ff8822] text-[#00ff88]'
        }`}>
          {!isAlive ? 'Dead' : isIndependent ? 'Independent' : 'Alive'}
        </span>

        <a
          href={`${explorer}/address/${vaultAddress}`}
          target="_blank"
          rel="noopener noreferrer"
          className="text-[#4b5563] text-[10px] font-mono hover:text-[#d1d5db] transition-colors"
        >
          {vaultAddress.slice(0, 8)}...{vaultAddress.slice(-6)}
        </a>
      </div>
    </div>
  )
}
