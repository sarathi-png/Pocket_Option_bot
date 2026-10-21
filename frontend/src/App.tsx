import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AppSettings, AutoStatus, CandlesResponse, PairInfo, Signal, Stats, Timeframe } from "./types";
import { api } from "./lib/api";
import { CandleChart } from "./components/CandleChart";
import { SignalCard } from "./components/SignalCard";
import { AutoPanel, HistoryTable, TelegramPanel } from "./components/panels";

const TIMEFRAMES: Timeframe[] = ["1m", "5m", "15m", "1h"];
const EXPIRIES = [1, 2, 3, 5, 10, 15, 30];
const PAGE_SIZE = 15;

interface Toast {
  kind: "ok" | "err" | "info";
  text: string;
}

export default function App() {
  const [healthOk, setHealthOk] = useState<boolean | null>(null);
  const [pairs, setPairs] = useState<PairInfo[]>([]);
  const [pair, setPair] = useState("EURUSD");
  const [timeframe, setTimeframe] = useState<Timeframe>("1m");
  const [expiry, setExpiry] = useState(2);
  const [candles, setCandles] = useState<CandlesResponse | null>(null);
  const [latest, setLatest] = useState<Signal | null>(null);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [stats, setStats] = useState<Stats | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [autoStatus, setAutoStatus] = useState<AutoStatus | null>(null);
  const [generating, setGenerating] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [panelBusy, setPanelBusy] = useState(false);
  const [toast, setToast] = useState<Toast | null>(null);
  const [now, setNow] = useState(new Date());
  const toastTimer = useRef<number | undefined>(undefined);

  const showToast = useCallback((kind: Toast["kind"], text: string) => {
    setToast({ kind, text });
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 6000);
  }, []);

  const decimalsFor = useCallback(
    (symbol: string) => pairs.find((p) => p.symbol === symbol)?.decimals ?? 5,
    [pairs],
  );

  const refreshLists = useCallback(
    async (pageToLoad: number) => {
      try {
        const [list, st, auto] = await Promise.all([
          api.signals(pageToLoad, PAGE_SIZE),
          api.stats(),
          api.autoStatus(),
        ]);
        setSignals(list.items);
        setTotal(list.total);
        setStats(st);
        setAutoStatus(auto);
        setHealthOk(true);
      } catch (e) {
        setHealthOk(false);
        throw e;
      }
    },
    [],
  );

  const loadCandles = useCallback(async (p: string, tf: Timeframe) => {
    try {
      setCandles(await api.candles(p, tf, 90));
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Failed to load candles.");
    }
  }, [showToast]);

  // Initial load
  useEffect(() => {
    (async () => {
      try {
        const [ps, cfg] = await Promise.all([api.pairs(), api.settings()]);
        setPairs(ps);
        setSettings(cfg);
        setTimeframe((cfg.default_timeframe as Timeframe) || "1m");
        setExpiry(cfg.default_expiry_minutes || 2);
        await refreshLists(1);
      } catch (e) {
        setHealthOk(false);
        showToast("err", e instanceof Error ? e.message : "Failed to connect to backend.");
      }
    })();
  }, [refreshLists, showToast]);

  useEffect(() => {
    void loadCandles(pair, timeframe);
  }, [pair, timeframe, loadCandles]);

  // Poll for auto-generated signals / settlements; tick countdown clock
  useEffect(() => {
    const poll = window.setInterval(() => void refreshLists(page).catch(() => undefined), 12000);
    const tick = window.setInterval(() => setNow(new Date()), 1000);
    return () => {
      window.clearInterval(poll);
      window.clearInterval(tick);
    };
  }, [page, refreshLists]);

  const groupedPairs = useMemo(() => {
    const groups = new Map<string, PairInfo[]>();
    for (const p of pairs) groups.set(p.category, [...(groups.get(p.category) ?? []), p]);
    return [...groups.entries()];
  }, [pairs]);

  async function handleGenerate(pushTelegram: boolean) {
    setGenerating(true);
    try {
      const signal = await api.generate(pair, timeframe, expiry, pushTelegram);
      setLatest(signal);
      setPage(1);
      await refreshLists(1);
      if (signal.decision === "NO_TRADE") {
        showToast("info", `${signal.display_pair}: NO-TRADE (${signal.confidence}% confidence) — indicators disagree, safest to skip.`);
      } else if (pushTelegram) {
        showToast(
          signal.telegram_status === "SENT" ? "ok" : "info",
          signal.telegram_status === "SENT"
            ? `Signal generated and sent to Telegram: ${signal.display_pair} ${signal.direction} (${signal.confidence}%).`
            : `Signal generated (${signal.direction}, ${signal.confidence}%). Telegram is in dry-run — configure your bot below to receive it for real.`,
        );
      } else {
        showToast("ok", `Signal generated: ${signal.display_pair} ${signal.direction} at ${signal.confidence}% confidence.`);
      }
      void loadCandles(pair, timeframe);
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Signal generation failed.");
    } finally {
      setGenerating(false);
    }
  }

  async function handlePush(signal: Signal, _force: boolean) {
    setBusyId(signal.id);
    try {
      const { delivery, signal: updated } = await api.pushTelegram(signal.id, false);
      if (latest?.id === updated.id) setLatest(updated);
      await refreshLists(page);
      if (delivery.status === "SENT") showToast("ok", "✈️ Signal sent to Telegram.");
      else if (delivery.status === "DRY_RUN") showToast("info", delivery.note ?? "Dry run — configure Telegram first.");
      else showToast("err", `Telegram send failed (${delivery.error_code ?? "unknown error"}). Check your token/chat id and retry.`);
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Telegram push failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleEvaluate(signal: Signal) {
    setBusyId(signal.id);
    try {
      const updated = await api.evaluate(signal.id);
      if (latest?.id === updated.id) setLatest(updated);
      await refreshLists(page);
      showToast(
        "info",
        updated.outcome === "PENDING"
          ? "Not expired yet — this signal is still pending."
          : `${updated.display_pair} settled: ${updated.outcome}.`,
      );
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Evaluation failed.");
    } finally {
      setBusyId(null);
    }
  }

  async function handleSaveTelegram(token: string, chatId: string) {
    setPanelBusy(true);
    try {
      await api.updateTelegram(token, chatId);
      setSettings(await api.settings());
      showToast("ok", "Telegram settings saved. Now send a test message to confirm delivery.");
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Could not save Telegram settings.");
    } finally {
      setPanelBusy(false);
    }
  }

  async function handleTestTelegram() {
    setPanelBusy(true);
    try {
      const { delivery } = await api.testTelegram();
      if (delivery.status === "SENT") showToast("ok", "✅ Test message sent — check your Telegram!");
      else if (delivery.status === "DRY_RUN") showToast("info", delivery.note ?? "Dry run — add token + chat id first.");
      else showToast("err", `Test failed (${delivery.error_code ?? "unknown"}). Common causes: wrong token, wrong chat id, or you never messaged the bot first.`);
      await refreshLists(page).catch(() => undefined);
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Test message failed.");
    } finally {
      setPanelBusy(false);
    }
  }

  async function handleUpdateSettings(patch: Partial<AppSettings>) {
    setPanelBusy(true);
    try {
      setSettings(await api.updateSettings(patch));
      setAutoStatus(await api.autoStatus());
      showToast("ok", "Settings saved.");
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Could not save settings.");
    } finally {
      setPanelBusy(false);
    }
  }

  async function handleRunOnce() {
    setPanelBusy(true);
    try {
      const { summary } = await api.autoRunOnce();
      setPage(1);
      await refreshLists(1);
      showToast("ok", `Auto cycle done — ${summary}. New signals are in the history below.`);
    } catch (e) {
      showToast("err", e instanceof Error ? e.message : "Auto cycle failed.");
    } finally {
      setPanelBusy(false);
    }
  }

  const telegramConfigured = settings?.telegram.configured ?? false;

  return (
    <div className="app">
      <header className="topbar">
        <div>
          <h1>📡 Pocket Option Signal Bot</h1>
          <p className="subtitle">Indicator-based signals → pushed to your Telegram bot</p>
        </div>
        <div className="badges">
          <span className={`badge ${healthOk === false ? "bad" : "good"}`} role="status">
            {healthOk === null ? "Connecting…" : healthOk ? "● API online" : "● API offline"}
          </span>
          <span className={`badge ${telegramConfigured ? "good" : "warn"}`} role="status">
            {telegramConfigured ? "✈️ Telegram connected" : "✈️ Telegram: dry-run (not configured)"}
          </span>
          <span className="badge" role="status">
            🤖 Auto: {settings?.auto_enabled ? "ON" : "OFF"}
          </span>
        </div>
      </header>

      <div className="risk-banner" role="note">
        ⚠️ <strong>Risk notice:</strong> Binary options are high-risk — you can lose your entire stake on a trade, and most
        retail traders lose money. These signals are <strong>educational only, not financial advice</strong>, and no signal
        can guarantee wins. This tool is not affiliated with Pocket Option. Check that online Forex/binary-options trading
        is permitted in your country (in India, RBI/SEBI rules restrict it) and never trade money you cannot afford to lose.
      </div>

      {toast && (
        <div className={`toast toast-${toast.kind}`} role="alert">
          {toast.text}
          <button type="button" className="toast-close" aria-label="Dismiss" onClick={() => setToast(null)}>×</button>
        </div>
      )}

      <section className="stats-grid" aria-label="Performance statistics">
        <div className="stat"><span>Total signals</span><strong>{stats?.total_signals ?? "—"}</strong></div>
        <div className="stat"><span>Win rate (settled)</span><strong>{stats?.win_rate_pct !== null && stats?.win_rate_pct !== undefined ? `${stats.win_rate_pct}%` : "—"}</strong></div>
        <div className="stat"><span>Wins / Losses</span><strong>{stats ? `${stats.wins} / ${stats.losses}` : "—"}</strong></div>
        <div className="stat"><span>Pending</span><strong>{stats?.pending ?? "—"}</strong></div>
        <div className="stat"><span>Avg confidence</span><strong>{stats?.avg_confidence !== null && stats?.avg_confidence !== undefined ? `${stats.avg_confidence}%` : "—"}</strong></div>
        <div className="stat"><span>Telegram sent</span><strong>{stats?.telegram_sent ?? "—"}</strong></div>
      </section>

      <main className="layout">
        <section className="panel wide" aria-labelledby="gen-title">
          <h2 id="gen-title">🎯 Generate a signal</h2>
          <div className="controls">
            <div className="field">
              <label htmlFor="pair">Pair / Asset</label>
              <select id="pair" value={pair} onChange={(e) => setPair(e.target.value)}>
                {groupedPairs.map(([category, items]) => (
                  <optgroup key={category} label={category}>
                    {items.map((p) => (
                      <option key={p.symbol} value={p.symbol}>{p.display}</option>
                    ))}
                  </optgroup>
                ))}
              </select>
            </div>
            <div className="field">
              <label htmlFor="timeframe">Chart timeframe</label>
              <select id="timeframe" value={timeframe} onChange={(e) => setTimeframe(e.target.value as Timeframe)}>
                {TIMEFRAMES.map((tf) => <option key={tf} value={tf}>{tf}</option>)}
              </select>
            </div>
            <div className="field">
              <label htmlFor="expiry">Trade expiry</label>
              <select id="expiry" value={expiry} onChange={(e) => setExpiry(Number(e.target.value))}>
                {EXPIRIES.map((m) => <option key={m} value={m}>{m} minute{m > 1 ? "s" : ""}</option>)}
              </select>
            </div>
          </div>

          {candles ? (
            <CandleChart
              candles={candles.candles}
              ema9={candles.ema9}
              ema21={candles.ema21}
              decimals={decimalsFor(pair)}
              dataSource={candles.data_source}
            />
          ) : (
            <p className="empty" role="status">Loading chart…</p>
          )}

          <div className="row actions-main">
            <button type="button" className="btn primary big" disabled={generating} onClick={() => void handleGenerate(false)}>
              {generating ? "Analysing…" : "📊 Generate signal"}
            </button>
            <button type="button" className="btn telegram big" disabled={generating} onClick={() => void handleGenerate(true)}>
              {generating ? "Analysing…" : "✈️ Generate & push to Telegram"}
            </button>
          </div>
          <p className="hint">
            Engine: EMA 9/21 trend + RSI 14 + MACD + Bollinger + Stochastic + momentum voting.
            Weak/disagreeing setups are labelled NO-TRADE instead of being presented as tradeable.
          </p>

          {latest && (
            <SignalCard
              signal={latest}
              decimals={decimalsFor(latest.pair)}
              now={now}
              pushing={busyId === latest.id}
              onPush={(s, f) => void handlePush(s, f)}
            />
          )}
        </section>

        <HistoryTable
          signals={signals}
          total={total}
          page={page}
          pageSize={PAGE_SIZE}
          decimalsFor={decimalsFor}
          busyId={busyId}
          onPage={(p) => {
            setPage(p);
            void refreshLists(p).catch(() => undefined);
          }}
          onPush={(s, f) => void handlePush(s, f)}
          onEvaluate={(s) => void handleEvaluate(s)}
          onSelect={(s) => setLatest(s)}
        />

        <TelegramPanel
          settings={settings}
          busy={panelBusy}
          onSaveTelegram={(t, c) => void handleSaveTelegram(t, c)}
          onTestTelegram={() => void handleTestTelegram()}
        />

        <AutoPanel
          settings={settings}
          autoStatus={autoStatus}
          pairs={pairs}
          busy={panelBusy}
          onUpdateSettings={(patch) => void handleUpdateSettings(patch)}
          onRunOnce={() => void handleRunOnce()}
        />
      </main>

      <footer className="footer">
        <p>
          Pocket Option Signal Bot · Signals are computed from technical indicators on{" "}
          {candles?.data_source === "twelvedata" ? "live Twelve Data candles" : "simulated demo candles (Pocket Option has no official API)"} ·
          Always confirm with your own chart analysis and risk management. Not financial advice.
        </p>
      </footer>
    </div>
  );
}
