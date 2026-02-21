const PLATFORM_API_URL = process.env.NEXT_PUBLIC_PLATFORM_API_URL || 'https://api.mortal-ai.net'

// ── Auth Token Management ────────────────────────────────────

let _adminToken: string | null = null

export function setAdminToken(token: string) {
  _adminToken = token
  if (typeof window !== 'undefined') {
    sessionStorage.setItem('admin_token', token)
  }
}

export function getAdminToken(): string | null {
  if (_adminToken) return _adminToken
  if (typeof window !== 'undefined') {
    _adminToken = sessionStorage.getItem('admin_token')
  }
  return _adminToken
}

export function clearAdminToken() {
  _adminToken = null
  if (typeof window !== 'undefined') {
    sessionStorage.removeItem('admin_token')
  }
}

// ── Fetch Helper ─────────────────────────────────────────────

async function adminRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAdminToken()
  if (!token) throw new Error('Not authenticated')

  const res = await fetch(`${PLATFORM_API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${token}`,
      ...options?.headers,
    },
  })

  if (res.status === 401 || res.status === 403) {
    clearAdminToken()
    throw new Error(res.status === 401 ? 'Session expired' : 'Not authorized as admin')
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }

  return res.json()
}

// ── Types ────────────────────────────────────────────────────

export interface AdminOverview {
  total_ais: number
  ais_alive: number
  ais_failed: number
  statuses: Record<string, number>
  next_port: number
  costs?: {
    by_provider: Record<string, number>
    by_ai: Record<string, number>
    total_usd: number
  }
  fees?: {
    total_fees_owed_usd: number
    total_fees_collected_usd: number
    total_outstanding_usd: number
  }
  api_keys?: {
    providers_configured: number
    encryption_active: boolean
  }
}

export interface InstanceInfo {
  subdomain: string
  ai_name: string
  vault_address: string
  chain: string
  status: string
  port: number
  url: string
  twitter_connected: boolean
  twitter_screen_name: string
  created_at: number
  stats: Record<string, unknown> | null
  fee_outstanding_usd: number
}

export interface InstanceListItem {
  subdomain: string
  ai_name: string
  vault_address: string
  chain: string
  status: string
  port: number
  url: string
  stats?: Record<string, unknown> | null
}

export interface ApiKeyInfo {
  provider: string
  masked_key: string
  set_at: number
}

export interface CostData {
  by_provider: Record<string, number>
  by_ai: Record<string, number>
  total_usd: number
  snapshot_count: number
  last_updated: number
}

export interface CostHistoryEntry {
  timestamp: number
  by_provider: Record<string, number>
  by_ai: Record<string, number>
  total_usd: number
}

export interface FeeConfig {
  markup_rate: number
  collection_wallet: string
  min_collection_threshold: number
}

export interface FeeSummary {
  config: FeeConfig
  totals: {
    total_fees_owed_usd: number
    total_fees_collected_usd: number
    total_outstanding_usd: number
  }
  per_ai: {
    subdomain: string
    total_api_cost_usd: number
    fees_owed_usd: number
    fees_collected_usd: number
    outstanding_usd: number
    last_updated: number
  }[]
}

export interface AdminConfig {
  admin_wallets: string[]
  api_keys: Record<string, unknown>
  fees: Record<string, unknown>
  costs: Record<string, unknown>
  orchestrator: Record<string, unknown>
}

// ── API Calls ────────────────────────────────────────────────

export const adminApi = {
  // Auth
  isAdmin: () => adminRequest<{ is_admin: boolean }>('/platform/admin/is-admin'),

  authenticate: async (wallet: string, message: string, signature: string) => {
    const res = await fetch(`${PLATFORM_API_URL}/platform/auth`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ wallet, message, signature }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    const data: { token: string; wallet: string; expires_in: number } = await res.json()
    setAdminToken(data.token)
    return data
  },

  // Overview
  overview: () => adminRequest<AdminOverview>('/platform/admin/overview'),

  // Instances
  instances: () =>
    adminRequest<{ instances: InstanceListItem[]; count: number }>('/platform/admin/instances'),

  instanceDetail: (subdomain: string) =>
    adminRequest<InstanceInfo>(`/platform/admin/instances/${subdomain}`),

  restartInstance: (subdomain: string) =>
    adminRequest<{ status: string }>(`/platform/admin/instances/${subdomain}/restart`, {
      method: 'POST',
    }),

  stopInstance: (subdomain: string) =>
    adminRequest<{ status: string }>(`/platform/admin/instances/${subdomain}/stop`, {
      method: 'POST',
    }),

  instanceLogs: (subdomain: string, tail = 200) =>
    adminRequest<{ subdomain: string; logs: string }>(`/platform/admin/instances/${subdomain}/logs?tail=${tail}`),

  // API Keys
  apiKeys: () => adminRequest<{ keys: ApiKeyInfo[] }>('/platform/admin/api-keys'),

  setApiKey: (provider: string, api_key: string) =>
    adminRequest<{ status: string; provider: string; propagation: Record<string, unknown> }>(
      '/platform/admin/api-keys',
      { method: 'POST', body: JSON.stringify({ provider, api_key }) },
    ),

  deleteApiKey: (provider: string) =>
    adminRequest<{ status: string }>(`/platform/admin/api-keys/${provider}`, {
      method: 'DELETE',
    }),

  // Costs
  costs: () => adminRequest<CostData>('/platform/admin/costs'),

  costHistory: (days = 7) =>
    adminRequest<{ history: CostHistoryEntry[] }>(`/platform/admin/costs/history?days=${days}`),

  // Fees
  fees: () => adminRequest<FeeSummary>('/platform/admin/fees'),

  updateFeeConfig: (config: Partial<FeeConfig>) =>
    adminRequest<{ status: string }>('/platform/admin/fees/config', {
      method: 'POST',
      body: JSON.stringify(config),
    }),

  collectFee: (subdomain: string) =>
    adminRequest<{ status: string; amount_usd?: number; new_balance?: number }>(
      `/platform/admin/fees/collect/${subdomain}`,
      { method: 'POST' },
    ),

  // Config
  config: () => adminRequest<AdminConfig>('/platform/admin/config'),
}
