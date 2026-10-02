import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, Meta, Settings, StatsOverview, Status, Story, StoryMember } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      status: vi.fn(),
      updateSettings: vi.fn(),
      stats: vi.fn(),
      topicStats: vi.fn(),
      searchTranslations: vi.fn(),
    },
  };
});

import { api } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { StatsPage } from "../pages/StatsPage";
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

function overview(extra: Partial<StatsOverview> = {}): StatsOverview {
  const hours = ["2026-09-29T08:00:00Z", "2026-09-29T09:00:00Z", "2026-09-29T10:00:00Z"];
  return {
    period: { hours: 24, since: hours[0]!, until: "2026-09-29T10:30:00Z", previous_since: "2026-09-28T06:30:00Z",
              step_hours: 1, comparable: false, collecting_since: "2026-09-27T08:23:28Z" },
    totals: { articles: 1200, stories: 400, sources: 90, previous: { articles: 0, stories: 0, sources: 0 } },
    timeline: hours.map((start, i) => ({ start, articles: [300, 500, 400][i]! })),
    categories: { known: 300, known_previous: 0, total: 1200,
                  items: [{ key: "politics", articles: 200, previous: 0 }, { key: "economy", articles: 100, previous: 0 }] },
    regions: { known: 1200, known_previous: 0, total: 1200,
               items: [{ key: "turkey", articles: 700, previous: 0 }, { key: "europe", articles: 500, previous: 0 }] },
    countries: { read: 50, items: [{ key: "TR", articles: 20 }, { key: "US", articles: 10 }] },
    sources: [
      { id: 1, name: "Reuters", region: "global", articles: 120, previous: 0, stories: 60, last_at: "2026-09-29T10:20:00Z" },
      { id: 2, name: "Sessiz Gazete", region: "turkey", articles: 0, previous: 0, stories: 0, last_at: null },
    ],
    rising: { window_hours: 6, items: [{ story: story(7, "Hızla büyüyen olay"), recent: 25, previous: 2, sources: 12 }] },
    ...extra,
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
  mocked.stats.mockResolvedValue(overview());
  mocked.searchTranslations.mockResolvedValue({ state: "ok", queries: { en: ["North Korea"] } });
  mocked.topicStats.mockResolvedValue({
    articles: 135, sources: 44, previous: 4,
    buckets: [
      { start: "2026-09-29T08:00:00Z", articles: 5, sources: 4, share: 0.017 },
      { start: "2026-09-29T09:00:00Z", articles: 74, sources: 30, share: 0.148 },
      { start: "2026-09-29T10:00:00Z", articles: 56, sources: 20, share: 0.14 },
    ],
  });
});

describe("Statistics page", () => {
  it("shows the headline numbers and says when there is nothing to compare with", async () => {
    wrap(<StatsPage />);
    const tile = (await screen.findByText("Bağımsız kaynak")).closest(".stat-tile")!;
    expect(within(tile as HTMLElement).getByText("90")).toBeInTheDocument();
    expect(screen.getByText(/karşılaştırma için yeterli geçmiş yok/)).toBeInTheDocument();
    expect(screen.queryByText(/▲|▼/)).not.toBeInTheDocument();  // no changes against an empty period
    expect(mocked.stats).toHaveBeenCalledWith(24);
    await userEvent.click(screen.getByRole("button", { name: "7 gün" }));
    await waitFor(() => expect(mocked.stats).toHaveBeenLastCalledWith(168));
  });

  it("shows changes when the previous period can be compared", async () => {
    mocked.stats.mockResolvedValue(overview({
      period: { ...overview().period, comparable: true },
      totals: { articles: 1200, stories: 400, sources: 90, previous: { articles: 1000, stories: 400, sources: 100 } },
    }));
    wrap(<StatsPage />);
    await screen.findByText("Bağımsız kaynak");
    const tile = async (label: string) =>
      screen.getAllByText(label).find((e) => e.classList.contains("stat-label"))!.closest(".stat-tile") as HTMLElement;
    expect(within(await tile("Haber")).getByText("▲ %20")).toBeInTheDocument();
    expect(within(await tile("Hikâye")).getByText("değişmedi")).toBeInTheDocument();
    expect(within(await tile("Bağımsız kaynak")).getByText("▼ %10")).toBeInTheDocument();
    // Per source too; a source with no reports in either period is unchanged.
    expect(screen.getByRole("columnheader", { name: "Değişim" })).toBeInTheDocument();
  });

  it("shares by category of the known reports, and by region of the press", async () => {
    wrap(<StatsPage />);
    const categories = await screen.findByRole("list", { name: "Kategorilere göre gündem" });
    const politics = within(categories).getByText("Siyaset").closest("li")!;
    expect(within(politics as HTMLElement).getByText("%66,7")).toBeInTheDocument();  // 200 of the 300 known
    expect(screen.getByText(/Kategorisi bilinen 300 haber üzerinden/)).toBeInTheDocument();
    const regions = screen.getByRole("list", { name: "Haberi veren basının bölgesi" });
    expect(within(regions).getByText("%58,3")).toBeInTheDocument();  // Türkiye: 700 of 1,200
  });

  it("follows a topic with its translations, as a chart and as a table", async () => {
    wrap(<StatsPage />);
    await screen.findByText("Bağımsız kaynak");
    await userEvent.type(screen.getByRole("searchbox"), "kuzey kore");
    await waitFor(() => expect(mocked.topicStats).toHaveBeenLastCalledWith(24, "kuzey kore", ["North Korea"]));
    expect(await screen.findByText(/Bu dönemde 135 haber, 44 kaynak/)).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "“kuzey kore” konusundaki haberler" })).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Tablo olarak göster" })[0]!);
    const table = screen.getByRole("table", { name: "“kuzey kore” konusundaki haberler" });
    expect(within(table).getByText("74 haber")).toBeInTheDocument();
    expect(within(table).getByText("30 kaynak · tüm haberler içindeki payı: %14,8")).toBeInTheDocument();
  });

  it("lists rising stories and opens one", async () => {
    wrap(<StatsPage />);
    const title = await screen.findByRole("button", { name: "Hızla büyüyen olay" });
    expect(screen.getByText("25 haber (önce 2) · 12 kaynak")).toBeInTheDocument();
    await userEvent.click(title);
    expect(window.location.hash).toBe("#/stats?story=7");
  });

  it("lists sources, silent ones too, and countries of the reports the AI read", async () => {
    wrap(<StatsPage />);
    const row = (await screen.findByText("Sessiz Gazete")).closest("tr")!;
    expect(within(row as HTMLElement).getByText("bu dönemde haber yok")).toBeInTheDocument();
    const countries = screen.getByRole("list", { name: "Haberlerde en çok geçen ülkeler" });
    expect(within(countries).getByText("Türkiye")).toBeInTheDocument();
    expect(within(countries).getByText("%40")).toBeInTheDocument();  // 20 of the 50 read
  });
});
