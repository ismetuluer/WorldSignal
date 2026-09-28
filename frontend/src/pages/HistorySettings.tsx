import { ApiError } from "../api/client";
import type { Settings } from "../api/types";
import { useToast } from "../components/Toasts";
import { Segmented } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";

const MORNING_HOURS = [6, 7, 8, 9, 10, 11, 12];
const FULLTEXT_DAYS = [7, 30, 90, 0];

/** When the history's "morning" is, and how long full texts are kept. */
export function HistorySettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, refreshStatus } = useAppState();

  const change = (patch: Partial<Settings>) =>
    updateSettings(patch).then(
      () => refreshStatus(),
      (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    );

  const m = status?.maintenance;
  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.history")}</h2>
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.history.morning")}</div>
            <div className="settings-row-hint">{t("settings.history.morningHint")}</div>
          </div>
          <select
            className="select"
            style={{ width: 120 }}
            aria-label={t("settings.history.morning")}
            value={settings["history.morning_hour"]}
            onChange={(e) => void change({ "history.morning_hour": Number(e.target.value) })}
          >
            {MORNING_HOURS.map((h) => (
              <option key={h} value={h}>{`${String(h).padStart(2, "0")}:00`}</option>
            ))}
          </select>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.history.fulltext")}</div>
            <div className="settings-row-hint">{t("settings.history.fulltextHint")}</div>
          </div>
          <Segmented
            label={t("settings.history.fulltext")}
            value={settings["retention.fulltext_days"]}
            onChange={(v) => void change({ "retention.fulltext_days": v })}
            options={FULLTEXT_DAYS.map((n) => ({
              value: n,
              label: n === 0 ? t("settings.history.keepForever") : t("settings.history.days", { n }),
            }))}
          />
        </div>

        {m ? (
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">
                {t("settings.history.size", { size: i18n.number(Math.round(m.database_bytes / 1_000_000)) })}
              </div>
              <div className="settings-status">
                <span>{t("settings.history.keeps")}</span>
                {m.last_run_at && m.last_removed ? (
                  <span>
                    {t("settings.history.lastRun", {
                      time: i18n.relative(m.last_run_at),
                      fulltexts: m.last_removed.fulltexts,
                      vectors: m.last_removed.vectors,
                    })}
                  </span>
                ) : (
                  <span>{t("settings.history.notRunYet")}</span>
                )}
                {m.last_error ? <span className="warn">{t("settings.history.failed")}</span> : null}
              </div>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
