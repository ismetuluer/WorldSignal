import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, Meta, Settings, Status, Story, StoryMember } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      status: vi.fn(),
      settings: vi.fn(),
      updateSettings: vi.fn(),
      articles: vi.fn(),
      sources: vi.fn(),
      stories: vi.fn(),
      story: vi.fn(),
      detachArticle: vi.fn(),
      mergeStories: vi.fn(),
      summarizeStory: vi.fn(),
      storyNote: vi.fn(),
      saveStoryNote: vi.fn(),
      meeting: vi.fn(),
      addToMeeting: vi.fn(),
      removeMeetingItem: vi.fn(),
      testOllama: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { FeedPage } from "../pages/FeedPage";
import { parseKeywords } from "../pages/StorySettings";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, NO_FULLTEXT, STORY_SETTINGS, STORY_WORKER } from "./fixtures";

const mocked = vi.mocked(api, true);

const SETTINGS: Settings = {
  "ui.language": "tr",
  "ui.theme": "light",
  "feed.window_hours": 24,
  "feed.view": "stories", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.labels": true, "work.limited": false, "work.start": 7, "work.end": 23, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null,
  "ai.enabled": true,
  "ai.url": "http://localhost:11434",
  "ai.model": "qwen3:14b",
  "ai.max_age_hours": 24,
  "ai.yield_gpu": true,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "middle_east"],
  home_region: "turkey",
  groups: ["turkey", "western"],
  kinds: ["exclusive", "opinion"],
  languages: ["en", "tr"],
  categories: ["politics", "diplomacy"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"], ai_prompt_defaults: { article: "Default article. {fields}", translate: "Into {language}." }, ai_input_defaults: { article: "Source: {source}\nHeadline: {title}" }, ai_limit_ranges: { batch_size: [10, 2, 25], article_chars: [6000, 200, 60000], batch_chars: [600, 100, 6000], story_reports: [8, 2, 30], story_report_chars: [700, 100, 6000] },
  data_dir: "C:\\data",
  version: "0.3.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "qwen3:14b", url: "http://localhost:11434", current_article_id: null,
  last_error: null, last_done_at: null, avg_seconds: 2.5, pending: 0, done: 10, failed: 0, done_24h: 10,
};
const STATUS: Status = {
  version: "0.3.0",
  ai: AI,
  stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 0, last_cycle_feeds: 5, last_cycle_errors: 0 },
  articles: { total: 3, recent: 3 }, extension: null,
};

const NOW = new Date().toISOString();

function member(id: number, source: string, extra: Partial<StoryMember> = {}): StoryMember {
  return {
    id, url: `https://x.example/${id}`, title: `Report ${id}`, summary: "", sort_at: NOW, language: "en",
    source_id: id, source_name: source, paywalled: false, exclusive: false, region: "europe", similarity: 0.8, assigned_by: "auto",
    ai_texts: {}, ...NO_FULLTEXT, ...extra,
  };
}

function story(id: number, extra: Partial<Story> = {}): Story {
  const members = extra.members ?? [member(id * 10, "Reuters"), member(id * 10 + 1, "BBC")];
  return {
    id, breaking: false, exclusive: false, first_seen_at: NOW, last_seen_at: NOW, article_count: members.length, source_count: members.length, score: 64.2,
    score_parts: {
      components: { sources: 0.5, freshness: 0.9, turkey: 1, interest: 0 },
      tags: [{ kind: "sources", count: 5 }, { kind: "age", hours: 0.5 }, { kind: "spreading", count: 4, hours: 3 }, { kind: "turkey", level: "direct" }],
    },
    turkey_relevance: "direct", category: "diplomacy", representative_id: members[0]!.id, representative: members[0]!,
    ai_status: "done", ai_texts: { tr: { title: `Hikâye ${id}`, summary: "Türkçe özet.", why: "Türkiye'yi doğrudan ilgilendiriyor." } },
    ai_issues: [], ai_article_count: members.length, ai_model: "qwen3:14b",
    sources: [...new Set(members.map((m) => m.source_name))].sort(), members, timeline: [],
    ...extra,
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
  vi.resetAllMocks(); // also drops answers left over from the previous test
  mocked.status.mockResolvedValue(STATUS);
  mocked.sources.mockResolvedValue([]);
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
  mocked.storyNote.mockResolvedValue({ note: null });
});

describe("Stories view", () => {
  it("shows ranked story cards with the reasons behind the score", async () => {
    mocked.stories.mockResolvedValue({ items: [story(1), story(2, { ai_status: null, ai_texts: {} })], total: 2 });
    wrap(<FeedPage />);
    const card = (await screen.findByText("Hikâye 1")).closest("li")!;
    expect(screen.getByText("2 hikâye · 24 saat")).toBeInTheDocument();
    expect(within(card).getByText("64")).toBeInTheDocument();
    expect(within(card).getByText("5 kaynak")).toBeInTheDocument();
    expect(within(card).getByText("3 saatte 4 kaynak")).toBeInTheDocument();
    expect(within(card).getByText("Türkiye bağlantısı")).toBeInTheDocument();
    expect(within(card).getByText("Türkiye'yi doğrudan ilgilendiriyor.")).toBeInTheDocument();
    expect(within(card).getByText("BBC · Reuters")).toBeInTheDocument();
    // Without a story summary the representative article's original title is shown.
    expect(screen.getByText("Report 20")).toBeInTheDocument();
    expect(mocked.stories).toHaveBeenCalledWith(expect.objectContaining({ hours: 24, sort: "score", min_sources: 1, offset: 0 }));
    expect(mocked.articles).not.toHaveBeenCalled();
  });

  it("marks breaking and exclusive stories", async () => {
    mocked.stories.mockResolvedValue({ items: [story(1, { breaking: true, exclusive: true }), story(2)], total: 2 });
    wrap(<FeedPage />);
    const first = (await screen.findByText("Hikâye 1")).closest("li")!;
    const breaking = within(first).getByText("Son dakika");
    expect(breaking.querySelector(".live-dot")).not.toBeNull();  // the blinking red dot
    expect(within(first).getByText("Özel haber")).toBeInTheDocument();
    const second = screen.getByText("Hikâye 2").closest("li")!;
    expect(within(second).queryByText("Son dakika")).not.toBeInTheDocument();
    expect(within(second).queryByText("Özel haber")).not.toBeInTheDocument();
  });

  it("names who reported first and where the outlets disagree", async () => {
    const disagree = { tr: { title: "Hikâye 1", summary: "Özet.", why: "", conflict: "Reuters 12 ölü, Al Jazeera 20 ölü bildirdi." } };
    mocked.stories.mockResolvedValue({
      items: [story(1, { first: { source: "Reuters", at: NOW }, ai_texts: disagree }), story(2)], total: 2,
    });
    wrap(<FeedPage />);
    const first = (await screen.findByText("Hikâye 1")).closest("li")!;
    expect(within(first).getByText(/İlk veren:/).closest("p")).toHaveTextContent("Reuters");
    expect(within(first).getByRole("note")).toHaveTextContent("Kaynaklar çelişiyor: Reuters 12 ölü, Al Jazeera 20 ölü bildirdi.");
    // No first outlet and no disagreement: nothing is shown.
    const second = screen.getByText("Hikâye 2").closest("li")!;
    expect(within(second).queryByText(/İlk veren:/)).not.toBeInTheDocument();
    expect(within(second).queryByText(/Kaynaklar çelişiyor/)).not.toBeInTheDocument();
  });

  it("switches between stories and articles and remembers the choice", async () => {
    mocked.stories.mockResolvedValue({ items: [story(1)], total: 1 });
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<FeedPage />);
    await screen.findByText("Hikâye 1");
    await userEvent.click(screen.getByRole("button", { name: "Haberler" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "feed.view": "articles" });
    await waitFor(() => expect(mocked.articles).toHaveBeenCalled());
  });

  it("filters to multi-source stories and sorts by recency", async () => {
    mocked.stories.mockResolvedValue({ items: [story(1)], total: 1 });
    wrap(<FeedPage />);
    await screen.findByText("Hikâye 1");
    await userEvent.click(screen.getByRole("button", { name: "Yalnızca çok kaynaklı" }));
    await waitFor(() => expect(mocked.stories).toHaveBeenLastCalledWith(expect.objectContaining({ min_sources: 2 })));
    await userEvent.click(screen.getByRole("button", { name: "En yeni" }));
    await waitFor(() => expect(mocked.stories).toHaveBeenLastCalledWith(expect.objectContaining({ sort: "recent", min_sources: 2 })));
  });

  it("explains an empty story list", async () => {
    mocked.stories.mockResolvedValue({ items: [], total: 0 });
    wrap(<FeedPage />);
    expect(await screen.findByText("Henüz hikâye yok")).toBeInTheDocument();
  });

  it("offers retry when stories cannot be loaded", async () => {
    mocked.stories.mockRejectedValue(new ApiError("server_unreachable", 0));
    wrap(<FeedPage />);
    expect(await screen.findByText("Bir sorun oluştu")).toBeInTheDocument();
    mocked.stories.mockResolvedValue({ items: [story(1)], total: 1 });
    await userEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    expect(await screen.findByText("Hikâye 1")).toBeInTheDocument();
  });

  it("warns when the clustering model is missing", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, stories: { ...STORY_WORKER, state: "model_missing", model: "bge-m3:latest" } });
    mocked.stories.mockResolvedValue({ items: [], total: 0 });
    wrap(<FeedPage />);
    expect(await screen.findByText("Hikâye birleştirme modeli yüklü değil")).toBeInTheDocument();
  });
});

describe("Story detail", () => {
  const full = story(1, {
    members: [
      member(10, "Reuters", { ai_texts: { tr: { title: "Reuters başlığı", summary: "" } }, language: "en" }),
      member(11, "BBC", { assigned_by: "user" }),
      member(12, "Al Jazeera", { language: "ar", title: "قمة" }),
    ],
    ai_issues: ["number_not_in_source:12"],
  });

  async function open() {
    mocked.stories.mockResolvedValue({ items: [story(1), story(2, { ai_texts: { tr: { title: "Başka olay", summary: "Türkçe özet." } } })], total: 2 });
    mocked.story.mockResolvedValue(full);
    wrap(<FeedPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Hikâye 1" }));
    return screen.findByRole("dialog");
  }

  it("shows the summary, the score breakdown and every report with its original link", async () => {
    const dialog = await open();
    expect(await within(dialog).findByText("Bu hikâyedeki haberler")).toBeInTheDocument();
    expect(within(dialog).getByText("Türkçe özet.")).toBeInTheDocument();
    expect(within(dialog).getByText("Dikkat: özette kaynaklarda geçmeyen sayı var (12). Haberleri kontrol edin.")).toBeInTheDocument();
    expect(within(dialog).getByText("Bağımsız kaynaklar")).toBeInTheDocument();
    expect(within(dialog).getByText("50 × 45%")).toBeInTheDocument();
    const report = within(dialog).getByRole("button", { name: /Reuters başlığı/ }).closest("li")!;
    expect(within(report).getByRole("link", { name: "Kaynağa git" })).toHaveAttribute("href", "https://x.example/10");
    expect(within(dialog).getByText("Sizin yerleştirdiğiniz")).toBeInTheDocument();
    expect(within(dialog).getByText("قمة").closest("span")).toHaveAttribute("dir", "rtl");
  });

  it("detaches a wrongly grouped report and reloads the list", async () => {
    const dialog = await open();
    mocked.detachArticle.mockResolvedValue({ story_id: 99, previous_story_id: 1 });
    const reports = await within(dialog).findAllByRole("button", { name: "Bu hikâyeden ayır" });
    const callsBefore = mocked.stories.mock.calls.length;
    await userEvent.click(reports[2]!);
    expect(mocked.detachArticle).toHaveBeenCalledWith(12);
    expect(await screen.findByText("Haber hikâyeden ayrıldı.")).toBeInTheDocument();
    await waitFor(() => expect(mocked.stories.mock.calls.length).toBeGreaterThan(callsBefore));
    expect(mocked.story).toHaveBeenCalledTimes(2);
  });

  it("merges another story into this one", async () => {
    const dialog = await open();
    await within(dialog).findByText("Bu hikâyedeki haberler");
    mocked.mergeStories.mockResolvedValue({ ...full, article_count: 5 });
    await userEvent.click(within(dialog).getByRole("button", { name: "Başka hikâyeyle birleştir" }));
    const other = await within(dialog).findByRole("button", { name: /Başka olay/ });
    // The story itself is not offered.
    expect(within(dialog).queryByRole("button", { name: /Hikâye 1/ })).not.toBeInTheDocument();
    await userEvent.click(other);
    expect(mocked.mergeStories).toHaveBeenCalledWith(2, 1);
    expect(await screen.findByText("Hikâyeler birleştirildi.")).toBeInTheDocument();
  });

  it("queues a new summary and shows an error when the server is unreachable", async () => {
    const dialog = await open();
    await within(dialog).findByText("Bu hikâyedeki haberler");
    mocked.summarizeStory.mockRejectedValueOnce(new ApiError("server_unreachable", 0));
    await userEvent.click(within(dialog).getByRole("button", { name: "Özeti yeniden yaz" }));
    expect(mocked.summarizeStory).toHaveBeenCalledWith(1);
    await waitFor(() => expect(within(dialog).getByRole("button", { name: "Özeti yeniden yaz" })).toBeEnabled());
    mocked.summarizeStory.mockResolvedValueOnce({ status: "pending" });
    await userEvent.click(within(dialog).getByRole("button", { name: "Özeti yeniden yaz" }));
    expect(await within(dialog).findByRole("button", { name: "Hikâye özeti hazırlanıyor" })).toBeDisabled();
  });

  it("opens the selected story with the keyboard", async () => {
    mocked.stories.mockResolvedValue({ items: [story(1), story(2, { ai_texts: { tr: { title: "Başka olay", summary: "Türkçe özet." } } })], total: 2 });
    mocked.story.mockResolvedValue(story(2, { ai_texts: { tr: { title: "Başka olay", summary: "Türkçe özet." } } }));
    wrap(<FeedPage />);
    await screen.findByText("Hikâye 1");
    await userEvent.keyboard("jj{Enter}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(mocked.story).toHaveBeenCalledWith(2);
  });
});

describe("Interest keywords", () => {
  it("splits, trims and de-duplicates (Turkish case rules)", () => {
    expect(parseKeywords(" enerji, Kıbrıs;; İSRAİL\nisrail , ENERJİ ")).toEqual(["enerji", "Kıbrıs", "İSRAİL"]);
    expect(parseKeywords("")).toEqual([]);
  });
});

describe("First stories", () => {
  it("appear without a manual refresh once clustering progresses", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      mocked.stories.mockResolvedValue({ items: [], total: 0 });
      mocked.status.mockResolvedValueOnce({ ...STATUS, stories: { ...STORY_WORKER, clustered: 0 } });
      wrap(<FeedPage />);
      expect(await screen.findByText("Henüz hikâye yok")).toBeInTheDocument();
      mocked.stories.mockResolvedValue({ items: [story(1)], total: 1 });
      await vi.advanceTimersByTimeAsync(20_000); // next status poll reports clustered articles
      expect(await screen.findByText("Hikâye 1")).toBeInTheDocument();
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("The user's AI languages", () => {
  it("steps a card through Turkish, Portuguese and Arabic, right to left for Arabic", async () => {
    const s = story(1, { ai_texts: {
      tr: { title: "Hikâye 1", summary: "Türkçe özet.", why: "" },
      pt: { title: "História 1", summary: "Resumo em português.", why: "" },
      ar: { title: "القصة 1", summary: "ملخص عربي.", why: "" },
    } });
    mocked.stories.mockResolvedValue({ items: [s], total: 1 });
    wrap(<FeedPage />, { ...SETTINGS, "ai.languages": ["tr", "pt", "ar"] });
    const card = (await screen.findByText("Hikâye 1")).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Göster: Portekizce" }));
    expect(within(card).getByText("Resumo em português.")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Göster: Arapça" }));
    expect(within(card).getByText("القصة 1").closest("h2")).toHaveAttribute("dir", "rtl");
    await userEvent.click(within(card).getByRole("button", { name: "Göster: Türkçe" }));
    expect(within(card).getByText("Hikâye 1")).toBeInTheDocument();
  });
});

describe("Turkish and English", () => {
  const bilingual = () =>
    story(1, { ai_texts: {
      tr: { title: "Hikâye 1", summary: "Türkçe özet.", why: "Türkiye'yi doğrudan ilgilendiriyor." },
      en: { title: "Story one", summary: "English summary.", why: "Directly concerns Türkiye." },
    } });

  it("shows the interface language and switches a card to the other one", async () => {
    mocked.stories.mockResolvedValue({ items: [bilingual()], total: 1 });
    wrap(<FeedPage />);
    const card = (await screen.findByText("Hikâye 1")).closest("li")!;
    await userEvent.click(within(card).getByRole("button", { name: "Göster: İngilizce" }));
    expect(within(card).getByText("Story one")).toBeInTheDocument();
    expect(within(card).getByText("English summary.")).toBeInTheDocument();
    await userEvent.click(within(card).getByRole("button", { name: "Göster: Türkçe" }));
    expect(within(card).getByText("Hikâye 1")).toBeInTheDocument();
  });

  it("an English interface shows English AI text, falling back to Turkish when English is missing", async () => {
    mocked.stories.mockResolvedValue({ items: [bilingual(), story(2)], total: 2 });
    wrap(<FeedPage />, { ...SETTINGS, "ui.language": "en" });
    expect(await screen.findByText("Story one")).toBeInTheDocument();
    expect(screen.getByText("Hikâye 2")).toBeInTheDocument(); // no English text: the Turkish one is shown
    expect(screen.getAllByRole("button", { name: "Show: Turkish" })).toHaveLength(1);
  });
});
