import { useI18n } from "../i18n";

/** "Breaking": a story spreading right now, or marked breaking by its publisher. The signal's arcs pulse outwards. */
export function BreakingBadge() {
  const { t } = useI18n();
  return (
    <span className="badge badge-breaking" title={t("badge.breakingHint")}>
      <svg className="signal-pulse" width="13" height="13" viewBox="0 0 24 24" aria-hidden="true" fill="none"
        stroke="currentColor" strokeWidth="2.6" strokeLinecap="round">
        <circle cx="12" cy="17" r="1.6" fill="currentColor" stroke="none" />
        <path className="arc arc-1" d="M8.5 14a4.5 4.5 0 0 1 7 0" />
        <path className="arc arc-2" d="M5.5 11a8.5 8.5 0 0 1 13 0" />
        <path className="arc arc-3" d="M2.5 8a12.5 12.5 0 0 1 19 0" />
      </svg>
      {t("badge.breaking")}
    </span>
  );
}

/** "Exclusive": the publisher marked the report as its own exclusive. */
export function ExclusiveBadge({ source }: { source?: string }) {
  const { t } = useI18n();
  return (
    <span className="badge badge-exclusive" title={source ? t("badge.exclusiveBy", { source }) : t("badge.exclusiveHint")}>
      <svg width="11" height="11" viewBox="0 0 24 24" aria-hidden="true" fill="currentColor">
        <path d="M12 2.5l2.9 6.1 6.6.8-4.9 4.6 1.3 6.6L12 17.3l-5.9 3.3 1.3-6.6-4.9-4.6 6.6-.8z" />
      </svg>
      {t("badge.exclusive")}
    </span>
  );
}
