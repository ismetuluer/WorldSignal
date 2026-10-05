import { useState } from "react";
import { Segmented } from "../components/controls";
import { useI18n } from "../i18n";
import { StoryList } from "./StoryList";

const WINDOWS = [3, 12, 24];

/** Breaking news: the stories that carry a publisher's "Son dakika" / "BREAKING" label, newest first. */
export function BreakingPage() {
  const { t, plural } = useI18n();
  const [hours, setHours] = useState(12);
  const [total, setTotal] = useState<number | null>(null);

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("breaking.title")}</h1>
          <p className="page-subtitle">
            {total === null ? t("common.loading") : `${plural("stories.count", total)} · ${t("breaking.hint")}`}
          </p>
        </div>
      </header>
      <div className="toolbar">
        <Segmented
          label={t("feed.window")}
          value={hours}
          onChange={setHours}
          options={WINDOWS.map((h) => ({ value: h, label: t("feed.window.hours", { n: h }) }))}
        />
      </div>
      <StoryList
        key={hours}
        query={{ hours, breaking: true }}
        defaultSort="recent"
        filtersActive={false}
        onClearFilters={() => undefined}
        onTotal={setTotal}
      />
    </div>
  );
}
