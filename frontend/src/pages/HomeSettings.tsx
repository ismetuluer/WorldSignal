import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { HomeInfo, Settings } from "../api/types";
import { MultiSelect } from "../components/MultiSelect";
import { useToast } from "../components/Toasts";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { useAppState } from "../state";
import { parseKeywords } from "./StorySettings";

/** "My country": which country the relevance filter, card labels and score use (country.py on the server). */
export function HomeSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, meta } = useAppState();
  const [info, setInfo] = useState<HomeInfo | null>(null);
  const [keywords, setKeywords] = useState(settings["home.keywords"].join(", "));

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const load = useCallback(() => api.home().then(setInfo, fail), [fail]);

  // Reload whenever a home setting changes; the server applies the defaults of a newly chosen country.
  const key = JSON.stringify([settings["home.country"], settings["home.related"], settings["home.topics"], settings["home.keywords"]]);
  useEffect(() => {
    void load();
  }, [key, load]);

  // While reports are being re-rated for a new country, check again until it is done.
  const syncing = info?.syncing ?? false;
  useEffect(() => {
    if (!syncing) return;
    const timer = window.setTimeout(() => void load(), 2000);
    return () => window.clearTimeout(timer);
  }, [syncing, info, load]);

  const savedKeywords = settings["home.keywords"];
  useEffect(() => setKeywords(savedKeywords.join(", ")), [savedKeywords]);

  const change = (patch: Partial<Settings>) => void updateSettings(patch).catch(fail);

  const byName = useCallback(
    (codes: string[]) =>
      codes
        .map((code) => ({ value: code, label: i18n.countryName(code) }))
        .sort((a, b) => a.label.localeCompare(b.label, i18n.locale)),
    [i18n],
  );
  const countryOptions = useMemo(() => byName(info?.countries ?? []), [info, byName]);

  const saveKeywords = () => {
    const list = parseKeywords(keywords);
    setKeywords(list.join(", "));
    if (JSON.stringify(list) !== JSON.stringify(settings["home.keywords"])) change({ "home.keywords": list });
  };

  const customised = settings["home.related"] !== null || settings["home.topics"] !== null;

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.home")}</h2>
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-status">{t("settings.home.hint")}</div>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.home.country")}</div>
            <div className="settings-row-hint">{t("settings.home.countryHint")}</div>
          </div>
          <select
            className="select"
            style={{ width: 260 }}
            aria-label={t("settings.home.country")}
            value={settings["home.country"]}
            disabled={!info}
            onChange={(e) => change({ "home.country": e.target.value })}
          >
            <option value="">{t("settings.home.system", { country: i18n.countryName(meta.system_country) })}</option>
            {countryOptions.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>

        {info ? (
          <>
            {info.syncing ? (
              <div className="settings-row">
                <div className="settings-status" role="status">
                  {t("settings.home.syncing")}
                </div>
              </div>
            ) : null}

            <div className="settings-row">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.home.neighbours")}</div>
                <div className="settings-row-hint">
                  {info.neighbours.length
                    ? byName(info.neighbours).map((c) => c.label).join(", ")
                    : t("settings.home.neighboursNone")}
                </div>
              </div>
            </div>

            <div className="settings-row">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.home.related")}</div>
                <div className="settings-row-hint">
                  {info.related.length ? byName(info.related).map((c) => c.label).join(", ") : t("settings.home.relatedHint")}
                </div>
              </div>
              <MultiSelect<string>
                label={t("settings.home.related")}
                options={countryOptions.filter((c) => c.value !== info.code)}
                selected={info.related}
                onChange={(next) => change({ "home.related": next })}
                searchable
                searchPlaceholder={t("settings.home.relatedSearch")}
              />
            </div>

            <div className="settings-row settings-row-block">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.home.topics")}</div>
                <div className="settings-row-hint">{t("settings.home.topicsHint")}</div>
              </div>
              <div className="check-grid">
                {info.all_topics.map((topic) => (
                  <label key={topic} className="check-row">
                    <input
                      type="checkbox"
                      checked={info.topics.includes(topic)}
                      onChange={(e) =>
                        change({
                          "home.topics": e.target.checked
                            ? info.all_topics.filter((x) => x === topic || info.topics.includes(x))
                            : info.topics.filter((x) => x !== topic),
                        })
                      }
                    />
                    <span>{t(`topic.${topic}` as MessageKey)}</span>
                  </label>
                ))}
              </div>
            </div>

            <div className="settings-row settings-row-block">
              <div className="settings-row-text">
                <div className="settings-row-title">{t("settings.home.keywords")}</div>
                <div className="settings-row-hint">{t("settings.home.keywordsHint")}</div>
              </div>
              <textarea
                className="textarea"
                rows={2}
                aria-label={t("settings.home.keywords")}
                value={keywords}
                onChange={(e) => setKeywords(e.target.value)}
                onBlur={saveKeywords}
              />
            </div>

            {customised ? (
              <div className="settings-row">
                <button className="btn" onClick={() => change({ "home.related": null, "home.topics": null })}>
                  {t("settings.home.reset")}
                </button>
              </div>
            ) : null}
          </>
        ) : null}
      </div>
    </section>
  );
}
