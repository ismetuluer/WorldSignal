import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, HistoryDay, Meta, Settings, Status, Story, StoryMember } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      status: vi.fn(),
      updateSettings: vi.fn(),
      historyMonth: vi.fn(),
      historyDay: vi.fn(),
      articles: vi.fn(),
      stories: vi.fn(),
      story: vi.fn(),
      storyNote: vi.fn(),
      searchTranslations: vi.fn(),
    },
  };
});

import { api } from "../api/client";
import { StoryDetail } from "../components/StoryDetail";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { localDay } from "../lib/hooks";
import { HistoryPage } from "../pages/HistoryPage";
import { HistorySettings } from "../pages/HistorySettings";
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
  "ai.model": "gemma4-26b-a4b",
  "ai.max_age_hours": 24,
  "ai.yield_gpu": true,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey", "europe"], home_region: "turkey", groups: ["turkey", "western"], kinds: ["exclusive", "opinion"], languages: ["en", "tr"], categories: ["politics"],
  ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"], data_dir: "C:\\data", version: "0.6.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "gemma4-26b-a4b", url: "http://localhost:11434", current_article_id: null,
  last_error: null, last_done_at: null, avg_seconds: 2.5, pending: 0, done: 10, failed: 0, done_24h: 10,
};
const STATUS: Status = {
  version: "0.6.0", ai: AI, stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 0, last_cycle_feeds: 5, last_cycle_errors: 0 },
  articles: { total: 3, recent: 3 }, extension: null,
};
const TODAY = localDay();

function member(id: number, name: string): StoryMember {
  return {
    id, url: `https://x.example/${id}`, title: `Report ${id}`, summary: "", sort_at: "2026-09-26T08:00:00Z", language: "en",
    source_id: id, source_name: name, paywalled: false, exclusive: false, region: "europe", similarity: 1, assigned_by: "auto",
    ai_texts: {}, ...NO_FULLTEXT,
  };
}

function story(id: number, title: string, extra: Partial<Story> = {}): Story {
  const members = [member(id * 10, "Reuters"), member(id * 10 + 1, "BBC")];
  return {
    id, breaking: false, exclusive: false, first_seen_at: "2026-09-26T06:00:00Z", last_seen_at: "2026-09-26T08:00:00Z", article_count: 2, source_count: 2,
    score: 61, score_parts: { tags: [{ kind: "sources", count: 2 }] }, turkey_relevance: "none", category: "politics",
    representative_id: members[0]!.id, representative: members[0]!, ai_status: "done", ai_texts: { tr: { title: title, summary: "Özet.", why: "" } },
     ai_issues: [], ai_article_count: 2, ai_model: "m",
    sources: ["BBC", "Reuters"], members, timeline: [], ...extra,
  };
}

function dayPage(extra: Partial<HistoryDay> = {}): HistoryDay {
  return {
    day: TODAY, moment: "morning", as_of: "2026-09-26T06:00:00Z", window_start: "2026-09-25T06:00:00Z",
    items: [story(1, "Sabahın en önemli olayı"), story(2, "İkinci olay")], total: 2, unclustered: 0, future: false, ...extra,
  };
}

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
  vi.resetAllMocks();
  mocked.status.mockResolvedValue(STATUS);
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
  mocked.historyMonth.mockResolvedValue({ month: TODAY.slice(0, 7), today: TODAY, days: [{ day: TODAY, articles: 120, stories: 45 }] });
  mocked.historyDay.mockResolvedValue(dayPage());
  mocked.storyNote.mockResolvedValue({ note: null });
  mocked.searchTranslations.mockResolvedValue({ state: "disabled", queries: {} });
});

describe("History page", () => {
  it("shows the day's stories as they were that morning and marks days on the calendar", async () => {
    wrap(<HistoryPage />);
    expect(await screen.findByText("Sabahın en önemli olayı")).toBeInTheDocument();
    expect(mocked.historyDay).toHaveBeenCalledWith(TODAY, { moment: "morning", min_sources: 1, limit: 30, offset: 0 });
    expect(screen.getByText(/itibarıyla, önceki 24 saat · 2 hikâye/)).toBeInTheDocument();
    const cal = screen.getByRole("region", { name: "Geçmiş günler" });
    expect(within(cal).getByRole("button", { name: /45 hikâye · 120 haber/ })).toHaveAttribute("aria-pressed", "true");
  });

  it("switches to the whole day and to multi-source stories", async () => {
    wrap(<HistoryPage />);
    await screen.findByText("Sabahın en önemli olayı");
    await userEvent.click(screen.getByRole("button", { name: "Günün tamamı" }));
    expect(mocked.historyDay).toHaveBeenLastCalledWith(TODAY, { moment: "day", min_sources: 1, limit: 30, offset: 0 });
    await userEvent.click(screen.getByRole("button", { name: "Yalnızca çok kaynaklı" }));
    expect(mocked.historyDay).toHaveBeenLastCalledWith(TODAY, { moment: "day", min_sources: 2, limit: 30, offset: 0 });
  });

  it("opens another day from the calendar", async () => {
    wrap(<HistoryPage />);
    await screen.findByText("Sabahın en önemli olayı");
    const other = TODAY.endsWith("-01") ? `${TODAY.slice(0, 8)}02` : `${TODAY.slice(0, 8)}01`;
    const cal = screen.getByRole("region", { name: "Geçmiş günler" });
    const target = within(cal).getAllByRole("button", { pressed: false }).find((b) => b.textContent === String(Number(other.slice(8))));
    await userEvent.click(target!);
    await waitFor(() => expect(mocked.historyDay).toHaveBeenLastCalledWith(other, expect.objectContaining({ moment: "morning" })));
  });

  it("explains a day before stories existed and shows its single articles", async () => {
    mocked.historyDay.mockResolvedValue(dayPage({ items: [], total: 0, unclustered: 209 }));
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    wrap(<HistoryPage />);
    expect(await screen.findByText("Bu gün için hikâye yok")).toBeInTheDocument();
    expect(screen.getByText(/O günkü 209 haber/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Haberleri göster" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenCalledWith(expect.objectContaining({ day: TODAY, limit: 60 })));
  });

  it("says when the morning has not come yet", async () => {
    mocked.historyDay.mockResolvedValue(dayPage({ items: [], total: 0, future: true }));
    wrap(<HistoryPage />);
    expect(await screen.findByText("Bu anın zamanı gelmedi")).toBeInTheDocument();
    expect(screen.getByText(/saat 09:00'daki sıralamayı/)).toBeInTheDocument();
  });

  it("offers a retry when the day cannot be loaded", async () => {
    mocked.historyDay.mockRejectedValueOnce(new Error("down")).mockResolvedValue(dayPage());
    wrap(<HistoryPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Yeniden dene" }));
    expect(await screen.findByText("Sabahın en önemli olayı")).toBeInTheDocument();
  });

  it("searches every day at once", async () => {
    mocked.stories.mockResolvedValue({ items: [story(7, "Eski seçim haberi")], total: 1 });
    mocked.articles.mockResolvedValue({ items: [], next: null, total: 0 });
    mocked.searchTranslations.mockResolvedValue({ state: "ok", queries: { en: ["election"], tr: ["seçim"] } });
    wrap(<HistoryPage />);
    await screen.findByText("Sabahın en önemli olayı");
    await userEvent.type(screen.getByRole("searchbox"), "seçim");
    expect(await screen.findByText("Eski seçim haberi")).toBeInTheDocument();
    // The search also runs in the sources' languages (the typed words themselves are not repeated).
    expect(await screen.findByText("Diğer dillerde de arandı: election")).toBeInTheDocument();
    const call = mocked.stories.mock.calls.at(-1)![0];
    expect(call).toMatchObject({ q: "seçim", qx: ["election"] });
    expect(call.hours).toBeUndefined(); // all days
    expect(screen.getByText("“seçim” için tüm günler")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Haberler" }));
    await waitFor(() => expect(mocked.articles).toHaveBeenCalledWith(expect.objectContaining({ q: "seçim" })));
    expect(mocked.articles.mock.calls.at(-1)![0].hours).toBeUndefined();
  });
});

describe("Story milestones", () => {
  it("lists the turning points in the story detail", async () => {
    mocked.story.mockResolvedValue(story(1, "Olay", {
      milestones: [
        { kind: "first", at: "2026-09-25T06:00:00Z", source: "Reuters" },
        { kind: "sources", at: "2026-09-25T09:00:00Z", source: "BBC", count: 5 },
        { kind: "turkey", at: "2026-09-25T10:00:00Z", source: "AA" },
        { kind: "latest", at: "2026-09-26T08:00:00Z", source: "BBC" },
      ],
    }));
    wrap(<StoryDetail storyId={1} onClose={() => undefined} onChanged={() => undefined} />);
    const list = await screen.findByRole("list", { name: "Dönüm noktaları" });
    expect(within(list).getByText("İlk haber: Reuters")).toBeInTheDocument();
    expect(within(list).getByText("5 bağımsız kaynağa ulaştı (BBC)")).toBeInTheDocument();
    expect(within(list).getByText("Türkiye bağlantısı ortaya çıktı (AA)")).toBeInTheDocument();
    expect(within(list).getByText("Son haber: BBC")).toBeInTheDocument();
  });

  it("shows no milestone list for a story with a single report", async () => {
    mocked.story.mockResolvedValue(story(1, "Olay", { milestones: [{ kind: "first", at: "2026-09-25T06:00:00Z", source: "Reuters" }] }));
    wrap(<StoryDetail storyId={1} onClose={() => undefined} onChanged={() => undefined} />);
    await screen.findByText("Bu hikâyedeki haberler");
    expect(screen.queryByRole("list", { name: "Dönüm noktaları" })).not.toBeInTheDocument();
  });
});

describe("History settings", () => {
  it("saves the morning hour and the full-text retention and shows the last clean-up", async () => {
    wrap(<HistorySettings />);
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sabah görünümünün saati" }), "8");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "history.morning_hour": 8 });
    await userEvent.click(screen.getByRole("button", { name: "Silme" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "retention.fulltext_days": 0 });
    expect(await screen.findByText("Veritabanı: yaklaşık 45 MB")).toBeInTheDocument();
    expect(screen.getByText(/2 tam metin, 150 eşleştirme kaydı silindi/)).toBeInTheDocument();
  });
});
