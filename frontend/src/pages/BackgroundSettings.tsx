import { api, ApiError } from "../api/client";
import type { Settings } from "../api/types";
import { useToast } from "../components/Toasts";
import { Segmented, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";

const MIN_SOURCES = [3, 5, 8, 12];
const MIN_SCORES = [50, 60, 75];
const HOURS = Array.from({ length: 24 }, (_, h) => h);

/** Running in the tray, and Windows notifications for stories that spread quickly. */
export function BackgroundSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, refreshStatus } = useAppState();

  const fail = (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
  const change = (patch: Partial<Settings>) => updateSettings(patch).then(() => refreshStatus(), fail);
  const hour = (h: number) => `${String(h).padStart(2, "0")}:00`;

  const available = status?.notify.available ?? false;
  const enabled = settings["notify.enabled"];

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.background")}</h2>
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.background.tray")}</div>
            <div className="settings-row-hint">{t("settings.background.trayHint")}</div>
          </div>
          <Switch
            checked={settings["app.close_to_tray"]}
            label={t("settings.background.tray")}
            onChange={(v) => void change({ "app.close_to_tray": v })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.notify")}</div>
            <div className="settings-row-hint">{t("settings.notify.hint")}</div>
            {!available ? (
              <div className="settings-row-hint warn" role="status">{t("settings.notify.unavailable")}</div>
            ) : null}
          </div>
          <Switch checked={enabled} label={t("settings.notify")} onChange={(v) => void change({ "notify.enabled": v })} />
        </div>

        {enabled ? (
          <>
            <div className="settings-row">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.notify.when")}</div>
                <div className="settings-row-hint">{t("settings.notify.whenHint")}</div>
              </div>
              <div className="segment-stack">
                <span>{t("settings.notify.sources")}</span>
                <Segmented
                  label={t("settings.notify.sources")}
                  value={settings["notify.min_sources"]}
                  onChange={(v) => void change({ "notify.min_sources": v })}
                  options={MIN_SOURCES.map((n) => ({ value: n, label: t("settings.notify.sourcesN", { n }) }))}
                />
                <span>{t("settings.notify.score")}</span>
                <Segmented
                  label={t("settings.notify.score")}
                  value={settings["notify.min_score"]}
                  onChange={(v) => void change({ "notify.min_score": v })}
                  options={MIN_SCORES.map((n) => ({ value: n, label: t("settings.fulltext.autoScoreN", { n }) }))}
                />
              </div>
            </div>

            <div className="settings-row">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.notify.quiet")}</div>
                <div className="settings-row-hint">{t("settings.notify.quietHint")}</div>
              </div>
              <div className="inline-row">
                {settings["notify.quiet"] ? (
                  <>
                    <select
                      className="select"
                      aria-label={t("settings.notify.quietStart")}
                      value={settings["notify.quiet_start"]}
                      onChange={(e) => void change({ "notify.quiet_start": Number(e.target.value) })}
                    >
                      {HOURS.map((h) => <option key={h} value={h}>{hour(h)}</option>)}
                    </select>
                    <span aria-hidden="true">–</span>
                    <select
                      className="select"
                      aria-label={t("settings.notify.quietEnd")}
                      value={settings["notify.quiet_end"]}
                      onChange={(e) => void change({ "notify.quiet_end": Number(e.target.value) })}
                    >
                      {HOURS.map((h) => <option key={h} value={h}>{hour(h)}</option>)}
                    </select>
                  </>
                ) : null}
                <Switch
                  checked={settings["notify.quiet"]}
                  label={t("settings.notify.quiet")}
                  onChange={(v) => void change({ "notify.quiet": v })}
                />
              </div>
            </div>

            <div className="settings-row">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.notify.test")}</div>
                <div className="settings-status">
                  {status?.notify.last_sent_at ? (
                    <span>{t("settings.notify.last", { time: i18n.relative(status.notify.last_sent_at) })}</span>
                  ) : (
                    <span>{t("settings.notify.none")}</span>
                  )}
                </div>
              </div>
              <button
                className="btn"
                disabled={!available}
                onClick={() =>
                  void api.testNotification().then(() => toast.show(t("settings.notify.testSent"), "success"), fail)
                }
              >
                {t("settings.notify.testButton")}
              </button>
            </div>
          </>
        ) : null}
      </div>
    </section>
  );
}
