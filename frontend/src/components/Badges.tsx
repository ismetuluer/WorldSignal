import { useI18n } from "../i18n";

/** "Breaking": a story spreading right now, or marked breaking by its publisher. A red dot blinks. */
export function BreakingBadge() {
  const { t } = useI18n();
  return (
    <span className="badge badge-breaking" title={t("badge.breakingHint")}>
      <span className="live-dot" aria-hidden="true" />
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
