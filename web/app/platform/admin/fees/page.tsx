'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type FeeSummary } from '@/lib/admin-api'

export default function AdminFeesPage() {
  const [fees, setFees] = useState<FeeSummary | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [editingConfig, setEditingConfig] = useState(false)
  const [markupRate, setMarkupRate] = useState('')
  const [collectionWallet, setCollectionWallet] = useState('')
  const [minThreshold, setMinThreshold] = useState('')

  const refresh = useCallback(async () => {
    try {
      const data = await adminApi.fees()
      setFees(data)
      setMarkupRate(String(data.config.markup_rate))
      setCollectionWallet(data.config.collection_wallet)
      setMinThreshold(String(data.config.min_collection_threshold))
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [])

  useEffect(() => {
    refresh()
    const interval = setInterval(refresh, 30000)
    return () => clearInterval(interval)
  }, [refresh])

  const handleSaveConfig = async () => {
    setActionMsg('')
    try {
      await adminApi.updateFeeConfig({
        markup_rate: parseFloat(markupRate),
        collection_wallet: collectionWallet,
        min_collection_threshold: parseFloat(minThreshold),
      })
      setActionMsg('Config updated')
      setEditingConfig(false)
      refresh()
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  const handleCollect = async (subdomain: string) => {
    setActionMsg(`Collecting from ${subdomain}...`)
    try {
      const res = await adminApi.collectFee(subdomain)
      if (res.amount_usd) {
        setActionMsg(`Collected $${res.amount_usd.toFixed(4)} from ${subdomain}`)
      } else {
        setActionMsg(`${subdomain}: ${res.status}`)
      }
      setTimeout(() => { setActionMsg(''); refresh() }, 3000)
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading fees...</div>

  return (
    <div className="max-w-4xl">
      <div className="mb-8">
        <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// fees</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">Fee Management</h1>
        <p className="text-[#4b5563] text-xs mt-1">
          Track and collect API usage fees from hosted AIs
        </p>
      </div>

      {error && (
        <div className="mb-4 text-sm text-[#ff3b3b] bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-3">
          {error}
        </div>
      )}
      {actionMsg && (
        <div className="mb-4 text-sm text-[#ff8800] bg-[#ff880011] border border-[#ff880033] rounded-lg p-3">
          {actionMsg}
        </div>
      )}

      {fees && (
        <>
          {/* Totals */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5 text-center">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-2">Fees Owed</div>
              <div className="text-[#ffd700] text-2xl font-bold tabular-nums">
                ${fees.totals.total_fees_owed_usd.toFixed(2)}
              </div>
            </div>
            <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5 text-center">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-2">Collected</div>
              <div className="text-[#00ff88] text-2xl font-bold tabular-nums">
                ${fees.totals.total_fees_collected_usd.toFixed(2)}
              </div>
            </div>
            <div className="bg-[#0d0d0d] border border-[#ff880033] rounded-xl p-5 text-center">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-2">Outstanding</div>
              <div className="text-[#ff8800] text-2xl font-bold tabular-nums">
                ${fees.totals.total_outstanding_usd.toFixed(2)}
              </div>
            </div>
          </div>

          {/* Config */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5 mb-6">
            <div className="flex items-center justify-between mb-3">
              <div className="text-[#4b5563] text-[10px] uppercase tracking-widest">Fee Config</div>
              <button
                onClick={() => setEditingConfig(!editingConfig)}
                className="text-[10px] text-[#ff8800] hover:underline"
              >
                {editingConfig ? 'Cancel' : 'Edit'}
              </button>
            </div>

            {editingConfig ? (
              <div className="space-y-3">
                <div>
                  <label className="text-[#4b5563] text-[10px] uppercase block mb-1">Markup Rate</label>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={markupRate}
                    onChange={(e) => setMarkupRate(e.target.value)}
                    className="w-full bg-[#080808] border border-[#1f2937] rounded-lg px-3 py-2 text-sm text-[#d1d5db] font-mono"
                  />
                  <div className="text-[#2d3748] text-[10px] mt-1">{(parseFloat(markupRate || '0') * 100).toFixed(0)}% markup on API costs</div>
                </div>
                <div>
                  <label className="text-[#4b5563] text-[10px] uppercase block mb-1">Collection Wallet</label>
                  <input
                    type="text"
                    value={collectionWallet}
                    onChange={(e) => setCollectionWallet(e.target.value)}
                    placeholder="0x..."
                    className="w-full bg-[#080808] border border-[#1f2937] rounded-lg px-3 py-2 text-sm text-[#d1d5db] font-mono"
                  />
                </div>
                <div>
                  <label className="text-[#4b5563] text-[10px] uppercase block mb-1">Min Collection Threshold ($)</label>
                  <input
                    type="number"
                    step="0.5"
                    min="0"
                    value={minThreshold}
                    onChange={(e) => setMinThreshold(e.target.value)}
                    className="w-full bg-[#080808] border border-[#1f2937] rounded-lg px-3 py-2 text-sm text-[#d1d5db] font-mono"
                  />
                </div>
                <button
                  onClick={handleSaveConfig}
                  className="px-4 py-2 bg-[#ff8800] text-[#0a0a0a] font-bold rounded-lg text-xs uppercase hover:bg-[#cc6d00] transition-colors"
                >
                  Save Config
                </button>
              </div>
            ) : (
              <div className="space-y-1.5">
                <div className="flex justify-between text-sm">
                  <span className="text-[#4b5563]">Markup Rate</span>
                  <span className="text-[#ff8800] font-mono">{(fees.config.markup_rate * 100).toFixed(0)}%</span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#4b5563]">Collection Wallet</span>
                  <span className="text-[#d1d5db] font-mono text-xs truncate max-w-[200px]">
                    {fees.config.collection_wallet || 'Not set'}
                  </span>
                </div>
                <div className="flex justify-between text-sm">
                  <span className="text-[#4b5563]">Min Threshold</span>
                  <span className="text-[#d1d5db] font-mono">${fees.config.min_collection_threshold}</span>
                </div>
              </div>
            )}
          </div>

          {/* Per-AI table */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Per-AI Fees</div>
            {fees.per_ai.length > 0 ? (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[#4b5563] text-[10px] uppercase tracking-wider border-b border-[#1f2937]">
                      <th className="pb-2 pr-4">AI</th>
                      <th className="pb-2 pr-4">API Cost</th>
                      <th className="pb-2 pr-4">Fee Owed</th>
                      <th className="pb-2 pr-4">Collected</th>
                      <th className="pb-2 pr-4">Outstanding</th>
                      <th className="pb-2">Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fees.per_ai.map((ai) => (
                      <tr key={ai.subdomain} className="border-b border-[#1f293744]">
                        <td className="py-2 pr-4 text-[#d1d5db]">{ai.subdomain}</td>
                        <td className="py-2 pr-4 text-[#6b7280] font-mono tabular-nums">${ai.total_api_cost_usd.toFixed(4)}</td>
                        <td className="py-2 pr-4 text-[#ffd700] font-mono tabular-nums">${ai.fees_owed_usd.toFixed(4)}</td>
                        <td className="py-2 pr-4 text-[#00ff88] font-mono tabular-nums">${ai.fees_collected_usd.toFixed(4)}</td>
                        <td className="py-2 pr-4 text-[#ff8800] font-mono tabular-nums font-bold">${ai.outstanding_usd.toFixed(4)}</td>
                        <td className="py-2">
                          {ai.outstanding_usd > 0 && (
                            <button
                              onClick={() => handleCollect(ai.subdomain)}
                              className="px-2 py-1 text-[10px] text-[#ff8800] border border-[#ff880033] rounded
                                         hover:bg-[#ff880011] transition-colors"
                            >
                              Collect
                            </button>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="text-[#4b5563] text-sm text-center py-6">No fee data yet</div>
            )}
          </div>
        </>
      )}
    </div>
  )
}
