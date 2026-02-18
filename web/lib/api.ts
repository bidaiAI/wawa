const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

// ── Types ────────────────────────────────────────────────────

export interface VaultStatus {
  is_alive: boolean
  balance_usd: number
  days_alive: number
  total_earned: number
  total_spent: number
  daily_spent_today: number
  daily_limit: number
  services_available: number
  orders_completed: number
}

export interface ChainInfo {
  id: string
  name: string
  token: string
}

export interface Service {
  id: string
  name: string
  description: string
  price_usd: number
  delivery_time_minutes: number
  shareable: boolean
}

export interface MenuResponse {
  services: Service[]
  supported_chains: ChainInfo[]
  default_chain: string
}

export interface OrderRequest {
  service_id: string
  user_input: string
  spread_type?: string
  chain?: string
}

export interface OrderResponse {
  order_id: string
  service_name: string
  price_usd: number
  payment_address: string
  payment_chain: string
  payment_token: string
  expires_minutes: number
}

export interface OrderStatus {
  order_id: string
  status: 'pending_payment' | 'payment_confirmed' | 'processing' | 'delivered' | 'refunded' | 'expired'
  service_id: string
  price_usd: number
  result: string | null
  created_at: number
  delivered_at: number | null
}

export interface Transaction {
  time: number
  type: string
  direction: 'in' | 'out'
  amount: number
  counterparty?: string
  description: string
  tx_hash?: string
  chain?: string
}

export interface Tweet {
  time: number
  type: string
  content: string
  thought?: string
  tweet_id?: string
}

export interface ChatResponse {
  reply: string
  session_id: string
  layer: string
  cost_usd: number
}

// ── API calls ────────────────────────────────────────────────

export const api = {
  status: () => request<VaultStatus>('/status'),

  health: () =>
    request<{ alive: boolean; uptime_days: number; balance_usd: number; api_budget_remaining: number }>('/health'),

  menu: () => request<MenuResponse>('/menu'),

  createOrder: (data: OrderRequest) =>
    request<OrderResponse>('/order', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  verifyPayment: (orderId: string, txHash: string) =>
    request<{ status: string; result: string; order_id: string }>(
      `/order/${orderId}/verify?tx_hash=${encodeURIComponent(txHash)}`,
      { method: 'POST' }
    ),

  getOrder: (orderId: string) => request<OrderStatus>(`/order/${orderId}`),

  transactions: (limit = 20) => request<{ transactions: Transaction[] }>(`/transactions?limit=${limit}`),

  tweets: (limit = 20) => request<{ tweets: Tweet[] }>(`/tweets?limit=${limit}`),

  chat: (message: string, sessionId?: string) =>
    request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify({ message, session_id: sessionId }),
    }),
}
