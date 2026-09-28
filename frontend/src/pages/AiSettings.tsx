import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { OllamaTestResult } from "../api/types";
import { useToast } from "../components/Toasts";
import { Segmented, Spinner, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { isHttpUrl } from "./sourceForm";

const MAX_AGES = [6, 12, 24, 48];

export function AiSettings() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, refreshStatus } = useAppState();
  const [url, setUrl] = useState(settings["ai.url"]);
  const [test, setTest] = useState<OllamaTestResult | null>(null);
  const [testing, setTesting] = useState(false);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  const runTest = useCallback(
    async (target: string) => {
      setTesting(true);
      try {
        setTest(await api.testOllama(target));
      } catch (e) {
        fail(e);
      } finally {
        setTesting(false);
      }
    },
    [fail],
  );

  // Load the installed model list for the saved address (on open and when it changes).
  const savedUrl = settings["ai.url"];
  useEffect(() => {
    void runTest(savedUrl);
  }, [runTest, savedUrl]);

  const change = (patch: Parameters<typeof updateSettings>[0]) =>
    updateSettings(patch).then(() => refreshStatus(), fail);

  const saveUrl = () => {
    const value = url.trim().replace(/\/+$/, "");
    if (!isHttpUrl(value) || value === settings["ai.url"]) return;
    void change({ "ai.url": value });
  };

  const ai = status?.ai;
  const model = settings["ai.model"];
  // Chat models only (embedding-only models cannot write summaries); unknown capabilities: offer it.
  const installed = (test?.models ?? []).filter((m) => m.capabilities === null || m.capabilities.includes("completion"));
  const modelInstalled = installed.some((m) => m.name === model);
  const urlInvalid = url.trim() !== "" && !isHttpUrl(url.trim());

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.ai")}</h2>
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.enabled")}</div>
            <div className="settings-row-hint">{t("settings.ai.enabledHint")}</div>
          </div>
          <Switch
            checked={settings["ai.enabled"]}
            label={t("settings.ai.enabled")}
            onChange={(v) => void change({ "ai.enabled": v })}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text" style={{ flex: 1 }}>
            <div className="settings-row-title">{t("settings.ai.url")}</div>
            <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
              <input
                className="input"
                value={url}
                aria-label={t("settings.ai.url")}
                aria-invalid={urlInvalid}
                onChange={(e) => setUrl(e.target.value)}
                onBlur={saveUrl}
                onKeyDown={(e) => {
                  if (e.key === "Enter") saveUrl();
                }}
              />
              <button className="btn" disabled={urlInvalid || testing} onClick={() => void runTest(url.trim())}>
                {testing ? <Spinner /> : null}
                {testing ? t("settings.ai.testing") : t("settings.ai.test")}
              </button>
            </div>
            {test ? (
              <div className="settings-row-hint" role="status" style={{ marginTop: 6 }}>
                {test.ok
                  ? plural("settings.ai.testOk", test.models.length, { version: test.version ?? "?" })
                  : t("settings.ai.testFail", { reason: t(`ai.state.${test.error_code === "timeout" ? "timeout" : "unreachable"}`) })}
              </div>
            ) : null}
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.model")}</div>
            <div className="settings-row-hint">{t("settings.ai.modelHint")}</div>
          </div>
          <select
            className="select"
            style={{ width: 260 }}
            aria-label={t("settings.ai.model")}
            value={model}
            onChange={(e) => void change({ "ai.model": e.target.value })}
          >
            {!model ? <option value="">{t("settings.ai.modelNone")}</option> : null}
            {model && !modelInstalled ? (
              // Until Ollama has answered we do not know yet whether the model is installed.
              <option value={model}>{test ? t("settings.ai.modelNotInstalled", { model }) : model}</option>
            ) : null}
            {installed.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name} · {m.parameters ?? "?"} · {i18n.number(m.size_gb)} GB
              </option>
            ))}
          </select>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.maxAge")}</div>
            <div className="settings-row-hint">{t("settings.ai.maxAgeHint")}</div>
          </div>
          <Segmented
            label={t("settings.ai.maxAge")}
            value={settings["ai.max_age_hours"]}
            onChange={(v) => void change({ "ai.max_age_hours": v })}
            options={MAX_AGES.map((n) => ({ value: n, label: t("settings.ai.lastHours", { n }) }))}
          />
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.yield")}</div>
            <div className="settings-row-hint">{t("settings.ai.yieldHint")}</div>
          </div>
          <Switch
            checked={settings["ai.yield_gpu"]}
            label={t("settings.ai.yield")}
            onChange={(v) => void change({ "ai.yield_gpu": v })}
          />
        </div>

        {ai ? (
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">
                {t("settings.ai.status")}: {t(`ai.state.${ai.state}`)}
                {ai.state === "gpu_busy" && ai.busy_with ? ` (${ai.busy_with})` : ""}
              </div>
              <div className="settings-status">
                <span>{t("settings.ai.queue", { pending: ai.pending, done: ai.done_24h })}</span>
                {ai.avg_seconds !== null ? <span>{t("settings.ai.avg", { seconds: ai.avg_seconds })}</span> : null}
                {ai.failed > 0 ? <span>{plural("settings.ai.failed", ai.failed)}</span> : null}
              </div>
            </div>
            {ai.failed > 0 || ai.state === "unreachable" || ai.state === "timeout" ? (
              <button className="btn" onClick={() => void api.retryAi().then(refreshStatus, fail)}>
                {t("settings.ai.retryFailed")}
              </button>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}
