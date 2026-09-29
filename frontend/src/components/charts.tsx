import { useEffect, useRef, useState, type ReactNode } from "react";
import { useI18n } from "../i18n";

/** Charts of the statistics page: plain SVG, one hue (--chart-1), hairline grid, a tooltip on hover and keyboard
 * focus, and a table with the same numbers (the tooltip never is the only way to read a value). */

export interface Column {
  key: string;
  /** Under the axis (only some are shown when there are many). */
  label: string;
  value: number;
  /** Tooltip: the value line first, then details. */
  title: string;
  details: string[];
}

const HEIGHT = 180;
const AXIS_W = 44;
const AXIS_H = 22;
const TOP = 8;
const MAX_BAR = 24;
const GAP = 2;
const RADIUS = 4;

function niceMax(max: number): number {
  if (max <= 0) return 1;
  const exp = 10 ** Math.floor(Math.log10(max));
  const step = [1, 2, 2.5, 5, 10].find((m) => m * exp >= max) ?? 10;
  return step * exp;
}

function useWidth<T extends HTMLElement>(fallback: number): [React.RefObject<T | null>, number] {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (el.clientWidth) setWidth(el.clientWidth);
    if (typeof ResizeObserver === "undefined") return;
    const ro = new ResizeObserver(([entry]) => {
      if (entry && entry.contentRect.width) setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  return [ref, width];
}

/** A bar with a 4px rounded data end, square at the baseline. */
function barPath(x: number, y: number, w: number, h: number): string {
  const r = Math.min(RADIUS, w / 2, h);
  return `M${x},${y + h}V${y + r}Q${x},${y} ${x + r},${y}H${x + w - r}Q${x + w},${y} ${x + w},${y + r}V${y + h}Z`;
}

export function ColumnChart({ columns, label, format }: { columns: Column[]; label: string; format: (n: number) => string }) {
  const { t } = useI18n();
  const [ref, width] = useWidth<HTMLDivElement>(640);
  const [active, setActive] = useState<number | null>(null);
  const [asTable, setAsTable] = useState(false);

  const max = niceMax(Math.max(0, ...columns.map((c) => c.value)));
  const plotW = Math.max(40, width - AXIS_W);
  const plotH = HEIGHT - AXIS_H - TOP;
  const slot = columns.length ? plotW / columns.length : plotW;
  const barW = Math.max(2, Math.min(MAX_BAR, slot - GAP));
  const every = Math.max(1, Math.ceil(columns.length / Math.max(1, Math.floor(plotW / 64))));
  const ticks = [0, max / 2, max];
  const y = (v: number) => TOP + plotH - (v / max) * plotH;
  const current = active !== null ? columns[active] : undefined;

  return (
    <div className="chart">
      <div className="chart-tools">
        <button type="button" className="btn btn-ghost btn-sm" aria-pressed={asTable} onClick={() => setAsTable((v) => !v)}>
          {asTable ? t("stats.showChart") : t("stats.showTable")}
        </button>
      </div>
      {asTable ? (
        <table className="chart-table">
          <caption className="sr-only">{label}</caption>
          <tbody>
            {columns.map((c) => (
              <tr key={c.key}>
                <th scope="row">{c.label}</th>
                <td>{c.title}</td>
                <td>{c.details.join(" · ")}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : (
        <div className="chart-plot" ref={ref}>
          <svg width={width} height={HEIGHT} role="img" aria-label={label}>
            {ticks.map((v) => (
              <g key={v}>
                <line className="chart-grid" x1={AXIS_W} x2={width} y1={y(v)} y2={y(v)} />
                <text className="chart-axis" x={AXIS_W - 8} y={y(v)} dy="0.32em" textAnchor="end">
                  {format(v)}
                </text>
              </g>
            ))}
            {columns.map((c, i) => {
              const x = AXIS_W + i * slot + (slot - barW) / 2;
              const h = (c.value / max) * plotH;
              return (
                <g key={c.key}>
                  {h > 0 ? <path className="chart-bar" data-active={active === i} d={barPath(x, y(c.value), barW, h)} /> : null}
                  {i % every === 0 ? (
                    <text className="chart-axis" x={x + barW / 2} y={HEIGHT - 6} textAnchor="middle">
                      {c.label}
                    </text>
                  ) : null}
                  <rect
                    className="chart-hit"
                    x={AXIS_W + i * slot}
                    y={TOP}
                    width={slot}
                    height={plotH}
                    tabIndex={0}
                    aria-label={`${c.label}: ${c.title}`}
                    onPointerEnter={() => setActive(i)}
                    onPointerLeave={() => setActive(null)}
                    onFocus={() => setActive(i)}
                    onBlur={() => setActive(null)}
                  />
                </g>
              );
            })}
          </svg>
          {current && active !== null ? (
            <div
              className="chart-tip"
              role="status"
              style={{ left: Math.min(Math.max(AXIS_W + (active + 0.5) * slot, 90), width - 90), top: 0 }}
            >
              <strong>{current.title}</strong>
              <span>{current.label}</span>
              {current.details.map((d) => (
                <span key={d}>{d}</span>
              ))}
            </div>
          ) : null}
        </div>
      )}
    </div>
  );
}

export interface Share {
  key: string;
  label: string;
  /** 0..1 of the whole. */
  share: number;
  /** Change in percentage points against the previous period; null when it cannot be compared. */
  change: number | null;
  detail: string;
}

/** Horizontal bars for shares of a whole, largest first; the numbers are written next to them. */
export function ShareBars({ items, label }: { items: Share[]; label: string }) {
  const { t, number } = useI18n();
  const max = Math.max(0.0001, ...items.map((i) => i.share));
  const pct = (x: number) => t("stats.percent", { n: number(Math.round(x * 1000) / 10) });
  return (
    <ul className="share-bars" aria-label={label}>
      {items.map((i) => (
        <li key={i.key} title={i.detail}>
          <span className="share-label">{i.label}</span>
          <span className="share-track" aria-hidden="true">
            <span className="share-bar" style={{ width: `${(i.share / max) * 100}%` }} />
          </span>
          <span className="share-value">{pct(i.share)}</span>
          <span className="share-change">
            {i.change === null
              ? ""
              : Math.abs(i.change) < 0.0005
                ? t("stats.noChange")
                : t(i.change > 0 ? "stats.pointsUp" : "stats.pointsDown", { n: number(Math.round(Math.abs(i.change) * 1000) / 10) })}
          </span>
        </li>
      ))}
    </ul>
  );
}

/** A headline number with its change against the previous period. */
export function StatTile({ label, value, change, hint }: { label: string; value: string; change?: ReactNode; hint?: string }) {
  return (
    <div className="stat-tile" title={hint}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {change ? <span className="stat-change">{change}</span> : null}
    </div>
  );
}
