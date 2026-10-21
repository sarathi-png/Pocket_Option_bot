import type { Signal } from "../types";
import { formatCountdown, formatPrice, formatTime, outcomeLabel, secondsUntil, telegramLabel } from "../lib/format";

interface Props {
  signal: Signal;
  decimals: number;
  now: Date;
  pushing: boolean;
  onPush: (signal: Signal, force: boolean) => void;
}

export function SignalCard({ signal, decimals, now, pushing, onPush }: Props) {
  const isCall = signal.direction === "CALL";
  const remaining = secondsUntil(signal.expires_at, now);
  const sent = signal.telegram_status === "SENT";
  return (
    <article className={`signal-card ${isCall ? "call" : "put"}`} aria-live="polite">
      <div className="signal-head">
        <div>
          <div className="signal-pair">{signal.display_pair}</div>
          <div className="signal-meta">
            {signal.timeframe} chart · {signal.expiry_minutes}m expiry · {formatTime(signal.created_at)} IST
          </div>
        </div>
        <div className={`direction ${isCall ? "up" : "down"}`} aria-label={`Direction ${signal.direction}`}>
          {isCall ? "🟢 CALL ▲" : "🔴 PUT ▼"}
        </div>
      </div>

      {signal.decision === "NO_TRADE" && (
        <p className="no-trade" role="note">
          ⚠️ <strong>NO-TRADE:</strong> indicators disagree or confidence is below your threshold.
          The safer action is to skip this one. It will not be auto-pushed.
        </p>
      )}

      <div className="confidence-row">
        <span>Confidence <strong>{signal.confidence}%</strong></span>
        <div className="confidence-bar" role="progressbar" aria-valuenow={signal.confidence} aria-valuemin={0} aria-valuemax={100}>
          <div style={{ width: `${signal.confidence}%` }} />
        </div>
        <span className="countdown" title="Time until this signal expires">
          ⏱ {signal.outcome === "PENDING" ? formatCountdown(remaining) : outcomeLabel(signal.outcome)}
        </span>
      </div>

      <dl className="signal-facts">
        <div><dt>Entry</dt><dd>{formatPrice(signal.entry_price, decimals)}</dd></div>
        <div><dt>Exit</dt><dd>{formatPrice(signal.exit_price, decimals)}</dd></div>
        <div><dt>Outcome</dt><dd>{outcomeLabel(signal.outcome)}</dd></div>
        <div><dt>Telegram</dt><dd>{telegramLabel(signal.telegram_status)}</dd></div>
        <div><dt>Source</dt><dd>{signal.source} · {signal.data_source} data</dd></div>
      </dl>

      <h3>Why this signal?</h3>
      <ul className="votes">
        {signal.votes.map((v) => (
          <li key={v.indicator} className={`vote vote-${v.direction.toLowerCase()}`}>
            <span aria-hidden="true">{v.direction === "CALL" ? "▲" : v.direction === "PUT" ? "▼" : "•"}</span>{" "}
            <strong>{v.indicator}</strong> — {v.detail} <span className="weight">(w {v.weight})</span>
          </li>
        ))}
      </ul>

      <div className="signal-actions">
        <button type="button" className="btn primary" disabled={pushing} onClick={() => onPush(signal, false)}>
          {pushing ? "Pushing…" : sent ? "✈️ Already sent — push again?" : "✈️ Push to Telegram"}
        </button>
        {sent && (
          <span className="hint">Re-pushing the same signal is blocked to prevent spam; clicking again returns the original delivery.</span>
        )}
      </div>
      <p className="micro-disclaimer">
        Educational signal only — not financial advice. Verify the setup on your chart before risking money.
      </p>
    </article>
  );
}
