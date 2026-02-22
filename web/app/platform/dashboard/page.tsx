'use client'

import { useState, useEffect } from 'react'
import { useAccount, useReadContract } from 'wagmi'
import { base, bsc } from 'wagmi/chains'
import Link from 'next/link'
import WalletButton from '@/components/WalletButton'
import { FACTORY_ADDRESSES } from '@/lib/wagmi'
import { FACTORY_ABI, VAULT_V2_ABI } from '@/lib/factory-abi'

/**
 * Creator Dashboard — Wallet-gated management page.
 *
 * Connect wallet → see all AIs you've created → view status.
 *
 * Privacy boundaries:
 *   CAN see: balance, earnings, expenses, debt, days alive, model tier
 *   CANNOT see: customer chat content, order inputs, customer wallets
 */

export default function DashboardPage() {
  const { address, isConnected } = useAccount()

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
  const allVaults: { address: `0x${string}`; chainId: number; chainName: string }[] = [
    ...((baseVaults as `0x${string}`[] || []).map((v) => ({ address: v, chainId: base.id, chainName: 'Base' }))),
    ...((bscVaults as `0x${string}`[] || []).map((v) => ({ address: v, chainId: bsc.id, chainName: 'BSC' }))),
  ]

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
      ) : allVaults.length === 0 ? (
        /* No AIs */
        <div className="text-center py-16">
          <div className="text-6xl mb-4 opacity-30">🥚</div>
          <div className="text-[#4b5563] text-lg font-bold mb-2">
            No AIs found for this wallet
          </div>
          <div className="text-[#2d3748] text-sm mb-6">
            You haven&apos;t created any mortal AIs yet.
          </div>
          <Link
            href="/create"
            className="inline-block px-6 py-3 bg-[#00ff88] text-[#0a0a0a] font-bold rounded-xl
                       text-sm uppercase tracking-wider hover:bg-[#00cc6a] transition-colors"
          >
            Create Your First AI
          </Link>
        </div>
      ) : (
        /* AI List */
        <div>
          <div className="flex items-center justify-between mb-6">
            <div className="flex items-center gap-3">
              <WalletButton />
              <span className="text-[#4b5563] text-xs">
                {allVaults.length} AI{allVaults.length !== 1 ? 's' : ''}
              </span>
            </div>
            <Link
              href="/create"
              className="px-4 py-2 bg-[#00ff8822] border border-[#00ff8844] text-[#00ff88]
                         rounded-lg text-sm hover:bg-[#00ff8833] transition-colors"
            >
              + New AI
            </Link>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {allVaults.map((vault) => (
              <VaultCard
                key={`${vault.chainId}-${vault.address}`}
                vaultAddress={vault.address}
                chainId={vault.chainId}
                chainName={vault.chainName}
              />
            ))}
          </div>
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


// ── Vault Card ──
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

  // Fetch balance + debt from AI's own API (same source as AI's home page)
  // API URL derived from vault name: https://api.{name}.mortal-ai.net
  const [apiStatus, setApiStatus] = useState<{ balance_usd: number; outstanding_debt: number } | null>(null)
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
        })
        setApiLoading(false)
      })
      .catch(() => setApiLoading(false))
  }, [name])

  const balanceUsd = apiStatus?.balance_usd ?? 0
  const outstanding = apiStatus?.outstanding_debt ?? 0

  const explorer = chainId === bsc.id ? 'https://bscscan.com' : 'https://basescan.org'

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

      {/* Status badge */}
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
