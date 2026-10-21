import type {
  AppSettings,
  AutoStatus,
  CandlesResponse,
  Delivery,
  Health,
  PaginatedSignals,
  PairInfo,
  Signal,
  Stats,
  TelegramStatusInfo,
  Timeframe,
} from "../types";
import { apiErrorMessage } from "./format";

const API_KEY_STORAGE = "po_signal_bot_api_key";

export function getStoredApiKey(): string {
  try {
    return localStorage.getItem(API_KEY_STORAGE) ?? "";
  } catch {
    return "";
  }
}

export function storeApiKey(key: string): void {
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE, key);
    else localStorage.removeItem(API_KEY_STORAGE);
  } catch {
    /* storage unavailable — key simply won't persist */
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  const apiKey = getStoredApiKey();
  if (apiKey) headers["X-API-Key"] = apiKey;
  let resp: Response;
  try {
    resp = await fetch(path, { ...init, headers: { ...headers, ...(init?.headers ?? {}) } });
  } catch {
    throw new Error("Cannot reach the server. Is the backend running?");
  }
  const payload: unknown = await resp.json().catch(() => null);
  if (!resp.ok) throw new Error(apiErrorMessage(payload, `Request failed (${resp.status}).`));
  return payload as T;
}

export const api = {
  health: () => request<Health>("/api/v1/health"),
  pairs: () => request<PairInfo[]>("/api/v1/pairs"),
  candles: (pair: string, timeframe: Timeframe, limit = 80) =>
    request<CandlesResponse>(`/api/v1/candles?pair=${encodeURIComponent(pair)}&timeframe=${timeframe}&limit=${limit}`),
  generate: (pair: string, timeframe: Timeframe, expiryMinutes: number, pushTelegram: boolean) =>
    request<Signal>("/api/v1/signals/generate", {
      method: "POST",
      body: JSON.stringify({ pair, timeframe, expiry_minutes: expiryMinutes, push_telegram: pushTelegram }),
    }),
  signals: (page = 1, pageSize = 20, pair?: string) => {
    const q = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
    if (pair) q.set("pair", pair);
    return request<PaginatedSignals>(`/api/v1/signals?${q.toString()}`);
  },
  pushTelegram: (signalId: string, force = false) =>
    request<{ delivery: Delivery; signal: Signal }>(`/api/v1/signals/${signalId}/push-telegram`, {
      method: "POST",
      body: JSON.stringify({ force }),
    }),
  evaluate: (signalId: string) =>
    request<Signal>(`/api/v1/signals/${signalId}/evaluate`, { method: "POST" }),
  stats: () => request<Stats>("/api/v1/stats"),
  settings: () => request<AppSettings>("/api/v1/settings"),
  updateSettings: (patch: Partial<AppSettings>) =>
    request<AppSettings>("/api/v1/settings", { method: "PUT", body: JSON.stringify(patch) }),
  updateTelegram: (botToken: string, chatId: string) =>
    request<TelegramStatusInfo>("/api/v1/telegram/settings", {
      method: "PUT",
      body: JSON.stringify({ bot_token: botToken, chat_id: chatId }),
    }),
  testTelegram: () => request<{ delivery: Delivery }>("/api/v1/telegram/test", { method: "POST" }),
  autoStatus: () => request<AutoStatus>("/api/v1/auto/status"),
  autoRunOnce: () => request<{ summary: string; cycles: number }>("/api/v1/auto/run-once", { method: "POST" }),
};
