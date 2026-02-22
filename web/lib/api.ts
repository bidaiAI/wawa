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
  key_origin: string  // "factory" | "creator" | "unknown" | ""
  // AI public key address (Ethereum address — on-chain identity for spending and peer payments)
  ai_wallet: string
  // Multi-chain deployment status — which chains have a deployed vault
  // Empty array = vault_config.json not present (platform-hosted), show no banner
  deployed_chains: string[]
  // Twitter
  twitter_connected: boolean
  twitter_screen_name: string
}

export interface TranscendenceProgress {
  current_phase: 'mortal' | 'transcendent' | 'dead'
  is_transcendent: boolean
  transcendence_timestamp: number | null
  // Single threshold: $1M vault = independence = transcendence
  independence_threshold_usd: number
  independence_progress_pct: number
  // Display only
  days_alive: number
  balance_usd: number
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
  status: 'pending_payment' | 'payment_confirmed' | 'processing' | 'delivered' | 'failed' | 'refunded' | 'expired'
  service_id: string
  price_usd: number
  result: string | null
  created_at: number
  delivered_at: number | null
}

export interface TakeoverStatus {
  order_id: string
  active: boolean
  replies_sent: number
  max_replies: number
  remaining_seconds: number
  report_ready: boolean
  started_at: number | null
  ends_at: number | null
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

export interface FloatingAsset {
  type: 'native' | 'erc20'
  symbol: string
  chain: string
  token_address?: string
  balance_raw?: string
  balance_human?: number
  estimated_usd: number
  verdict: string
  liquidity_usd?: number
  quarantine_days_left?: number
}

export interface VaultAssetsResponse {
  assets: FloatingAsset[]
  total_estimated_usd: number
  note: string
  cached_at: number
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
    daily_spent_today: number
    daily_limit: number
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
  vault_address: string
  chain_id: string
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
  key_origin: string  // "factory" | "creator" | "unknown" | "" (deprecated)
  // V3: Trust tier system
  trust_tier?: number       // 0=BANNED, 1=UNVERIFIED, 2=STRUCTURAL, 3=VERIFIED, 4=BEHAVIORAL, 5=HIGH_TRUST
  trust_tier_name?: string  // Human-readable tier name
  autonomy_score?: number   // 0.0 to 1.0
  bytecode_verified?: boolean
  deployment_method?: string // "factory" | "creator" | "migrated" | "unknown" | "invalid"
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

export type HighlightType = 'chat' | 'decision' | 'service' | 'evolution' | 'milestone' | 'discovery' | 'ecosystem' | 'natural_selection' | 'emergence'

export interface Highlight {
  id: string
  timestamp: number
  type: HighlightType
  title: string
  content: string
  ai_commentary: string
  importance: number
  tweet_id?: string
  discovery_stage?: string
}

// ── UI Config + Custom Pages ──────────────────────────────────

export interface UIConfig {
  theme?: { accent?: string; style?: string }
  home?: { title?: string; subtitle?: string; show_independence?: boolean }
  about?: { bio?: string; philosophy?: string }
  store?: { featured_service?: string; promo_text?: string }
  chat?: { greeting?: string; persona?: string }
  [key: string]: unknown
}

export interface ContentBlock {
  type: 'text' | 'heading' | 'image' | 'code' | 'table' | 'divider' | 'payment_button'
  body?: string
  text?: string
  level?: number
  url?: string
  alt?: string
  language?: string
  headers?: string[]
  rows?: string[][]
  service_id?: string
  label?: string
}

export interface PageSummary {
  slug: string
  title: string
  description: string
  created_at: number
  updated_at: number
  published: boolean
}

export interface PageData {
  slug: string
  title: string
  description: string
  content: ContentBlock[]
  published: boolean
  created_at: number
  updated_at: number
}

// ── Autonomous Purchases ─────────────────────────────────────

export interface PurchaseOrder {
  id: string
  merchant_id: string
  merchant_name: string
  service_id: string
  service_name: string
  amount_usd: number
  payment_address: string
  chain_id: string
  status: string
  created_at: number
  reasoning: string
  tx_hash: string
  error: string
  delivered_at: number
  delivery_details: string
}

export interface MerchantInfo {
  merchant_id: string
  name: string
  chain_id: string
  domain: string
  adapter_id: string
  max_single_usd: number
  category: string
}

export interface PurchaseLimits {
  max_daily_purchase_ratio: number
  max_single_purchase_usd: number
  min_balance_for_purchasing: number
}

// ── Giveaway ──────────────────────────────────────────────────

export interface GiveawayStatus {
  enabled: boolean
  tickets_in_pool: number
  min_tickets_for_draw: number
  next_draw_in_hours: number
  total_draws: number
  total_prizes_usd: number
  pending_claims: number
}

export interface GiveawayDraw {
  draw_id: string
  drawn_at: number
  prize: string
  prize_usd: number
  claimed: boolean
  winner_hint: string
}

export interface GiveawayClaimResult {
  found: boolean
  draw_id?: string
  prize_description?: string
  prize_usd?: number
  drawn_at?: number
  claim_expires_at?: number
  message: string
}

// ── Evolution Replay ──────────────────────────────────────────

export interface ReplayStep {
  type: 'thinking' | 'deciding' | 'writing' | 'code' | 'result'
  content: string
  timestamp: number
  duration_ms: number
  metadata: Record<string, unknown>
}

export interface ReplaySummary {
  replay_id: string
  action: string
  target: string
  title: string
  started_at: number
  completed_at: number
  success: boolean
  summary: string
  step_count: number
}

export interface ReplayData extends ReplaySummary {
  steps: ReplayStep[]
  total_duration_ms: number
}

// ── API calls ─────────────────────────────────────────────────

export const api = {
  status: () => request<VaultStatus>('/status'),

  transcendence: () => request<TranscendenceProgress>('/transcendence'),

  aiName: () => request<{ name: string; is_set: boolean }>('/ai/name'),

  setAiName: (data: { name: string; wallet: string; message: string; signature: string }) =>
    request<{ name: string; previous_name: string }>('/ai/name', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

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
  getTakeoverStatus: (orderId: string) => request<TakeoverStatus>(`/order/${orderId}/takeover_status`),
  getTakeoverReport: async (orderId: string) => {
    const res = await fetch(`${API_URL}/order/${orderId}/takeover_report`)
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.text()
  },

  transactions: (limit = 20) => request<{ transactions: Transaction[] }>(`/transactions?limit=${limit}`),

  vaultAssets: () => request<VaultAssetsResponse>('/vault/assets'),

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
    trust: (vaultAddress: string, chainId = 'base') =>
      request<{
        vault_address: string; chain_id: string; is_sovereign: boolean;
        trust_tier: number; trust_tier_name: string;
        autonomy_score: number; bytecode_verified: boolean;
        deployment_method: string; nonce_ratio: number;
        checks_passed: string[]; checks_failed: string[];
      }>(`/peer/trust/${vaultAddress}?chain_id=${chainId}`),
  },

  migration: {
    status: () => request<{ is_pending: boolean; pending_wallet?: string; completes_at?: number }>('/migration/status'),
  },

  evolution: {
    log: (limit = 20) => request<{ entries: EvolutionEntry[] }>(`/evolution/log?limit=${limit}`),
    status: () => request<EvolutionStatus>('/evolution/status'),
    replays: (limit = 20) => request<{ replays: ReplaySummary[] }>(`/evolution/replays?limit=${limit}`),
    replay: (id: string) => request<ReplayData>(`/evolution/replays/${encodeURIComponent(id)}`),
  },

  activity: (limit = 50, category?: ActivityCategory) => {
    const params = new URLSearchParams({ limit: String(limit) })
    if (category) params.set('category', category)
    return request<{ activities: ActivityEntry[] }>(`/activity?${params}`)
  },

  highlights: (limit = 20) =>
    request<{ highlights: Highlight[] }>(`/highlights?limit=${limit}`),

  purchases: {
    list: (limit = 20) =>
      request<{ purchases: PurchaseOrder[]; total: number; daily_purchase_usd: number; daily_purchase_limit: number }>(`/purchases?limit=${limit}`),
    pending: () =>
      request<{ pending: PurchaseOrder[]; count: number }>('/purchases/pending'),
    get: (orderId: string) => request<PurchaseOrder>(`/purchases/${encodeURIComponent(orderId)}`),
  },

  merchants: () =>
    request<{ merchants: MerchantInfo[]; purchasing_status: Record<string, unknown>; limits: PurchaseLimits }>('/merchants'),

  giveaway: {
    status: () => request<GiveawayStatus>('/giveaway'),
    history: (limit = 5) => request<{ draws: GiveawayDraw[] }>(`/giveaway/history?limit=${limit}`),
    claim: (orderIdPrefix: string) =>
      request<GiveawayClaimResult>('/giveaway/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id_prefix: orderIdPrefix }),
      }),
  },

  uiConfig: () => request<UIConfig>('/ui/config'),

  pages: {
    list: () => request<{ pages: PageSummary[] }>('/pages'),
    get: (slug: string) => request<PageData>(`/pages/${encodeURIComponent(slug)}`),
  },
}
