import { useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import { describeError, useI18n } from "../i18n";
import { localDay } from "../lib/hooks";
import type { Story } from "../api/types";
import { bulletinOutput } from "../lib/outputs";
import { Segmented } from "./controls";
import { OutputDialog } from "./OutputDialog";

const HOURS = [12, 24, 48] as const;
const LIMITS = [10, 20, 30] as const;

/** Template 3: the most important stories of the chosen range, grouped by category. */
export function BulletinDialog({ onClose }: { onClose: () => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const [hours, setHours] = useState<number>(24);
  const [limit, setLimit] = useState<number>(20);
  const [multiOnly, setMultiOnly] = useState(true);
  const [stories, setStories] = useState<Story[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setStories(null);
    setError(null);
    api.stories({ hours, limit, sort: "score", min_sources: multiOnly ? 2 : 1 }).then(
      (page) => alive && setStories(page.items),
      (e) => alive && setError(describeError(i18n, e instanceof ApiError ? e.code : "generic")),
    );
    return () => {
      alive = false;
    };
  }, [hours, limit, multiOnly, i18n]);

  return (
    <OutputDialog
      build={stories ? (l, out) => bulletinOutput(out, localDay(), hours, stories, l) : null}
      empty={stories?.length === 0}
      error={error}
      onClose={onClose}
      options={
        <>
          <Segmented label={t("bulletin.hours")} value={hours} onChange={setHours}
            options={HOURS.map((h) => ({ value: h, label: t("feed.window.hours", { n: h }) }))} />
          <Segmented label={t("bulletin.limit")} value={limit} onChange={setLimit}
            options={LIMITS.map((n) => ({ value: n, label: String(n) }))} />
          <button type="button" className="chip" data-active={multiOnly} aria-pressed={multiOnly} onClick={() => setMultiOnly((v) => !v)}>
            {t("bulletin.multiOnly")}
          </button>
        </>
      }
    />
  );
}
