import { useEffect, useRef, useState, type RefObject } from "react";
import { Spinner, StateView } from "../components/controls";
import { useI18n } from "../i18n";
import { isTypingTarget } from "../lib/hooks";
import { keyOf, useShortcuts, type ShortcutAction } from "../lib/shortcuts";
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
 * The "next" / "previous" keys (J / K by default) move the selection through the list, the "open" keys (Enter / O)
 * activate the selected card.
 * Items are found by their ``data-index`` attribute. Loads more when the selection nears the end.
 */
export function useListKeys(
  listRef: RefObject<HTMLElement | null>,
  count: number,
  loadMore: () => void,
  activate: (el: HTMLElement, index: number) => void,
  /** Extra actions on the selected item, by shortcut action (e.g. meeting = add to the meeting list). */
  extra: Partial<Record<ShortcutAction, (index: number) => void>> = {},
): [number, (i: number) => void] {
  const extraRef = useRef(extra);
  extraRef.current = extra;
  const [selected, setSelected] = useState(-1);
  const keys = useShortcuts();
  const activateRef = useRef(activate);
  activateRef.current = activate;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || document.querySelector(".backdrop")) return;
      if (isTypingTarget(e.target) || count === 0) return;
      const key = keyOf(e);
      if (key === null) return;
      if (keys.next.includes(key) || keys.prev.includes(key)) {
        e.preventDefault();
        const forward = keys.next.includes(key);
        setSelected((i) => (forward ? Math.min(count - 1, i + 1) : Math.max(0, i - 1)));
      } else if (keys.open.includes(key) && selected >= 0) {
        const el = listRef.current?.querySelector<HTMLElement>(`[data-index="${selected}"]`);
        if (!el) return;
        e.preventDefault();
        activateRef.current(el, selected);
      } else if (selected >= 0) {
        const action = (Object.keys(extraRef.current) as ShortcutAction[]).find((a) => keys[a]?.includes(key));
        if (!action) return;
        e.preventDefault();
        extraRef.current[action]?.(selected);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [count, selected, listRef, keys]);

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
