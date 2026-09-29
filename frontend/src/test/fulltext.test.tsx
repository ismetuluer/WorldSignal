import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, FullText, FullTextSite, Meta, Settings, Source, Status, Story, StoryMember } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      status: vi.fn(),
      updateSettings: vi.fn(),
      sources: vi.fn(),
      updateSource: vi.fn(),
      story: vi.fn(),
      storyNote: vi.fn(),
      fulltext: vi.fn(),
      requestFulltext: vi.fn(),
      translateFulltext: vi.fn(),
      browsers: vi.fn(),
      openLogin: vi.fn(),
      fulltextSites: vi.fn(),
      testSite: vi.fn(),
      resumeFulltextSource: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { TRANSLATION_POLL_MS } from "../components/FullText";
import { StoryDetail } from "../components/StoryDetail";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { fulltextErrorKey } from "../lib/fulltext";
import { FullTextSettings } from "../pages/FullTextSettings";
import { SourceEditor } from "../pages/SourceEditor";
import { SubscriptionSitesSection } from "../pages/SubscriptionSites";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, NO_FULLTEXT, STORY_SETTINGS, STORY_WORKER } from "./fixtures";

const mocked = vi.mocked(api, true);

const SETTINGS: Settings = {
  "ui.language": "tr",
  "ui.theme": "light",
  "feed.window_hours": 24,
  "feed.view": "stories", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null,
  "ai.enabled": true,
  "ai.url": "http://localhost:11434",
  "ai.model": "gemma4-26b-a4b",
  "ai.max_age_hours": 24,
  "ai.yield_gpu": true,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "europe"],
  groups: ["turkey", "western"],
  kinds: ["exclusive", "opinion"],
  languages: ["en", "tr"],
  categories: ["politics", "diplomacy"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"],
  data_dir: "C:\\data",
  version: "0.5.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "gemma4-26b-a4b", url: "http://localhost:11434", current_article_id: null,
  last_error: null, last_done_at: null, avg_seconds: 2.5, pending: 0, done: 10, failed: 0, done_24h: 10,
};
const STATUS: Status = {
  version: "0.5.0",
  ai: AI,
  stories: STORY_WORKER,
  fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 0, last_cycle_feeds: 5, last_cycle_errors: 0 },
  articles: { total: 3, recent: 3 },
};
const BROWSERS = {
  browsers: [
    { name: "Brave", path: "C:\\Brave\\brave.exe" },
    { name: "Edge", path: "C:\\Edge\\msedge.exe" },
  ],
  chosen: "C:\\Brave\\brave.exe",
  own_profile: "D:\\Veri\\WorldSignal\\browser-profile",
  main_profile_in_use: true,
};
const NOW = new Date().toISOString();

function source(id: number, name: string, extra: Partial<Source> = {}): Source {
  return {
    id, slug: name.toLowerCase(), name, homepage: null, catalog_group: "western", owner: null, region: "europe",
    language: "en", reliability: 1, enabled: true, paywalled: false, verified: true, note: null, origin: "catalog",
    fulltext_mode: "http", fulltext_paused_until: null, feeds: [], articles_24h: 4, last_success_at: NOW, status: "ok", ...extra,
  };
}

function member(id: number, name: string, extra: Partial<StoryMember> = {}): StoryMember {
  return {
    id, url: `https://x.example/${id}`, title: `Report ${id}`, summary: "", sort_at: NOW, language: "en",
    source_id: id, source_name: name, paywalled: false, exclusive: false, region: "europe", similarity: 0.8, assigned_by: "auto",
    ai_texts: {}, ...NO_FULLTEXT, ...extra,
  };
}

function story(members: StoryMember[]): Story {
  return {
    id: 1, breaking: false, exclusive: false, first_seen_at: NOW, last_seen_at: NOW, article_count: members.length, source_count: members.length, score: 70,
    score_parts: {}, turkey_relevance: "none", category: "diplomacy", representative_id: members[0]!.id, representative: members[0]!,
    ai_status: "done", ai_texts: { tr: { title: "Hikâye", summary: "Özet.", why: "" } },
    ai_issues: [], ai_article_count: members.length, ai_model: "gemma4-26b-a4b",
    sources: members.map((m) => m.source_name), members, timeline: [],
  };
}

function fulltext(extra: Partial<FullText> = {}): FullText {
  return {
    article_id: 10, status: "done", reason: "user", attempts: 1, method: "browser",
    text: "First paragraph of the article.\n\nSecond paragraph.", chars: 48, error_code: null, fetched_at: NOW,
    translate_status: null, translations: {}, ...extra,
  };
}

function wrap(ui: ReactNode, settings: Settings = SETTINGS) {
  return render(
    <AppStateProvider initialSettings={settings} initialMeta={META}>
      <I18nProvider lang={settings["ui.language"]}>
        <ToastProvider>{ui}</ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}

const SITES: FullTextSite[] = [
  { id: 1, name: "The New York Times", homepage: "https://www.nytimes.com", fulltext_mode: "browser",
    fulltext_paused_until: null, queued: 0, last: { status: "failed", error_code: "paywall", at: NOW } },
  { id: 3, name: "Financial Times", homepage: "https://www.ft.com", fulltext_mode: "browser",
    fulltext_paused_until: null, queued: 0, last: { status: "done", error_code: null, at: NOW } },
  { id: 5, name: "Le Monde", homepage: "https://www.lemonde.fr", fulltext_mode: "browser",
    fulltext_paused_until: null, queued: 0, last: null },
];

beforeEach(() => {
  vi.resetAllMocks();
  mocked.status.mockResolvedValue(STATUS);
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
  mocked.browsers.mockResolvedValue(BROWSERS);
  mocked.storyNote.mockResolvedValue({ note: null });
  mocked.fulltextSites.mockResolvedValue({ sites: SITES, login_window_open: false });
});

describe("Full-text settings", () => {
  it("lists the browsers found and saves the chosen one", async () => {
    wrap(<FullTextSettings />);
    const select = await screen.findByRole("combobox", { name: "Tarayıcı" });
    expect(within(select).getAllByRole("option").map((o) => o.textContent)).toEqual(["Otomatik (Brave)", "Brave", "Edge"]);
    await userEvent.selectOptions(select, "C:\\Edge\\msedge.exe");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.browser_path": "C:\\Edge\\msedge.exe" });
  });

  it("explains a missing browser and offers no site to open", async () => {
    mocked.browsers.mockResolvedValue({ ...BROWSERS, browsers: [], chosen: null });
    const { unmount } = wrap(<FullTextSettings />);
    expect(await screen.findByText(/Brave, Chrome veya Edge bulunamadı/)).toBeInTheDocument();
    unmount();
    wrap(<SubscriptionSitesSection />);
    await screen.findByRole("list", { name: "Abonelik siteleri" });
    expect(screen.queryByRole("button", { name: /giriş için aç/ })).not.toBeInTheDocument();
  });

  it("points to the subscription sites, which moved to the Sources page", async () => {
    wrap(<FullTextSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Kaynaklar'da aç" }));
    expect(window.location.hash).toBe("#/sources");
    expect(screen.queryByRole("list", { name: "Abonelik siteleri" })).not.toBeInTheDocument();
  });

  it("sets the reading pace of subscription sites", async () => {
    wrap(<FullTextSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "30 dk" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.browser_gap_min": 30 });
    await userEvent.click(screen.getByRole("button", { name: "5 sayfa" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.browser_per_day": 5 });
    await userEvent.click(screen.getByRole("switch", { name: "Gece abonelik sitelerini okuma" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.browser_night_rest": false });
  });

  it("lists subscription sites with the result of their latest attempt", async () => {
    wrap(<SubscriptionSitesSection />);
    const list = await screen.findByRole("list", { name: "Abonelik siteleri" });
    const row = (name: string) => within(list).getByText(name).closest("li")!;
    expect(within(row("The New York Times")).getByText(/Abonelik duvarı: giriş gerekli/)).toBeInTheDocument();
    expect(within(row("Financial Times")).getByText(/Tam metin alındı/)).toBeInTheDocument();
    expect(within(row("Le Monde")).getByText("Henüz denenmedi")).toBeInTheDocument();
  });

  it("opens a site in World Signal's profile to sign in", async () => {
    mocked.openLogin.mockResolvedValue({ status: "opened" });
    wrap(<SubscriptionSitesSection />);
    await userEvent.click(await screen.findByRole("button", { name: "The New York Times sitesini giriş için aç" }));
    expect(mocked.openLogin).toHaveBeenCalledWith({ source_id: 1 });
    expect(await screen.findByText(/The New York Times World Signal tarayıcısında açıldı/)).toBeInTheDocument();
  });

  it("tries a site and shows it queued", async () => {
    mocked.testSite.mockResolvedValue({ article_id: 44, status: "pending" });
    wrap(<SubscriptionSitesSection />);
    const button = await screen.findByRole("button", { name: "Le Monde için tam metni dene" });
    mocked.fulltextSites.mockResolvedValue({ sites: SITES.map((s) => (s.id === 5 ? { ...s, queued: 1 } : s)), login_window_open: false });
    await userEvent.click(button);
    expect(mocked.testSite).toHaveBeenCalledWith(5);
    expect(await screen.findByText("Sırada…")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Le Monde için tam metni dene" })).toBeDisabled();
  });

  it("says so when the newest article already has its full text", async () => {
    mocked.testSite.mockResolvedValue({ article_id: 44, status: "done" });
    wrap(<SubscriptionSitesSection />);
    await userEvent.click(await screen.findByRole("button", { name: "Financial Times için tam metni dene" }));
    expect(await screen.findByText("Financial Times: en yeni haberin tam metni zaten alınmış.")).toBeInTheDocument();
  });

  it("asks to close the sign-in window while it is open", async () => {
    mocked.fulltextSites.mockResolvedValue({ sites: SITES, login_window_open: true });
    wrap(<SubscriptionSitesSection />);
    expect(await screen.findByText("World Signal tarayıcı penceresi açık")).toBeInTheDocument();
  });

  it("explains an error when a site cannot be tried", async () => {
    mocked.testSite.mockRejectedValue(new ApiError("no_articles", 409));
    wrap(<SubscriptionSitesSection />);
    await userEvent.click(await screen.findByRole("button", { name: "Le Monde için tam metni dene" }));
    expect(await screen.findByText("Bu kaynaktan henüz haber toplanmadı.")).toBeInTheDocument();
  });

  it("warns that the main profile is locked while the browser is open", async () => {
    const { unmount } = wrap(<FullTextSettings />, { ...SETTINGS, "fulltext.profile": "main" });
    expect(await screen.findByText(/Tarayıcınız şu an açık/)).toBeInTheDocument();
    unmount();
    wrap(<SubscriptionSitesSection />, { ...SETTINGS, "fulltext.profile": "main" });
    await screen.findByRole("list", { name: "Abonelik siteleri" });
    expect(screen.queryByRole("button", { name: /giriş için aç/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Kendi tarayıcınızda sitelere giriş yapın/)).toBeInTheDocument();
  });

  it("turns on the browser for every enabled paid source", async () => {
    mocked.sources.mockResolvedValue([
      source(1, "NYT", { paywalled: true, fulltext_mode: "off" }),
      source(2, "FT", { paywalled: true, fulltext_mode: "browser" }),
      source(3, "BBC"),
      source(4, "WSJ", { paywalled: true, enabled: false, fulltext_mode: "off" }),
    ]);
    mocked.updateSource.mockImplementation(async (id, patch) => source(id, "x", patch));
    wrap(<FullTextSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Hepsinde tarayıcıyı aç" }));
    expect(await screen.findByText("1 ücretli kaynakta tarayıcı açıldı.")).toBeInTheDocument();
    expect(mocked.updateSource).toHaveBeenCalledTimes(1);
    expect(mocked.updateSource).toHaveBeenCalledWith(1, { fulltext_mode: "browser" });
  });

  it("shows the queue, a paused site and resumes it", async () => {
    const until = new Date(Date.now() + 3600_000).toISOString();
    mocked.status.mockResolvedValue({
      ...STATUS,
      fulltext: {
        ...FULLTEXT_WORKER, state: "ok", pending: 3, done: 7, failed: 1, blocked: 1, last_error: "bot_check",
        paused_sources: [{ id: 5, name: "The Times", fulltext_paused_until: until }],
      },
    });
    mocked.resumeFulltextSource.mockResolvedValue({ status: "resumed" });
    wrap(<FullTextSettings />);
    expect(await screen.findByText("3 haber sırada · 7 tam metin alındı")).toBeInTheDocument();
    expect(screen.getByText("2 haberin tam metni alınamadı")).toBeInTheDocument();
    expect(screen.getByText(/Son sorun: site bir robot doğrulaması gösterdi/)).toBeInTheDocument();
    const paused = screen.getByRole("list", { name: "Bekletilen siteler" });
    expect(within(paused).getByText(/The Times: .* saatine kadar bekletiliyor/)).toBeInTheDocument();
    await userEvent.click(within(paused).getByRole("button", { name: "Devam ettir" }));
    expect(mocked.resumeFulltextSource).toHaveBeenCalledWith(5);
  });

  it("saves the pace limits", async () => {
    wrap(<FullTextSettings />);
    await userEvent.click(await screen.findByRole("button", { name: "Saatte 2" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.per_site_hour": 2 });
    await userEvent.click(screen.getByRole("button", { name: "Hiçbiri" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.auto_per_story": 0 });
  });
});

describe("Source editor full-text mode", () => {
  it("saves the chosen method and shows a pause", async () => {
    const until = new Date(Date.now() + 3600_000).toISOString();
    const src = source(1, "NYT", { paywalled: true, fulltext_mode: "off", fulltext_paused_until: until });
    mocked.updateSource.mockResolvedValue({ ...src, fulltext_mode: "browser" });
    const onChanged = vi.fn();
    wrap(<SourceEditor source={src} onClose={() => undefined} onChanged={onChanged} onDeleted={() => undefined} />);
    expect(screen.getByText(/Site bir engel gösterdi/)).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Tam metin" });
    expect(select).toHaveValue("off");
    await userEvent.selectOptions(select, "browser");
    expect(screen.getByText(/oturum açtığınız tarayıcı profiliyle/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(mocked.updateSource).toHaveBeenCalledWith(1, { fulltext_mode: "browser" });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
  });
});

describe("Full text in a story", () => {
  const MEMBERS = [
    member(10, "Reuters", { fulltext_status: "done", fulltext_chars: 1234 }),
    member(11, "NYT", { paywalled: true, fulltext_status: "blocked", fulltext_error: "bot_check" }),
    member(12, "BBC", { fulltext_status: "pending" }),
    member(13, "AA", { language: "tr" }),
  ];

  async function openStory(members = MEMBERS) {
    mocked.story.mockResolvedValue(story(members));
    wrap(<StoryDetail storyId={1} onClose={() => undefined} onChanged={() => undefined} />);
    return screen.findByRole("dialog");
  }

  it("shows each report's full-text state with the fitting action", async () => {
    const dialog = await openStory();
    expect(await within(dialog).findByRole("button", { name: "Tam metni oku (1.234 karakter)" })).toBeInTheDocument();
    expect(within(dialog).getByText(/Site engelledi: site bir robot doğrulaması gösterdi/)).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Yeniden dene" })).toBeInTheDocument();
    expect(within(dialog).getByText("Tam metin sırada…")).toBeInTheDocument();
    expect(within(dialog).getByRole("button", { name: "Tam metni getir" })).toBeInTheDocument();
  });

  it("queues a full text on request and reloads the story", async () => {
    const dialog = await openStory();
    mocked.requestFulltext.mockResolvedValue({ status: "pending" });
    const before = mocked.story.mock.calls.length;
    await userEvent.click(await within(dialog).findByRole("button", { name: "Tam metni getir" }));
    expect(mocked.requestFulltext).toHaveBeenCalledWith(13);
    expect(await screen.findByText("Tam metin sıraya alındı.")).toBeInTheDocument();
    await waitFor(() => expect(mocked.story.mock.calls.length).toBeGreaterThan(before));
  });

  it("reads the original text and asks for a translation", { timeout: 15000 }, async () => {
    mocked.fulltext.mockResolvedValue({ fulltext: fulltext() });
    mocked.translateFulltext.mockResolvedValue({ status: "pending" });
    const dialog = await openStory();
    await userEvent.click(await within(dialog).findByRole("button", { name: /Tam metni oku/ }));
    const reader = (await screen.findAllByRole("dialog")).at(-1)!;
    expect(within(reader).getByText("Tam metin yalnızca sizin okumanız içindir; çıktılara konmaz.")).toBeInTheDocument();
    // The Turkish tab opens first for a Turkish interface; nothing is translated yet.
    expect(await within(reader).findByText("Henüz çevrilmedi")).toBeInTheDocument();
    await userEvent.click(within(reader).getByRole("button", { name: "Çevir" }));
    expect(mocked.translateFulltext).toHaveBeenCalledWith(10);
    expect(await within(reader).findByText("Çevriliyor…")).toBeInTheDocument();
    // The finished translation appears without any action (the reader keeps asking while it is pending).
    mocked.fulltext.mockResolvedValue({ fulltext: fulltext({ translate_status: "done", translations: { tr: "Makalenin ilk paragrafı." } }) });
    expect(await within(reader).findByText("Makalenin ilk paragrafı.", {}, { timeout: TRANSLATION_POLL_MS + 2000 })).toBeInTheDocument();
    await userEvent.click(within(reader).getByRole("button", { name: "Orijinal (İngilizce)" }));
    expect(within(reader).getByText("First paragraph of the article.")).toBeInTheDocument();
    expect(within(reader).getByText("Second paragraph.")).toBeInTheDocument();
  });

  it("shows a finished translation labelled as AI output", async () => {
    mocked.fulltext.mockResolvedValue({
      fulltext: fulltext({ translate_status: "done", translations: { tr: "Makalenin ilk paragrafı.", en: "First paragraph of the article." } }),
    });
    const dialog = await openStory();
    await userEvent.click(await within(dialog).findByRole("button", { name: /Tam metni oku/ }));
    const reader = (await screen.findAllByRole("dialog")).at(-1)!;
    expect(await within(reader).findByText("Makalenin ilk paragrafı.")).toBeInTheDocument();
    expect(within(reader).getByText(/Otomatik çeviri/)).toBeInTheDocument();
    // An English article has no English translation tab.
    expect(within(reader).queryByRole("button", { name: "English" })).not.toBeInTheDocument();
  });

  it("does not offer a translation while the AI is off", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, ai: { ...AI, state: "disabled" } });
    mocked.fulltext.mockResolvedValue({ fulltext: fulltext() });
    const dialog = await openStory();
    await userEvent.click(await within(dialog).findByRole("button", { name: /Tam metni oku/ }));
    const reader = (await screen.findAllByRole("dialog")).at(-1)!;
    expect(await within(reader).findByText(/özetlemeyi açın/)).toBeInTheDocument();
    expect(within(reader).queryByRole("button", { name: "Çevir" })).not.toBeInTheDocument();
  });
});

describe("fulltextErrorKey", () => {
  it("maps known codes, HTTP codes and unknown ones", () => {
    expect(fulltextErrorKey("paywall")).toBe("fulltext.error.paywall");
    expect(fulltextErrorKey("http_403")).toBe("fulltext.error.http");
    expect(fulltextErrorKey("weird")).toBe("fulltext.error.other");
  });
});
