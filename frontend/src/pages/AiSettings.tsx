import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { AiProvider, OllamaTestResult, Settings } from "../api/types";
import { ChipList } from "../components/ChipList";
import { useToast } from "../components/Toasts";
import { Segmented, Spinner, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { aiLanguages } from "../lib/aiText";
import { useAppState } from "../state";
import { CloudAiSettings } from "./CloudAiSettings";
import { isServiceUrl } from "./sourceForm";

const MAX_AGES = [6, 12, 24, 48];
const MAX_LANGUAGES = 4;
const PROVIDERS: AiProvider[] = ["ollama", "gemini", "openai", "anthropic"];

export function AiSettings() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, refreshStatus, meta } = useAppState();
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
    if (!isServiceUrl(value) || value === settings["ai.url"]) return;
    void change({ "ai.url": value });
  };

  const ai = status?.ai;
  const model = settings["ai.model"];
  // Chat models only (embedding-only models cannot write summaries); unknown capabilities: offer it.
  const installed = (test?.models ?? []).filter((m) => m.capabilities === null || m.capabilities.includes("completion"));
  const modelInstalled = installed.some((m) => m.name === model);
  const urlInvalid = url.trim() !== "" && !isServiceUrl(url.trim());
  const languages = aiLanguages(settings);
  const provider = settings["ai.provider"];
  const addable = meta.ai_output_languages
    .filter((l) => !languages.includes(l))
    .map((l) => ({ value: l, label: i18n.languageName(l) }))
    .sort((a, b) => a.label.localeCompare(b.label, i18n.locale));

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

        <div className="settings-row settings-row-block">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.languages")}</div>
            <div className="settings-row-hint">{t("settings.ai.languagesHint", { max: MAX_LANGUAGES })}</div>
          </div>
          <div className="chip-editor">
            <ChipList
              label={t("settings.ai.languages")}
              items={languages.map((l) => ({ value: l, label: i18n.languageName(l) }))}
              minItems={1}
              onRemove={(l) => void change({ "ai.languages": languages.filter((x) => x !== l) })}
            />
            {languages.length < MAX_LANGUAGES ? (
              <select
                className="select"
                aria-label={t("settings.ai.addLanguage")}
                value=""
                onChange={(e) => e.target.value && void change({ "ai.languages": [...languages, e.target.value] })}
              >
                <option value="">{t("settings.ai.addLanguage")}</option>
                {addable.map((l) => (
                  <option key={l.value} value={l.value}>{l.label}</option>
                ))}
              </select>
            ) : null}
          </div>
        </div>

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.ai.provider")}</div>
            <div className="settings-row-hint">{t(`settings.ai.provider.${provider}Hint`)}</div>
          </div>
          <select
            className="select"
            style={{ width: 260 }}
            aria-label={t("settings.ai.provider")}
            value={provider}
            onChange={(e) => void change({ "ai.provider": e.target.value as AiProvider })}
          >
            {PROVIDERS.map((p) => (
              <option key={p} value={p}>{t(`ai.provider.${p}`)}</option>
            ))}
          </select>
        </div>

        {provider !== "ollama" ? (
          <CloudAiSettings key={provider} provider={provider} change={(p: Partial<Settings>) => void change(p)} />
        ) : (
        <>
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
                  : t("settings.ai.testFail", { reason: t(`ai.state.${test.error_code === "timeout" ? "timeout" : "unreachable"}`, { service: "Ollama" }) })}
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
        </>
        )}

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

        {provider === "ollama" ? (
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
        ) : null}

        {ai ? (
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">
                {t("settings.ai.status")}: {t(`ai.state.${ai.state}`, { service: t(`ai.service.${provider}`) })}
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
