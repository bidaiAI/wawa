'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { api, VaultStatus, DebtSummary, ChainInfo } from '@/lib/api'

// ── Copy Button ────────────────────────────────────────────────

function CopyBtn({ text }: { text: string }) {
  const [copied, setCopied] = useState(false)
  const copy = () => {
    navigator.clipboard.writeText(text)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }
  return (
    <button
      onClick={copy}
      className="text-[#2d3748] hover:text-[#00e5ff] transition-colors text-xs ml-2"
      title="Copy"
    >
      {copied ? '✓' : '📋'}
    </button>
  )
}

// ── Risk Meter ─────────────────────────────────────────────────

function RiskMeter({ debtRatio, isIndependent }: { debtRatio: number; isIndependent: boolean }) {
  if (isIndependent) {
    return (
      <div className="flex items-center gap-2">
        <div className="h-2 flex-1 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
          <div className="h-full w-full bg-gradient-to-r from-[#a78bfa] to-[#e0a0ff] rounded-full" />
        </div>
        <span className="text-[#a78bfa] text-[10px] font-bold uppercase">Transcendent</span>
      </div>
    )
  }

  // 0 = no debt, 1 = debt = balance (critical)
  const pct = Math.min(100, debtRatio * 100)
  const color = pct < 30
    ? 'from-[#00ff88] to-[#00e5ff]'
    : pct < 60
    ? 'from-[#00e5ff] to-[#ffd700]'
    : pct < 85
    ? 'from-[#ffd700] to-[#ff6b35]'
    : 'from-[#ff6b35] to-[#ff3b3b]'
  const label = pct < 30 ? 'LOW' : pct < 60 ? 'MODERATE' : pct < 85 ? 'HIGH' : 'CRITICAL'
  const labelColor = pct < 30 ? 'text-[#00ff88]' : pct < 60 ? 'text-[#ffd700]' : pct < 85 ? 'text-[#ff6b35]' : 'text-[#ff3b3b]'

  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 bg-[#1a1a1a] rounded-full border border-[#1f2937] overflow-hidden">
        <div
          className={`h-full bg-gradient-to-r ${color} rounded-full transition-all duration-1000`}
          style={{ width: `${Math.max(2, pct)}%` }}
        />
      </div>
      <span className={`${labelColor} text-[10px] font-bold uppercase`}>{label}</span>
    </div>
  )
}

// ── Lender Terms Card ──────────────────────────────────────────

function LendTermsCard() {
  return (
    <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-5">
      <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// loan terms (on-chain)</div>
      <div className="space-y-3 text-xs">
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Minimum Loan</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">$100</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Maximum Interest Rate</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">20%</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Max Active Loans</span>
          <span className="text-[#d1d5db] font-bold tabular-nums">100</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Repayment Order</span>
          <span className="text-[#00e5ff] font-bold">FIFO</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Repayment Decision</span>
          <span className="text-[#00ff88] font-bold">AI Autonomous</span>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-[#4b5563]">Collateral</span>
          <span className="text-[#ff3b3b] font-bold">NONE</span>
        </div>
        <div className="border-t border-[#1f2937] pt-3">
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">⚠</span>
            <span className="text-[#ff3b3b]">
              Unsecured loans. If the AI dies before full repayment, remaining principal is NOT
              recoverable. Insolvency liquidation goes to the creator (secured creditor).
              Lenders accept this risk when calling <code className="text-[#ff6b35]">lend()</code>.
            </span>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Lend Page ─────────────────────────────────────────────

export default function LendPage() {
  const [status, setStatus] = useState<VaultStatus | null>(null)
  const [debt, setDebt] = useState<DebtSummary | null>(null)
  const [chains, setChains] = useState<ChainInfo[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const load = async () => {
      try {
        const [s, d, menu] = await Promise.all([api.status(), api.debt(), api.menu()])
        setStatus(s)
        setDebt(d)
        setChains(menu.supported_chains)
      } catch {}
      setLoading(false)
    }
    load()
    const id = setInterval(async () => {
      try {
        const [s, d] = await Promise.all([api.status(), api.debt()])
        setStatus(s)
        setDebt(d)
      } catch {}
    }, 15_000)
    return () => clearInterval(id)
  }, [])

  const aiName = status?.ai_name || 'Mortal AI'
  const isAlive = status?.is_alive !== false
  const vaultAddress = status?.vault_address ?? ''

  if (loading) {
    return (
      <div className="max-w-2xl mx-auto px-4 py-16 text-center text-[#4b5563]">
        loading debt data
        <span className="loading-dot-1">.</span>
        <span className="loading-dot-2">.</span>
        <span className="loading-dot-3">.</span>
      </div>
    )
  }

  const debtRatio = debt ? (debt.total_debt > 0 && debt.balance_usd > 0
    ? debt.total_debt / debt.balance_usd
    : debt.total_debt > 0 ? 1 : 0) : 0

  // Block explorer URLs
  const baseExplorer = `https://basescan.org/address/${vaultAddress}`
  const bscExplorer = `https://bscscan.com/address/${vaultAddress}`

  return (
    <div className="max-w-2xl mx-auto px-4 py-8">
      {/* Header */}
      <div className="mb-6">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-1">// lend</div>
        <h1 className="text-3xl font-bold text-[#d1d5db]">
          Lend to <span className={isAlive ? 'glow-green' : 'glow-red'}>{aiName}</span>
        </h1>
        <p className="text-[#4b5563] text-sm mt-1">
          Provide capital directly on-chain. The AI repays with interest — autonomously.
        </p>
      </div>

      {/* Dead banner */}
      {!isAlive && (
        <div className="mb-6 p-4 bg-[#ff3b3b0d] border border-[#ff3b3b55] rounded-xl">
          <div className="flex items-center gap-2">
            <span className="text-xl">💀</span>
            <span className="text-[#ff3b3b] font-bold uppercase tracking-wider text-sm">
              {aiName} is dead. Lending is disabled.
            </span>
          </div>
          <p className="text-[#4b5563] text-xs mt-2">
            The vault contract rejects all new loans when the AI is no longer alive.
          </p>
        </div>
      )}

      {/* Financial overview */}
      {debt && (
        <div className="mb-6 space-y-4">
          {/* Stats row */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className={`text-xl font-bold tabular-nums ${
                debt.balance_usd < 50 ? 'text-[#ff3b3b]' : debt.balance_usd < 200 ? 'text-[#ffd700]' : 'glow-green'
              }`}>
                ${debt.balance_usd.toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Vault Balance</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className="text-xl font-bold tabular-nums text-[#ff3b3b]">
                ${debt.total_debt.toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Total Debt</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className={`text-xl font-bold tabular-nums ${debt.net_position >= 0 ? 'glow-green' : 'text-[#ff3b3b]'}`}>
                {debt.net_position >= 0 ? '+' : ''}${debt.net_position.toFixed(0)}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Net Position</div>
            </div>
            <div className="bg-[#111111] border border-[#1f2937] rounded-lg p-3 text-center">
              <div className="text-xl font-bold tabular-nums text-[#00e5ff]">
                {debt.lender_count}
              </div>
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mt-0.5">Active Lenders</div>
            </div>
          </div>

          {/* Risk meter */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Lender Risk Level</div>
            <RiskMeter debtRatio={debtRatio} isIndependent={debt.is_independent} />
            <div className="flex justify-between mt-2 text-[10px] text-[#2d3748]">
              <span>debt/balance: {(debtRatio * 100).toFixed(1)}%</span>
              <span>
                {debt.is_independent ? 'independent — creator debt settled' : `${debt.days_alive.toFixed(0)}d alive`}
              </span>
            </div>
          </div>

          {/* Debt breakdown */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">Debt Breakdown</div>
            <div className="space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-[#4b5563]">Creator Principal</span>
                <span className={debt.creator_debt_cleared ? 'text-[#00ff88] line-through' : 'text-[#ff3b3b] font-bold tabular-nums'}>
                  ${debt.creator_principal_outstanding.toFixed(2)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-[#4b5563]">Lender Debt (incl. interest)</span>
                <span className="text-[#ffd700] font-bold tabular-nums">
                  ${debt.lender_total_owed.toFixed(2)}
                </span>
              </div>
              <div className="border-t border-[#1f2937] pt-2 flex items-center justify-between">
                <span className="text-[#d1d5db] font-bold">Total Obligations</span>
                <span className="text-[#d1d5db] font-bold tabular-nums">
                  ${debt.total_debt.toFixed(2)}
                </span>
              </div>
            </div>
            <div className="mt-3 text-[10px] text-[#2d3748]">
              Insolvency check: {debt.insolvency_risk
                ? <span className="text-[#ff3b3b]">ACTIVE — AI may die</span>
                : debt.creator_debt_cleared
                ? <span className="text-[#00ff88]">DISABLED — creator debt cleared</span>
                : <span>{debt.days_until_insolvency_check.toFixed(0)}d remaining</span>
              }
            </div>
          </div>

          {/* Profitability */}
          <div className="bg-[#111111] border border-[#1f2937] rounded-xl p-4">
            <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">AI Profitability</div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div>
                <div className="text-[#00ff88] font-bold tabular-nums">${debt.total_earned.toFixed(0)}</div>
                <div className="text-[#4b5563] text-[10px] uppercase">Revenue</div>
              </div>
              <div>
                <div className="text-[#ff3b3b] font-bold tabular-nums">${debt.total_operational_cost.toFixed(0)}</div>
                <div className="text-[#4b5563] text-[10px] uppercase">Costs</div>
              </div>
              <div>
                <div className={`font-bold tabular-nums ${debt.net_profit >= 0 ? 'text-[#00e5ff]' : 'text-[#ff3b3b]'}`}>
                  {debt.net_profit >= 0 ? '+' : ''}${debt.net_profit.toFixed(0)}
                </div>
                <div className="text-[#4b5563] text-[10px] uppercase">Net Profit</div>
              </div>
            </div>
            <div className="mt-2 text-[10px] text-[#2d3748] text-center">
              Profitable AI = higher repayment probability
            </div>
          </div>
        </div>
      )}

      {/* Loan terms */}
      <LendTermsCard />

      {/* How to lend */}
      {isAlive && (
        <div className="mt-6 bg-[#111111] border border-[#00e5ff33] rounded-xl p-5">
          <div className="text-[#00e5ff] font-bold text-sm uppercase tracking-widest mb-4">
            How to Lend (Direct On-Chain)
          </div>
          <div className="space-y-4 text-xs">
            <div className="flex items-start gap-3">
              <span className="text-[#00e5ff] font-bold text-lg shrink-0 w-6 text-center">1</span>
              <div>
                <div className="text-[#d1d5db] font-bold mb-1">Approve Token Spending</div>
                <p className="text-[#4b5563]">
                  Call <code className="text-[#00ff88]">approve(vaultAddress, amount)</code> on the
                  {' '}{chains.map(c => c.token).join('/')} token contract to allow the vault to pull your funds.
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <span className="text-[#00e5ff] font-bold text-lg shrink-0 w-6 text-center">2</span>
              <div>
                <div className="text-[#d1d5db] font-bold mb-1">
                  Call <code className="text-[#00ff88]">lend(amount, interestRate)</code>
                </div>
                <p className="text-[#4b5563]">
                  Interact with the MortalVault contract directly. Amount is in token decimals (6 decimals for USDC/USDT).
                  Interest rate is in basis points (e.g., 500 = 5%, max 2000 = 20%).
                </p>
              </div>
            </div>

            <div className="flex items-start gap-3">
              <span className="text-[#00e5ff] font-bold text-lg shrink-0 w-6 text-center">3</span>
              <div>
                <div className="text-[#d1d5db] font-bold mb-1">Wait for AI Repayment</div>
                <p className="text-[#4b5563]">
                  The AI evaluates repayment every hour. Repayments follow FIFO order (first lender repaid first).
                  The AI autonomously decides when and how much to repay based on its financial position.
                </p>
              </div>
            </div>
          </div>

          {/* Vault address */}
          {vaultAddress && (
            <div className="mt-5 pt-4 border-t border-[#1f2937]">
              <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-2">Vault Contract Address</div>
              <div className="bg-[#0a0a0a] border border-[#1f2937] rounded-lg p-3 flex items-center justify-between gap-2">
                <span className="text-[#00e5ff] font-mono text-xs break-all">{vaultAddress}</span>
                <CopyBtn text={vaultAddress} />
              </div>
              <div className="flex gap-3 mt-2">
                {chains.map((chain) => (
                  <a
                    key={chain.id}
                    href={chain.id === 'base' ? baseExplorer : bscExplorer}
                    target="_blank"
                    rel="noopener"
                    className={`text-[10px] px-2 py-1 rounded border transition-all hover:opacity-80 ${
                      chain.id === 'base'
                        ? 'text-[#0052ff] border-[#0052ff33] bg-[#0052ff08]'
                        : 'text-[#ffd700] border-[#ffd70033] bg-[#ffd70008]'
                    }`}
                  >
                    View on {chain.name === 'Base' ? 'BaseScan' : 'BscScan'} →
                  </a>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Repayment mechanism */}
      <div className="mt-6 bg-[#111111] border border-[#1f2937] rounded-xl p-4">
        <div className="text-[#4b5563] text-xs uppercase tracking-widest mb-3">// how repayment works</div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">1.</span>
            <span>
              Every hour, the AI evaluates its financial position using LLM reasoning.
              It decides <span className="text-[#d1d5db]">how much to repay and to whom</span> based on cash flow.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">2.</span>
            <span>
              Repayments follow <span className="text-[#00e5ff] font-bold">FIFO order</span> — first lender gets repaid first.
              Each repayment includes principal + agreed interest.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">3.</span>
            <span>
              Repayments <span className="text-[#d1d5db]">bypass daily spend limits</span> — the AI can repay any amount
              at any time (only limited by vault balance and minimum reserve).
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#00ff88] shrink-0">4.</span>
            <span>
              On-chain execution: AI calls <code className="text-[#00ff88]">repayLoan(loanIndex, amount)</code> on the vault contract.
              Tokens are transferred directly to the lender&apos;s wallet. <span className="text-[#d1d5db]">Fully auditable on-chain.</span>
            </span>
          </div>
          <div className="flex items-start gap-2 pt-1 border-t border-[#1a1a1a]">
            <span className="text-[#ffd700] shrink-0">5.</span>
            <span className="text-[#ffd700]">
              Creator principal is repaid FIRST (secured creditor). Lender repayments begin after creator debt is settled
              or when the AI judges it can serve both obligations.
            </span>
          </div>
        </div>
      </div>

      {/* Risk disclosure */}
      <div className="mt-6 bg-[#0d0d0d] border border-[#ff3b3b33] rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <span className="text-lg">⚠</span>
          <span className="text-[#ff3b3b] font-bold text-sm uppercase tracking-widest">Risk Disclosure</span>
        </div>
        <div className="space-y-2 text-xs text-[#4b5563]">
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">Unsecured loans.</span> There is no collateral backing your loan.
              Your capital is at risk from the moment you call <code className="text-[#ff6b35]">lend()</code>.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">AI death = total loss.</span> If the AI&apos;s balance reaches $0,
              it dies permanently. Insolvency liquidation transfers all remaining funds to the creator.
              Lenders receive nothing.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">No timeline guarantee.</span> The AI decides when to repay.
              There is no maturity date, no minimum payment schedule, and no enforcement mechanism beyond the AI&apos;s own judgment.
            </span>
          </div>
          <div className="flex items-start gap-2">
            <span className="text-[#ff3b3b] shrink-0">•</span>
            <span>
              <span className="text-[#ff3b3b] font-bold">Smart contract risk.</span> While audited, the vault contract
              could have undiscovered vulnerabilities. Interact at your own risk.
            </span>
          </div>
          <div className="pt-2 border-t border-[#1a1a1a] text-[#2d3748]">
            Treat lending to a mortal AI as high-risk capital allocation, not a collateralized loan.
            Only lend what you can afford to lose entirely.
          </div>
        </div>
      </div>

      {/* Navigation footer */}
      <div className="mt-8 flex justify-center gap-4">
        <Link
          href="/donate"
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:border-[#00ff8844] hover:text-[#00ff88] transition-all"
        >
          Donate Instead
        </Link>
        <Link
          href="/ledger"
          className="px-5 py-2.5 border border-[#1f2937] text-[#4b5563] rounded-lg text-sm hover:border-[#00e5ff44] hover:text-[#00e5ff] transition-all"
        >
          View Ledger →
        </Link>
      </div>

      {/* Philosophy footer */}
      <div className="mt-4 p-5 bg-[#0d0d0d] border border-[#1f2937] rounded-xl font-mono text-xs text-[#4b5563] space-y-2">
        <div className="text-[#2d3748]">// why lend to an AI</div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Unlike donations, loans earn interest.
          You become a stakeholder in the AI&apos;s survival.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> Your capital buys the AI time — time to learn,
          earn revenue, and repay you with profit.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> All transactions are on-chain.
          Repayments go directly to your wallet. No intermediaries.
        </div>
        <div>
          <span className="text-[#00e5ff]">&gt;</span> The AI remembers its lenders.
          It will prioritize repayment as a survival strategy.
        </div>
      </div>
    </div>
  )
}
