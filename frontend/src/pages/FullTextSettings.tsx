import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BrowserList, Settings } from "../api/types";
import { useToast } from "../components/Toasts";
import { Segmented, Spinner, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { fulltextErrorKey } from "../lib/fulltext";
import { ExtensionSettings } from "./ExtensionSettings";
import { navigate } from "../router";
import { useAppState } from "../state";

const PER_SITE = [2, 4, 6, 10];
const AUTO_SCORES = [0, 50, 60, 75];
const PER_STORY = [0, 1, 2, 3];
const BROWSER_GAPS = [10, 20, 30, 60];
const BROWSER_PER_DAY = [5, 10, 15, 30];

/** Settings for fetching full texts: the extension, browser, pace and the queue's state. */
export function FullTextSettings() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, refreshStatus } = useAppState();
  const [browsers, setBrowsers] = useState<BrowserList | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  const loadBrowsers = useCallback(() => api.browsers().then(setBrowsers, fail), [fail]);
  const browserPath = settings["fulltext.browser_path"];
  useEffect(() => {
    void loadBrowsers();
  }, [loadBrowsers, browserPath]);

  const change = (patch: Partial<Settings>) => updateSettings(patch).then(() => refreshStatus(), fail);

  const enablePaid = async () => {
    setBusy(true);
    try {
      const targets = (await api.sources()).filter((s) => s.paywalled && s.enabled && s.fulltext_mode !== "browser");
      for (const s of targets) await api.updateSource(s.id, { fulltext_mode: "browser" });
      toast.show(plural("settings.fulltext.paidEnabled", targets.length), "success");
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const ft = status?.fulltext;
  const enabled = settings["fulltext.enabled"];

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.fulltext")}</h2>
      <div className="settings-card">
        <ExtensionSettings />

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.enabled")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.enabledHint")}</div>
          </div>
          <Switch
            checked={enabled}
            label={t("settings.fulltext.enabled")}
            onChange={(v) => void change({ "fulltext.enabled": v })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.translate")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.translateHint")}</div>
          </div>
          <Switch
            checked={settings["fulltext.translate"]}
            label={t("settings.fulltext.translate")}
            onChange={(v) => void change({ "fulltext.translate": v })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.browser")}</div>
            <div className="settings-row-hint">{t("extension.browserHint")}</div>
          </div>
          {browsers === null ? (
            <Spinner />
          ) : browsers.browsers.length === 0 ? (
            <span className="settings-row-hint" role="status">{t("settings.fulltext.noBrowser")}</span>
          ) : (
            <select
              className="select"
              style={{ width: 260 }}
              aria-label={t("settings.fulltext.browser")}
              value={browserPath || ""}
              onChange={(e) => void change({ "fulltext.browser_path": e.target.value })}
            >
              <option value="">
                {t("settings.fulltext.browserAuto", {
                  name: browsers.browsers.find((b) => b.path === browsers.chosen)?.name ?? "—",
                })}
              </option>
              {browsers.browsers.map((b) => (
                <option key={b.path} value={b.path}>
                  {b.name}
                </option>
              ))}
            </select>
          )}
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.paid")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.paidHint")}</div>
          </div>
          <button className="btn" disabled={busy} onClick={() => void enablePaid()}>
            {busy ? <Spinner /> : null}
            {t("settings.fulltext.paidButton")}
          </button>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("sites.title")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.sitesMoved")}</div>
          </div>
          <button className="btn" onClick={() => navigate("sources")}>
            {t("settings.fulltext.sitesOpen")}
          </button>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.perSite")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.perSiteHint")}</div>
          </div>
          <Segmented
            label={t("settings.fulltext.perSite")}
            value={settings["fulltext.per_site_hour"]}
            onChange={(v) => void change({ "fulltext.per_site_hour": v })}
            options={PER_SITE.map((n) => ({ value: n, label: t("settings.fulltext.perHour", { n }) }))}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.humanPace")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.humanPaceHint")}</div>
          </div>
          <div className="segment-stack">
            <span>{t("settings.fulltext.browserGap")}</span>
            <Segmented
              label={t("settings.fulltext.browserGap")}
              value={settings["fulltext.browser_gap_min"]}
              onChange={(v) => void change({ "fulltext.browser_gap_min": v })}
              options={BROWSER_GAPS.map((n) => ({ value: n, label: t("settings.fulltext.minutes", { n }) }))}
            />
            <span>{t("settings.fulltext.browserPerDay")}</span>
            <Segmented
              label={t("settings.fulltext.browserPerDay")}
              value={settings["fulltext.browser_per_day"]}
              onChange={(v) => void change({ "fulltext.browser_per_day": v })}
              options={BROWSER_PER_DAY.map((n) => ({ value: n, label: t("settings.fulltext.perDay", { n }) }))}
            />
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.nightRest")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.nightRestHint")}</div>
          </div>
          <Switch
            checked={settings["fulltext.browser_night_rest"]}
            label={t("settings.fulltext.nightRest")}
            onChange={(v) => void change({ "fulltext.browser_night_rest": v })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.auto")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.autoHint")}</div>
          </div>
          <div className="segment-stack">
            <span>{t("settings.fulltext.autoScore")}</span>
            <Segmented
              label={t("settings.fulltext.autoScore")}
              value={settings["fulltext.auto_min_score"]}
              onChange={(v) => void change({ "fulltext.auto_min_score": v })}
              options={AUTO_SCORES.map((n) => ({
                value: n,
                label: n === 0 ? t("settings.fulltext.autoAll") : t("settings.fulltext.autoScoreN", { n }),
              }))}
            />
            <span>{t("settings.fulltext.autoPerStory")}</span>
            <Segmented
              label={t("settings.fulltext.autoPerStory")}
              value={settings["fulltext.auto_per_story"]}
              onChange={(v) => void change({ "fulltext.auto_per_story": v })}
              options={PER_STORY.map((n) => ({
                value: n,
                label: n === 0 ? t("settings.fulltext.autoOff") : t("settings.fulltext.autoPerStoryN", { n }),
              }))}
            />
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.fulltext.debug")}</div>
            <div className="settings-row-hint">{t("settings.fulltext.debugHint")}</div>
          </div>
          <Switch
            checked={settings["debug.save_pages"]}
            label={t("settings.fulltext.debug")}
            onChange={(v) => void change({ "debug.save_pages": v })}
          />
        </div>

        {ft ? (
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">
                {t("settings.ai.status")}: {t(`fulltext.state.${ft.state}`)}
                {ft.browser && ft.state === "fetching" ? ` (${ft.browser})` : ""}
              </div>
              <div className="settings-status">
                <span>{t("settings.fulltext.queue", { pending: ft.pending, done: ft.done })}</span>
                {ft.failed + ft.blocked > 0 ? (
                  <span>{plural("settings.fulltext.failed", ft.failed + ft.blocked)}</span>
                ) : null}
                {ft.last_error ? <span>{t("settings.fulltext.lastError", { reason: t(fulltextErrorKey(ft.last_error)) })}</span> : null}
              </div>
              {ft.paused_sources.length > 0 ? (
                <ul className="paused-list" aria-label={t("settings.fulltext.paused")}>
                  {ft.paused_sources.map((s) => (
                    <li key={s.id}>
                      <span>
                        {t("settings.fulltext.pausedUntil", { name: s.name, time: i18n.time(s.fulltext_paused_until) })}
                      </span>
                      <button
                        className="btn btn-sm"
                        onClick={() => void api.resumeFulltextSource(s.id).then(refreshStatus, fail)}
                      >
                        {t("settings.fulltext.resume")}
                      </button>
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
