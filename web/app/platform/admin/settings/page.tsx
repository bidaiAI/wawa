'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type AdminConfig } from '@/lib/admin-api'

export default function AdminSettingsPage() {
  const [config, setConfig] = useState<AdminConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const refresh = useCallback(async () => {
    try {
      const data = await adminApi.config()
      setConfig(data)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [])

  useEffect(() => { refresh() }, [refresh])

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading settings...</div>

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// settings</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">Platform Settings</h1>
      </div>

      {error && (
        <div className="mb-4 text-sm text-[#ff3b3b] bg-[#ff3b3b11] border border-[#ff3b3b33] rounded-lg p-3">
          {error}
        </div>
      )}

      {config && (
        <div className="space-y-4">
          {/* Admin Wallets */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Admin Wallets</div>
            {config.admin_wallets.length > 0 ? (
              config.admin_wallets.map((w) => (
                <div key={w} className="text-[#d1d5db] font-mono text-xs mb-1">{w}</div>
              ))
            ) : (
              <div className="text-[#4b5563] text-sm">No admin wallets configured</div>
            )}
            <div className="text-[#2d3748] text-[10px] mt-3">
              Set via PLATFORM_ADMIN_WALLETS env var on VPS
            </div>
          </div>

          {/* API Keys Status */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">API Keys</div>
            {Object.entries(config.api_keys).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm mb-1.5">
                <span className="text-[#4b5563]">{key}</span>
                <span className="text-[#d1d5db] font-mono">{String(value)}</span>
              </div>
            ))}
          </div>

          {/* Fee Status */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Fee Tracker</div>
            {Object.entries(config.fees).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm mb-1.5">
                <span className="text-[#4b5563]">{key}</span>
                <span className="text-[#d1d5db] font-mono">{String(value)}</span>
              </div>
            ))}
          </div>

          {/* Cost Aggregator */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Cost Aggregator</div>
            {Object.entries(config.costs).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm mb-1.5">
                <span className="text-[#4b5563]">{key}</span>
                <span className="text-[#d1d5db] font-mono">{String(value)}</span>
              </div>
            ))}
          </div>

          {/* Orchestrator */}
          <div className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-5">
            <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-3">Orchestrator</div>
            {Object.entries(config.orchestrator).map(([key, value]) => (
              <div key={key} className="flex justify-between text-sm mb-1.5">
                <span className="text-[#4b5563]">{key}</span>
                <span className="text-[#d1d5db] font-mono text-xs">{JSON.stringify(value)}</span>
              </div>
            ))}
          </div>

          {/* Info */}
          <div className="text-[#2d3748] text-[10px] mt-6">
            Most settings are configured via environment variables on the VPS.
            Fee config can be edited from the Fees page.
          </div>
        </div>
      )}
    </div>
  )
}
