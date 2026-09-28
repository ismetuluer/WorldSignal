import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ArticleQuery, HistoryDay, HistoryMoment, HistoryMonth, Story } from "../api/types";
import { Calendar, longDay } from "../components/Calendar";
import { Banner, SearchField, Segmented, Spinner, StateView } from "../components/controls";
import { useMeeting } from "../components/meeting";
import { StoryCard } from "../components/StoryCard";
import { StoryDetail } from "../components/StoryDetail";
import { describeError, useI18n } from "../i18n";
import { isTypingTarget, localDay, useDebounced } from "../lib/hooks";
import { useAppState } from "../state";
import { ArticleList } from "./ArticleList";
import { useListKeys } from "./feedShared";
import { StoryList } from "./StoryList";

const PAGE_SIZE = 30;
const NO_FILTERS = { region: [], group: [], lang: [], source: [], category: [], turkey: false };

/**
 * History: pick a day on the calendar and see its stories ranked as they were that morning (or at the
 * end of that day), or search every day at once.
 */
export function HistoryPage() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const today = localDay();
  const [day, setDay] = useState(today);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [calendar, setCalendar] = useState<HistoryMonth | null>(null);
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 250);
  const [searchKind, setSearchKind] = useState<"stories" | "articles">("stories");
  const [view, setView] = useState<"stories" | "articles">("stories");
  const searchRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api.historyMonth(month).then(setCalendar, () => setCalendar({ month, today, days: [] }));
  }, [month, today]);

  // "/" focuses the search box.
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

  const marks = useMemo(
    () =>
      new Map(
        (calendar?.days ?? []).map((d) => [
          d.day,
          d.stories > 0
            ? `${plural("stories.count", d.stories)} · ${plural("history.articles", d.articles)}`
            : plural("history.articles", d.articles),
        ]),
      ),
    [calendar, plural],
  );

  const pick = (d: string) => {
    setDay(d);
    setMonth(d.slice(0, 7));
    setSearch("");
  };

  const searchQuery = useMemo<ArticleQuery>(() => ({ ...NO_FILTERS, q }), [q]);
  const dayQuery = useMemo<ArticleQuery>(() => ({ ...NO_FILTERS, day }), [day]);

  return (
    <div className="page page-wide">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("history.title")}</h1>
          <p className="page-subtitle">{q ? t("history.searchAll", { q }) : longDay(i18n, day)}</p>
        </div>
        <div className="history-search">
          <SearchField ref={searchRef} value={search} onChange={setSearch} placeholder={t("history.searchPlaceholder")} />
        </div>
      </header>

      <div className="notebook">
        <Calendar
          label={t("history.calendar")}
          month={month}
          onMonth={setMonth}
          day={day}
          today={today}
          onPick={pick}
          marks={marks}
          footer={
            day !== today || q ? <button className="btn btn-sm" onClick={() => pick(today)}>{t("notebook.today")}</button> : null
          }
        />

        <div className="notebook-day">
          {q ? (
            <>
              <div className="list-options">
                <Segmented
                  label={t("history.searchKind")}
                  value={searchKind}
                  onChange={setSearchKind}
                  options={[
                    { value: "stories", label: t("feed.view.stories") },
                    { value: "articles", label: t("feed.view.articles") },
                  ]}
                />
              </div>
              {searchKind === "stories" ? (
                <StoryList query={searchQuery} filtersActive={false} onClearFilters={() => setSearch("")} onTotal={() => undefined} />
              ) : (
                <ArticleList query={searchQuery} filtersActive={false} onClearFilters={() => setSearch("")} onTotal={() => undefined} />
              )}
            </>
          ) : (
            <>
              <div className="list-options">
                <Segmented
                  label={t("history.view")}
                  value={view}
                  onChange={setView}
                  options={[
                    { value: "stories", label: t("feed.view.stories") },
                    { value: "articles", label: t("feed.view.articles") },
                  ]}
                />
              </div>
              {view === "stories" ? (
                <DayStories key={day} day={day} onShowArticles={() => setView("articles")} />
              ) : (
                <ArticleList query={dayQuery} filtersActive={false} onClearFilters={() => undefined} onTotal={() => undefined} />
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

/** One day's stories, ranked as they were at the chosen moment. */
function DayStories({ day, onShowArticles }: { day: string; onShowArticles: () => void }) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const { settings } = useAppState();
  const meeting = useMeeting();
  const [moment, setMoment] = useState<HistoryMoment>("morning");
  const [multiOnly, setMultiOnly] = useState(false);
  const [page, setPage] = useState<HistoryDay | null>(null);
  const [items, setItems] = useState<Story[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [openId, setOpenId] = useState<number | null>(null);
  const listRef = useRef<HTMLOListElement>(null);
  const requestId = useRef(0);
  const minSources = multiOnly ? 2 : 1;

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setPage(null);
    setError(null);
    try {
      const res = await api.historyDay(day, { moment, min_sources: minSources, limit: PAGE_SIZE, offset: 0 });
      if (id !== requestId.current) return;
      setPage(res);
      setItems(res.items);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof ApiError ? e.code : "generic");
    }
  }, [day, moment, minSources]);

  useEffect(() => {
    void load();
  }, [load]);

  const hasMore = !!page && items.length < page.total;
  const loadMore = useCallback(async () => {
    if (!hasMore || loadingMore) return;
    const id = requestId.current;
    setLoadingMore(true);
    try {
      const res = await api.historyDay(day, { moment, min_sources: minSources, limit: PAGE_SIZE, offset: items.length });
      if (id !== requestId.current) return;
      setItems((list) => {
        const known = new Set(list.map((s) => s.id));
        return [...list, ...res.items.filter((s) => !known.has(s.id))];
      });
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      setLoadingMore(false);
    }
  }, [hasMore, loadingMore, day, moment, minSources, items.length]);

  const [selected, setSelected] = useListKeys(
    listRef,
    items.length,
    () => void loadMore(),
    (_, index) => setOpenId(items[index]?.id ?? null),
    meeting.available ? { t: (index) => items[index] && void meeting.toggle(items[index].id) } : {},
  );

  const hour = String(settings["history.morning_hour"]).padStart(2, "0");
  let content: React.ReactNode;
  if (error && items.length === 0) {
    content = (
      <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)}
        action={<button className="btn" onClick={() => void load()}>{t("common.retry")}</button>} />
    );
  } else if (!page) {
    content = <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>;
  } else if (page.future) {
    content = <StateView icon="info" title={t("history.future.title")} body={t("history.future.body", { hour })} />;
  } else if (items.length === 0) {
    content = page.unclustered > 0 ? (
      <StateView
        icon="inbox"
        title={t("history.noStories.title")}
        body={plural("history.noStories.body", page.unclustered)}
        action={<button className="btn" onClick={onShowArticles}>{t("history.showArticles")}</button>}
      />
    ) : (
      <StateView icon="inbox" title={t("history.empty.title")} body={multiOnly ? t("history.empty.multi") : t("history.empty.body")} />
    );
  } else {
    content = (
      <>
        <ol className="article-list" ref={listRef} aria-label={t("history.ranking")}>
          {items.map((s, index) => (
            <StoryCard key={s.id} story={s} index={index} selected={index === selected} onSelect={setSelected}
              onOpen={(story) => setOpenId(story.id)} />
          ))}
        </ol>
        <div className="list-footer">
          {loadingMore ? (
            <Spinner label={t("common.loading")} />
          ) : hasMore ? (
            <button className="btn" onClick={() => void loadMore()}>{t("feed.loadMore")}</button>
          ) : (
            <span>{t("feed.end")}</span>
          )}
        </div>
      </>
    );
  }

  return (
    <>
      <div className="list-options">
        <Segmented
          label={t("history.moment")}
          value={moment}
          onChange={setMoment}
          options={[
            { value: "morning", label: t("history.moment.morning", { hour }) },
            { value: "day", label: t("history.moment.day") },
          ]}
        />
        <button type="button" className="chip" data-active={multiOnly} aria-pressed={multiOnly} onClick={() => setMultiOnly((v) => !v)}>
          {t("stories.multiOnly")}
        </button>
      </div>
      {page && !page.future ? (
        <p className="field-hint" role="status">
          {moment === "morning"
            ? t("history.asOf.morning", { time: i18n.dateTime(page.as_of), count: plural("stories.count", page.total) })
            : t("history.asOf.day", { count: plural("stories.count", page.total) })}
          {page.unclustered > 0 && items.length > 0 ? ` · ${plural("history.unclustered", page.unclustered)}` : ""}
        </p>
      ) : null}
      {error && items.length > 0 ? <Banner kind="error" icon="alert" title={t("error.title")} body={describeError(i18n, error)} /> : null}
      {content}
      {openId !== null ? <StoryDetail storyId={openId} onClose={() => setOpenId(null)} onChanged={() => void load()} /> : null}
    </>
  );
}
