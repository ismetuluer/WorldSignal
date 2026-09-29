import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api/client";
import type { FeedFilters, Source } from "../api/types";
import { AiBanner, StoryBanner } from "../components/AiBanner";
import { BulletinDialog } from "../components/BulletinDialog";
import { Icon } from "../components/Icon";
import { MultiSelect } from "../components/MultiSelect";
import { Banner, SearchField, Segmented } from "../components/controls";
import { SearchLanguagesNote } from "../components/SearchLanguages";
import { useI18n } from "../i18n";
import { isTypingTarget, useDebounced } from "../lib/hooks";
import { useSearchTranslations } from "../lib/searchTranslations";
import { useAppState } from "../state";
import { ArticleList } from "./ArticleList";
import { type FeedQuery } from "./feedShared";
import { StoryList } from "./StoryList";

const WINDOWS = [6, 24, 72, 168] as const;

type Filters = FeedFilters;

const NO_FILTERS: Filters = { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false };

export function FeedPage() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const { settings, updateSettings, status, meta } = useAppState();

  const [hours, setHours] = useState<number>(settings["feed.window_hours"]);
  const [search, setSearch] = useState("");
  const query = useDebounced(search.trim(), 250);
  // Filters are remembered between sessions (setting "feed.filters").
  const [filters, setFiltersState] = useState<Filters>(() => ({ ...NO_FILTERS, ...settings["feed.filters"] }));
  const [sources, setSources] = useState<Source[]>([]);
  const setFilters = (change: Filters | ((f: Filters) => Filters)) => {
    const next = typeof change === "function" ? change(filters) : change;
    setFiltersState(next);
    updateSettings({ "feed.filters": next }).catch(() => undefined);
  };

  const view = settings["feed.view"];
  const homeOn = settings["home.enabled"];
  const [total, setTotal] = useState<number | null>(null);
  const searchRef = useRef<HTMLInputElement>(null);
  const [bulletin, setBulletin] = useState(false);

  useEffect(() => {
    api.sources().then(setSources, () => undefined);
  }, [status?.collector.last_cycle_at]);

  // A remembered source that was deleted since would silently empty the feed: forget it.
  useEffect(() => {
    if (!sources.length || !filters.sources.length) return;
    const known = new Set(sources.map((s) => s.id));
    if (filters.sources.some((id) => !known.has(id))) {
      setFilters((f) => ({ ...f, sources: f.sources.filter((id) => known.has(id)) }));
    }
  }, [sources]);

  // "/" focuses the search box (J/K and Enter are handled by the list).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".backdrop")) return;
      if (e.key === "/" && !isTypingTarget(e.target)) {
        e.preventDefault();
        searchRef.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const languages = useSearchTranslations(query);
  const feedQuery = useMemo<FeedQuery>(
    () => ({
      hours,
      q: query || undefined,
      qx: languages.phrases,
      region: filters.regions,
      group: filters.groups,
      lang: filters.langs,
      source: filters.sources,
      category: filters.categories,
      turkey: homeOn && filters.turkey,
    }),
    [hours, query, languages.phrases, filters, homeOn],
  );

  const changeView = (v: "stories" | "articles") => {
    setTotal(null);
    updateSettings({ "feed.view": v }).catch(() => undefined);
  };

  const changeHours = (h: number) => {
    setHours(h);
    updateSettings({ "feed.window_hours": h }).catch(() => undefined);
  };

  const filtersActive =
    (homeOn && filters.turkey) ||
    filters.regions.length + filters.groups.length + filters.langs.length + filters.sources.length + filters.categories.length > 0;

  const sourceOptions = useMemo(
    () =>
      sources
        .filter((s) => s.enabled)
        .map((s) => ({ value: s.id, label: s.name, hint: s.articles_24h ? String(s.articles_24h) : undefined }))
        .sort((a, b) => a.label.localeCompare(b.label, i18n.locale)),
    [sources, i18n.locale],
  );

  const windowLabel = (h: number) =>
    h % 24 === 0 && h >= 48 ? t("feed.window.days", { n: h / 24 }) : t("feed.window.hours", { n: h });

  const collector = status?.collector;

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("feed.title")}</h1>
          <p className="page-subtitle">
            {total === null
              ? t("common.loading")
              : `${plural(view === "stories" ? "stories.count" : "feed.count", total)} · ${windowLabel(hours)}`}
          </p>
        </div>
        <div className="header-actions header-actions-stack">
          <button className="btn" onClick={() => setBulletin(true)}>
            <Icon name="print" size={16} />
            {t("bulletin.open")}
          </button>
          <span className="field-hint">{t("feed.shortcutHint")}</span>
        </div>
      </header>
      {bulletin ? <BulletinDialog onClose={() => setBulletin(false)} /> : null}

      {collector?.offline ? (
        <Banner icon="offline" title={t("status.offline.title")} body={t("status.offline.body")} />
      ) : null}
      <AiBanner />
      {view === "stories" ? <StoryBanner /> : null}

      <div className="toolbar">
        <Segmented
          label={t("feed.view")}
          value={view}
          onChange={changeView}
          options={[
            { value: "stories" as const, label: t("feed.view.stories") },
            { value: "articles" as const, label: t("feed.view.articles") },
          ]}
        />
        <SearchField ref={searchRef} value={search} onChange={setSearch} placeholder={t("feed.searchPlaceholder")} shortcut="/" />
        <Segmented
          label={t("feed.window")}
          value={hours}
          onChange={changeHours}
          options={WINDOWS.map((h) => ({ value: h, label: windowLabel(h) }))}
        />
        <div className="filter-row">
          <MultiSelect
            label={t("filter.region")}
            options={meta.regions.map((r) => ({ value: r, label: t(`region.${r}`) }))}
            selected={filters.regions}
            onChange={(regions) => setFilters((f) => ({ ...f, regions }))}
          />
          <MultiSelect
            label={t("filter.group")}
            options={[...meta.groups, ...meta.kinds].map((g) => ({ value: g, label: t(`group.${g}`) }))}
            selected={filters.groups}
            onChange={(groups) => setFilters((f) => ({ ...f, groups }))}
          />
          <MultiSelect
            label={t("filter.language")}
            options={meta.languages.map((l) => ({ value: l, label: i18n.languageName(l) }))}
            selected={filters.langs}
            onChange={(langs) => setFilters((f) => ({ ...f, langs }))}
          />
          <MultiSelect
            label={t("filter.category")}
            options={meta.categories.map((c) => ({ value: c, label: t(`category.${c}`) }))}
            selected={filters.categories}
            onChange={(categories) => setFilters((f) => ({ ...f, categories }))}
          />
          {homeOn ? (
            <button
              type="button"
              className="chip"
              data-active={filters.turkey}
              aria-pressed={filters.turkey}
              onClick={() => setFilters((f) => ({ ...f, turkey: !f.turkey }))}
            >
              {t("filter.turkey")}
            </button>
          ) : null}
          <MultiSelect
            label={t("filter.source")}
            options={sourceOptions}
            selected={filters.sources}
            onChange={(ids) => setFilters((f) => ({ ...f, sources: ids }))}
            searchable
            searchPlaceholder={t("filter.searchSources")}
          />
          {filtersActive ? (
            <button className="btn btn-ghost btn-sm" onClick={() => setFilters(NO_FILTERS)}>
              {t("filter.clear")}
            </button>
          ) : null}
        </div>
      </div>
      <SearchLanguagesNote languages={languages} />

      {view === "stories" ? (
        <StoryList query={feedQuery} filtersActive={filtersActive} onClearFilters={() => setFilters(NO_FILTERS)} onTotal={setTotal} />
      ) : (
        <ArticleList query={feedQuery} filtersActive={filtersActive} onClearFilters={() => setFilters(NO_FILTERS)} onTotal={setTotal} />
      )}
    </div>
  );
}
