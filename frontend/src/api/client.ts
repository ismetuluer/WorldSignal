import type {
  ArticlePage,
  UpdateStatus,
  BackupInfo,
  BackupList,
  BrowserList,
  ExtensionInfo,
  FullText,
  FullTextSite,
  HistoryDay,
  HistoryMoment,
  HistoryMonth,
  ArticleQuery,
  FeedPatch,
  FeedTestResult,
  MeetingItem,
  MeetingList,
  CloudProvider,
  CloudTestResult,
  HomeInfo,
  Meta,
  NotebookDay,
  NotebookMonth,
  OllamaTestResult,
  SearchTranslations,
  Settings,
  Source,
  SourceInput,
  StatsHours,
  StatsOverview,
  TopicStats,
  SourcePatch,
  Status,
  Story,
  StoryNote,
  StoryPage,
  StoryQuery,
} from "./types";

const TOKEN_KEY = "worldsignal.token";

/** Error with a machine-readable code that the UI translates. */
export class ApiError extends Error {
  constructor(
    public readonly code: string,
    public readonly status: number,
    message = code,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/**
 * The desktop window opens `/?t=<token>`. The token is moved to
 * sessionStorage and removed from the address so it does not linger in
 * history. In development (Vite) a fixed token comes from VITE_DEV_TOKEN.
 */
export function initToken(): string | null {
  const url = new URL(window.location.href);
  const fromUrl = url.searchParams.get("t");
  if (fromUrl) {
    sessionStorage.setItem(TOKEN_KEY, fromUrl);
    url.searchParams.delete("t");
    window.history.replaceState(null, "", url.pathname + url.search + url.hash);
    return fromUrl;
  }
  return sessionStorage.getItem(TOKEN_KEY) ?? (import.meta.env.VITE_DEV_TOKEN as string | undefined) ?? null;
}

let token: string | null = null;

export function setToken(value: string | null): void {
  token = value;
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let resp: Response;
  try {
    resp = await fetch(`/api${path}`, {
      method,
      headers: {
        ...(token ? { "X-WorldSignal-Token": token } : {}),
        ...(body !== undefined ? { "Content-Type": "application/json" } : {}),
      },
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
  } catch {
    throw new ApiError("server_unreachable", 0);
  }
  if (resp.status === 204) return undefined as T;
  let data: unknown = null;
  try {
    data = await resp.json();
  } catch {
    if (!resp.ok) throw new ApiError(`http_${resp.status}`, resp.status);
  }
  if (!resp.ok) {
    const detail = (data as { detail?: unknown } | null)?.detail;
    if (resp.status === 422) throw new ApiError("validation", 422);
    if (detail && typeof detail === "object" && "code" in detail) {
      throw new ApiError(String((detail as { code: unknown }).code), resp.status);
    }
    throw new ApiError(`http_${resp.status}`, resp.status);
  }
  return data as T;
}

function query(params: Record<string, unknown>): string {
  const qs = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    if (Array.isArray(value)) value.forEach((v) => qs.append(key, String(v)));
    else qs.set(key, String(value));
  }
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const api = {
  status: () => request<Status>("GET", "/status"),
  meta: () => request<Meta>("GET", "/meta"),
  home: () => request<HomeInfo>("GET", "/home"),
  settings: () => request<Settings>("GET", "/settings"),
  updateSettings: (patch: Partial<Settings>) => request<Settings>("PATCH", "/settings", patch),

  articles: (q: ArticleQuery) =>
    request<ArticlePage>("GET", `/articles${query({ ...q, turkey: q.turkey ? "true" : undefined })}`),
  stats: (hours: StatsHours) => request<StatsOverview>("GET", `/stats${query({ hours })}`),
  topicStats: (hours: StatsHours, q: string, qx: string[]) =>
    request<TopicStats>("GET", `/stats/topic${query({ hours, q, qx })}`),
  searchTranslations: (q: string) => request<SearchTranslations>("GET", `/search/translations${query({ q })}`),
  requestAi: (articleId: number) => request<{ status: string }>("POST", `/articles/${articleId}/ai`),
  testOllama: (url: string) => request<OllamaTestResult>("POST", "/ai/test", { url }),
  /** Which cloud services have an API key (the keys themselves are never sent back). */
  aiKeys: () => request<Record<CloudProvider, boolean>>("GET", "/ai/keys"),
  setAiKey: (provider: CloudProvider, key: string) => request<Record<CloudProvider, boolean>>("PUT", `/ai/keys/${provider}`, { key }),
  deleteAiKey: (provider: CloudProvider) => request<Record<CloudProvider, boolean>>("DELETE", `/ai/keys/${provider}`),
  testCloud: (provider: CloudProvider, url?: string) =>
    request<CloudTestResult>("POST", "/ai/cloud/test", url ? { provider, url } : { provider }),
  retryAi: () => request<{ requeued: number }>("POST", "/ai/retry"),

  stories: (q: StoryQuery) =>
    request<StoryPage>("GET", `/stories${query({ ...q, turkey: q.turkey ? "true" : undefined })}`),
  story: (id: number) => request<Story>("GET", `/stories/${id}`),
  detachArticle: (articleId: number) =>
    request<{ story_id: number; previous_story_id: number | null }>("POST", `/articles/${articleId}/detach`),
  mergeStories: (storyId: number, into: number) => request<Story>("POST", `/stories/${storyId}/merge`, { into }),
  summarizeStory: (storyId: number) => request<{ status: string }>("POST", `/stories/${storyId}/summarize`),

  storyNote: (storyId: number) => request<{ note: StoryNote | null }>("GET", `/stories/${storyId}/note`),
  saveStoryNote: (storyId: number, body: string) =>
    request<{ note: StoryNote | null }>("PUT", `/stories/${storyId}/note`, { body }),
  meeting: (day?: string) => request<MeetingList>("GET", `/meeting${query({ day })}`),
  addToMeeting: (storyId: number) => request<MeetingItem>("POST", "/meeting", { story_id: storyId }),
  updateMeetingItem: (itemId: number, comment: string) => request<MeetingItem>("PATCH", `/meeting/${itemId}`, { comment }),
  removeMeetingItem: (itemId: number) => request<void>("DELETE", `/meeting/${itemId}`),
  reorderMeeting: (day: string, ids: number[]) => request<MeetingList>("PUT", "/meeting/order", { day, ids }),
  notebookMonth: (month: string) => request<NotebookMonth>("GET", `/notebook${query({ month })}`),
  notebookDay: (day: string) => request<NotebookDay>("GET", `/notebook/${day}`),
  saveDayNote: (day: string, body: string) =>
    request<{ day_note: NotebookDay["day_note"] }>("PUT", `/notebook/${day}/note`, { body }),

  historyMonth: (month: string) => request<HistoryMonth>("GET", `/history${query({ month })}`),
  historyDay: (day: string, q: { moment: HistoryMoment; min_sources?: number; limit?: number; offset?: number }) =>
    request<HistoryDay>("GET", `/history/${day}${query(q)}`),

  sources: () => request<Source[]>("GET", "/sources"),
  createSource: (input: SourceInput) => request<Source>("POST", "/sources", input),
  updateSource: (id: number, patch: SourcePatch) => request<Source>("PATCH", `/sources/${id}`, patch),
  deleteSource: (id: number) => request<void>("DELETE", `/sources/${id}`),
  refreshSource: (id: number) => request<{ scheduled: number }>("POST", `/sources/${id}/refresh`),
  addFeed: (sourceId: number, url: string, label: string | null) =>
    request<Source>("POST", `/sources/${sourceId}/feeds`, { url, label }),
  updateFeed: (id: number, patch: FeedPatch) => request<Source>("PATCH", `/feeds/${id}`, patch),
  deleteFeed: (id: number) => request<void>("DELETE", `/feeds/${id}`),
  testFeed: (url: string) => request<FeedTestResult>("POST", "/feeds/test", { url }),

  fulltext: (articleId: number) => request<{ fulltext: FullText | null }>("GET", `/articles/${articleId}/fulltext`),
  requestFulltext: (articleId: number) => request<{ status: string }>("POST", `/articles/${articleId}/fulltext`),
  translateFulltext: (articleId: number) =>
    request<{ status: string }>("POST", `/articles/${articleId}/fulltext/translate`),
  browsers: () => request<BrowserList>("GET", "/fulltext/browsers"),
  openLogin: (target: { url?: string; source_id?: number } = {}) =>
    request<{ status: string }>("POST", "/fulltext/login", { url: target.url ?? null, source_id: target.source_id ?? null }),
  fulltextSites: () => request<{ sites: FullTextSite[]; login_window_open: boolean }>("GET", "/fulltext/sites"),
  testSite: (sourceId: number) =>
    request<{ article_id: number; status: string }>("POST", `/fulltext/sites/${sourceId}/test`),
  resumeFulltextSource: (sourceId: number) => request<{ status: string }>("POST", `/fulltext/sources/${sourceId}/resume`),

  backups: () => request<BackupList>("GET", "/backups"),
  makeBackup: () => request<BackupInfo>("POST", "/backups"),
  scheduleRestore: (name: string) =>
    request<{ scheduled: BackupInfo; can_restart: boolean }>("POST", "/backups/restore", { name }),
  cancelRestore: () => request<void>("DELETE", "/backups/restore"),
  restartApp: () => request<{ ok: boolean }>("POST", "/app/restart"),
  mailDraft: (d: { subject: string; html: string; text: string; cut_note: string }) =>
    request<{ method: "outlook" | "default"; cut: boolean }>("POST", "/mail/draft", d),
  update: () => request<UpdateStatus>("GET", "/update"),
  checkUpdate: () => request<UpdateStatus>("POST", "/update/check"),
  downloadUpdate: () => request<UpdateStatus>("POST", "/update/download"),
  applyUpdate: () => request<{ ok: boolean }>("POST", "/update/apply"),
  dismissUpdateResult: () => request<void>("DELETE", "/update/result"),
  testNotification: () => request<{ ok: boolean }>("POST", "/notify/test"),

  runCollector: () => request<{ scheduled: number }>("POST", "/collector/run"),
  openDataDir: () => request<{ ok: boolean }>("POST", "/app/open-data-dir"),
  openExtensionDir: () => request<{ ok: boolean }>("POST", "/app/open-extension-dir"),
  extension: () => request<ExtensionInfo>("GET", "/extension"),
  renewExtensionCode: () => request<{ code: string }>("POST", "/extension/code"),
};
