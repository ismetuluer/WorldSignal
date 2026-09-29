import { useEffect, useRef, useState, type RefObject } from "react";
import { Spinner, StateView } from "../components/controls";
import { useI18n } from "../i18n";
import { isTypingTarget } from "../lib/hooks";
import { useAppState } from "../state";

/** Filters shared by the stories and articles views of the feed. */
export interface FeedQuery {
  hours: number;
  q?: string;
  /** Translations of q (api.searchTranslations): a report matching any of them is found too. */
  qx?: string[];
  region: string[];
  group: string[];
  lang: string[];
  source: number[];
  category: string[];
  turkey: boolean;
}

/** Empty list: explains whether that is a search, a filter or the very first collection. */
export function FeedEmpty({
  query,
  filtersActive,
  onClearFilters,
  emptyTitle,
  emptyBody,
}: {
  query?: string;
  filtersActive: boolean;
  onClearFilters: () => void;
  /** Stories use their own wording for "nothing yet". */
  emptyTitle?: string;
  emptyBody?: string;
}) {
  const { t } = useI18n();
  const { status } = useAppState();
  const collector = status?.collector;
  const firstRun = !collector?.last_cycle_at || (collector.busy && (status?.articles.total ?? 0) === 0);

  if (query) {
    return <StateView icon="search" title={t("feed.empty.search.title", { q: query })} body={t("feed.empty.search.body")} />;
  }
  if (firstRun && !filtersActive) {
    return <StateView icon="signal" title={t("feed.empty.first.title")} body={t("feed.empty.first.body")} action={<Spinner />} />;
  }
  if (!filtersActive && emptyTitle) {
    return <StateView icon="signal" title={emptyTitle} body={emptyBody} />;
  }
  return (
    <StateView
      icon="inbox"
      title={t("feed.empty.filtered.title")}
      body={t("feed.empty.filtered.body")}
      action={filtersActive ? <button className="btn" onClick={onClearFilters}>{t("filter.clear")}</button> : undefined}
    />
  );
}

/**
 * J/K moves the selection through the list, Enter/O activates the selected card.
 * Items are found by their ``data-index`` attribute. Loads more when the selection nears the end.
 */
export function useListKeys(
  listRef: RefObject<HTMLElement | null>,
  count: number,
  loadMore: () => void,
  activate: (el: HTMLElement, index: number) => void,
  /** Extra single-letter shortcuts on the selected item (e.g. T = add to meeting). */
  extra: Record<string, (index: number) => void> = {},
): [number, (i: number) => void] {
  const extraRef = useRef(extra);
  extraRef.current = extra;
  const [selected, setSelected] = useState(-1);
  const activateRef = useRef(activate);
  activateRef.current = activate;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".backdrop")) return;
      if (isTypingTarget(e.target) || count === 0) return;
      const key = e.key.toLowerCase();
      if (key === "j" || key === "k") {
        e.preventDefault();
        setSelected((i) => (key === "j" ? Math.min(count - 1, i + 1) : Math.max(0, i - 1)));
      } else if ((key === "enter" || key === "o") && selected >= 0) {
        const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`);
        if (!el) return;
        e.preventDefault();
        activateRef.current(el, selected);
      } else if (selected >= 0 && extraRef.current[key]) {
        e.preventDefault();
        extraRef.current[key]!(selected);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, selected, listRef]);

  useEffect(() => {
    if (selected < 0) return;
    listRef.current?.querySelector(`[data-index="${selected}"]`)?.scrollIntoView({ block: "nearest" });
    if (selected >= count - 5) loadMore();
  }, [selected, count, loadMore, listRef]);

  // A reset (new list) clamps the selection.
  useEffect(() => {
    if (selected >= count) setSelected(count - 1);
  }, [count, selected]);

  return [selected, setSelected];
}
