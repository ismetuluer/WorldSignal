import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, Article, Meta, Settings, Source, Status } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      update: vi.fn(),
      status: vi.fn(),
      meta: vi.fn(),
      settings: vi.fn(),
      updateSettings: vi.fn(),
      articles: vi.fn(),
      sources: vi.fn(),
      updateSource: vi.fn(),
      runCollector: vi.fn(),
      testFeed: vi.fn(),
      createSource: vi.fn(),
      requestAi: vi.fn(),
      retryAi: vi.fn(),
      testOllama: vi.fn(),
      searchTranslations: vi.fn(),
      browsers: vi.fn(),
      fulltextSites: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { App } from "../App";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { FeedPage } from "../pages/FeedPage";
import { AddSourceDialog } from "../pages/AddSourceDialog";
import { SourcesPage } from "../pages/SourcesPage";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, STORY_SETTINGS, STORY_WORKER, UPDATE_IDLE } from "./fixtures";

const mocked = vi.mocked(api, true);

const SETTINGS: Settings = {
  "ui.language": "tr",
  "ui.theme": "light",
  "feed.window_hours": 24,
  "ai.enabled": true,
  "ai.url": "http://localhost:11434",
  "ai.model": "qwen3:14b",
  "ai.max_age_hours": 24,
  "ai.yield_gpu": true,
  "feed.view": "articles", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.labels": true, "work.limited": false, "work.start": 7, "work.end": 23, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "europe"],
  home_region: "turkey",
  groups: ["turkey", "western"],
  kinds: ["exclusive", "opinion"],
  languages: ["en", "tr"],
  categories: ["politics", "economy"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"],
  data_dir: "D:\\Veri\\WorldSignal",
  version: "0.1.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "qwen3:14b", url: "http://localhost:11434", current_article_id: null,
  last_error: null, last_done_at: null, avg_seconds: 2.5, pending: 0, done: 10, failed: 0, done_24h: 10,
};
const STATUS: Status = {
  version: "0.1.0",
  ai: AI,
  stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 3, last_cycle_feeds: 5, last_cycle_errors: 0 },
  articles: { total: 3, recent: 3 },
};

function article(id: number, title: string, extra: Partial<Article> = {}): Article {
  return {
    id, title, url: `https://x.example/${id}`, summary: `${title} özeti`, author: null,
    published_at: new Date().toISOString(), first_seen_at: new Date().toISOString(), sort_at: new Date().toISOString(),
    language: "tr", source_id: 1, source_name: "Beta Haber", region: "turkey", catalog_group: "turkey", paywalled: false, exclusive: false, breaking: false,
    ai_status: null, ai_texts: {}, category: null, countries: [], turkey_relevance: null, turkey_links: [],
    ai_issues: [], ai_model: null, ai_error: null,
    ...extra,
  };
}

function source(id: number, name: string, extra: Partial<Source> = {}): Source {
  return {
    id, slug: name.toLowerCase(), name, homepage: null, catalog_group: "turkey", owner: null, region: "turkey",
    language: "tr", reliability: 1, enabled: true, paywalled: false, verified: true, note: null, origin: "catalog", fulltext_mode: "http", fulltext_paused_until: null,
    feeds: [], articles_24h: 4, last_success_at: new Date().toISOString(), status: "ok", ...extra,
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

beforeEach(() => {
  vi.clearAllMocks();
  mocked.update.mockResolvedValue(UPDATE_IDLE);
  mocked.status.mockResolvedValue(STATUS);
  mocked.sources.mockResolvedValue([]);
  mocked.searchTranslations.mockResolvedValue({ state: "disabled", queries: {} });
  mocked.browsers.mockResolvedValue({ browsers: [], chosen: null, own_profile: "C:\WS\browser-profile", main_profile_in_use: false });
  mocked.fulltextSites.mockResolvedValue({ sites: [], login_window_open: false });
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
});

describe("FeedPage", () => {
  it("lists articles with source, language and paywall badges", async () => {
    mocked.articles.mockResolvedValue({
      items: [
        article(1, "IRAK'ta seçim"),
        article(2, "Leaders meet", { language: "en", paywalled: true, source_name: "Alpha" }),
        article(3, "قمة عربية", { language: "ar" }),
      ],
      next: null,
      total: 3,
    });
    wrap(<FeedPage />);
    expect(await screen.findByText("IRAK'ta seçim")).toBeInTheDocument();
    expect(screen.getByText("3 haber · 24 saat")).toBeInTheDocument();
    const english = screen.getByText("Leaders meet").closest("li")!;
    expect(within(english).getByText("İngilizce")).toBeInTheDocument();
    expect(within(english).getByText("Ücretli")).toBeInTheDocument();
    expect(screen.getByText("قمة عربية").closest("li")).toHaveAttribute("dir", "rtl");
    expect(screen.getByText("Bu aralıktaki tüm haberler gösterildi.")).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "IRAK'ta seçim" });
    expect(link).toHaveAttribute("target", "_blank");
    expect(link).toHaveAttribute("rel", expect.stringContaining("noopener"));
  });

  it("shows the search empty state and passes the query to the API", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await userEvent.type(screen.getByRole("searchbox"), "ırak");
    expect(await screen.findByText("“ırak” için sonuç yok")).toBeInTheDocument();
    expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ q: "ırak", hours: 24 }));
    expect(await screen.findByText("Yapay zekâ kapalı; yalnızca yazdığınız kelimelerle arandı.")).toBeInTheDocument();
  });

  it("searches the translations of the typed words as soon as the AI has written them", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    let answer: (v: { state: string; queries: Record<string, string[]> }) => void = () => undefined;
    mocked.searchTranslations.mockReturnValue(new Promise((resolve) => (answer = resolve)));
    wrap(<FeedPage />);
    await userEvent.type(screen.getByRole("searchbox"), "kuzey kore");
    // The typed words are searched at once …
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ q: "kuzey kore", qx: [] })));
    expect(screen.getByText("Diğer dillerde de aranıyor…")).toBeInTheDocument();
    // The AI is asked once the typing has stopped, with the whole words.
    await waitFor(() => expect(mocked.searchTranslations).toHaveBeenCalledWith("kuzey kore"));
    expect(mocked.searchTranslations).toHaveBeenCalledTimes(1);
    // … and the translations follow.
    answer({ state: "ok", queries: { en: ["North Korea"], ru: ["Северная Корея"] } });
    expect(await screen.findByText("Diğer dillerde de arandı: North Korea · Северная Корея")).toBeInTheDocument();
    await waitFor(() =>
      expect(mocked.articles).toHaveBeenLastCalledWith(
        expect.objectContaining({ q: "kuzey kore", qx: ["North Korea", "Северная Корея"] }),
      ),
    );
  });

  it("shows an error state with retry when loading fails", async () => {
    // Every attempt fails until the server "comes back" (the page also retries by itself on the next status poll).
    mocked.articles.mockRejectedValue(new ApiError("server_unreachable", 0));
    wrap(<FeedPage />);
    expect(await screen.findByText(/arka plan hizmetine ulaşılamıyor/)).toBeInTheDocument();
    mocked.articles.mockResolvedValue({ items: [article(1, "Geri geldi")], next: null, total: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(await screen.findByText("Geri geldi")).toBeInTheDocument();
  });

  it("shows the offline banner", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, collector: { ...STATUS.collector, offline: true } });
    mocked.articles.mockResolvedValue({ items: [article(1, "Eski haber")], next: null, total: 1 });
    wrap(<FeedPage />);
    expect(await screen.findByText("İnternet bağlantısı yok gibi görünüyor")).toBeInTheDocument();
  });

  it("changes the time window and remembers it", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "7 gün" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ hours: 168 })));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "feed.window_hours": 168 });
  });

  it("remembers the filters and starts with the remembered ones", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    const { unmount } = wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Türkiye bağlantılı" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ turkey: true })));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({
      "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: true },
    });
    unmount();

    // Next start: the saved filters apply before anything is clicked; a source deleted since is forgotten.
    mocked.articles.mockClear();
    mocked.updateSettings.mockClear();
    mocked.sources.mockResolvedValue([source(7, "Reuters")]);
    const remembered = { regions: [], groups: ["agency"], langs: [], sources: [7, 99], categories: [], turkey: false };
    wrap(<FeedPage />, { ...SETTINGS, "feed.filters": remembered });
    await waitFor(() =>
      expect(mocked.articles).toHaveBeenCalledWith(expect.objectContaining({ group: ["agency"], source: [7, 99] })),
    );
    await waitFor(() =>
      expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "feed.filters": { ...remembered, sources: [7] } }),
    );
    expect((await screen.findAllByRole("button", { name: "Filtreleri temizle" })).length).toBeGreaterThan(0);
  });

  it("moves the selection with J and K", async () => {
    mocked.articles.mockResolvedValue({ items: [article(1, "Bir"), article(2, "İki")], next: null, total: 2 });
    wrap(<FeedPage />);
    await screen.findByText("Bir");
    act(() => {
      fireEvent.keyDown(window, { key: "j" });
    });
    expect(screen.getByText("Bir").closest("li")).toHaveAttribute("aria-selected", "true");
    act(() => {
      fireEvent.keyDown(window, { key: "j" });
    });
    expect(screen.getByText("İki").closest("li")).toHaveAttribute("aria-selected", "true");
    act(() => {
      fireEvent.keyDown(window, { key: "k" });
    });
    expect(screen.getByText("Bir").closest("li")).toHaveAttribute("aria-selected", "true");
  });

  it("renders in English when the UI language is English", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />, { ...SETTINGS, "ui.language": "en" });
    expect(await screen.findByRole("heading", { name: "Feed" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "24 hours" })).toBeInTheDocument();
  });
});

describe("SourcesPage", () => {
  it("puts subscription sources in their own section, naming their usual group", async () => {
    mocked.sources.mockResolvedValue([
      source(1, "Beta Haber"),
      source(2, "Paid Times", { catalog_group: "western", region: "europe", language: "en", paywalled: true }),
    ]);
    wrap(<SourcesPage />);
    const paid = (await screen.findByText("Ücretli kaynaklar")).closest("section")!;
    expect(within(paid).getByText("Paid Times")).toBeInTheDocument();
    expect(within(paid).getByText(/Batı gazeteleri ve yayıncıları · Avrupa/)).toBeInTheDocument();
    expect(within(paid).queryByText("Beta Haber")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /Batı gazeteleri/ })).not.toBeInTheDocument();  // its only source moved
  });

  it("shows the subscription sites below the paid sources", async () => {
    mocked.sources.mockResolvedValue([source(2, "Paid Times", { paywalled: true, fulltext_mode: "browser" })]);
    mocked.fulltextSites.mockResolvedValue({
      sites: [{ id: 2, name: "Paid Times", homepage: "https://paid.example", fulltext_mode: "browser",
                fulltext_paused_until: null, queued: 0, last: null }],
      login_window_open: false,
    });
    wrap(<SourcesPage />);
    const list = await screen.findByRole("list", { name: "Abonelik siteleri" });
    expect(within(list).getByText("Henüz denenmedi")).toBeInTheDocument();
    expect(within(list).getByRole("button", { name: "Paid Times için tam metni dene" })).toBeInTheDocument();
    // Searching the sources hides it.
    await userEvent.type(screen.getByRole("searchbox"), "paid");
    await waitFor(() => expect(screen.queryByRole("list", { name: "Abonelik siteleri" })).not.toBeInTheDocument());
  });

  it("groups sources, separates unverified ones and shows errors", async () => {
    mocked.sources.mockResolvedValue([
      source(1, "Beta Haber"),
      source(2, "Alpha News", {
        catalog_group: "western", region: "europe", language: "en", status: "error",
        feeds: [{
          id: 9, source_id: 2, url: "https://a.example/rss", label: null, enabled: true, verified: true,
          fetch_interval_min: 15, last_attempt_at: null, last_success_at: null, next_fetch_at: null,
          last_status: "error", last_error_code: "http_403", last_error_detail: null, consecutive_failures: 2,
          last_item_count: null, last_new_count: null,
        }],
      }),
      source(3, "Dead Feed", { verified: false, enabled: false, status: "disabled" }),
    ]);
    wrap(<SourcesPage />);
    expect(await screen.findByText("Türk kaynakları")).toBeInTheDocument();
    expect(screen.getByText("Batı gazeteleri ve yayıncıları")).toBeInTheDocument();
    expect(screen.getByText("Doğrulanmamış kaynaklar")).toBeInTheDocument();
    expect(screen.getByText("2 etkin · 1 hatalı · 1 doğrulanmamış")).toBeInTheDocument();
    expect(screen.getByText(/otomatik okuyuculara erişim izni vermiyor/)).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Hatalı (1)" }));
    expect(screen.queryByText("Beta Haber")).not.toBeInTheDocument();
    expect(screen.getByText("Alpha News")).toBeInTheDocument();
  });

  it("toggles a source and rolls back on failure", async () => {
    const beta = source(1, "Beta Haber");
    mocked.sources.mockResolvedValue([beta]);
    mocked.updateSource.mockRejectedValueOnce(new ApiError("server_unreachable", 0));
    wrap(<SourcesPage />);
    const toggle = await screen.findByRole("switch", { name: "Beta Haber kaynağını aç veya kapat" });
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "true"));
    expect(await screen.findByText(/arka plan hizmetine ulaşılamıyor/)).toBeInTheDocument();

    mocked.updateSource.mockResolvedValueOnce({ ...beta, enabled: false, status: "disabled" });
    await userEvent.click(toggle);
    await waitFor(() => expect(toggle).toHaveAttribute("aria-checked", "false"));
    expect(mocked.updateSource).toHaveBeenLastCalledWith(1, { enabled: false });
  });
});

describe("AddSourceDialog", () => {
  it("offers the feeds a web page has and tests the chosen one", async () => {
    mocked.testFeed
      .mockResolvedValueOnce({
        ok: false, error_code: "not_a_feed",
        suggestions: [
          { url: "https://site.example/feed", kind: "rss", title: "Son dakika" },
          { url: "https://site.example/news-sitemap.xml", kind: "sitemap", title: "" },
        ],
      })
      .mockResolvedValueOnce({
        ok: true, error_code: null, title: null, language: "tr", item_count: 40, newest_at: null,
        sample_titles: ["Başlık"], final_url: "https://site.example/news-sitemap.xml",
      });
    wrap(<AddSourceDialog onClose={() => undefined} onAdded={() => undefined} />);
    await userEvent.type(screen.getByRole("textbox"), "https://site.example/");
    await userEvent.click(screen.getByRole("button", { name: "Test et" }));
    expect(await screen.findByText("Bu sitede bulunan akışlar:")).toBeInTheDocument();
    expect(screen.getByText("Son dakika")).toBeInTheDocument();
    expect(screen.getByText("Haber site haritası")).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Dene" })[1]!);
    expect(mocked.testFeed).toHaveBeenLastCalledWith("https://site.example/news-sitemap.xml");
    expect(await screen.findByText("Akış çalışıyor: 40 haber bulundu.")).toBeInTheDocument();
    expect(screen.getByDisplayValue("https://site.example/news-sitemap.xml")).toBeInTheDocument();
  });

  it("says so when a page offers nothing, and explains robots.txt refusals", async () => {
    mocked.testFeed
      .mockResolvedValueOnce({ ok: false, error_code: "not_a_feed", suggestions: [] })
      .mockResolvedValueOnce({ ok: false, error_code: "robots_disallow" });
    wrap(<AddSourceDialog onClose={() => undefined} onAdded={() => undefined} />);
    await userEvent.type(screen.getByRole("textbox"), "https://empty.example/");
    await userEvent.click(screen.getByRole("button", { name: "Test et" }));
    expect(await screen.findByText(/izin verilen bir haber site haritası bulunamadı/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Test et" }));
    expect(await screen.findByText(/robots.txt dosyasında otomatik okuyuculara/)).toBeInTheDocument();
  });
});

describe("App", () => {
  it("explains when opened without a session token", () => {
    render(<App hasToken={false} />);
    expect(screen.getByText("Bu sayfa World Signal penceresinin içinden açılmalı.")).toBeInTheDocument();
  });
});
