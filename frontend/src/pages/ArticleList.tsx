import { Fragment, useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Article, ArticleQuery } from "../api/types";
import { ArticleCard } from "../components/ArticleCard";
import { useToast } from "../components/Toasts";
import { Banner, Spinner, StateView } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useMeeting } from "../components/meeting";
import { useAppState } from "../state";
import { FeedEmpty, useListKeys } from "./feedShared";

const PAGE_SIZE = 60;

/** The individual-articles view of the feed (newest first, infinite scroll). */
export function ArticleList({
  query: feedQuery,
  filtersActive,
  onClearFilters,
  onTotal,
}: {
  /** The feed passes its hours and filters; the history passes one day or a search over all days. */
  query: ArticleQuery;
  filtersActive: boolean;
  onClearFilters: () => void;
  onTotal: (total: number | null) => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const { status, refreshStatus } = useAppState();
  const toast = useToast();

  const [items, setItems] = useState<Article[]>([]);
  const [next, setNext] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [newCount, setNewCount] = useState(0);

  const requestId = useRef(0);
  const listRef = useRef<HTMLOListElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const loadedAtCycle = useRef<string | null>(null);

  const baseQuery: ArticleQuery = { ...feedQuery, limit: PAGE_SIZE };

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await api.articles({ ...feedQuery, limit: PAGE_SIZE });
      if (id !== requestId.current) return;
      setItems(page.items);
      setNext(page.next);
      onTotal(page.total);
      setNewCount(0);
      setSelected(-1);
      loadedAtCycle.current = status?.collector.last_cycle_at ?? null;
    } catch (e) {
      if (id === requestId.current) setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
    // status is read only to remember which cycle the list reflects.
  }, [feedQuery]);

  useEffect(() => {
    void load();
  }, [load]);

  // After each background fetch, check whether newer articles arrived.
  const lastCycle = status?.collector.last_cycle_at ?? null;
  useEffect(() => {
    if (!lastCycle || loading || lastCycle === loadedAtCycle.current) return;
    if (items.length === 0) {
      void load();
      return;
    }
    const known = new Set(items.map((a) => a.id));
    const top = items[0]?.sort_at ?? "";
    api.articles({ ...baseQuery, limit: 100, before: null }).then(
      (page) => setNewCount(page.items.filter((a) => !known.has(a.id) && a.sort_at >= top).length),
      () => undefined,
    );
    // Only re-run when a new cycle finishes.
  }, [lastCycle]);

  // When the AI finishes articles, refresh the Turkish fields of the loaded cards in place
  // (without reordering the list or adding new articles).
  const aiDone = status?.ai.done ?? 0;
  useEffect(() => {
    if (items.length === 0) return;
    const id = requestId.current;
    const timer = window.setTimeout(() => {
      api.articles({ ...baseQuery, limit: Math.min(500, items.length + 20), before: null }).then(
        (page) => {
          if (id !== requestId.current) return;
          const byId = new Map(page.items.map((a) => [a.id, a]));
          setItems((list) => list.map((a) => byId.get(a.id) ?? a));
        },
        () => undefined,
      );
    }, 1500);
    return () => window.clearTimeout(timer);
    // Only re-run when the AI completed more work.
  }, [aiDone]);

  const aiAvailable = !!status && status.ai.state !== "disabled" && status.ai.state !== "no_model";

  const requestAi = useCallback(
    async (article: Article) => {
      setItems((list) => list.map((a) => (a.id === article.id ? { ...a, ai_status: "pending" } : a)));
      try {
        await api.requestAi(article.id);
        toast.show(t("ai.requested"), "success");
        refreshStatus();
      } catch (e) {
        setItems((list) => list.map((a) => (a.id === article.id ? article : a)));
        toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
      }
    },
    [toast, t, i18n, refreshStatus],
  );

  const loadMore = useCallback(async () => {
    if (!next || loadingMore) return;
    const id = requestId.current;
    setLoadingMore(true);
    try {
      const page = await api.articles({ ...feedQuery, limit: PAGE_SIZE, before: next });
      if (id !== requestId.current) return;
      setItems((list) => [...list, ...page.items]);
      setNext(page.next);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      setLoadingMore(false);
    }
  }, [feedQuery, next, loadingMore]);

  // Infinite scroll.
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || !next) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) void loadMore();
    }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [next, loadMore]);

  // J/K move, Enter/O open the original, T adds the report to the meeting list.
  const meeting = useMeeting();
  const [selected, setSelected] = useListKeys(
    listRef,
    items.length,
    loadMore,
    (el) => el.querySelector<HTMLElement>(".article-title button, .article-title a")?.click(),
    meeting.available ? { meeting: (index) => items[index] && void meeting.toggleArticle(items[index].id) } : {},
  );

  let content: React.ReactNode;
  if (loading && items.length === 0) {
    content = <Skeletons label={t("common.loading")} />;
  } else if (error && items.length === 0) {
    content = (
      <StateView
        icon="alert"
        title={t("error.title")}
        body={describeError(i18n, error)}
        action={<button className="btn" onClick={() => void load()}>{t("common.retry")}</button>}
      />
    );
  } else if (items.length === 0) {
    content = <FeedEmpty query={feedQuery.q} filtersActive={filtersActive} onClearFilters={onClearFilters} />;
  } else {
    let lastDay = "";
    content = (
      <>
        <ol className="article-list" ref={listRef} aria-label={t("feed.title")}>
          {items.map((a, index) => {
            const day = i18n.dayLabel(a.sort_at);
            const showDay = day !== lastDay;
            lastDay = day;
            return (
              <Fragment key={a.id}>
                {showDay ? <li className="day-heading" aria-hidden="true">{day}</li> : null}
                <ArticleCard
                  article={a}
                  index={index}
                  selected={index === selected}
                  onSelect={setSelected}
                  onRequestAi={requestAi}
                  aiAvailable={aiAvailable}
                />
              </Fragment>
            );
          })}
        </ol>
        <div ref={sentinelRef} />
        <div className="list-footer">
          {loadingMore ? (
            <Spinner label={t("common.loading")} />
          ) : next ? (
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
      {error && items.length > 0 ? (
        <Banner kind="error" icon="alert" title={t("error.title")} body={describeError(i18n, error)} />
      ) : null}
      {newCount > 0 ? (
        <div className="new-arrivals">
          <button
            className="btn btn-primary"
            onClick={() => {
              void load();
              document.querySelector(".main")?.scrollTo({ top: 0 });
            }}
          >
            {plural("feed.newArrivals", newCount)}
          </button>
        </div>
      ) : null}
      {content}
    </>
  );
}

export function Skeletons({ label }: { label: string }) {
  return (
    <div className="article-list" aria-busy="true" aria-label={label}>
      {Array.from({ length: 6 }, (_, i) => (
        <div key={i} className="skeleton" />
      ))}
    </div>
  );
}
