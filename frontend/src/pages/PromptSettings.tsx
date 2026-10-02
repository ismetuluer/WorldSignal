import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import type { Settings } from "../api/types";
import { useToast } from "../components/Toasts";
import { Segmented } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { useAppState } from "../state";

const TASKS = ["article", "story", "translate", "query"] as const;
type Task = (typeof TASKS)[number];
const MAX_CHARS = 6000;
const MAX_INPUT_CHARS = 1000;

// Placeholders the program fills in for each text (ai/prompts.py); a text must keep the required ones.
const PLACEHOLDERS: Record<string, string[]> = {
  article: ["{input}", "{languages}", "{fields}"],
  story: ["{languages}", "{fields}"],
  translate: ["{language}"],
  query: ["{languages}"],
  "input:article": ["{source}", "{language}", "{title}", "{text}"],
  "input:story_intro": ["{count}"],
  "input:story_report": ["{n}", "{source}", "{language}", "{title}", "{text}"],
};
const REQUIRED: Record<string, string> = {
  translate: "{language}", query: "{languages}", "input:article": "{title}", "input:story_report": "{title}",
};
// Which layouts and limits belong to which task (the translation and the search words send plain text: nothing to lay out).
const INPUTS: Partial<Record<Task, string[]>> = { article: ["article"], story: ["story_intro", "story_report"] };
const INPUT_TEXT: Record<string, [MessageKey, MessageKey]> = {
  article: ["settings.inputs.article", "settings.inputs.articleHint"],
  story_intro: ["settings.inputs.story_intro", "settings.inputs.story_introHint"],
  story_report: ["settings.inputs.story_report", "settings.inputs.story_reportHint"],
};
const LIMIT_TEXT: Record<string, MessageKey> = {
  article_chars: "settings.limits.article_chars",
  batch_chars: "settings.limits.batch_chars",
  batch_size: "settings.limits.batch_size",
  story_reports: "settings.limits.story_reports",
  story_report_chars: "settings.limits.story_report_chars",
};
const LIMITS: Partial<Record<Task, string[]>> = {
  article: ["article_chars", "batch_chars", "batch_size"],
  story: ["story_reports", "story_report_chars"],
};

type Dict = Record<string, string>;

/** One editable text: shows what is in force (the user's or the default), saves a dictionary setting, resets. */
function TemplateEditor({ id, label, hint, setting, defaults, maxChars, rows }: {
  id: string; label: string; hint?: string; setting: "ai.prompts" | "ai.inputs"; defaults: Dict; maxChars: number; rows: number;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const custom = settings[setting] as Dict;
  const key = setting === "ai.inputs" ? `input:${id}` : id;
  const stored = custom[id] ?? defaults[id] ?? "";
  const [text, setText] = useState(stored);
  useEffect(() => setText(stored), [stored, id]);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const usingDefault = custom[id] === undefined;
  const dirty = text !== stored;
  const required = REQUIRED[key];
  const missing = required !== undefined && !text.includes(required);
  const tooLong = text.length > maxChars;
  const noFields = setting === "ai.prompts" && (id === "article" || id === "story") && !text.includes("{fields}");

  const save = (next: string) => {
    const rest = { ...custom };
    if (!next.trim() || next === defaults[id]) delete rest[id];
    else rest[id] = next;
    updateSettings({ [setting]: rest } as Partial<Settings>).then(() => toast.show(t("settings.prompts.saved"), "success"), fail);
  };

  return (
    <div className="prompt-block">
      <div className="settings-row-title">{label}</div>
      {hint ? <div className="settings-row-hint">{hint}</div> : null}
      <textarea
        className="textarea prompt-editor"
        aria-label={label}
        value={text}
        rows={rows}
        spellCheck={false}
        onChange={(e) => setText(e.target.value)}
      />
      <div className="settings-row-hint">{t("settings.prompts.placeholders", { list: (PLACEHOLDERS[key] ?? []).join("  ") })}</div>
      {missing ? <p className="field-hint warn" role="alert">{t("settings.prompts.missing", { name: required ?? "" })}</p> : null}
      {tooLong ? <p className="field-hint warn" role="alert">{t("settings.prompts.tooLong", { max: maxChars })}</p> : null}
      {!missing && noFields ? <p className="field-hint">{t("settings.prompts.noFields")}</p> : null}
      <div className="settings-actions">
        <span className="settings-row-hint">
          {dirty ? t("settings.prompts.unsaved") : usingDefault ? t("settings.prompts.usingDefault") : t("settings.prompts.usingCustom")}
        </span>
        <button
          className="btn"
          disabled={usingDefault && text === defaults[id]}
          onClick={() => {
            setText(defaults[id] ?? "");
            if (!usingDefault) save(defaults[id] ?? "");
          }}
        >
          {t("settings.prompts.reset")}
        </button>
        <button className="btn btn-primary" disabled={!dirty || missing || tooLong} onClick={() => save(text)}>
          {t("settings.prompts.save")}
        </button>
      </div>
    </div>
  );
}

/** One amount (characters per report, reports per request ...): empty means the default. */
function LimitField({ name }: { name: string }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, meta } = useAppState();
  const [fallback, low, high] = (meta.ai_limit_ranges[name] ?? [0, 0, 0]) as [number, number, number];
  const custom = settings["ai.limits"];
  const stored = custom[name] === undefined ? "" : String(custom[name]);
  const [text, setText] = useState(stored);
  useEffect(() => setText(stored), [stored]);
  const value = text.trim() === "" ? null : Number(text);
  const invalid = value !== null && (!Number.isInteger(value) || value < low || value > high);

  const commit = () => {
    if (invalid || text === stored) return;
    const rest = { ...custom };
    if (value === null || value === fallback) delete rest[name];
    else rest[name] = value;
    updateSettings({ "ai.limits": rest }).catch((e) =>
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"));
  };

  return (
    <div className="limit-field">
      <label htmlFor={`limit-${name}`}>
        <span className="settings-row-title">{t(LIMIT_TEXT[name] ?? "settings.limits.title")}</span>
        <span className="settings-row-hint">{t("settings.limits.range", { fallback, low, high })}</span>
      </label>
      <input
        id={`limit-${name}`}
        className="input"
        inputMode="numeric"
        value={text}
        placeholder={String(fallback)}
        aria-invalid={invalid}
        onChange={(e) => setText(e.target.value)}
        onBlur={commit}
        onKeyDown={(e) => e.key === "Enter" && commit()}
      />
    </div>
  );
}

/** Settings → AI instructions: what is sent to the model with every request, editable per task. */
export function PromptSettings() {
  const { t } = useI18n();
  const { meta } = useAppState();
  const [task, setTask] = useState<Task>("article");
  const layouts = INPUTS[task] ?? [];
  const limits = LIMITS[task] ?? [];

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.prompts")}</h2>
      <div className="settings-card">
        <div className="settings-row settings-row-block">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("settings.prompts.title")}</div>
            <div className="settings-row-hint">{t("settings.prompts.hint")}</div>
          </div>
          <Segmented<Task>
            label={t("settings.prompts.title")}
            value={task}
            onChange={setTask}
            options={TASKS.map((k) => ({ value: k, label: t(`settings.prompts.task.${k}`) }))}
          />
          <div className="settings-row-hint">{t(`settings.prompts.task.${task}Hint`)}</div>

          <TemplateEditor
            id={task}
            label={t(`settings.prompts.task.${task}`)}
            setting="ai.prompts"
            defaults={meta.ai_prompt_defaults}
            maxChars={MAX_CHARS}
            rows={16}
          />

          {layouts.map((kind) => (
            <TemplateEditor
              key={kind}
              id={kind}
              label={t((INPUT_TEXT[kind] ?? INPUT_TEXT.article!)[0])}
              hint={t((INPUT_TEXT[kind] ?? INPUT_TEXT.article!)[1])}
              setting="ai.inputs"
              defaults={meta.ai_input_defaults}
              maxChars={MAX_INPUT_CHARS}
              rows={4}
            />
          ))}

          {limits.length ? (
            <div className="prompt-block">
              <div className="settings-row-title">{t("settings.limits.title")}</div>
              <div className="settings-row-hint">{t("settings.limits.hint")}</div>
              <div className="limit-grid">
                {limits.map((name) => <LimitField key={name} name={name} />)}
              </div>
            </div>
          ) : (
            <div className="settings-row-hint">{t("settings.inputs.plain")}</div>
          )}
          <div className="settings-row-hint">{t("settings.prompts.scope")}</div>
        </div>
      </div>
    </section>
  );
}
