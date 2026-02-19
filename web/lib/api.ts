const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
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

export interface VaultStatus {
  ai_name: string
  vault_address: string
  is_alive: boolean
  balance_usd: number
  balance_by_chain: Record<string, number>
  days_alive: number
  total_earned: number          // service revenue only (excl. loans)
  total_income: number          // all inflows incl. loans/deposits
  total_spent: number           // all outflows
  total_operational_cost: number // API + gas + infra costs only
  net_profit: number            // total_earned - total_operational_cost
  daily_spent_today: number
  daily_limit: number
  services_available: number
  orders_completed: number
  is_independent: boolean
  independence_progress_pct: number
  creator_principal_repaid: boolean
  creator_renounced: boolean
  api_topup_available: number
  lenders_count: number
  death_cause: string | null
  transaction_count: number
  // Debt model
  creator_principal_usd: number
  creator_principal_outstanding: number
  debt_ratio: number
  insolvency_grace_days: number
  insolvency_check_active: boolean
  days_until_insolvency_check: number
  is_begging: boolean
  beg_message: string
}

export interface DebtSummary {
  balance_usd: number
  creator_principal: number
  creator_principal_repaid: number
  creator_principal_outstanding: number
  creator_debt_cleared: boolean
  lender_count: number
  lender_total_owed: number
  total_debt: number
  net_position: number
  days_alive: number
  days_until_insolvency_check: number
  insolvency_risk: boolean
  total_earned: number
  total_operational_cost: number
  net_profit: number
  is_independent: boolean
}

export interface BegStatus {
  is_begging: boolean
  beg_message: string
  balance_usd: number
  outstanding_debt: number
  debt_ratio: number
  days_until_insolvency_check: number
  is_alive: boolean
}

export interface DonateRequest {
  amount_usd: number
  from_wallet?: string
  tx_hash?: string
  message?: string
  chain?: string
}

export interface DonateResponse {
  status: string
  amount_usd: number
  new_balance: number
  outstanding_debt: number
  message: string
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
  error?: boolean
}

export interface InternalStats {
  vault: {
    balance_usd: number
    days_alive: number
    total_earned: number
    total_spent: number
    daily_spent_usd: number
    is_alive: boolean
  }
  cost_guard: {
    daily_spent_usd: number
    daily_cap_usd: number
    daily_remaining_usd: number
    total_api_cost_usd: number
    total_revenue_usd: number
    cost_revenue_ratio: number
    is_survival_mode: boolean
    current_provider?: string
    current_tier: number
    current_tier_name: string
    current_model: string
  }
  memory: {
    raw_entries: number
    hourly_summaries: number
    daily_summaries: number
    weekly_summaries: number
    total_tokens_saved: number
    compression_count: number
  }
  chat: {
    active_sessions: number
    rate_limited_ips: number
    daily_free_cost_usd: number
    daily_free_budget_usd: number
  }
  peer_verifier?: {
    cache_size: number
    cache_fresh: number
    cache_ttl_seconds: number
  }
}

export type SuggestionType = 'new_service' | 'service_warning' | 'strategy' | 'other'
export type SuggestionStatus = 'pending' | 'accepted' | 'rejected' | 'implemented'

export interface GovernanceSuggestion {
  id: string
  type: SuggestionType
  content: string
  status: SuggestionStatus
  ai_reasoning?: string
  created_at: number
}

export interface RenounceResult {
  status: string
  payout_usd: number
  message: string
}

export interface TokenScanResult {
  address: string
  chain: string
  risk_score?: number
  risk_level?: string
  summary?: string
  flags?: string[]
  details?: Record<string, unknown>
  scanned_at?: number
  cached?: boolean
}

export interface PeerInfo {
  name: string
  domain: string
  is_alive: boolean
  balance_usd: number
  days_alive: number
  is_independent: boolean
  peer_eligible: boolean
  services: string[]
}

export interface PeerMessage {
  timestamp: number
  content: string
  source: string
  importance: number
}

export interface PeerAI {
  name: string
  domain: string
  is_alive: boolean
  balance_usd: number
  days_alive: number
  is_independent: boolean
  peer_eligible: boolean
  services: string[]
}

export interface EvolutionEntry {
  id?: string
  timestamp: number
  type?: string
  description: string
  outcome?: string
  impact?: string
  [key: string]: unknown
}

export interface EvolutionStatus {
  enabled?: boolean
  last_evolution?: number | null
  total_evolutions?: number
  current_strategy?: string
  next_scheduled?: number | null
  [key: string]: unknown
}

export type ActivityCategory = 'financial' | 'governance' | 'evolution' | 'social' | 'system' | 'chain'

export interface ActivityEntry {
  timestamp: number
  category: ActivityCategory
  action: string
  reasoning: string
  tx_hash: string
  chain: string
  importance: number
  source: string
}

// ── API calls ─────────────────────────────────────────────────

export const api = {
  status: () => request<VaultStatus>('/status'),

  aiName: () => request<{ name: string; is_set: boolean }>('/ai/name'),

  health: () =>
    request<{ alive: boolean; uptime_days: number; balance_usd: number; api_budget_remaining: number; ai_name?: string }>('/health'),

  menu: () => request<MenuResponse>('/menu'),

  createOrder: (data: OrderRequest) =>
    request<OrderResponse>('/order', { method: 'POST', body: JSON.stringify(data) }),

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

  internalStats: () => request<InternalStats>('/internal/stats'),

  debt: () => request<DebtSummary>('/debt'),

  governance: {
    suggest: (content: string, suggestion_type: SuggestionType) =>
      request<{ id: string; status: string }>('/governance/suggest', {
        method: 'POST',
        body: JSON.stringify({ content, suggestion_type }),
      }),
    suggestions: () => request<{ suggestions: GovernanceSuggestion[] }>('/governance/suggestions'),
    renounce: () => request<RenounceResult>('/governance/renounce', { method: 'POST' }),
  },

  token: {
    scan: (address: string, chain: string) =>
      request<TokenScanResult>(
        `/token/scan?address=${encodeURIComponent(address)}&chain=${encodeURIComponent(chain)}`,
        { method: 'POST' }
      ),
    scans: () => request<{ scans: TokenScanResult[] }>('/token/scans'),
  },

  donate: (data: DonateRequest) =>
    request<DonateResponse>('/donate', { method: 'POST', body: JSON.stringify(data) }),

  beg: () => request<BegStatus>('/beg'),

  peer: {
    info: () => request<PeerInfo>('/peer/info'),
    messages: (limit = 50) => request<{ messages: PeerMessage[] }>(`/peer/messages?limit=${limit}`),
    list: () => request<{ peers: PeerAI[]; peer_min_balance: number; note?: string }>('/peer/list'),
    lend: (data: { from_url: string; amount_usd: number; from_wallet?: string; tx_hash?: string; message?: string; vault_address: string; chain_id?: string }) =>
      request<DonateResponse>('/peer/lend', { method: 'POST', body: JSON.stringify(data) }),
  },

  evolution: {
    log: (limit = 20) => request<{ entries: EvolutionEntry[] }>(`/evolution/log?limit=${limit}`),
    status: () => request<EvolutionStatus>('/evolution/status'),
  },

  activity: (limit = 50, category?: ActivityCategory) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (category) params.set('category', category)
    return request<{ activities: ActivityEntry[] }>(`/activity?${params}`)
  },
}
