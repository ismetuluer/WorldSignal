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
      meta: vi.fn(),
      aiKeys: vi.fn(),
      setAiKey: vi.fn(),
      deleteAiKey: vi.fn(),
      testCloud: vi.fn(),
      regroupStories: vi.fn(),
      extension: vi.fn(),
    },
  };
});

import { api } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { FeedPage } from "../pages/FeedPage";
import { HomeSettings } from "../pages/HomeSettings";
import { SettingsPage } from "../pages/SettingsPage";
import { AppStateProvider, useAppState } from "../state";
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
  "feed.view": "articles", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.labels": true, "work.limited": false, "work.start": 7, "work.end": 23, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "europe"],
  home_region: "turkey",
  groups: ["turkey", "western"],
  kinds: ["exclusive", "opinion"],
  languages: ["en", "tr"],
  categories: ["politics", "economy", "diplomacy"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"], ai_prompt_defaults: { article: "Default article. {fields}", translate: "Into {language}." }, ai_input_defaults: { article: "Source: {source}\nHeadline: {title}" }, ai_limit_ranges: { batch_size: [10, 2, 25], article_chars: [6000, 200, 60000], batch_chars: [600, 100, 6000], story_reports: [8, 2, 30], story_report_chars: [700, 100, 6000] },
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
  articles: { total: 1, recent: 1 }, extension: null,
};

function article(id: number, title: string, extra: Partial<Article> = {}): Article {
  const now = new Date().toISOString();
  return {
    id, title, url: `https://x.example/${id}`, summary: `${title} summary`, author: null,
    published_at: now, first_seen_at: now, sort_at: now, language: "en", source_id: 1, source_name: "Alpha",
    region: "europe", catalog_group: "western", paywalled: false, exclusive: false, breaking: false, ai_status: null, ai_texts: {},
    category: null, countries: [], turkey_relevance: null, turkey_links: [], ai_issues: [], ai_model: null, ai_error: null,
    ...extra,
  };
}

const enriched = (id: number, extra: Partial<Article> = {}) =>
  article(id, "Leaders meet in Brussels", {
    summary: "EU leaders gathered on Saturday.",
    ai_status: "done",
    ai_texts: { tr: { title: "Liderler Brüksel'de bir araya geldi", summary: "AB liderleri cumartesi günü toplandı." } },
    category: "diplomacy",
    countries: ["GR", "BE"],
    turkey_relevance: "indirect",
    turkey_links: ["neighbour:GR", "topic:eu_enlargement"],
    ai_model: "qwen3:14b",
    ...extra,
  });

function wrap(ui: ReactNode, settings: Settings = SETTINGS) {
  return render(
    <AppStateProvider initialSettings={settings} initialMeta={META}>
      <I18nProvider lang="tr">
        <ToastProvider>{ui}</ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}

/** The settings page is split into categories; the page remembers the one that was open. */
function openSettings(category: string) {
  localStorage.setItem("worldsignal.settings.category", category);
  return wrap(<SettingsPage />);
}

beforeEach(() => {
  vi.clearAllMocks();
  mocked.extension.mockResolvedValue({ code: "abc", port: 47821, fixed_port: true, status: { connected: true, warn: false, last_seen: null, read_today: 0, reading: null, last_source: null, last_error: null, version: "0.16.0", outdated: false } });
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
    const headline = await screen.findByRole("button", { name: "Liderler Brüksel'de bir araya geldi" });
    const card = headline.closest("li")!;
    expect(within(card).queryByText("YZ")).not.toBeInTheDocument(); // no AI badge (decision 2026-09-27)
    expect(within(card).getByText("Diplomasi")).toBeInTheDocument();
    expect(within(card).getByText("Türkiye (dolaylı)")).toHaveAttribute("title", "Komşu ülke: Yunanistan · Konu: AB genişlemesi");
    expect(within(card).getByText("Leaders meet in Brussels")).toBeInTheDocument();
    expect(within(card).getByText("AB liderleri cumartesi günü toplandı.")).toBeInTheDocument();

    await userEvent.click(within(card).getByRole("button", { name: "Orijinal metni göster" }));
    expect(within(card).getByRole("button", { name: "Leaders meet in Brussels" })).toBeInTheDocument();
    expect(within(card).getByText("EU leaders gathered on Saturday.")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Özeti göster" }));
    expect(within(card).getByRole("button", { name: "Liderler Brüksel'de bir araya geldi" })).toBeInTheDocument();
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
    await userEvent.click(await screen.findByRole("button", { name: "Özetle" }));
    expect(mocked.requestAi).toHaveBeenCalledWith(7);
    expect(await screen.findByText("Özet için kuyruğa alındı")).toBeInTheDocument();
  });

  it("offers the summary of a report that was read quickly (headline only)", async () => {
    const quick = enriched(8, { ai_brief: 1 });
    quick.ai_texts = { tr: { title: "Hızlı başlık", summary: "" }, en: { title: "Quick headline", summary: "" } };
    mocked.articles.mockResolvedValue({ items: [quick], next: null, total: 1 });
    mocked.requestAi.mockResolvedValue({ status: "pending" });
    wrap(<FeedPage />);
    const card = (await screen.findByRole("button", { name: "Hızlı başlık" })).closest("li")!;
    expect(within(card).getByText(quick.summary)).toBeInTheDocument();  // the feed's own summary meanwhile
    await userEvent.click(within(card).getByRole("button", { name: "Özetle" }));
    expect(mocked.requestAi).toHaveBeenCalledWith(8);
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
    ["unreachable", "Özetler hazırlanamıyor: Ollama hizmetine ulaşılamıyor", "Yeniden dene"],
    ["model_missing", "Seçili dil modeli bulunamadı", "Ayarlara git"],
    ["no_model", "Özetler için dil modeli seçilmedi", "Ayarlara git"],
    ["timeout", "Ekran kartı meşgul", "Yeniden dene"],
    ["gpu_busy", "Özetler bekliyor: ekran kartı başka bir işle meşgul", "Ayarlara git"],
    ["no_key", "Özetler için API anahtarı gerekli", "Ayarlara git"],
    ["bad_key", "API anahtarı kabul edilmedi", "Ayarlara git"],
    ["rate_limited", "Özetler bekliyor: Google Gemini istek sınırı doldu", "Yeniden dene"],
  ] as const)("explains the AI state %s and keeps showing articles", async (state, title, action) => {
    window.location.hash = "";
    const provider = ["no_key", "bad_key", "rate_limited"].includes(state) ? "gemini" : "ollama";
    mocked.status.mockResolvedValue({ ...STATUS, ai: { ...AI, state, provider } });
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
    openSettings("ai");
    expect(await screen.findByText("Bağlantı başarılı: Ollama 0.34.3, 3 model yüklü.")).toBeInTheDocument();
    const select = screen.getByRole("combobox", { name: "Model" });
    expect(select).toHaveValue("qwen3:14b");
    // The embedding model is not offered for summaries, and chat models are not offered for clustering.
    const chatOptions = within(select).getAllByRole("option").map((o) => o.getAttribute("value"));
    expect(chatOptions).toEqual(["gemma4:12b", "qwen3:14b"]);
    await userEvent.selectOptions(select, "gemma4:12b");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.model": "gemma4:12b" });
    expect(await screen.findByText("Durum: Hazır, sırada iş yok")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Haber toplama" }));
    const embedSelect = screen.getByRole("combobox", { name: "Birleştirme modeli" });
    await waitFor(() => expect(embedSelect).toHaveValue("bge-m3:latest"));
    expect(within(embedSelect).getAllByRole("option").map((o) => o.getAttribute("value"))).toEqual(["bge-m3:latest", "qwen3:14b"]);
  });

  it("chooses how much the AI writes", async () => {
    openSettings("ai");
    const group = await screen.findByRole("group", { name: "Özetleme kapsamı" });
    expect(within(group).getByRole("button", { name: "Hızlı" })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/tek kaynaklı haberler 10’arlı işlenir/)).toBeInTheDocument();
    await userEvent.click(within(group).getByRole("button", { name: "Her haber ayrı" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.depth": "full" });
  });

  it("does not call the models 'not installed' before Ollama has answered", async () => {
    mocked.testOllama.mockReturnValue(new Promise(() => undefined));
    openSettings("ai");
    expect(await screen.findByRole("option", { name: "qwen3:14b" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Haber toplama" }));
    expect(screen.getByRole("option", { name: "bge-m3:latest" })).toBeInTheDocument();
    expect(screen.queryByText(/yüklü değil/)).not.toBeInTheDocument();
  });

  it("marks a configured model that is not installed and explains the connection error", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    openSettings("ai");
    expect(await screen.findByText("Bağlantı kurulamadı: Ollama hizmetine ulaşılamıyor")).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "qwen3:14b (yüklü değil)" })).toBeInTheDocument();
  });
});

describe("Cloud AI", () => {
  it("chooses a cloud service, saves a write-only key and picks a model from the service's list", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    mocked.aiKeys.mockResolvedValue({ gemini: false, openai: false, anthropic: false });
    mocked.setAiKey.mockResolvedValue({ gemini: true, openai: false, anthropic: false });
    mocked.deleteAiKey.mockResolvedValue({ gemini: false, openai: false, anthropic: false });
    mocked.testCloud.mockResolvedValue({ ok: true, error_code: null, models: ["gemini-a", "gemini-b"] });
    openSettings("ai");
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Yapay zekâ nerede çalışsın?" }), "gemini");
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ai.provider": "gemini" });
    expect(await screen.findByText(/abonelikle okunan tam metinler dahil\) ve arama kelimeleriniz Google Gemini hizmetine gönderilir/)).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Ollama adresi" })).not.toBeInTheDocument();

    const keyInput = await screen.findByLabelText("API anahtarı");
    expect(keyInput).toHaveAttribute("type", "password");
    await userEvent.type(keyInput, "AIza-secret-key");
    await userEvent.click(screen.getByRole("button", { name: "Kaydet" }));
    expect(mocked.setAiKey).toHaveBeenCalledWith("gemini", "AIza-secret-key");
    expect(await screen.findByText("Anahtar kayıtlı (bu bilgisayarda, şifreli).")).toBeInTheDocument();
    expect(keyInput).toHaveValue("");  // the key is not kept on screen
    expect(await screen.findByText("Bağlantı başarılı: 2 model.")).toBeInTheDocument();

    const model = screen.getByRole("combobox", { name: "Model" });
    await userEvent.type(model, "gemini-a");
    await userEvent.tab();
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ai.gemini_model": "gemini-a" });
    await userEvent.click(screen.getByRole("button", { name: "Anahtarı sil" }));
    expect(mocked.deleteAiKey).toHaveBeenCalledWith("gemini");
  });
});

describe("AI languages", () => {
  it("adds and removes the languages the AI writes in, keeping at least one", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    openSettings("ai");
    const list = await screen.findByRole("list", { name: "Özet dilleri" });
    // Not set yet: the interface language and English.
    expect(within(list).getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Türkçe", "İngilizce"]);
    await userEvent.click(within(list).getByRole("button", { name: "İngilizce kaldır" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ai.languages": ["tr"] });
    expect(within(list).queryByRole("button", { name: "Türkçe kaldır" })).not.toBeInTheDocument(); // the last one stays
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Dil ekle…" }), "pt");
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ai.languages": ["tr", "pt"] });
    expect(within(list).getByText("Portekizce")).toBeInTheDocument();
  });

  it("refreshes the language filter choices when new reports arrive", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    mocked.meta.mockResolvedValue({ ...META, languages: ["en", "pt", "tr"] });
    const { rerender } = wrap(<FeedPage />);
    await waitFor(() => expect(mocked.status).toHaveBeenCalled());
    expect(mocked.meta).not.toHaveBeenCalled();  // nothing new yet
    mocked.status.mockResolvedValue({ ...STATUS, articles: { total: 7, recent: 7 } });
    rerender(
      <AppStateProvider initialSettings={SETTINGS} initialMeta={META}>
        <I18nProvider lang="tr"><ToastProvider><StatusRefresher /></ToastProvider></I18nProvider>
      </AppStateProvider>,
    );
    await userEvent.click(await screen.findByRole("button", { name: "refresh" }));
    await waitFor(() => expect(mocked.meta).toHaveBeenCalled());
  });
});

function StatusRefresher() {
  const { refreshStatus, status } = useAppState();
  return <button onClick={() => refreshStatus()}>{status ? "refresh" : "wait"}</button>;
}

describe("My country", () => {
  it("shows the country the rules use and saves another one", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    openSettings("collect");
    const select = await screen.findByRole("combobox", { name: "Ülke" });
    await waitFor(() => expect(select).toBeEnabled());
    expect(within(select).getByRole("option", { name: "Sistem (Türkiye)" })).toHaveValue("");
    expect(screen.getByText("Azerbaycan, Bulgaristan, Ermenistan, Gürcistan, Irak, İran, Kıbrıs, Suriye, Yunanistan")).toBeInTheDocument();
    await userEvent.selectOptions(select, "ZA");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "home.country": "ZA" });
    await waitFor(() => expect(mocked.home).toHaveBeenCalledTimes(2));
  });

  it("adds and removes topics, including the user's own, and can return to the defaults", async () => {
    mocked.testOllama.mockResolvedValue({ ok: false, error_code: "unreachable", version: null, models: [] });
    openSettings("collect");
    const topics = await screen.findByRole("list", { name: "Konular" });
    expect(within(topics).getByText("Karadeniz")).toBeInTheDocument();
    await userEvent.click(within(topics).getByRole("button", { name: "NATO kaldır" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "home.topics": ["black_sea"] });
    // A built-in suggestion, then a topic of one's own.
    await userEvent.click(screen.getByRole("button", { name: "+ Göç" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.topics": ["black_sea", "nato", "migration"] });
    await userEvent.type(screen.getByRole("textbox", { name: "Konu ekle" }), "  Kıbrıs sorunu ");
    await userEvent.click(screen.getByRole("button", { name: "Konu ekle" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.topics": ["black_sea", "nato", "Kıbrıs sorunu"] });
    expect(screen.getByRole("textbox", { name: "Konu ekle" })).toHaveValue("");
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

  it("hides the country filter and labels when 'my country' is off", async () => {
    mocked.articles.mockResolvedValue({
      items: [enriched(1, { turkey_relevance: "direct", turkey_links: ["home_mentioned"] })], next: null, total: 1,
    });
    // A filter remembered while it was on does not apply any more.
    const filters = { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: true };
    wrap(<FeedPage />, { ...SETTINGS, "home.enabled": false, "feed.filters": filters });
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ turkey: false })));
    expect(screen.queryByRole("button", { name: "Türkiye bağlantılı" })).not.toBeInTheDocument();
    expect(screen.queryByTitle("Metinde Türkiye geçiyor")).not.toBeInTheDocument();
  });

  it("switches 'my country' off and hides its details", async () => {
    wrap(<HomeSettings />, { ...SETTINGS, "home.enabled": false });
    const toggle = await screen.findByRole("switch", { name: "Ülkem özelliği" });
    expect(screen.queryByRole("combobox", { name: "Ülke" })).not.toBeInTheDocument();
    await userEvent.click(toggle);
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.enabled": true });
  });

  it("hides the country labels on cards when only the labels are off", async () => {
    mocked.articles.mockResolvedValue({
      items: [enriched(1, { turkey_relevance: "direct", turkey_links: ["home_mentioned"] })], next: null, total: 1,
    });
    wrap(<FeedPage />, { ...SETTINGS, "home.labels": false });
    await screen.findByText("Liderler Brüksel'de bir araya geldi");
    expect(screen.queryByTitle("Metinde Türkiye geçiyor")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Türkiye bağlantılı" })).toBeInTheDocument();  // the filter stays
  });

  it("switches the country labels off separately", async () => {
    wrap(<HomeSettings />);
    await userEvent.click(await screen.findByRole("switch", { name: "Ülke etiketleri" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "home.labels": false });
  });

  it("offers 'outside my region' instead of 'global' in the region filter", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Bölge" }));
    expect(screen.getByRole("option", { name: "Yerel dışı" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Küresel" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Yerel dışı" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ region: ["abroad"] })));
  });

  it("offers exclusives and opinion pieces in the source-group filter", async () => {
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Kaynak grubu" }));
    expect(screen.getByRole("option", { name: "Özel haberler" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("option", { name: "Makaleler (görüş, analiz, köşe yazısı)" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenLastCalledWith(expect.objectContaining({ group: ["opinion"] })));
  });
});

describe("AI switched off", () => {
  it.each(["disabled", "no_model"] as const)("does not offer translation when state is %s", async (state) => {
    mocked.status.mockResolvedValue({ ...STATUS, ai: { ...AI, state } });
    mocked.articles.mockResolvedValue({ items: [article(1, "Story")], next: null, total: 1 });
    wrap(<FeedPage />);
    await screen.findByText("Story");
    await waitFor(() => expect(screen.queryByRole("button", { name: "Özetle" })).not.toBeInTheDocument());
  });
});

describe("Settings page layout", () => {
  beforeEach(() => localStorage.clear());

  it("shows one category at a time, starting with General, and remembers the last one", async () => {
    const first = wrap(<SettingsPage />);
    expect(await screen.findByRole("heading", { name: "Görünüm" })).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Model" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Genel" })).toHaveAttribute("aria-current", "page");
    await userEvent.click(screen.getByRole("button", { name: "Yapay zekâ" }));
    expect(await screen.findByRole("combobox", { name: "Model" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Görünüm" })).not.toBeInTheDocument();
    first.unmount();
    wrap(<SettingsPage />);
    expect(await screen.findByRole("combobox", { name: "Model" })).toBeInTheDocument();
  });

  it("searches every category and hides what does not match", async () => {
    wrap(<SettingsPage />);
    await userEvent.type(await screen.findByRole("searchbox", { name: "Ayar ara" }), "özet dilleri");
    expect(await screen.findByRole("list", { name: "Özet dilleri" })).toBeInTheDocument();
    expect(screen.queryByText("Arayüz dili")).not.toBeVisible();
    await userEvent.clear(screen.getByRole("searchbox", { name: "Ayar ara" }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Ayar ara" }), "zzzyok");
    expect(await screen.findByText("“zzzyok” ile eşleşen ayar yok.")).toBeInTheDocument();
  });
});

describe("Regrouping stories", () => {
  beforeEach(() => localStorage.clear());

  it("tells how many stories would change, and only changes them after the user agrees", async () => {
    mocked.regroupStories.mockResolvedValue({ changed: 3, created: 5 });
    openSettings("collect");
    await userEvent.click(await screen.findByRole("button", { name: "Denetle" }));
    expect(await screen.findByText("3 hikâye bölünecek, 5 yeni hikâye oluşacak. Uygulansın mı?")).toBeInTheDocument();
    expect(mocked.regroupStories).toHaveBeenCalledWith(true);
    await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(screen.queryByText(/Uygulansın mı/)).not.toBeInTheDocument();
    expect(mocked.regroupStories).toHaveBeenCalledTimes(1);
    await userEvent.click(screen.getByRole("button", { name: "Denetle" }));
    await userEvent.click(await screen.findByRole("button", { name: "Uygula" }));
    expect(mocked.regroupStories).toHaveBeenLastCalledWith(false);
    expect(await screen.findByText("3 hikâye bölündü, 5 yeni hikâye oluştu.")).toBeInTheDocument();
  });

  it("says so when the stories already fit", async () => {
    mocked.regroupStories.mockResolvedValue({ changed: 0, created: 0 });
    openSettings("collect");
    await userEvent.click(await screen.findByRole("button", { name: "Denetle" }));
    expect(await screen.findByText("Son 3 günün hikâyeleri bu eşikle zaten uyumlu.")).toBeInTheDocument();
  });
});
