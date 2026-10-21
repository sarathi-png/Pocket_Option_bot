import type { Candle } from "../types";
import { formatPrice } from "../lib/format";

interface Props {
  candles: Candle[];
  ema9: (number | null)[];
  ema21: (number | null)[];
  decimals: number;
  dataSource: string;
}

const W = 860;
const H = 300;
const PAD = { top: 12, right: 64, bottom: 18, left: 8 };

export function CandleChart({ candles, ema9, ema21, decimals, dataSource }: Props) {
  if (candles.length === 0) {
    return <div className="chart-empty" role="status">No candle data yet — pick a pair to load the chart.</div>;
  }
  const values = candles.flatMap((c) => [c.high, c.low]);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const plotW = W - PAD.left - PAD.right;
  const plotH = H - PAD.top - PAD.bottom;
  const x = (i: number) => PAD.left + (i / Math.max(1, candles.length - 1)) * plotW;
  const y = (v: number) => PAD.top + ((max - v) / range) * plotH;
  const candleW = Math.max(2, plotW / candles.length - 2);
  const line = (series: (number | null)[]) =>
    series.map((v, i) => (v === null ? null : `${x(i)},${y(v)}`)).filter(Boolean).join(" ");
  const last = candles[candles.length - 1];

  return (
    <figure className="chart" aria-label={`Candlestick chart, last price ${formatPrice(last.close, decimals)}`}>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" preserveAspectRatio="none" className="chart-svg">
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={PAD.left} x2={W - PAD.right} y1={PAD.top + plotH * f} y2={PAD.top + plotH * f} className="grid-line" />
        ))}
        {candles.map((c, i) => {
          const up = c.close >= c.open;
          return (
            <g key={c.timestamp + i} className={up ? "candle-up" : "candle-down"}>
              <line x1={x(i)} x2={x(i)} y1={y(c.high)} y2={y(c.low)} className="wick" />
              <rect
                x={x(i) - candleW / 2}
                width={candleW}
                y={y(Math.max(c.open, c.close))}
                height={Math.max(1.5, Math.abs(y(c.open) - y(c.close)))}
              />
            </g>
          );
        })}
        <polyline points={line(ema9)} className="ema9" fill="none" />
        <polyline points={line(ema21)} className="ema21" fill="none" />
        <text x={W - PAD.right + 6} y={y(max)} className="axis-label">{formatPrice(max, decimals)}</text>
        <text x={W - PAD.right + 6} y={y(min)} className="axis-label">{formatPrice(min, decimals)}</text>
        <text x={W - PAD.right + 6} y={y(last.close)} className="axis-label last">{formatPrice(last.close, decimals)}</text>
      </svg>
      <figcaption className="chart-caption">
        <span><span className="dot dot-ema9" /> EMA 9</span>
        <span><span className="dot dot-ema21" /> EMA 21</span>
        <span>Data: {dataSource === "simulated" ? "simulated candles (demo) — set TWELVE_DATA_API_KEY for live data" : "live (Twelve Data)"}</span>
      </figcaption>
    </figure>
  );
}
