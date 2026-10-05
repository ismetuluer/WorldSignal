export type Region =
  | "global"
  | "north_america"
  | "latin_america"
  | "europe"
  | "middle_east"
  | "russia_ukraine"
  | "caucasus_central_asia"
  | "asia"
  | "africa"
  | "turkey";

export type CatalogGroup =
  | "western"
  | "agency"
  | "middle_east"
  | "russia_ukraine"
  | "asia"
  | "europe"
  | "other"
  | "turkey"
  | "sports";

export type UiLanguage = "tr" | "en";

/** One AI text: a headline, a summary and (stories, meeting items) why it deserves the meeting. */
export interface AiText {
  title: string;
  summary: string;
  why?: string;
  /** Where outlets contradict each other on a fact (empty or missing: they agree). */
  conflict?: string;
  /** Stories: the key names, figures and statements, one per line ("" none; missing: written before 0.13.4). */
  points?: string;
}

/** AI texts by language code ("tr", "pt", …): the languages of the setting ai.languages. */
export type AiTexts = Record<string, AiText>;
export type ThemeSetting = "system" | "light" | "dark";

export interface FeedFilters {
  regions: string[];
  groups: string[];
  langs: string[];
  sources: number[];
  categories: string[];
  turkey: boolean;
}

export interface Settings {
  "ui.language": UiLanguage;
  "ui.theme": ThemeSetting;
  /** A CSS font-family list ("Georgia, serif"); "" is the program's own. */
  /** Keys per action ("search", "next", "prev", "open", "meeting"); an action that is not here has its default. */
  "ui.shortcuts": Record<string, string[]>;
  "ui.font": string;
  /** Text size as a percentage of the normal size. */
  "ui.font_scale": number;
  /** "#rrggbb" per theme; "" is the theme's own colour. */
  "ui.text_color_light": string;
  "ui.text_color_dark": string;
  "feed.window_hours": number;
  "feed.view": "stories" | "articles";
  "feed.filters": FeedFilters;
  "update.auto_check": boolean;
  "update.auto_download": boolean;
  /** "My country" (ISO code); "" = Windows' region. related/topics null = the country's own defaults. */
  /** "My country" on/off: off leaves the country link out of the score, filter and badges. */
  "home.enabled": boolean;
  /** Rate reports for "my country" and show the labels (the ratings are not redone while off). */
  "home.labels": boolean;
  "home.country": string;
  "home.related": string[] | null;
  "home.topics": string[] | null;
  "home.keywords": string[];
  "ai.enabled": boolean;
  /** Languages the AI writes in; null = the interface language and English. */
  "ai.languages": string[] | null;
  "ai.provider": AiProvider;
  "ai.gemini_model": string;
  "ai.openai_model": string;
  "ai.openai_url": string;
  "ai.anthropic_model": string;
  /** Requests per minute to a cloud service. */
  "ai.cloud_rpm": number;
  "ai.url": string;
  "ai.model": string;
  "ai.max_age_hours": number;
  "ai.yield_gpu": boolean;
  "ai.depth": AiDepth;
  /** The user's own wording of the AI instructions, per task; a task that is not here uses the default. */
  "ai.prompts": Record<string, string>;
  /** How a report is laid out in the request, per kind (article, story_intro, story_report). */
  "ai.inputs": Record<string, string>;
  /** How much of a report is sent: characters, reports per request ... */
  "ai.limits": Record<string, number>;
  "stories.embed_model": string;
  "stories.embed_summary": boolean;
  "stories.threshold": number;
  "stories.cohesion": number;
  "stories.min_sources_for_ai": number;
  "score.w_sources": number;
  "score.w_freshness": number;
  "score.w_turkey": number;
  "score.w_interest": number;
  "interest.keywords": string[];
  "interest.categories": Category[];
  "interest.regions": Region[];
  "fulltext.enabled": boolean;
  /** Also translate every full text that arrives (summary + full text); off: the summary only. */
  "fulltext.translate": boolean;
  "fulltext.browser_path": string;
  /** Where the browser extension lives: the everyday browser, or a profile of World Signal's own. */
  "extension.profile": "daily" | "own";
  /** Who reads the subscription sites: World Signal's own browser, or the extension in the user's browser. */
  /** Extension reader: start the user's browser without a window when it is closed. */
  /** Keep the HTML of the pages that are read (local, last 40) to see where a publisher puts a label. */
  "debug.save_pages": boolean;
  "fulltext.launch_browser": boolean;
  "fulltext.per_site_hour": number;
  "fulltext.browser_gap_min": number;
  "fulltext.browser_per_day": number;
  "fulltext.browser_night_rest": boolean;
  "fulltext.auto_min_score": number;
  "fulltext.auto_per_story": number;
  "history.morning_hour": number;
  "retention.fulltext_days": number;
  "backup.keep_daily": number;
  "app.close_to_tray": boolean;
  "notify.enabled": boolean;
  "notify.min_score": number;
  "notify.min_sources": number;
  "notify.breaking": boolean;
  "notify.breaking_min_sources": number;
  /** Working hours: off = the background work runs all day and night. */
  "work.limited": boolean;
  "work.start": number;
  "work.end": number;
  "notify.quiet": boolean;
  "notify.quiet_start": number;
  "notify.quiet_end": number;
}

export type Category =
  | "diplomacy"
  | "conflict_defense"
  | "politics"
  | "economy"
  | "energy"
  | "technology"
  | "science_health"
  | "environment"
  | "disaster"
  | "society"
  | "justice"
  | "sports"
  | "culture"
  | "other";

export type TurkeyRelevance = "none" | "indirect" | "direct";
export type AiItemStatus = "pending" | "done" | "failed";

export interface Article {
  id: number;
  url: string;
  title: string;
  summary: string;
  author: string | null;
  published_at: string | null;
  first_seen_at: string;
  sort_at: string;
  language: string;
  source_id: number;
  source_name: string;
  region: Region;
  catalog_group: CatalogGroup;
  paywalled: boolean;
  exclusive: boolean;
  breaking: boolean;
  /** AI enrichment; the texts are only set when ai_status is "done". */
  ai_status: AiItemStatus | null;
  ai_texts: AiTexts;
  /** Read in a batch ("fast"): headline only, the summary is written on request. */
  ai_brief?: number | null;
  category: Category | null;
  /** ISO 3166-1 alpha-2 codes the AI found in the text. */
  countries: string[];
  turkey_relevance: TurkeyRelevance | null;
  /** Relevance to the user's country and why: "home_mentioned", "neighbour:GR", "related:KZ", "topic:nato". */
  turkey_links: string[];
  ai_issues: string[];
  ai_model: string | null;
  ai_error: string | null;
  /** The full text of the report: its state in the queue (null: never asked for). */
  fulltext_status?: FullTextStatus | null;
  fulltext_error?: string | null;
  fulltext_chars?: number | null;
  fulltext_translate_status?: AiItemStatus | null;
}

export interface ArticlePage {
  items: Article[];
  next: string | null;
  /** Total matches; only present on the first page. */
  total: number | null;
}

export type FeedStatus = "pending" | "ok" | "not_modified" | "error";
export type SourceStatus = "ok" | "partial" | "error" | "pending" | "disabled" | "no_feeds";

export interface Feed {
  id: number;
  source_id: number;
  url: string;
  label: string | null;
  enabled: boolean;
  verified: boolean;
  fetch_interval_min: number;
  last_attempt_at: string | null;
  last_success_at: string | null;
  next_fetch_at: string | null;
  last_status: FeedStatus;
  last_error_code: string | null;
  last_error_detail: string | null;
  consecutive_failures: number;
  last_item_count: number | null;
  last_new_count: number | null;
}

export interface Source {
  id: number;
  slug: string;
  name: string;
  homepage: string | null;
  catalog_group: CatalogGroup;
  owner: string | null;
  region: Region;
  language: string;
  reliability: number;
  enabled: boolean;
  paywalled: boolean;
  verified: boolean;
  note: string | null;
  origin: "catalog" | "user";
  fulltext_mode: FullTextMode;
  fulltext_paused_until: string | null;
  feeds: Feed[];
  articles_24h: number;
  last_success_at: string | null;
  status: SourceStatus;
}

export interface CollectorStatus {
  running: boolean;
  busy: boolean;
  offline: boolean;
  last_cycle_at: string | null;
  last_cycle_new: number;
  last_cycle_feeds: number;
  last_cycle_errors: number;
}

export type AiState =
  | "starting"
  | "ok"
  | "idle"
  | "disabled"
  | "no_model"
  | "unreachable"
  | "model_missing"
  | "timeout"
  | "gpu_busy"
  | "resting"
  | "no_key"
  | "bad_key"
  | "rate_limited";

/** Where the AI runs: Ollama (this or another computer) or a cloud service the user chose. */
export type AiProvider = "ollama" | "gemini" | "openai" | "anthropic";
export type CloudProvider = Exclude<AiProvider, "ollama">;

export interface CloudTestResult {
  ok: boolean;
  error_code: string | null;
  models: string[];
}

export interface AiStatus {
  running: boolean;
  state: AiState;
  provider?: AiProvider;
  /** Other model(s) occupying the GPU when state is "gpu_busy". */
  busy_with: string | null;
  model: string | null;
  url: string | null;
  current_article_id: number | null;
  last_error: string | null;
  last_done_at: string | null;
  avg_seconds: number | null;
  pending: number;
  done: number;
  failed: number;
  done_24h: number;
}

export interface OllamaModel {
  name: string;
  size_gb: number;
  parameters: string | null;
  /** "completion", "embedding", ...; null when Ollama does not report it. */
  capabilities: string[] | null;
}

export interface OllamaTestResult {
  ok: boolean;
  error_code: string | null;
  version: string | null;
  models: OllamaModel[];
}

export type StoryWorkerState = "starting" | "ok" | "idle" | "no_model" | "unreachable" | "model_missing" | "timeout";

export interface StoryWorkerStatus {
  running: boolean;
  state: StoryWorkerState;
  model: string | null;
  last_error: string | null;
  embedded: number;
  clustered: number;
  stories: number;
  multi_source: number;
}

export type ScoreTag =
  | { kind: "sources"; count: number }
  | { kind: "age"; hours: number }
  | { kind: "spreading"; count: number; hours: number }
  | { kind: "turkey"; level: "direct" | "indirect" }
  | { kind: "interest"; matches: string[] };

export interface ScoreParts {
  components?: { sources: number; freshness: number; turkey: number; interest: number };
  tags?: ScoreTag[];
}

export interface StoryMember {
  id: number;
  url: string;
  title: string;
  summary: string;
  sort_at: string;
  language: string;
  source_id: number;
  source_name: string;
  paywalled: boolean;
  exclusive: boolean;
  region: Region;
  similarity: number | null;
  assigned_by: "auto" | "user";
  ai_texts: AiTexts;
  fulltext_status: FullTextStatus | null;
  fulltext_error: string | null;
  fulltext_chars: number | null;
  fulltext_translate_status: AiItemStatus | null;
}

export type FullTextMode = "off" | "http" | "browser";
export type FullTextStatus = "pending" | "done" | "failed" | "blocked";
export type FullTextWorkerState = "starting" | "disabled" | "idle" | "no_browser" | "profile_in_use" | "fetching" | "ok";

export interface FullTextWorkerStatus {
  running: boolean;
  state: FullTextWorkerState;
  browser: string | null;
  profile: "own" | "main" | null;
  current_article_id: number | null;
  last_error: string | null;
  last_done_at: string | null;
  pending: number;
  done: number;
  failed: number;
  blocked: number;
  paused_sources: { id: number; name: string; fulltext_paused_until: string }[];
}

export interface FullText {
  article_id: number;
  status: FullTextStatus;
  reason: "auto" | "notebook" | "user";
  attempts: number;
  method: "http" | "browser" | null;
  text: string | null;
  chars: number | null;
  error_code: string | null;
  fetched_at: string | null;
  translate_status: AiItemStatus | null;
  /** Translations of the text by language (not into the article's own language). */
  translations: Record<string, string>;
}

export interface FullTextSite {
  id: number;
  name: string;
  homepage: string | null;
  fulltext_mode: FullTextMode;
  fulltext_paused_until: string | null;
  /** Reports of this site waiting for their full text. */
  queued: number;
  /** The latest finished attempt: shows whether the sign-in works. */
  last: { status: FullTextStatus; error_code: string | null; at: string } | null;
}

export interface BrowserList {
  browsers: { name: string; path: string }[];
  chosen: string | null;
  own_profile: string;
  main_profile_in_use: boolean;
}

export interface Story {
  id: number;
  /** The first outlet to report the event (by publication time); null with a single outlet. */
  first?: { source: string; at: string } | null;
  first_seen_at: string;
  last_seen_at: string;
  article_count: number;
  source_count: number;
  score: number;
  score_parts: ScoreParts;
  /** Spreading right now (3+ independent sources within the hour) or marked breaking by its publisher. */
  breaking: boolean;
  /** A report is marked exclusive by its publisher. */
  exclusive: boolean;
  turkey_relevance: TurkeyRelevance;
  category: Category | null;
  representative_id: number | null;
  representative: StoryMember | null;
  ai_status: AiItemStatus | null;
  /** The story's own AI texts (title, summary, why) by language; empty until ai_status is "done". */
  ai_texts: AiTexts;
  ai_issues: string[];
  ai_article_count: number | null;
  ai_model: string | null;
  sources: string[];
  members: StoryMember[];
  timeline: { day: string; articles: number }[];
  /** Turning points; only in the single-story answer. */
  milestones?: Milestone[];
}

export type Milestone =
  | { kind: "first" | "turkey" | "latest"; at: string; source: string }
  | { kind: "own_language_source"; at: string; source: string; language: string }
  | { kind: "sources"; at: string; source: string; count: number };

export interface MaintenanceStatus {
  last_run_at: string | null;
  last_removed: { fulltexts: number; vectors: number } | null;
  last_error: string | null;
  last_backup: string | null;
  backup_error: string | null;
  database_bytes: number;
}

export interface NotifyStatus {
  /** A desktop window with a tray icon can show notifications (not in server-only mode). */
  available: boolean;
  last_sent_at: string | null;
  last_story_id: number | null;
  sent: number;
}

// -- backups (phase 7) ---------------------------------------------------------------------------

export interface BackupInfo {
  name: string;
  label: string;
  /** Local time the copy was made (ISO without zone). */
  created: string;
  bytes: number;
}

export interface BackupList {
  backups: BackupInfo[];
  pending_restore: string | null;
  last_restore: { name: string; at: string; ok: boolean; error?: string; safety_copy?: string } | null;
  can_restart: boolean;
}

// -- history (phase 6) ---------------------------------------------------------------------------

export type HistoryMoment = "morning" | "day";

export interface HistoryMonth {
  month: string;
  today: string;
  days: { day: string; articles: number; stories: number }[];
}

export interface HistoryDay {
  day: string;
  moment: HistoryMoment;
  /** The moment the ranking reflects (UTC). */
  as_of: string;
  window_start: string;
  items: Story[];
  total: number;
  /** Reports of that window that were never grouped into stories (collected before stories existed). */
  unclustered: number;
  /** The chosen moment has not come yet. */
  future: boolean;
}

export interface StoryPage {
  items: Story[];
  total: number;
}

export interface StoryQuery {
  hours?: number;
  source?: number[];
  region?: string[];
  group?: string[];
  lang?: string[];
  category?: string[];
  turkey?: boolean;
  /** Stories with a report the publisher labelled as breaking news (last 24 h, or `hours`). */
  breaking?: boolean;
  min_sources?: number;
  q?: string;
  /** Translations of q (api.searchTranslations): a report matching any of them is found too. */
  qx?: string[];
  sort?: "score" | "recent";
  limit?: number;
  offset?: number;
}

export interface Status {
  version: string;
  collector: CollectorStatus;
  ai: AiStatus;
  stories: StoryWorkerStatus;
  fulltext: FullTextWorkerStatus;
  maintenance: MaintenanceStatus;
  notify: NotifyStatus;
  articles: { total: number; recent: number };
  /** Stories with a breaking-news label in the last three hours (the sidebar badge). */
  breaking?: number;
  /** The browser extension's reader; null when this program has no extension bridge. */
  extension: (ExtensionStatus & { active: boolean }) | null;
}

export interface ExtensionStatus {
  /** Heard from within the wait the program handed it. */
  connected: boolean;
  /** The extension reads but has been silent long enough to tell the user (the sidebar warning). */
  warn: boolean;
  last_seen: string | null;
  read_today: number;
  reading: string | null;
  last_source: string | null;
  last_error: string | null;
  /** The version the extension reported (null: an older copy that does not report one). */
  version: string | null;
  /** The browser runs another copy of the extension than the program's: press Reload on the extensions page. */
  outdated: boolean;
}

/** GET /api/extension: the pairing code the extension needs, where to find the program, and the connection. */
export interface ExtensionInfo {
  code: string;
  port: number;
  fixed_port: boolean;
  status: ExtensionStatus;
}

export type FeedKind = "exclusive" | "opinion";

/** A region of the feed's filter: a source's region, or "abroad" (every source outside the local region). */
export type FeedRegion = Region | "abroad";

export interface Meta {
  regions: Region[];
  /** The local region ("turkey" for a user in Türkiye), or null where there is none: "abroad" is then not offered. */
  home_region: Region | null;
  groups: CatalogGroup[];
  /** Virtual groups of the feed's source-group filter: exclusives and opinion pieces from any source. */
  kinds: FeedKind[];
  languages: string[];
  categories: Category[];
  ui_languages: UiLanguage[];
  data_dir: string;
  version: string;
  /** The country the relevance rules use now, and the one "" (Windows' region) stands for. */
  home_country: string;
  system_country: string;
  /** Language codes the AI can write in. */
  ai_output_languages: string[];
  /** The program's own wording of every AI instruction (ai/prompts.py). */
  ai_prompt_defaults: Record<string, string>;
  ai_input_defaults: Record<string, string>;
  /** Per limit: [default, lowest, highest]. */
  ai_limit_ranges: Record<string, number[]>;
}

/** GET /api/home: the user's country as the rules see it. */
export interface HomeInfo {
  code: string;
  system_country: string | null;
  neighbours: string[];
  related: string[];
  topics: string[];
  keywords: string[];
  countries: string[];
  all_topics: string[];
  syncing: boolean;
}

/** A feed a web page offers: an RSS/Atom link in the page, or a news sitemap robots.txt allows. */
export interface FeedSuggestion {
  url: string;
  kind: "rss" | "sitemap";
  title: string;
}

export interface FeedTestResult {
  ok: boolean;
  error_code: string | null;
  /** When the address was a web page (not_a_feed). */
  suggestions?: FeedSuggestion[];
  error_detail?: string;
  title?: string | null;
  language?: string | null;
  item_count?: number;
  newest_at?: string | null;
  sample_titles?: string[];
  final_url?: string;
}

export interface SourceInput {
  name: string;
  feed_url: string;
  homepage?: string | null;
  catalog_group: CatalogGroup;
  owner?: string | null;
  region: Region;
  language: string;
  reliability: number;
  paywalled: boolean;
}

export type SourcePatch = Partial<
  Pick<Source, "name" | "homepage" | "catalog_group" | "owner" | "region" | "language" | "reliability" | "enabled" | "paywalled" | "fulltext_mode">
>;

export type FeedPatch = Partial<Pick<Feed, "label" | "enabled" | "fetch_interval_min">>;

/** How much the AI writes: every report / stories cover their reports / also headlines of single reports only. */
export type AiDepth = "full" | "stories" | "fast";

// -- statistics (repo/stats.py) ----------------------------------------------------------------
export type StatsHours = 24 | 168 | 720;

export interface StatsCounts {
  articles: number;
  sources: number;
  stories: number;
}

export interface StatsShare {
  key: string;
  articles: number;
  previous: number;
}

export interface StatsShares {
  /** Reports with a key (category known) in this period, and in the previous one. */
  known: number;
  known_previous: number;
  /** All reports of this period. */
  total: number;
  items: StatsShare[];
}

export interface StatsSource {
  id: number;
  name: string;
  region: string;
  articles: number;
  previous: number;
  stories: number;
  last_at: string | null;
}

export interface RisingStory {
  story: Story;
  recent: number;
  previous: number;
  sources: number;
}

export interface StatsOverview {
  period: { hours: StatsHours; since: string; until: string; previous_since: string; step_hours: number;
    comparable: boolean; collecting_since: string | null };
  totals: StatsCounts & { previous: StatsCounts };
  timeline: { start: string; articles: number }[];
  categories: StatsShares;
  regions: StatsShares;
  countries: { read: number; items: { key: string; articles: number }[] };
  sources: StatsSource[];
  rising: { window_hours: number; items: RisingStory[] };
}

export interface TopicStats {
  articles: number;
  sources: number;
  previous: number;
  buckets: { start: string; articles: number; sources: number; share: number }[];
}

/** The search words in the sources' languages; ``state`` says why there are none ("disabled", "gpu_busy" …). */
export interface SearchTranslations {
  state: string;
  queries: Record<string, string[]>;
}

export interface ArticleQuery {
  hours?: number;
  source?: number[];
  region?: string[];
  group?: string[];
  lang?: string[];
  category?: string[];
  turkey?: boolean;
  q?: string;
  /** Translations of q (api.searchTranslations): a report matching any of them is found too. */
  qx?: string[];
  before?: string | null;
  limit?: number;
  /** One local calendar day (YYYY-MM-DD) instead of hours. */
  day?: string;
}

// -- notebook (phase 4) ------------------------------------------------------------------------

export interface StoryNote {
  id: number;
  story_id: number | null;
  /** Local day (YYYY-MM-DD) the note was started: where it is filed in the notebook. */
  day: string;
  /** Story headline when the note was last saved (the story may change or disappear). */
  title: string;
  body: string;
  created_at: string;
  updated_at: string;
  /** Only in a notebook day listing. */
  story_exists?: boolean;
}

export interface MeetingItem {
  id: number;
  day: string;
  story_id: number | null;
  /** Set when the item is one report instead of a story (then story_id is null). */
  article_id: number | null;
  position: number;
  comment: string;
  /** The headline when there is no AI text (e.g. the original title). */
  title: string;
  texts: AiTexts;
  category: Category | null;
  sources: { name: string; url: string }[];
  created_at: string;
  updated_at: string;
}

export interface MeetingList {
  day: string;
  today: string;
  items: MeetingItem[];
}

export interface NotebookDay {
  day: string;
  today: string;
  day_note: { body: string; updated_at: string } | null;
  meeting: MeetingItem[];
  notes: StoryNote[];
}

export interface NotebookMonth {
  month: string;
  today: string;
  days: { day: string; notes: number; meeting: number; day_note: boolean }[];
}

export interface UpdateRelease {
  version: string;
  tag: string | null;
  notes: string;
  published_at: string | null;
  page: string | null;
  size: number | null;
}

export interface UpdateStatus {
  state: "idle" | "checking" | "up_to_date" | "available" | "downloading" | "ready" | "applying" | "error";
  current: string;
  latest: UpdateRelease | null;
  progress: number | null;
  error: string | null;
  checked_at: string | null;
  /** Why this copy cannot replace itself: running from source, from a network folder, or a read-only folder. */
  unsupported: "dev" | "network" | "readonly" | null;
  releases_url: string;
  last_update: { ok: boolean; from: string | null; to: string | null; at: string; notes?: string | null; error?: string } | null;
  can_quit: boolean;
}
