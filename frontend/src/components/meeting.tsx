import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { api, ApiError } from "../api/client";
import type { MeetingItem } from "../api/types";
import { describeError, useI18n } from "../i18n";
import { useToast } from "./Toasts";

interface MeetingApi {
  /** False outside a MeetingProvider (e.g. isolated page tests): meeting controls are hidden. */
  available: boolean;
  day: string | null;
  items: MeetingItem[];
  loaded: boolean;
  error: string | null;
  has: (storyId: number) => boolean;
  hasArticle: (articleId: number) => boolean;
  toggle: (storyId: number) => Promise<void>;
  /** The same for one report (a story is not needed). */
  toggleArticle: (articleId: number) => Promise<void>;
  remove: (itemId: number) => Promise<void>;
  reorder: (ids: number[]) => Promise<void>;
  setComment: (itemId: number, comment: string) => Promise<void>;
  reload: () => Promise<void>;
}

const MeetingContext = createContext<MeetingApi>({
  available: false,
  day: null,
  items: [],
  loaded: false,
  error: null,
  has: () => false,
  hasArticle: () => false,
  toggle: async () => undefined,
  toggleArticle: async () => undefined,
  remove: async () => undefined,
  reorder: async () => undefined,
  setComment: async () => undefined,
  reload: async () => undefined,
});

/** Today's meeting list, shared by the feed (add/remove), story details and the meeting page. */
export function MeetingProvider({ children }: { children: ReactNode }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const [day, setDay] = useState<string | null>(null);
  const [items, setItems] = useState<MeetingItem[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const itemsRef = useRef(items);
  itemsRef.current = items;

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  const reload = useCallback(async () => {
    try {
      const list = await api.meeting();
      setDay(list.today);
      setItems(list.items);
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    } finally {
      setLoaded(true);
    }
  }, []);

  useEffect(() => {
    void reload();
    // A new day starts a new list: re-check when the window comes back.
    const onFocus = () => void reload();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [reload]);

  // Adds the item when it is not on the list, removes it when it is (a story or one report).
  const flip = useCallback(
    async (find: (i: MeetingItem) => boolean, add: () => Promise<MeetingItem>) => {
      const existing = itemsRef.current.find(find);
      try {
        if (existing) {
          await api.removeMeetingItem(existing.id);
          setItems((list) => list.filter((i) => i.id !== existing.id));
          toast.show(t("meeting.removed"), "success");
        } else {
          const item = await add();
          setItems((list) => (list.some((i) => i.id === item.id) ? list : [...list, item]));
          toast.show(t("meeting.added"), "success");
        }
      } catch (e) {
        fail(e);
        void reload();
      }
    },
    [toast, t, fail, reload],
  );
  const toggle = useCallback((storyId: number) => flip((i) => i.story_id === storyId, () => api.addToMeeting(storyId)), [flip]);
  const toggleArticle = useCallback(
    (articleId: number) => flip((i) => i.article_id === articleId, () => api.addArticleToMeeting(articleId)),
    [flip],
  );

  const remove = useCallback(
    async (itemId: number) => {
      try {
        await api.removeMeetingItem(itemId);
        setItems((list) => list.filter((i) => i.id !== itemId));
      } catch (e) {
        fail(e);
        void reload();
      }
    },
    [fail, reload],
  );

  const reorder = useCallback(
    async (ids: number[]) => {
      const before = itemsRef.current;
      const byId = new Map(before.map((i) => [i.id, i]));
      setItems(ids.map((id) => byId.get(id)).filter((i): i is MeetingItem => !!i)); // optimistic
      try {
        const list = await api.reorderMeeting(day ?? "", ids);
        setItems(list.items);
      } catch (e) {
        setItems(before);
        fail(e);
        void reload();
      }
    },
    [day, fail, reload],
  );

  const setComment = useCallback(async (itemId: number, comment: string) => {
    const item = await api.updateMeetingItem(itemId, comment); // errors go to the caller (autosave retries)
    setItems((list) => list.map((i) => (i.id === itemId ? { ...i, comment: item.comment } : i)));
  }, []);

  const value = useMemo<MeetingApi>(
    () => ({
      available: true,
      day,
      items,
      loaded,
      error,
      has: (storyId) => items.some((i) => i.story_id === storyId),
      hasArticle: (articleId) => items.some((i) => i.article_id === articleId),
      toggle,
      toggleArticle,
      remove,
      reorder,
      setComment,
      reload,
    }),
    [day, items, loaded, error, toggle, toggleArticle, remove, reorder, setComment, reload],
  );
  return <MeetingContext.Provider value={value}>{children}</MeetingContext.Provider>;
}

export function useMeeting(): MeetingApi {
  return useContext(MeetingContext);
}
