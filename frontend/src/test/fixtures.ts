import type {
  HomeInfo, UpdateStatus, FullTextWorkerStatus, MaintenanceStatus, NotifyStatus, Settings, StoryWorkerStatus } from "../api/types";

/** Settings keys added since Phase 3 (stories, score, full text); spread into each test's settings. */
export const STORY_SETTINGS = {
  "ai.provider": "ollama" as const,
  "ai.gemini_model": "",
  "ai.openai_model": "",
  "ai.openai_url": "https://api.openai.com/v1",
  "ai.anthropic_model": "",
  "ai.cloud_rpm": 10,
  "stories.embed_model": "bge-m3:latest",
  "stories.embed_summary": false,
  "stories.threshold": 0.6,
  "stories.cohesion": 0.45,
  "stories.min_sources_for_ai": 2,
  "score.w_sources": 0.45,
  "score.w_freshness": 0.25,
  "score.w_turkey": 0.2,
  "score.w_interest": 0.1,
  "interest.keywords": [],
  "interest.categories": [],
  "interest.regions": [],
  "fulltext.enabled": true, "fulltext.translate": false,
  "fulltext.browser_path": "",
  "extension.profile": "daily" as const,
  "fulltext.launch_browser": false,
  "debug.save_pages": false,
  "notify.breaking": true,
  "notify.breaking_min_sources": 3,
  "fulltext.per_site_hour": 4,
  "ai.depth": "fast",
  "ai.prompts": {},
  "ui.shortcuts": {}, "ui.font": "", "ui.font_scale": 100, "ui.text_color_light": "", "ui.text_color_dark": "",
  "ai.inputs": {},
  "ai.limits": {},
  "fulltext.browser_gap_min": 20,
  "fulltext.browser_per_day": 15,
  "fulltext.browser_night_rest": true,
  "fulltext.auto_min_score": 60,
  "fulltext.auto_per_story": 2,
  "history.morning_hour": 9,
  "retention.fulltext_days": 30,
  "backup.keep_daily": 14,
  "app.close_to_tray": true,
  "notify.enabled": true,
  "notify.min_score": 60,
  "notify.min_sources": 5,
  "notify.quiet": true,
  "notify.quiet_start": 23,
  "notify.quiet_end": 7,
} satisfies Partial<Settings>;

export const STORY_WORKER: StoryWorkerStatus = {
  running: true, state: "idle", model: "bge-m3:latest", last_error: null, embedded: 3, clustered: 3, stories: 2, multi_source: 1,
};

export const FULLTEXT_WORKER: FullTextWorkerStatus = {
  running: true, state: "idle", browser: "Brave", profile: "own", current_article_id: null, last_error: null,
  last_done_at: null, pending: 0, done: 0, failed: 0, blocked: 0, paused_sources: [],
};

/** Full-text fields of a story member that has none yet. */
export const NO_FULLTEXT = {
  fulltext_status: null, fulltext_error: null, fulltext_chars: null, fulltext_translate_status: null,
} as const;

export const MAINTENANCE: MaintenanceStatus = {
  last_run_at: "2026-09-27T08:00:00Z", last_removed: { fulltexts: 2, vectors: 150 }, last_error: null,
  last_backup: "worldsignal-20260927-080000-daily.db", backup_error: null, database_bytes: 45_000_000,
};

export const NOTIFY: NotifyStatus = { available: true, last_sent_at: null, last_story_id: null, sent: 0 };

/** GET /api/home for a user in Türkiye with the default rules. */
export const HOME: HomeInfo = {
  code: "TR", system_country: "TR", neighbours: ["AM", "AZ", "BG", "CY", "GE", "GR", "IQ", "IR", "SY"],
  related: ["AZ", "KZ", "UZ", "KG", "TM"], topics: ["black_sea", "nato"], keywords: [],
  countries: ["TR", "ZA", "GR", "KZ", "AZ", "UZ", "KG", "TM", "AM", "BG", "CY", "GE", "IQ", "IR", "SY"],
  all_topics: ["black_sea", "eastern_mediterranean", "nato", "eu_enlargement", "migration", "turkic_states"], syncing: false,
};

export const UPDATE_IDLE: UpdateStatus = {
  state: "up_to_date", current: "0.8.0", latest: null, progress: null, error: null, checked_at: null, unsupported: null,
  releases_url: "https://github.com/x/WorldSignal/releases", last_update: null, can_quit: true,
};
