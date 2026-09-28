import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CloudProvider, CloudTestResult, Settings } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Spinner } from "../components/controls";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { useAppState } from "../state";
import { isServiceUrl } from "./sourceForm";

const MODEL_KEY: Record<CloudProvider, "ai.gemini_model" | "ai.openai_model" | "ai.anthropic_model"> = {
  gemini: "ai.gemini_model",
  openai: "ai.openai_model",
  anthropic: "ai.anthropic_model",
};
const OPENAI_URL = "https://api.openai.com/v1";

/** The state text that explains a failed connection test. */
function failReason(code: string | null): string {
  return code === "no_key" || code === "bad_key" || code === "rate_limited" || code === "timeout" ? code : "unreachable";
}

/** Settings rows for a cloud AI service: what is sent, the API key (write-only), address, model and pace. */
export function CloudAiSettings({ provider, change }: { provider: CloudProvider; change: (patch: Partial<Settings>) => void }) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { settings } = useAppState();
  const [hasKey, setHasKey] = useState<boolean | null>(null);
  const [key, setKey] = useState("");
  const [test, setTest] = useState<CloudTestResult | null>(null);
  const [testing, setTesting] = useState(false);
  const [url, setUrl] = useState(settings["ai.openai_url"]);
  const modelKey = MODEL_KEY[provider];
  const [model, setModel] = useState(settings[modelKey]);
  const [rpm, setRpm] = useState(String(settings["ai.cloud_rpm"]));
  const service = t(`ai.service.${provider}` as MessageKey);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  const savedUrl = settings["ai.openai_url"];
  const runTest = useCallback(async () => {
    setTesting(true);
    try {
      setTest(await api.testCloud(provider, provider === "openai" ? savedUrl : undefined));
    } catch (e) {
      fail(e);
    } finally {
      setTesting(false);
    }
  }, [provider, savedUrl, fail]);

  const savedModel = settings[modelKey];
  useEffect(() => setModel(savedModel), [savedModel]);
  useEffect(() => {
    setTest(null);
    api.aiKeys().then((k) => setHasKey(k[provider]), fail);
  }, [provider, fail]);

  const saveKey = async () => {
    try {
      const status = await api.setAiKey(provider, key.trim());
      setHasKey(status[provider]);
      setKey("");
      toast.show(t("settings.cloud.keySaved"), "success");
      void runTest();
    } catch (e) {
      fail(e);
    }
  };

  const removeKey = async () => {
    try {
      setHasKey((await api.deleteAiKey(provider))[provider]);
      setTest(null);
    } catch (e) {
      fail(e);
    }
  };

  const saveModel = () => {
    const value = model.trim();
    if (value !== settings[modelKey]) change({ [modelKey]: value });
  };

  const saveUrl = () => {
    const value = url.trim().replace(/\/+$/, "");
    if (isServiceUrl(value) && value !== settings["ai.openai_url"]) change({ "ai.openai_url": value });
  };

  const saveRpm = () => {
    const n = Math.round(Number(rpm));
    if (Number.isFinite(n) && n >= 1 && n <= 600 && n !== settings["ai.cloud_rpm"]) change({ "ai.cloud_rpm": n });
    else setRpm(String(settings["ai.cloud_rpm"]));
  };

  const listId = `cloud-models-${provider}`;
  const urlInvalid = url.trim() !== "" && !isServiceUrl(url.trim());

  return (
    <>
      <div className="settings-row">
        <p className="article-warning" role="note" style={{ margin: 0 }}>
          <Icon name="info" size={13} />
          {t("settings.cloud.warning", { service })}
        </p>
      </div>

      {provider === "openai" ? (
        <div className="settings-row">
          <div className="settings-row-text" style={{ flex: 1 }}>
            <div className="settings-row-title">{t("settings.cloud.url")}</div>
            <div className="settings-row-hint">{t("settings.cloud.urlHint")}</div>
            <input
              className="input"
              style={{ marginTop: 6 }}
              value={url}
              placeholder={OPENAI_URL}
              aria-label={t("settings.cloud.url")}
              aria-invalid={urlInvalid}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={saveUrl}
              onKeyDown={(e) => e.key === "Enter" && saveUrl()}
            />
          </div>
        </div>
      ) : null}

      <div className="settings-row">
        <div className="settings-row-text" style={{ flex: 1 }}>
          <div className="settings-row-title">{t("settings.cloud.key")}</div>
          <div className="settings-row-hint">
            {hasKey === null ? t("common.loading") : hasKey ? t("settings.cloud.keySet") : t("settings.cloud.keyHint", { service })}
          </div>
          <form
            style={{ display: "flex", gap: 8, marginTop: 6 }}
            onSubmit={(e) => {
              e.preventDefault();
              if (key.trim().length >= 8) void saveKey();
            }}
          >
            <input
              className="input"
              type="password"
              autoComplete="off"
              value={key}
              placeholder={hasKey ? t("settings.cloud.keyReplace") : t("settings.cloud.keyPlaceholder")}
              aria-label={t("settings.cloud.key")}
              onChange={(e) => setKey(e.target.value)}
            />
            <button type="submit" className="btn" disabled={key.trim().length < 8}>{t("common.save")}</button>
            {hasKey ? (
              <button type="button" className="btn" onClick={() => void removeKey()}>{t("settings.cloud.keyRemove")}</button>
            ) : null}
          </form>
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-text" style={{ flex: 1 }}>
          <div className="settings-row-title">{t("settings.ai.model")}</div>
          <div className="settings-row-hint">{t("settings.cloud.modelHint")}</div>
          <div style={{ display: "flex", gap: 8, marginTop: 6 }}>
            <input
              className="input"
              list={listId}
              value={model}
              placeholder={t("settings.cloud.modelPlaceholder")}
              aria-label={t("settings.ai.model")}
              onChange={(e) => setModel(e.target.value)}
              onBlur={saveModel}
              onKeyDown={(e) => e.key === "Enter" && saveModel()}
            />
            <datalist id={listId}>
              {(test?.models ?? []).map((m) => (
                <option key={m} value={m} />
              ))}
            </datalist>
            <button className="btn" disabled={testing} onClick={() => void runTest()}>
              {testing ? <Spinner /> : null}
              {testing ? t("settings.ai.testing") : t("settings.ai.test")}
            </button>
          </div>
          {test ? (
            <div className="settings-row-hint" role="status" style={{ marginTop: 6 }}>
              {test.ok
                ? plural("settings.cloud.testOk", test.models.length)
                : t("settings.cloud.testFail", { reason: t(`ai.state.${failReason(test.error_code)}` as MessageKey, { service }) })}
            </div>
          ) : null}
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-text">
          <div className="settings-row-title">{t("settings.cloud.rpm")}</div>
          <div className="settings-row-hint">{t("settings.cloud.rpmHint")}</div>
        </div>
        <input
          className="input"
          style={{ width: 90 }}
          type="number"
          min={1}
          max={600}
          value={rpm}
          aria-label={t("settings.cloud.rpm")}
          onChange={(e) => setRpm(e.target.value)}
          onBlur={saveRpm}
        />
      </div>
    </>
  );
}
