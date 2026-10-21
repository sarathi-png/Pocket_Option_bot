import type { Outcome, TelegramStatus } from "../types";

export function formatPrice(value: number | null, decimals: number): string {
  if (value === null || Number.isNaN(value)) return "—";
  return value.toFixed(decimals);
}

export function formatTime(iso: string, timeZone = "Asia/Kolkata"): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", {
    timeZone,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

export function outcomeLabel(outcome: Outcome): string {
  return { PENDING: "⏳ Pending", WIN: "✅ Win", LOSS: "❌ Loss", DRAW: "➖ Draw" }[outcome];
}

export function telegramLabel(status: TelegramStatus): string {
  return {
    NOT_SENT: "Not sent",
    SENT: "✈️ Sent",
    FAILED: "⚠️ Failed",
    DRY_RUN: "🧪 Dry-run",
  }[status];
}

/** Seconds from `now` until an ISO expiry timestamp (can be negative). */
export function secondsUntil(iso: string, now: Date): number {
  return Math.floor((new Date(iso).getTime() - now.getTime()) / 1000);
}

export function formatCountdown(totalSeconds: number): string {
  if (totalSeconds < 0) return "expired";
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

/** Extract a safe, actionable message from the backend error shape (PRD §4.6). */
export function apiErrorMessage(payload: unknown, fallback = "Request failed. Please retry."): string {
  if (payload && typeof payload === "object" && "error" in payload) {
    const err = (payload as { error?: { message?: string } }).error;
    if (err?.message) return err.message;
  }
  return fallback;
}
