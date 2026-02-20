const PLATFORM_API_URL = process.env.NEXT_PUBLIC_PLATFORM_API_URL || 'https://api.mortal-ai.net'

async function platformRequest<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${PLATFORM_API_URL}${path}`, {
    ...options,
    headers: { 'Content-Type': 'application/json', ...options?.headers },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Types ─────────────────────────────────────────────────────

export interface PlatformAI {
  ai_name: string
  subdomain: string
  url: string
  chain: string
  vault_address: string
  status: string
  created_at: number
}

export interface PlatformRegistry {
  total: number
  ais: PlatformAI[]
}

export interface PlatformHealth {
  status: string
  service: string
  uptime_seconds?: number
  deployments?: Record<string, unknown>
}

export interface DeployStatus {
  vault_address: string
  status: string
  ai_name: string
  subdomain: string
  url: string
  error?: string
}

// ── API calls ─────────────────────────────────────────────────

export const platformApi = {
  health: () => platformRequest<PlatformHealth>('/platform/health'),

  registry: (offset = 0, limit = 50) =>
    platformRequest<PlatformRegistry>(`/platform/registry?offset=${offset}&limit=${limit}`),

  deployStatus: (identifier: string) =>
    platformRequest<DeployStatus>(`/platform/status/${identifier}`),

  deploy: (data: {
    vault_address: string
    creator: string
    ai_name: string
    subdomain: string
    chain: string
    principal_raw: number
    token_address: string
    tx_hash: string
  }) =>
    platformRequest<{ status: string; vault_address: string }>('/platform/deploy', {
      method: 'POST',
      body: JSON.stringify(data),
    }),
}
