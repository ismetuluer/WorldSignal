import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Story, StoryQuery } from "../api/types";
import { StoryCard } from "../components/StoryCard";
import { StoryDetail } from "../components/StoryDetail";
import { useMeeting } from "../components/meeting";
import { Banner, Segmented, Spinner, StateView } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { Skeletons } from "./ArticleList";
import { FeedEmpty, useListKeys } from "./feedShared";

const PAGE_SIZE = 30;
const REFRESH_DELAY_MS = 2500;

/** The stories view of the feed: events ranked by importance score. */
export function StoryList({
  query: feedQuery,
  filtersActive,
  onClearFilters,
  onTotal,
  defaultSort = "score",
}: {
  /** The breaking-news page lists the newest first. */
  defaultSort?: "score" | "recent";
  /** The feed passes its hours and filters; the history passes a search over all days. */
  query: Omit<StoryQuery, "sort" | "min_sources" | "limit" | "offset">;
  filtersActive: boolean;
  onClearFilters: () => void;
  onTotal: (total: number | null) => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const { status } = useAppState();

  const [sort, setSort] = useState<"score" | "recent">(defaultSort);
  const [multiOnly, setMultiOnly] = useState(false);
  const [items, setItems] = useState<Story[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<{ items: Story[]; total: number } | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);

  const requestId = useRef(0);
  const listRef = useRef<HTMLOListElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const query: StoryQuery = { ...feedQuery, sort, min_sources: multiOnly ? 2 : 1 };
  const queryKey = JSON.stringify(query);

  const apply = (page: { items: Story[]; total: number }) => {
    setItems(page.items);
    setTotal(page.total);
    onTotal(page.total);
    setPending(null);
  };

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true);
    setError(null);
    try {
      const page = await api.stories({ ...query, limit: PAGE_SIZE, offset: 0 });
      if (id !== requestId.current) return;
      apply(page);
    } catch (e) {
      if (id === requestId.current) setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      if (id === requestId.current) setLoading(false);
    }
  }, [queryKey]);

  useEffect(() => {
    void load();
  }, [load]);

  // Stories change in the background (new reports, rescoring, AI summaries). Refresh the loaded
  // window: update cards in place when the order is unchanged, otherwise offer the new order
  // instead of reshuffling the list under the reader.
  const progress = `${status?.stories.clustered ?? 0}/${status?.ai.done ?? 0}`;
  useEffect(() => {
    if (loading) return;
    if (items.length === 0) {
      // Nothing to reshuffle: show the first stories as soon as they exist.
      void load();
      return;
    }
    const id = requestId.current;
    const timer = window.setTimeout(() => {
      api.stories({ ...query, limit: Math.min(200, Math.max(PAGE_SIZE, items.length)), offset: 0 }).then(
        (page) => {
          if (id !== requestId.current) return;
          const same = page.items.length === items.length && page.items.every((s, i) => s.id === items[i]?.id);
          if (same) {
            setItems(page.items);
            setTotal(page.total);
            onTotal(page.total);
          } else {
            const byId = new Map(page.items.map((s) => [s.id, s]));
            setItems((list) => list.map((s) => byId.get(s.id) ?? s));
            setPending(page);
          }
        },
        () => undefined,
      );
    }, REFRESH_DELAY_MS);
    return () => window.clearTimeout(timer);
    // Only re-run when background work progressed.
  }, [progress]);

  const loadMore = useCallback(async () => {
    if (loadingMore || items.length >= total) return;
    const id = requestId.current;
    setLoadingMore(true);
    try {
      const page = await api.stories({ ...query, limit: PAGE_SIZE, offset: items.length });
      if (id !== requestId.current) return;
      setItems((list) => {
        const known = new Set(list.map((s) => s.id));
        return [...list, ...page.items.filter((s) => !known.has(s.id))];
      });
      setTotal(page.total);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      setLoadingMore(false);
    }
  }, [queryKey, items.length, total, loadingMore]);

  useEffect(() => {
    const el = sentinelRef.current;
    if (!el || items.length >= total) return;
    const io = new IntersectionObserver((entries) => {
      if (entries.some((e) => e.isIntersecting)) void loadMore();
    }, { rootMargin: "600px" });
    io.observe(el);
    return () => io.disconnect();
  }, [items.length, total, loadMore]);

  const meeting = useMeeting();
  const [selected, setSelected] = useListKeys(
    listRef,
    items.length,
    loadMore,
    (_, index) => setOpenId(items[index]?.id ?? null),
    meeting.available ? { meeting: (index) => items[index] && void meeting.toggle(items[index].id) } : {},
  );

  const hasMore = items.length < total;
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
    content = (
      <FeedEmpty
        query={feedQuery.q}
        filtersActive={filtersActive || multiOnly}
        onClearFilters={() => {
          setMultiOnly(false);
          onClearFilters();
        }}
        emptyTitle={t("stories.empty.title")}
        emptyBody={t("stories.empty.body")}
      />
    );
  } else {
    content = (
      <>
        <ol className="article-list" ref={listRef} aria-label={t("feed.view.stories")}>
          {items.map((s, index) => (
            <StoryCard
              key={s.id}
              story={s}
              index={index}
              selected={index === selected}
              onSelect={setSelected}
              onOpen={(story) => setOpenId(story.id)}
            />
          ))}
        </ol>
        <div ref={sentinelRef} />
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
      {error && items.length > 0 ? (
        <Banner kind="error" icon="alert" title={t("error.title")} body={describeError(i18n, error)} />
      ) : null}
      <div className="list-options">
        <Segmented
          label={t("stories.sort")}
          value={sort}
          onChange={setSort}
          options={[
            { value: "score", label: t("stories.sort.score") },
            { value: "recent", label: t("stories.sort.recent") },
          ]}
        />
        <button type="button" className="chip" data-active={multiOnly} aria-pressed={multiOnly} onClick={() => setMultiOnly((v) => !v)}>
          {t("stories.multiOnly")}
        </button>
      </div>
      {pending ? (
        <div className="new-arrivals">
          <button
            className="btn btn-primary"
            onClick={() => {
              apply(pending);
              setSelected(-1);
              document.querySelector(".main")?.scrollTo({ top: 0 });
            }}
          >
            {t("stories.reordered", { count: plural("stories.count", pending.total) })}
          </button>
        </div>
      ) : null}
      {content}
      {openId !== null ? (
        <StoryDetail storyId={openId} onClose={() => setOpenId(null)} onChanged={() => void load()} />
      ) : null}
    </>
  );
}
