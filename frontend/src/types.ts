export type Timeframe = "1m" | "5m" | "15m" | "1h";
export type Direction = "CALL" | "PUT";
export type Outcome = "PENDING" | "WIN" | "LOSS" | "DRAW";
export type TelegramStatus = "NOT_SENT" | "SENT" | "FAILED" | "DRY_RUN";

export interface PairInfo {
  symbol: string;
  display: string;
  category: string;
  decimals: number;
}

export interface Vote {
  indicator: string;
  direction: "CALL" | "PUT" | "NEUTRAL";
  weight: number;
  detail: string;
}

export interface Signal {
  id: string;
  pair: string;
  display_pair: string;
  direction: Direction;
  decision: "TRADE" | "NO_TRADE";
  timeframe: string;
  expiry_minutes: number;
  confidence: number;
  entry_price: number;
  exit_price: number | null;
  outcome: Outcome;
  data_source: string;
  indicators: Record<string, unknown>;
  votes: Vote[];
  reasoning: string[];
  source: string;
  telegram_status: TelegramStatus;
  created_at: string;
  expires_at: string;
  evaluated_at: string | null;
}

export interface PaginatedSignals {
  items: Signal[];
  total: number;
  page: number;
  page_size: number;
}

export interface Candle {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface CandlesResponse {
  pair: string;
  timeframe: string;
  data_source: string;
  candles: Candle[];
  ema9: (number | null)[];
  ema21: (number | null)[];
}

export interface Stats {
  total_signals: number;
  trade_signals: number;
  no_trade_signals: number;
  pending: number;
  wins: number;
  losses: number;
  draws: number;
  win_rate_pct: number | null;
  avg_confidence: number | null;
  telegram_sent: number;
  telegram_failed: number;
  telegram_dry_run: number;
  by_pair: { pair: string; signals: number; avg_confidence: number | null }[];
}

export interface TelegramStatusInfo {
  configured: boolean;
  bot_token_masked: string;
  chat_id_masked: string;
  deliveries_sent: number;
}

export interface Delivery {
  id: string;
  signal_id: string | null;
  kind: string;
  status: "SENT" | "FAILED" | "DRY_RUN";
  provider_message_id: string | null;
  error_code: string | null;
  attempt_count: number;
  message_preview: string;
  created_at: string | null;
  note: string | null;
}

export interface AppSettings {
  auto_enabled: boolean;
  auto_push_telegram: boolean;
  min_confidence: number;
  watchlist: string[];
  auto_interval_seconds: number;
  default_timeframe: string;
  default_expiry_minutes: number;
  telegram: TelegramStatusInfo;
}

export interface Health {
  status: string;
  telegram_configured: boolean;
  auto_enabled: boolean;
  scheduler_running: boolean;
  market_data: string;
  disclaimer: string;
}

export interface AutoStatus {
  scheduler_running: boolean;
  auto_enabled: boolean;
  auto_push_telegram: boolean;
  cycles_completed: number;
  last_run: string;
}
