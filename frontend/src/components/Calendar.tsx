import { useMemo, type ReactNode } from "react";
import { useI18n, type I18n } from "../i18n";
import { Icon } from "./Icon";

export function shiftMonth(month: string, delta: number): string {
  const [y, m] = month.split("-").map(Number);
  const d = new Date(y!, m! - 1 + delta, 1);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

/** Monday-first weeks of a month; null = padding cell. */
export function monthGrid(month: string): (string | null)[][] {
  const [y, m] = month.split("-").map(Number);
  const first = new Date(y!, m! - 1, 1);
  const days = new Date(y!, m!, 0).getDate();
  const offset = (first.getDay() + 6) % 7;
  const cells: (string | null)[] = Array.from({ length: offset }, () => null);
  for (let d = 1; d <= days; d++) cells.push(`${month}-${String(d).padStart(2, "0")}`);
  while (cells.length % 7) cells.push(null);
  const weeks: (string | null)[][] = [];
  for (let i = 0; i < cells.length; i += 7) weeks.push(cells.slice(i, i + 7));
  return weeks;
}

export function longDay(i18n: I18n, day: string): string {
  return new Intl.DateTimeFormat(i18n.locale, { dateStyle: "full" }).format(new Date(`${day}T12:00:00`));
}

/**
 * Month calendar used by the notebook and the history. Days listed in ``marks`` get a dot and
 * the mark's text in their accessible name.
 */
export function Calendar({
  label,
  month,
  onMonth,
  day,
  today,
  onPick,
  marks,
  footer,
}: {
  label: string;
  month: string;
  onMonth: (month: string) => void;
  day: string;
  today: string;
  onPick: (day: string) => void;
  marks: Map<string, string>;
  footer?: ReactNode;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const weekdays = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(i18n.locale, { weekday: "short" });
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i))); // 2024-01-01 was a Monday
  }, [i18n.locale]);
  const monthTitle = new Intl.DateTimeFormat(i18n.locale, { month: "long", year: "numeric" }).format(new Date(`${month}-15T12:00:00`));

  return (
    <section className="calendar" aria-label={label}>
      <div className="calendar-head">
        <button type="button" className="icon-btn" aria-label={t("notebook.prevMonth")} onClick={() => onMonth(shiftMonth(month, -1))}>
          <Icon name="chevronLeft" size={16} />
        </button>
        <span className="calendar-month">{monthTitle}</span>
        <button type="button" className="icon-btn" aria-label={t("notebook.nextMonth")} onClick={() => onMonth(shiftMonth(month, 1))}>
          <Icon name="chevronRight" size={16} />
        </button>
      </div>
      <table className="calendar-grid">
        <thead>
          <tr>{weekdays.map((w) => <th key={w} scope="col">{w}</th>)}</tr>
        </thead>
        <tbody>
          {monthGrid(month).map((week, i) => (
            <tr key={i}>
              {week.map((d, j) => (
                <td key={j}>
                  {d ? (
                    <button
                      type="button"
                      className="calendar-day"
                      aria-pressed={d === day}
                      aria-current={d === today ? "date" : undefined}
                      aria-label={`${longDay(i18n, d)}${marks.has(d) ? ` · ${marks.get(d)}` : ""}`}
                      onClick={() => onPick(d)}
                    >
                      {Number(d.slice(8))}
                      {marks.has(d) ? <span className="calendar-dot" aria-hidden="true" /> : null}
                    </button>
                  ) : null}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {footer}
    </section>
  );
}
