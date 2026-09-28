import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, Article, Meta, Settings, Status } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      update: vi.fn(),
      status: vi.fn(),
      updateSettings: vi.fn(),
      articles: vi.fn(),
      sources: vi.fn(),
      requestAi: vi.fn(),
      retryAi: vi.fn(),
      testOllama: vi.fn(),
      openDataDir: vi.fn(),
      browsers: vi.fn(),
      backups: vi.fn(),
      fulltextSites: vi.fn(),
      home: vi.fn(),
    },
  };
});

import { api } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { FeedPage } from "../pages/FeedPage";
import { SettingsPage } from "../pages/SettingsPage";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, HOME, MAINTENANCE, NOTIFY, STORY_SETTINGS, STORY_WORKER, UPDATE_IDLE } from "./fixtures";

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
  "feed.view": "articles", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [],
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "europe"],
  groups: ["turkey", "western"],
  languages: ["en", "tr"],
  categories: ["politics", "economy", "diplomacy"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR",
  data_dir: "C:\\data",
  version: "0.2.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "qwen3:14b", url: "http://localhost:11434", current_article_id: null,
  last_error: null, last_done_at: null, avg_seconds: 2.5, pending: 0, done: 10, failed: 0, done_24h: 10,
};
const STATUS: Status = {
  version: "0.2.0",
  ai: AI,
  stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 0, last_cycle_feeds: 5, last_cycle_errors: 0 },
  articles: { total: 1, recent: 1 },
};

function article(id: number, title: string, extra: Partial<Article> = {}): Article {
  const now = new Date().toISOString();
  return {
    id, title, url: `https://x.example/${id}`, summary: `${title} summary`, author: null,
    published_at: now, first_seen_at: now, sort_at: now, language: "en", source_id: 1, source_name: "Alpha",
    region: "europe", catalog_group: "western", paywalled: false, exclusive: false, breaking: false, ai_status: null, title_tr: null, summary_tr: null, title_en: null, summary_en: null,
    category: null, countries: [], turkey_relevance: null, turkey_links: [], ai_issues: [], ai_model: null, ai_error: null,
    ...extra,
  };
}

const enriched = (id: number, extra: Partial<Article> = {}) =>
  article(id, "Leaders meet in Brussels", {
    summary: "EU leaders gathered on Saturday.",
    ai_status: "done",
    title_tr: "Liderler Brüksel'de bir araya geldi",
    summary_tr: "AB liderleri cumartesi günü toplandı.",
    category: "diplomacy",
    countries: ["GR", "BE"],
    turkey_relevance: "indirect",
    turkey_links: ["neighbour:GR", "topic:eu_enlargement"],
    ai_model: "qwen3:14b",
    ...extra,
  });

function wrap(ui: ReactNode) {
  return render(
    <AppStateProvider initialSettings={SETTINGS} initialMeta={META}>
      <I18nProvider lang="tr">
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
  mocked.fulltextSites.mockResolvedValue({ sites: [], login_window_open: false });
  mocked.backups.mockResolvedValue({ backups: [], pending_restore: null, last_restore: null, can_restart: true });
  mocked.browsers.mockResolvedValue({ browsers: [], chosen: null, own_profile: "C:\ws\browser-profile", main_profile_in_use: false });
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
  mocked.home.mockResolvedValue(HOME);
});

describe("AI in the feed", () => {
  it("shows the Turkish AI title with category, relevance and the original one click away", async () => {
    mocked.articles.mockResolvedValue({ items: [enriched(1)], next: null, total: 1 });
    wrap(<FeedPage />);
    const link = await screen.findByRole("link", { name: "Liderler Brüksel'de bir araya geldi" });
    const card = link.closest("li")!;
    expect(within(card).queryByText("YZ")).not.toBeInTheDocument(); // no AI badge (decision 2026-09-27)
    expect(within(card).getByText("Diplomasi")).toBeInTheDocument();
    expect(within(card).getByText("Türkiye (dolaylı)")).toHaveAttribute("title", "Komşu ülke: Yunanistan · Konu: AB genişlemesi");
    expect(within(card).getByText("Leaders meet in Brussels")).toBeInTheDocument();
    expect(within(card).getByText("AB liderleri cumartesi günü toplandı.")).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "Orijinal metni göster" }));
    expect(within(card).getByRole("link", { name: "Leaders meet in Brussels" })).toBeInTheDocument();
    expect(within(card).getByText("EU leaders gathered on Saturday.")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Türkçe özeti göster" }));
    expect(within(card).getByRole("link", { name: "Liderler Brüksel'de bir araya geldi" })).toBeInTheDocument();
  });

  it("warns about numbers the AI invented", async () => {
    mocked.articles.mockResolvedValue({ items: [enriched(1, { ai_issues: ["number_not_in_source:15"] })], next: null, total: 1 });
    wrap(<FeedPage />);
    expect(await screen.findByText(/kaynakta geçmeyen bir sayı var \(15\)/)).toBeInTheDocument();
  });

  it("requests translation for an unprocessed article", async () => {
    mocked.articles.mockResolvedValue({ items: [article(7, "Old story")], next: null, total: 1 });
    mocked.requestAi.mockResolvedValue({ status: "pending" });
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Türkçeleştir" }));
    expect(mocked.requestAi).toHaveBeenCalledWith(7);
    expect(await screen.findByText("Özet için kuyruğa alındı")).toBeInTheDocument();
  });

  it("passes category and Türkiye filters to the API", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Türkiye bağlantılı" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ turkey: true })));
    await userEvent.click(screen.getByRole("button", { name: "Kategori" }));
    await userEvent.click(screen.getByRole("option", { name: "Ekonomi" }));
    await waitFor(() =>
      expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ category: ["economy"] })),
    );
  });

  it.each([
    ["unreachable", "Özetler hazırlanamıyor: Ollama'ya ulaşılamıyor", "Yeniden dene"],
    ["model_missing", "Seçili dil modeli bu bilgisayarda yüklü değil", "Ayarlara git"],
    ["no_model", "Özetler için dil modeli seçilmedi", "Ayarlara git"],
    ["timeout", "Ekran kartı meşgul", "Yeniden dene"],
    ["gpu_busy", "Özetler bekliyor: ekran kartı başka bir işle meşgul", "Ayarlara git"],
  ] as const)("explains the AI state %s and keeps showing articles", async (state, title, action) => {
    window.location.hash = "";
    mocked.status.mockResolvedValue({ ...STATUS, ai: { ...AI, state } });
    mocked.articles.mockResolvedValue({ items: [article(1, "Original language story")], next: null, total: 1 });
    mocked.retryAi.mockResolvedValue({ requeued: 0 });
    wrap(<FeedPage />);
    expect(await screen.findByText(title)).toBeInTheDocument();
    expect(screen.getByText("Original language story")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: action }));
    if (action === "Yeniden dene") expect(mocked.retryAi).toHaveBeenCalled();
    else expect(window.location.hash).toBe("#/settings");
  });

  it("shows no AI banner when the AI works", async () => {
    mocked.articles.mockResolvedValue({ items: [article(1, "Story")], next: null, total: 1 });
    wrap(<FeedPage />);
    await screen.findByText("Story");
    expect(screen.queryByText(/Yapay zekâ/)).not.toBeInTheDocument();
  });
});

describe("AI settings", () => {
  it("lists installed models and saves the chosen one", async () => {
    mocked.testOllama.mockResolvedValue({
      ok: true, error_code: null, version: "0.34.3",
      models: [
        { name: "bge-m3:latest", size_gb: 1.2, parameters: "566.70M", capabilities: ["embedding"] },
        { name: "gemma4:12b", size_gb: 7.6, parameters: "11.9B", capabilities: ["completion"] },
        { name: "qwen3:14b", size_gb: 9.3, parameters: "14.8B", capabilities: null },
      ],
    });
    wrap(<SettingsPage />);
    expect(await screen.findByText("Bağlantı başarılı: Ollama 0.34.3, 3 model yüklü.")).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Model" });
    expect(select).toHaveValue("qwen3:14b");
    // The embedding model is not offered for summaries, and chat models are not offered for clustering.
    const chatOptions = within(select).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(chatOptions).toEqual(["gemma4:12b", "qwen3:14b"]);
    const embedSelect = screen.getByRole("combobox", { name: "Birleştirme modeli" });
    await waitFor(() => expect(embedSelect).toHaveValue("bge-m3:latest"));
    expect(within(embedSelect).getAllByRole("option").map((o) => o.getAttribute("value"))).toEqual(["bge-m3:latest", "qwen3:14b"]);
    await userEvent.selectOptions(select, "gemma4:12b");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.model": "gemma4:12b" });
    expect(await screen.findByText("Durum: Hazır, sırada iş yok")).toBeInTheDocument();
  });

  it("does not call the models 'not installed' before Ollama has answered", async () => {
    mocked.testOllama.mockReturnValue(new Promise(() => undefined));
    wrap(<SettingsPage />);
    expect(await screen.findByRole("option", { name: "qwen3:14b" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "bge-m3:latest" })).toBeInTheDocument();
    expect(screen.queryByText(/yüklü değil/)).not.toBeInTheDocument();
  });

  it("marks a configured model that is not installed and explains the connection error", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    wrap(<SettingsPage />);
    expect(await screen.findByText("Bağlantı kurulamadı: Ollama'ya ulaşılamıyor")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "qwen3:14b (yüklü değil)" })).toBeInTheDocument();
  });
});

describe("My country", () => {
  it("shows the country the rules use and saves another one", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    wrap(<SettingsPage />);
    const select = await screen.findByRole("combobox", { name: "Ülke" });
    await waitFor(() => expect(select).toBeEnabled());
    expect(within(select).getByRole("option", { name: "Sistem (Türkiye)" })).toHaveValue("");
    expect(screen.getByText("Azerbaycan, Bulgaristan, Ermenistan, Gürcistan, Irak, İran, Kıbrıs, Suriye, Yunanistan")).toBeInTheDocument();
    await userEvent.selectOptions(select, "ZA");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "home.country": "ZA" });
    await waitFor(() => expect(mocked.home).toHaveBeenCalledTimes(2));
  });

  it("edits topics and extra words and can return to the defaults", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    wrap(<SettingsPage />);
    const nato = await screen.findByRole("checkbox", { name: "NATO" });
    expect(nato).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Göç" })).not.toBeChecked();
    await userEvent.click(nato);
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "home.topics": ["black_sea"] });
    await userEvent.click(screen.getByRole("checkbox", { name: "Göç" }));
    // Topics are saved in the server's order, whatever order they were ticked in.
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.topics": ["black_sea", "nato", "migration"] });
    const words = screen.getByRole("textbox", { name: "Ek kelimeler" });
    await userEvent.type(words, "İzmir, TBMM ,izmir");
    await userEvent.tab();
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.keywords": ["İzmir", "TBMM"] });
    await userEvent.click(await screen.findByRole("button", { name: "Varsayılana dön" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.related": null, "home.topics": null });
  });

  it("names the user's country on cards", async () => {
    mocked.articles.mockResolvedValue({
      items: [enriched(1, { turkey_relevance: "direct", turkey_links: ["home_mentioned"] })], next: null, total: 1,
    });
    wrap(<FeedPage />);
    const badge = await screen.findByTitle("Metinde Türkiye geçiyor");
    expect(badge).toHaveTextContent("Türkiye");
  });
});

describe("AI switched off", () => {
  it.each(["disabled", "no_model"] as const)("does not offer translation when state is %s", async (state) => {
    mocked.status.mockResolvedValue({ ...STATUS, ai: { ...AI, state } });
    mocked.articles.mockResolvedValue({ items: [article(1, "Story")], next: null, total: 1 });
    wrap(<FeedPage />);
    await screen.findByText("Story");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Türkçeleştir" })).not.toBeInTheDocument());
  });
});
