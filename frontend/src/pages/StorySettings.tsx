import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { OllamaModel, Settings } from "../api/types";
import { MultiSelect } from "../components/MultiSelect";
import { useToast } from "../components/Toasts";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";

const WEIGHTS = ["sources", "freshness", "turkey", "interest"] as const;

/** Keywords as typed ("enerji, Kıbrıs,  NATO") -> clean list, duplicates dropped. */
export function parseKeywords(text: string): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const raw of text.split(/[,\n;]/)) {
    const k = raw.trim().slice(0, 60);
    const key = k.toLocaleLowerCase("tr");
    if (k && !seen.has(key)) {
      seen.add(key);
      out.push(k);
    }
  }
  return out.slice(0, 100);
}

export function StorySettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, status, meta, refreshStatus } = useAppState();
  const [models, setModels] = useState<OllamaModel[] | null>(null);
  const [keywords, setKeywords] = useState(settings["interest.keywords"].join(", "));
  const [threshold, setThreshold] = useState(settings["stories.threshold"]);
  const [weights, setWeights] = useState(() => Object.fromEntries(WEIGHTS.map((k) => [k, settings[`score.w_${k}`]])));

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const change = (patch: Partial<Settings>) => updateSettings(patch).then(() => refreshStatus(), fail);

  // Switching the model also switches to its measured threshold (server side); follow it.
  const savedThreshold = settings["stories.threshold"];
  useEffect(() => setThreshold(savedThreshold), [savedThreshold]);

  const url = settings["ai.url"];
  useEffect(() => {
    let alive = true;
    api.testOllama(url).then(
      (r) => alive && setModels(r.ok ? r.models : []),
      () => alive && setModels([]),
    );
    return () => {
      alive = false;
    };
  }, [url]);

  const model = settings["stories.embed_model"];
  // Offer embedding models; when Ollama does not report capabilities, offer every model.
  const choices = (models ?? []).filter((m) => m.capabilities === null || m.capabilities.includes("embedding"));
  const installed = choices.some((m) => m.name === model);

  const saveKeywords = () => {
    const list = parseKeywords(keywords);
    setKeywords(list.join(", "));
    if (JSON.stringify(list) !== JSON.stringify(settings["interest.keywords"])) void change({ "interest.keywords": list });
  };

  const st = status?.stories;

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.stories")}</h2>
      <div className="settings-card">
        {st ? (
          <div className="settings-row">
            <div className="settings-status" role="status">
              {t("settings.stories.status", { stories: i18n.number(st.stories), multi: i18n.number(st.multi_source), embedded: i18n.number(st.embedded) })}
            </div>
          </div>
        ) : null}

        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.stories.model")}</div>
            <div className="settings-row-hint">{t("settings.stories.modelHint")}</div>
          </div>
          <select
            className="select"
            style={{ width: 260 }}
            aria-label={t("settings.stories.model")}
            value={model}
            disabled={models === null}
            onChange={(e) => void change({ "stories.embed_model": e.target.value })}
          >
            {!installed ? (
              // Until Ollama has answered we do not know yet whether the model is installed.
              <option value={model}>{models === null ? model : t("settings.ai.modelNotInstalled", { model })}</option>
            ) : null}
            {choices.map((m) => (
              <option key={m.name} value={m.name}>
                {m.name} · {m.parameters ?? "?"} · {i18n.number(m.size_gb)} GB
              </option>
            ))}
          </select>
        </div>

        <div className="settings-row">
          <div className="settings-row-text" style={{ flex: 1 }}>
            <div className="settings-row-title">{t("settings.stories.threshold")}</div>
            <div className="settings-row-hint">{t("settings.stories.thresholdHint")}</div>
          </div>
          <div className="range-field">
            <input
              type="range"
              className="range"
              min={0.5}
              max={0.95}
              step={0.01}
              value={threshold}
              aria-label={t("settings.stories.threshold")}
              onChange={(e) => setThreshold(Number(e.target.value))}
              onPointerUp={() => threshold !== settings["stories.threshold"] && void change({ "stories.threshold": threshold })}
              onKeyUp={() => threshold !== settings["stories.threshold"] && void change({ "stories.threshold": threshold })}
            />
            <span className="score-num">{i18n.number(threshold)}</span>
          </div>
        </div>

        <div className="settings-row settings-row-block">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.stories.weights")}</div>
            <div className="settings-row-hint">{t("settings.stories.weightsHint")}</div>
          </div>
          <div className="weight-grid">
            {WEIGHTS.filter((k) => k !== "turkey" || settings["home.enabled"]).map((k) => {
              const key = `score.w_${k}` as const;
              const commit = () => weights[k] !== settings[key] && void change({ [key]: weights[k] });
              return (
                <label key={k} className="weight-row">
                  <span>{t(`stories.component.${k}`)}</span>
                  <input
                    type="range"
                    className="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={weights[k]}
                    onChange={(e) => setWeights((w) => ({ ...w, [k]: Number(e.target.value) }))}
                    onPointerUp={commit}
                    onKeyUp={commit}
                  />
                  <span className="score-num">{Math.round((weights[k] ?? 0) * 100)}</span>
                </label>
              );
            })}
          </div>
        </div>

        <div className="settings-row settings-row-block">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.stories.interest")}</div>
          </div>
          <label className="field" style={{ width: "100%" }}>
            <span className="field-label">{t("settings.stories.keywords")}</span>
            <textarea
              className="textarea"
              rows={2}
              value={keywords}
              onChange={(e) => setKeywords(e.target.value)}
              onBlur={saveKeywords}
            />
            <span className="field-hint">{t("settings.stories.keywordsHint")}</span>
          </label>
          <div className="filter-row">
            <MultiSelect
              label={t("settings.stories.categories")}
              options={meta.categories.map((c) => ({ value: c, label: t(`category.${c}`) }))}
              selected={settings["interest.categories"]}
              onChange={(v) => void change({ "interest.categories": v as Settings["interest.categories"] })}
            />
            <MultiSelect
              label={t("settings.stories.regions")}
              options={meta.regions.map((r) => ({ value: r, label: t(`region.${r}`) }))}
              selected={settings["interest.regions"]}
              onChange={(v) => void change({ "interest.regions": v as Settings["interest.regions"] })}
            />
          </div>
        </div>
      </div>
    </section>
  );
}
