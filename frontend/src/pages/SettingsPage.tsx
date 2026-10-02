import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { Settings, ThemeSetting, UiLanguage } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Segmented, SearchField } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { useAppState } from "../state";
import { AiSettings } from "./AiSettings";
import { LookSettings } from "./LookSettings";
import { PromptSettings } from "./PromptSettings";
import { ShortcutSettings } from "./ShortcutSettings";
import { FullTextSettings } from "./FullTextSettings";
import { BackgroundSettings } from "./BackgroundSettings";
import { BackupSettings } from "./BackupSettings";
import { UpdateSettings } from "../components/Update";
import { HistorySettings } from "./HistorySettings";
import { HomeSettings } from "./HomeSettings";
import { StorySettings } from "./StorySettings";

const LANGUAGE_LABELS: Record<UiLanguage, string> = { tr: "Türkçe", en: "English" };

const CATEGORY_KEY = "worldsignal.settings.category";
type CategoryId = "general" | "collect" | "ai" | "fulltext" | "archive" | "system";
const CATEGORIES: { id: CategoryId; label: MessageKey }[] = [
  { id: "general", label: "settings.cat.general" },
  { id: "collect", label: "settings.cat.collect" },
  { id: "ai", label: "settings.cat.ai" },
  { id: "fulltext", label: "settings.cat.fulltext" },
  { id: "archive", label: "settings.cat.archive" },
  { id: "system", label: "settings.cat.system" },
];

function savedCategory(): CategoryId {
  try {
    const id = localStorage.getItem(CATEGORY_KEY);
    return CATEGORIES.some((c) => c.id === id) ? (id as CategoryId) : "general";
  } catch {
    return "general";
  }
}

/** Search: hide every row (and group) that does not mention the words; returns how many groups are left. */
function filterGroups(root: HTMLElement, query: string): number {
  const words = query.toLocaleLowerCase("tr").split(/\s+/).filter(Boolean);
  const textOf = (el: Element, selector: string) =>
    [...el.querySelectorAll(selector)].map((n) => n.textContent ?? "").join(" ").toLocaleLowerCase("tr");
  let shown = 0;
  root.querySelectorAll<HTMLElement>(".settings-group").forEach((group) => {
    const title = textOf(group, ".section-title");
    const rows = [...group.querySelectorAll<HTMLElement>(".settings-row")];
    let visible = 0;
    for (const row of rows) {
      const text = `${title} ${textOf(row, ".settings-row-title, .settings-row-hint, .subsection-title, label, button")}`;
      const match = words.every((w) => text.includes(w));
      row.hidden = !match;
      if (match) visible += 1;
    }
    const whole = rows.length === 0 && words.every((w) => (group.textContent ?? "").toLocaleLowerCase("tr").includes(w));
    group.hidden = visible === 0 && !whole;
    if (!group.hidden) shown += 1;
  });
  return shown;
}

export function SettingsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, meta } = useAppState();

  const change = (patch: Partial<Settings>) => {
    updateSettings(patch).catch((e: unknown) =>
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    );
  };

  const [category, setCategory] = useState<CategoryId>(savedCategory);
  const [query, setQuery] = useState("");
  const [shown, setShown] = useState(1);
  const content = useRef<HTMLDivElement>(null);
  const searching = query.trim() !== "";

  const choose = (id: CategoryId) => {
    setCategory(id);
    setQuery("");
    try {
      localStorage.setItem(CATEGORY_KEY, id);
    } catch {
      // the choice is only a convenience; without storage it starts at "General" next time
    }
  };

  const pages: Record<CategoryId, ReactNode> = {
    general: (
      <>
      <section className="settings-group">
        <h2 className="section-title">{t("settings.appearance")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.theme")}</div>
            </div>
            <Segmented<ThemeSetting>
              label={t("settings.theme")}
              value={settings["ui.theme"]}
              onChange={(v) => change({ "ui.theme": v })}
              options={[
                { value: "system", label: t("settings.theme.system") },
                { value: "light", label: t("settings.theme.light") },
                { value: "dark", label: t("settings.theme.dark") },
              ]}
            />
          </div>
          <LookSettings />
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.language")}</div>
              <div className="settings-row-hint">{t("settings.languageHint")}</div>
            </div>
            <Segmented<UiLanguage>
              label={t("settings.language")}
              value={settings["ui.language"]}
              onChange={(v) => change({ "ui.language": v })}
              options={meta.ui_languages.map((l) => ({ value: l, label: LANGUAGE_LABELS[l] ?? l }))}
            />
          </div>
        </div>
      </section>
        <ShortcutSettings />
      </>
    ),
    collect: (
      <>
        <HomeSettings />
        <StorySettings />
      </>
    ),
    ai: (
      <>
        <AiSettings />
        <PromptSettings />
      </>
    ),
    fulltext: <FullTextSettings />,
    archive: (
      <>
        <HistorySettings />
        <BackupSettings />
      </>
    ),
    system: (
      <>
        <BackgroundSettings />
        <UpdateSettings />
      <section className="settings-group">
        <h2 className="section-title">{t("settings.data")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.dataDir")}</div>
              <div className="path">{meta.data_dir}</div>
              <div className="settings-row-hint">{t("settings.dataDirHint")}</div>
            </div>
            <button
              className="btn"
              onClick={() =>
                api.openDataDir().catch((e: unknown) =>
                  toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
                )
              }
            >
              <Icon name="folder" size={16} />
              {t("settings.openDataDir")}
            </button>
          </div>
        </div>
      </section>
      <section className="settings-group">
        <h2 className="section-title">{t("settings.about")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-title">{t("app.name")}</div>
            <span className="settings-row-hint">{t("settings.version", { version: meta.version })}</span>
          </div>
        </div>
      </section>
      </>
    ),
  };

  // While searching every category is drawn and the rows that do not match are hidden.
  useEffect(() => {
    if (!searching || !content.current) return;
    const root = content.current;
    const run = () => setShown(filterGroups(root, query));
    run();
    const watch = new MutationObserver(run);
    watch.observe(root, { childList: true, subtree: true });
    return () => watch.disconnect();
  }, [query, searching]);

  return (
    <div className="page page-wide">
      <header className="page-header">
        <h1 className="page-title">{t("settings.title")}</h1>
        <div className="settings-search">
          <SearchField value={query} onChange={setQuery} placeholder={t("settings.search")} />
        </div>
      </header>

      <div className="settings-layout">
        <nav className="settings-nav" aria-label={t("settings.categories")}>
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              className={`settings-nav-item${!searching && c.id === category ? " active" : ""}`}
              aria-current={!searching && c.id === category ? "page" : undefined}
              onClick={() => choose(c.id)}
            >
              {t(c.label)}
            </button>
          ))}
        </nav>
        <div className="settings-content" ref={content}>
          {searching ? CATEGORIES.map((c) => <div key={c.id}>{pages[c.id]}</div>) : pages[category]}
          {searching && shown === 0 ? <p className="field-hint">{t("settings.searchEmpty", { query: query.trim() })}</p> : null}
        </div>
      </div>
    </div>
  );
}
