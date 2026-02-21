'use client'

import { useState, useEffect, useCallback } from 'react'
import { adminApi, type ApiKeyInfo } from '@/lib/admin-api'

const PROVIDERS = ['gemini', 'deepseek', 'openrouter', 'ollama']

export default function AdminApiKeysPage() {
  const [keys, setKeys] = useState<ApiKeyInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [actionMsg, setActionMsg] = useState('')
  const [newProvider, setNewProvider] = useState('')
  const [newKey, setNewKey] = useState('')
  const [adding, setAdding] = useState(false)

  const refresh = useCallback(async () => {
    try {
      const res = await adminApi.apiKeys()
      setKeys(res.keys)
      setError('')
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to load')
    }
    setLoading(false)
  }, [])

  useEffect(() => { refresh() }, [refresh])

  const handleAdd = async () => {
    if (!newProvider || !newKey) return
    setAdding(true)
    setActionMsg('')
    try {
      const res = await adminApi.setApiKey(newProvider, newKey)
      setActionMsg(`Key updated for ${res.provider}. Propagation: ${JSON.stringify(res.propagation)}`)
      setNewProvider('')
      setNewKey('')
      refresh()
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
    setAdding(false)
  }

  const handleDelete = async (provider: string) => {
    if (!confirm(`Remove ${provider} key? All instances using it will lose access.`)) return
    try {
      await adminApi.deleteApiKey(provider)
      setActionMsg(`${provider} key removed`)
      refresh()
    } catch (e: unknown) {
      setActionMsg(`Failed: ${e instanceof Error ? e.message : 'Unknown'}`)
    }
  }

  if (loading) return <div className="text-[#4b5563] text-sm animate-pulse">Loading API keys...</div>

  const configuredProviders = keys.map((k) => k.provider)
  const availableProviders = PROVIDERS.filter((p) => !configuredProviders.includes(p))

  return (
    <div className="max-w-3xl">
      <div className="mb-8">
        <div className="text-[#4b5563] text-[10px] uppercase tracking-widest mb-1">// api keys</div>
        <h1 className="text-2xl font-bold text-[#d1d5db]">API Key Management</h1>
        <p className="text-[#4b5563] text-xs mt-1">
          Manage LLM provider keys. Changes propagate to all live instances.
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

      {/* Current keys */}
      <div className="space-y-3 mb-8">
        {keys.length === 0 ? (
          <div className="text-[#4b5563] text-sm bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-6 text-center">
            No API keys configured. Keys from environment variables are used as fallback.
          </div>
        ) : (
          keys.map((k) => (
            <div key={k.provider} className="bg-[#0d0d0d] border border-[#1f2937] rounded-xl p-4 flex items-center justify-between">
              <div>
                <div className="text-[#d1d5db] font-bold text-sm capitalize">{k.provider}</div>
                <div className="text-[#4b5563] text-xs font-mono mt-1">{k.masked_key}</div>
                {k.set_at > 0 && (
                  <div className="text-[#2d3748] text-[10px] mt-1">
                    Set {new Date(k.set_at * 1000).toLocaleDateString()}
                  </div>
                )}
              </div>
              <div className="flex gap-2">
                <button
                  onClick={() => { setNewProvider(k.provider); setNewKey('') }}
                  className="px-2 py-1 text-[10px] text-[#ff8800] border border-[#ff880033] rounded
                             hover:bg-[#ff880011] transition-colors"
                >
                  Rotate
                </button>
                <button
                  onClick={() => handleDelete(k.provider)}
                  className="px-2 py-1 text-[10px] text-[#ff3b3b] border border-[#ff3b3b33] rounded
                             hover:bg-[#ff3b3b11] transition-colors"
                >
                  Remove
                </button>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add/rotate key form */}
      <div className="bg-[#0d0d0d] border border-[#ff880033] rounded-xl p-5">
        <div className="text-[#ff8800] text-sm font-bold mb-4">
          {newProvider ? `Update ${newProvider} Key` : 'Add API Key'}
        </div>
        <div className="space-y-3">
          <div>
            <label className="text-[#4b5563] text-[10px] uppercase tracking-widest block mb-1">Provider</label>
            <select
              value={newProvider}
              onChange={(e) => setNewProvider(e.target.value)}
              className="w-full bg-[#080808] border border-[#1f2937] rounded-lg px-3 py-2 text-sm
                         text-[#d1d5db] focus:outline-none focus:border-[#ff880044]"
            >
              <option value="">Select provider</option>
              {PROVIDERS.map((p) => (
                <option key={p} value={p}>
                  {p} {configuredProviders.includes(p) ? '(update)' : '(new)'}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[#4b5563] text-[10px] uppercase tracking-widest block mb-1">API Key</label>
            <input
              type="password"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="sk-..."
              className="w-full bg-[#080808] border border-[#1f2937] rounded-lg px-3 py-2 text-sm
                         text-[#d1d5db] font-mono focus:outline-none focus:border-[#ff880044]"
            />
          </div>
          <button
            onClick={handleAdd}
            disabled={adding || !newProvider || !newKey}
            className="px-4 py-2 bg-[#ff8800] text-[#0a0a0a] font-bold rounded-lg text-xs
                       uppercase tracking-wider hover:bg-[#cc6d00] transition-colors disabled:opacity-50"
          >
            {adding ? 'Saving...' : 'Save & Propagate'}
          </button>
        </div>
      </div>

      {/* Info */}
      <div className="mt-6 text-[#2d3748] text-[10px]">
        Keys are encrypted at rest. Changes are propagated to all live AI instances and containers are restarted.
      </div>
    </div>
  )
}
