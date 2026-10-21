import { useState } from "react";
import type { AppSettings, AutoStatus, PairInfo, Signal } from "../types";
import { formatPrice, formatTime, outcomeLabel, telegramLabel } from "../lib/format";
import { getStoredApiKey, storeApiKey } from "../lib/api";

/* ------------------------------------------------------------------ */
/* Telegram setup panel                                                */
/* ------------------------------------------------------------------ */
interface TelegramProps {
  settings: AppSettings | null;
  busy: boolean;
  onSaveTelegram: (token: string, chatId: string) => void;
  onTestTelegram: () => void;
}

export function TelegramPanel({ settings, busy, onSaveTelegram, onTestTelegram }: TelegramProps) {
  const [token, setToken] = useState("");
  const [chatId, setChatId] = useState("");
  const [apiKey, setApiKey] = useState(getStoredApiKey());
  const tg = settings?.telegram;

  return (
    <section className="panel" aria-labelledby="telegram-title">
      <h2 id="telegram-title">✈️ Telegram delivery</h2>
      <p className={`status-line ${tg?.configured ? "ok" : "warn"}`} role="status">
        {tg?.configured
          ? `Connected — token ${tg.bot_token_masked}, chat ${tg.chat_id_masked} · ${tg.deliveries_sent} message(s) sent so far.`
          : "Not configured yet — pushes run in dry-run mode (recorded, not sent) until you add your bot token + chat id below."}
      </p>

      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault();
          onSaveTelegram(token.trim(), chatId.trim());
          setToken("");
        }}
      >
        <label htmlFor="bot-token">Bot token (from @BotFather)</label>
        <input
          id="bot-token"
          type="password"
          autoComplete="off"
          placeholder={tg?.bot_token_masked ? `Current: ${tg.bot_token_masked} — leave blank to keep` : "123456789:AA…"}
          value={token}
          onChange={(e) => setToken(e.target.value)}
        />
        <label htmlFor="chat-id">Chat ID (your user id, group id, or @channel)</label>
        <input
          id="chat-id"
          type="text"
          autoComplete="off"
          placeholder={tg?.chat_id_masked ? `Current: ${tg.chat_id_masked} — leave blank to keep` : "e.g. 123456789 or -1001234567890"}
          value={chatId}
          onChange={(e) => setChatId(e.target.value)}
        />
        <div className="row">
          <button type="submit" className="btn primary" disabled={busy || (!token.trim() && !chatId.trim())}>
            Save Telegram settings
          </button>
          <button type="button" className="btn" disabled={busy} onClick={onTestTelegram}>
            Send test message
          </button>
        </div>
        <p className="hint">The token is stored only on the server and shown masked. Never share it publicly.</p>
      </form>

      <details className="howto">
        <summary>How to create your Telegram bot (2 minutes)</summary>
        <ol>
          <li>Open Telegram and talk to <strong>@BotFather</strong> → send <code>/newbot</code> → choose a name/username → copy the <strong>token</strong>.</li>
          <li>Open your new bot and send it any message (e.g. “hi”) — a bot cannot message you first.</li>
          <li>
            Find your chat id: talk to <strong>@userinfobot</strong> (it replies with your id), or open{" "}
            <code>https://api.telegram.org/bot&lt;TOKEN&gt;/getUpdates</code> and read <code>chat.id</code>.
          </li>
          <li>Paste token + chat id above → <strong>Save</strong> → <strong>Send test message</strong>.</li>
          <li>For a channel/group: add the bot as admin, post once, then use the channel username (<code>@mychannel</code>) or the <code>-100…</code> id from getUpdates.</li>
        </ol>
      </details>

      <details className="howto">
        <summary>Server API key (only if your backend sets API_KEY)</summary>
        <div className="stack">
          <label htmlFor="api-key">X-API-Key sent with generate/push requests (stored in this browser only)</label>
          <input
            id="api-key"
            type="password"
            value={apiKey}
            onChange={(e) => {
              setApiKey(e.target.value);
              storeApiKey(e.target.value.trim());
            }}
            placeholder="Leave empty for local development"
          />
        </div>
      </details>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Automation panel                                                    */
/* ------------------------------------------------------------------ */
interface AutoProps {
  settings: AppSettings | null;
  autoStatus: AutoStatus | null;
  pairs: PairInfo[];
  busy: boolean;
  onUpdateSettings: (patch: Partial<AppSettings>) => void;
  onRunOnce: () => void;
}

export function AutoPanel({ settings, autoStatus, pairs, busy, onUpdateSettings, onRunOnce }: AutoProps) {
  if (!settings) return <section className="panel"><h2>🤖 Auto signals</h2><p>Loading settings…</p></section>;
  const toggleWatch = (symbol: string, on: boolean) => {
    const next = on ? [...settings.watchlist, symbol] : settings.watchlist.filter((p) => p !== symbol);
    if (next.length >= 1) onUpdateSettings({ watchlist: next });
  };
  return (
    <section className="panel" aria-labelledby="auto-title">
      <h2 id="auto-title">🤖 Auto signals</h2>
      <p className="status-line" role="status">
        Scheduler {autoStatus?.scheduler_running ? "running" : "stopped"} · {autoStatus?.cycles_completed ?? 0} cycle(s) · last: {autoStatus?.last_run ?? "—"}
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={settings.auto_enabled}
          disabled={busy}
          onChange={(e) => onUpdateSettings({ auto_enabled: e.target.checked })}
        />
        Enable automatic generation every {settings.auto_interval_seconds}s
      </label>
      <label className="check">
        <input
          type="checkbox"
          checked={settings.auto_push_telegram}
          disabled={busy}
          onChange={(e) => onUpdateSettings({ auto_push_telegram: e.target.checked })}
        />
        Auto-push TRADE signals to Telegram
      </label>

      <label htmlFor="min-confidence">
        Minimum confidence to trade: <strong>{settings.min_confidence}%</strong>
      </label>
      <input
        id="min-confidence"
        type="range"
        min={50}
        max={95}
        step={1}
        value={settings.min_confidence}
        disabled={busy}
        onChange={(e) => onUpdateSettings({ min_confidence: Number(e.target.value) })}
      />
      <p className="hint">Signals below this (or with &lt;60% indicator agreement) are marked NO-TRADE and never auto-pushed.</p>

      <label htmlFor="interval">Interval (seconds)</label>
      <input
        id="interval"
        type="number"
        min={30}
        max={3600}
        step={30}
        defaultValue={settings.auto_interval_seconds}
        disabled={busy}
        onBlur={(e) => onUpdateSettings({ auto_interval_seconds: Number(e.target.value) })}
      />

      <fieldset className="watchlist">
        <legend>Watchlist pairs</legend>
        {pairs.map((p) => (
          <label key={p.symbol} className="check small">
            <input
              type="checkbox"
              checked={settings.watchlist.includes(p.symbol)}
              disabled={busy}
              onChange={(e) => toggleWatch(p.symbol, e.target.checked)}
            />
            {p.display}
          </label>
        ))}
      </fieldset>

      <button type="button" className="btn" disabled={busy} onClick={onRunOnce}>
        ▶ Run one auto cycle now
      </button>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* History table                                                       */
/* ------------------------------------------------------------------ */
interface HistoryProps {
  signals: Signal[];
  total: number;
  page: number;
  pageSize: number;
  decimalsFor: (pair: string) => number;
  busyId: string | null;
  onPage: (page: number) => void;
  onPush: (signal: Signal, force: boolean) => void;
  onEvaluate: (signal: Signal) => void;
  onSelect: (signal: Signal) => void;
}

export function HistoryTable({ signals, total, page, pageSize, decimalsFor, busyId, onPage, onPush, onEvaluate, onSelect }: HistoryProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize));
  if (signals.length === 0) {
    return (
      <section className="panel wide" aria-labelledby="history-title">
        <h2 id="history-title">🕘 Signal history</h2>
        <p className="empty" role="status">No signals yet. Generate your first signal above — it will appear here with its outcome after expiry.</p>
      </section>
    );
  }
  return (
    <section className="panel wide" aria-labelledby="history-title">
      <h2 id="history-title">🕘 Signal history <span className="hint">({total} total)</span></h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Time (IST)</th><th>Pair</th><th>Dir</th><th>TF / Expiry</th>
              <th>Entry → Exit</th><th>Conf.</th><th>Decision</th><th>Outcome</th><th>Telegram</th><th>Actions</th>
            </tr>
          </thead>
          <tbody>
            {signals.map((s) => (
              <tr key={s.id} onClick={() => onSelect(s)} className="clickable" title="Click to view details">
                <td>{formatTime(s.created_at)}</td>
                <td>{s.display_pair}<span className="hint"> {s.source === "auto" ? "(auto)" : ""}</span></td>
                <td className={s.direction === "CALL" ? "up-text" : "down-text"}>
                  {s.direction === "CALL" ? "▲ CALL" : "▼ PUT"}
                </td>
                <td>{s.timeframe} / {s.expiry_minutes}m</td>
                <td>{formatPrice(s.entry_price, decimalsFor(s.pair))} → {formatPrice(s.exit_price, decimalsFor(s.pair))}</td>
                <td>{s.confidence}%</td>
                <td>{s.decision}</td>
                <td>{outcomeLabel(s.outcome)}</td>
                <td>{telegramLabel(s.telegram_status)}</td>
                <td className="actions" onClick={(e) => e.stopPropagation()}>
                  <button type="button" className="btn tiny" disabled={busyId === s.id} onClick={() => onPush(s, false)}>
                    Push
                  </button>
                  {s.outcome === "PENDING" && (
                    <button type="button" className="btn tiny" disabled={busyId === s.id} onClick={() => onEvaluate(s)}>
                      Settle
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="row pager">
        <button type="button" className="btn" disabled={page <= 1} onClick={() => onPage(page - 1)}>← Prev</button>
        <span>Page {page} of {pages}</span>
        <button type="button" className="btn" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next →</button>
      </div>
    </section>
  );
}
