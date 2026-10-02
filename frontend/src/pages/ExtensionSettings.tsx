import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ExtensionInfo } from "../api/types";
import { Segmented, Switch } from "../components/controls";
import { useToast } from "../components/Toasts";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { fulltextErrorKey } from "../lib/fulltext";
import { useAppState } from "../state";

const REFRESH_MS = 15_000;
const EXTENSION_ERRORS = ["tab_closed", "load_failed", "script_failed", "record_failed"];
const MASK = "•".repeat(12);

type Reader = "automation" | "extension";

/** Who reads the subscription sites: World Signal's own browser, or the extension in the user's browser. */
export function ExtensionSettings() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const reader = settings["fulltext.reader"];
  const [info, setInfo] = useState<ExtensionInfo | null>(null);
  const [loadFailed, setLoadFailed] = useState(false);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  // Bumped when the code is renewed: a poll that was already in flight carries the old code and must not put it back.
  const renewals = useRef(0);

  useEffect(() => {
    if (reader !== "extension") return;
    const load = () => {
      const seen = renewals.current;
      return api.extension().then(
        (next) => {
          if (seen !== renewals.current) return;
          setInfo(next);
          setLoadFailed(false);
        },
        () => setLoadFailed(true),
      );
    };
    void load();
    const timer = window.setInterval(load, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [reader]);

  // The code is shown masked and is never put in a toast or a log: it is the key to the program's local API.
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(info?.code ?? "");
      toast.show(t("extension.copied"), "success");
    } catch {
      toast.show(t("extension.copyFailed"), "error");
    }
  };
  const renew = async () => {
    renewals.current += 1;
    try {
      const { code } = await api.renewExtensionCode();
      setInfo((i) => (i ? { ...i, code } : i));
      toast.show(t("extension.renewed"), "success");
    } catch (e) {
      fail(e);
    }
  };
  const choose = (v: Reader) => updateSettings({ "fulltext.reader": v }).catch(fail);

  // What the extension reports (tab closed, ...) or the program's own full-text outcome (bot check, paywall, ...).
  const errorText = (code: string) =>
    EXTENSION_ERRORS.includes(code) ? t(`extension.error.${code}` as MessageKey) : t(fulltextErrorKey(code));

  const s = info?.status;
  return (
    <div className="settings-row settings-row-block extension-reader">
      <div className="settings-row-text">
        <div className="settings-row-title">{t("extension.reader")}</div>
        <div className="settings-row-hint">{t("extension.readerHint")}</div>
      </div>
      <Segmented<Reader>
        label={t("extension.reader")}
        value={reader}
        onChange={(v) => void choose(v)}
        options={[
          { value: "extension", label: t("extension.reader.extension") },
          { value: "automation", label: t("extension.reader.automation") },
        ]}
      />
      {reader === "extension" ? (
        <>
          <ol className="extension-steps">
            <li>
              {t("extension.step1")}{" "}
              <button type="button" className="link-btn" onClick={() => void api.openExtensionDir().catch(fail)}>
                {t("extension.openDir")}
              </button>
            </li>
            <li>{t("extension.step2")}</li>
            <li>{t("extension.step3")}</li>
          </ol>
          {info ? (
            <div className="extension-actions">
              <code className="extension-code" aria-hidden="true">{MASK}</code>
              <button type="button" className="btn btn-sm" onClick={() => void copy()}>{t("extension.copy")}</button>
              <button type="button" className="btn btn-sm" onClick={() => void renew()}>{t("extension.renew")}</button>
            </div>
          ) : null}
          {info && !info.fixed_port ? (
            <div className="extension-actions">
              <span className="field-hint warn" role="status">{t("extension.restart")}</span>
              <button
                type="button"
                className="btn btn-sm"
                onClick={() => void api.restartApp().catch(fail)}
              >
                {t("backup.restartNow")}
              </button>
            </div>
          ) : null}
          {loadFailed ? <p className="field-hint warn" role="status">{t("extension.loadFailed")}</p> : null}
          {s ? (
            <div className="extension-state">
              <p className={s.connected ? "field-hint" : "field-hint warn"} role="status">
                {s.connected
                  ? s.reading
                    ? t("extension.reading", { source: s.reading })
                    : `${t("extension.connected")} · ${plural("extension.readToday", s.read_today)}`
                  : t("extension.notConnected")}
              </p>
              {s.last_seen ? <p className="field-hint">{t("extension.lastSeen", { time: i18n.relative(s.last_seen) })}</p> : null}
              {s.last_error ? (
                <p className="field-hint warn">{t("extension.lastError", { reason: errorText(s.last_error) })}</p>
              ) : null}
            </div>
          ) : null}
          <div className="extension-actions extension-launch">
            <span className="settings-row-hint">{t("extension.launch")}</span>
            <Switch
              checked={settings["fulltext.launch_browser"]}
              label={t("extension.launch")}
              onChange={(v) => void updateSettings({ "fulltext.launch_browser": v }).catch(fail)}
            />
          </div>
        </>
      ) : null}
    </div>
  );
}
