import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, MeetingItem, Meta, NotebookDay, Settings, Status, Story } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      mailDraft: vi.fn(),
      status: vi.fn(),
      updateSettings: vi.fn(),
      sources: vi.fn(),
      stories: vi.fn(),
      story: vi.fn(),
      storyNote: vi.fn(),
      saveStoryNote: vi.fn(),
      meeting: vi.fn(),
      addToMeeting: vi.fn(),
      removeMeetingItem: vi.fn(),
      updateMeetingItem: vi.fn(),
      reorderMeeting: vi.fn(),
      notebookMonth: vi.fn(),
      notebookDay: vi.fn(),
      saveDayNote: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { MeetingProvider } from "../components/meeting";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { localDay } from "../lib/hooks";
import { FeedPage } from "../pages/FeedPage";
import { MeetingPage } from "../pages/MeetingPage";
import { NotebookPage } from "../pages/NotebookPage";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, NO_FULLTEXT, STORY_SETTINGS, STORY_WORKER } from "./fixtures";

const mocked = vi.mocked(api, true);
const TODAY = localDay();

const SETTINGS: Settings = {
  "ui.language": "tr", "ui.theme": "light", "feed.window_hours": 24, "feed.view": "stories", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null,
  "ai.enabled": true, "ai.url": "http://localhost:11434", "ai.model": "m", "ai.max_age_hours": 24, "ai.yield_gpu": true,
  ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey"], groups: ["turkey"], kinds: ["exclusive", "opinion"], languages: ["tr"], categories: ["politics"], ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"],
  data_dir: "C:\\data", version: "0.4.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "m", url: "u", current_article_id: null, last_error: null,
  last_done_at: null, avg_seconds: 1, pending: 0, done: 1, failed: 0, done_24h: 1,
};
const STATUS: Status = {
  version: "0.4.0", ai: AI, stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY, articles: { total: 1, recent: 1 },
  collector: { running: true, busy: false, offline: false, last_cycle_at: "2026-09-27T08:00:00Z", last_cycle_new: 0, last_cycle_feeds: 1, last_cycle_errors: 0 },
};

function item(id: number, extra: Partial<MeetingItem> = {}): MeetingItem {
  return {
    id, day: TODAY, story_id: id * 10, position: id - 1, comment: "", title: `Öneri ${id}`, texts: { tr: { title: `Öneri ${id}`, summary: `Özet ${id}`, why: `Gerekçe ${id}` } },
    category: "politics", sources: [{ name: "AA", url: "https://aa.example/1" }], created_at: TODAY, updated_at: TODAY, ...extra,
  };
}

function story(id: number): Story {
  const m = {
    id: id * 100, url: "https://x.example/1", title: "Orig", summary: "", sort_at: "2026-09-27T08:00:00Z", language: "tr",
    source_id: 1, source_name: "AA", paywalled: false, exclusive: false, region: "turkey" as const, similarity: 1, assigned_by: "auto" as const,
    ai_texts: {}, ...NO_FULLTEXT,
  };
  return {
    id, breaking: false, exclusive: false, first_seen_at: m.sort_at, last_seen_at: m.sort_at, article_count: 1, source_count: 1, score: 40, score_parts: { tags: [] },
    turkey_relevance: "none", category: "politics", representative_id: m.id, representative: m, ai_status: "done",
    ai_texts: { tr: { title: `Hikâye ${id}`, summary: "Özet.", why: "" } }, ai_issues: [], ai_article_count: 1, ai_model: "m",
    sources: ["AA"], members: [m], timeline: [],
  };
}

function wrap(ui: ReactNode) {
  return render(
    <AppStateProvider initialSettings={SETTINGS} initialMeta={META}>
      <I18nProvider lang="tr">
        <ToastProvider>
          <MeetingProvider>{ui}</MeetingProvider>
        </ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  mocked.status.mockResolvedValue(STATUS);
  mocked.sources.mockResolvedValue([]);
  mocked.storyNote.mockResolvedValue({ note: null });
  mocked.meeting.mockResolvedValue({ day: TODAY, today: TODAY, items: [item(1), item(2), item(3)] });
});

describe("Meeting list", () => {
  it("shows today's proposals and reorders with the arrow buttons", async () => {
    mocked.reorderMeeting.mockImplementation(async (day, ids) => ({
      day, today: TODAY, items: ids.map((id, i) => ({ ...item(id), position: i })),
    }));
    wrap(<MeetingPage />);
    expect(await screen.findByText("Öneri 1")).toBeInTheDocument();
    expect(screen.getByText(/3 öneri/)).toBeInTheDocument();
    const third = screen.getByText("Öneri 3").closest("li")!;
    await userEvent.click(within(third).getByRole("button", { name: "Yukarı taşı" }));
    expect(mocked.reorderMeeting).toHaveBeenCalledWith(TODAY, [1, 3, 2]);
    await waitFor(() =>
      expect(screen.getAllByRole("listitem").map((li) => li.querySelector(".meeting-title")?.textContent)).toEqual(["Öneri 1", "Öneri 3", "Öneri 2"]),
    );
    expect(within(screen.getByText("Öneri 1").closest("li")!).getByRole("button", { name: "Yukarı taşı" })).toBeDisabled();
  });

  it("reorders by drag and drop", async () => {
    mocked.reorderMeeting.mockImplementation(async (day, ids) => ({ day, today: TODAY, items: ids.map((id) => item(id)) }));
    wrap(<MeetingPage />);
    await screen.findByText("Öneri 1");
    const rows = screen.getAllByRole("listitem");
    const grip = rows[2]!.querySelector(".meeting-grip")!;
    fireEvent.dragStart(grip, { dataTransfer: { setData: () => undefined, effectAllowed: "" } });
    fireEvent.dragOver(rows[0]!);
    fireEvent.drop(rows[0]!);
    expect(mocked.reorderMeeting).toHaveBeenCalledWith(TODAY, [3, 1, 2]);
  });

  it("restores the order and says so when reordering fails", async () => {
    mocked.reorderMeeting.mockRejectedValue(new ApiError("server_unreachable", 0));
    wrap(<MeetingPage />);
    await screen.findByText("Öneri 1");
    await userEvent.click(within(screen.getByText("Öneri 2").closest("li")!).getByRole("button", { name: "Aşağı taşı" }));
    expect(await screen.findByText(/sunucu|ulaşılamıyor/i)).toBeInTheDocument();
    expect(screen.getAllByRole("listitem").map((li) => li.querySelector(".meeting-title")?.textContent)).toEqual(["Öneri 1", "Öneri 2", "Öneri 3"]);
  });

  it("saves a short reason and removes a proposal", async () => {
    mocked.updateMeetingItem.mockImplementation(async (id, comment) => ({ ...item(id), comment }));
    mocked.removeMeetingItem.mockResolvedValue(undefined);
    wrap(<MeetingPage />);
    await screen.findByText("Öneri 1");
    const first = screen.getByText("Öneri 1").closest("li")!;
    await userEvent.type(within(first).getByRole("textbox", { name: "Kısa gerekçe" }), "İlk sırada{Enter}");
    await waitFor(() => expect(mocked.updateMeetingItem).toHaveBeenLastCalledWith(1, "İlk sırada"));
    await userEvent.click(within(first).getByRole("button", { name: "Listeden çıkar" }));
    expect(mocked.removeMeetingItem).toHaveBeenCalledWith(1);
    await waitFor(() => expect(screen.queryByText("Öneri 1")).not.toBeInTheDocument());
  });

  it("offers the meeting output with the user's reason", async () => {
    mocked.meeting.mockResolvedValue({ day: TODAY, today: TODAY, items: [item(1, { comment: "Benim gerekçem" })] });
    wrap(<MeetingPage />);
    await screen.findByText("Öneri 1");
    await userEvent.click(screen.getByRole("button", { name: "Çıktı al" }));
    const frame = (await screen.findByTitle("Önizleme")) as HTMLIFrameElement;
    expect(frame.getAttribute("srcdoc")).toContain("1. Öneri 1");
    expect(frame.getAttribute("srcdoc")).toContain("Benim gerekçem");
    expect(screen.getByRole("button", { name: /Biçimli kopyala/ })).toBeEnabled();
  });

  it("opens an e-mail draft of the meeting list", async () => {
    mocked.meeting.mockResolvedValue({ day: TODAY, today: TODAY, items: [item(1, { comment: "Benim gerekçem" })] });
    mocked.mailDraft.mockResolvedValueOnce({ method: "outlook", cut: false });
    wrap(<MeetingPage />);
    await screen.findByText("Öneri 1");
    await userEvent.click(screen.getByRole("button", { name: "Çıktı al" }));
    await userEvent.click(await screen.findByRole("button", { name: "E-postayla gönder" }));
    await waitFor(() => expect(mocked.mailDraft).toHaveBeenCalledTimes(1));
    const draft = mocked.mailDraft.mock.calls[0]![0];
    expect(draft.subject).toMatch(/^Toplantı öneri listesi · /);
    expect(draft.html).toContain("Benim gerekçem");
    expect(draft.text).toContain("1. Öneri 1");
    expect(await screen.findByText("Outlook'ta taslak açıldı. Alıcıyı yazıp gönderin.")).toBeInTheDocument();

    // No mail program at all: the user is told to copy instead.
    mocked.mailDraft.mockRejectedValueOnce(new ApiError("no_mail_program", 409));
    await userEvent.click(screen.getByRole("button", { name: "E-postayla gönder" }));
    expect(await screen.findByText(/e-posta uygulaması bulunamadı/)).toBeInTheDocument();
  });

  it("explains an empty list", async () => {
    mocked.meeting.mockResolvedValue({ day: TODAY, today: TODAY, items: [] });
    wrap(<MeetingPage />);
    expect(await screen.findByText("Bugünün listesi boş")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Çıktı al" })).toBeDisabled();
  });
});

describe("Feed shortcut", () => {
  it("T adds the selected story to today's meeting list", async () => {
    mocked.meeting.mockResolvedValue({ day: TODAY, today: TODAY, items: [] });
    mocked.stories.mockResolvedValue({ items: [story(7), story(8)], total: 2 });
    mocked.addToMeeting.mockImplementation(async (sid) => item(1, { story_id: sid }));
    wrap(<FeedPage />);
    await screen.findByText("Hikâye 7");
    await userEvent.keyboard("jjt");
    expect(mocked.addToMeeting).toHaveBeenCalledWith(8);
    const card = screen.getByText("Hikâye 8").closest("li")!;
    expect(await within(card).findByRole("button", { name: /Toplantıda/ })).toHaveAttribute("aria-pressed", "true");
    // Pressing T again takes it off the list.
    mocked.removeMeetingItem.mockResolvedValue(undefined);
    await userEvent.keyboard("t");
    expect(mocked.removeMeetingItem).toHaveBeenCalledWith(1);
  });
});

describe("Notebook", () => {
  const DAY_DATA: NotebookDay = {
    day: TODAY, today: TODAY, day_note: { body: "Sabah notu", updated_at: TODAY },
    meeting: [item(1, { comment: "Açılış" })],
    notes: [
      { id: 5, story_id: 7, day: TODAY, title: "Hikâye 7", body: "Muhabir arandı", created_at: TODAY, updated_at: TODAY, story_exists: true },
      { id: 6, story_id: null, day: TODAY, title: "Silinmiş hikâye", body: "Eski not", created_at: TODAY, updated_at: TODAY, story_exists: false },
    ],
  };

  it("shows the day, saves the day note and outputs the selected notes", async () => {
    mocked.notebookMonth.mockResolvedValue({ month: TODAY.slice(0, 7), today: TODAY, days: [{ day: TODAY, notes: 2, meeting: 1, day_note: true }] });
    mocked.notebookDay.mockResolvedValue(DAY_DATA);
    mocked.saveDayNote.mockResolvedValue({ day_note: { body: "x", updated_at: TODAY } });
    mocked.story.mockResolvedValue(story(7));
    wrap(<NotebookPage />);
    const dayNote = await screen.findByRole("textbox", { name: "Günün notu" });
    expect(dayNote).toHaveValue("Sabah notu");
    expect(screen.getByText("Öneri 1")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Hikâye notları" })).toBeInTheDocument();
    expect(screen.getByText("Hikâye artık yok; notunuz duruyor.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Kayıt var/ })).toHaveAttribute("aria-pressed", "true");

    await userEvent.type(dayNote, " ve ek");
    await waitFor(() => expect(mocked.saveDayNote).toHaveBeenLastCalledWith(TODAY, "Sabah notu ve ek"));

    const output = screen.getByRole("button", { name: /Seçtiklerimi çıktı al/ });
    expect(output).toBeDisabled();
    await userEvent.click(screen.getByRole("checkbox", { name: /Hikâye 7/ }));
    await userEvent.click(screen.getByRole("checkbox", { name: /Silinmiş hikâye/ }));
    await userEvent.click(screen.getByRole("button", { name: "Seçtiklerimi çıktı al (2)" }));
    const frame = (await screen.findByTitle("Önizleme")) as HTMLIFrameElement;
    const html = frame.getAttribute("srcdoc")!;
    expect(html).toContain("Muhabir arandı");
    expect(html).toContain("Özet."); // from the live story
    expect(html).toContain("Silinmiş hikâye");
    expect(mocked.story).toHaveBeenCalledWith(7);
    expect(mocked.story).toHaveBeenCalledTimes(1);
  });

  it("moves between months and days", async () => {
    mocked.notebookMonth.mockImplementation(async (month) => ({ month, today: TODAY, days: [] }));
    mocked.notebookDay.mockImplementation(async (day) => ({ day, today: TODAY, day_note: null, meeting: [], notes: [] }));
    wrap(<NotebookPage />);
    expect(await screen.findByText("Bu güne ait toplantı listesi ya da hikâye notu yok.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Önceki ay" }));
    const [y, m] = TODAY.split("-").map(Number);
    const prev = new Date(y!, m! - 2, 1);
    const prevMonth = `${prev.getFullYear()}-${String(prev.getMonth() + 1).padStart(2, "0")}`;
    await waitFor(() => expect(mocked.notebookMonth).toHaveBeenLastCalledWith(prevMonth));
    await userEvent.click(screen.getAllByRole("button", { name: /\b15\b|^15/ })[0] ?? screen.getByText("15"));
    await waitFor(() => expect(mocked.notebookDay).toHaveBeenLastCalledWith(`${prevMonth}-15`));
    await userEvent.click(screen.getByRole("button", { name: "Bugün" }));
    await waitFor(() => expect(mocked.notebookDay).toHaveBeenLastCalledWith(TODAY));
  });

  it("offers retry when the day cannot be loaded", async () => {
    mocked.notebookMonth.mockResolvedValue({ month: TODAY.slice(0, 7), today: TODAY, days: [] });
    mocked.notebookDay.mockRejectedValueOnce(new ApiError("server_unreachable", 0)).mockResolvedValue({
      day: TODAY, today: TODAY, day_note: null, meeting: [], notes: [],
    });
    wrap(<NotebookPage />);
    expect(await screen.findByText("Bir sorun oluştu")).toBeInTheDocument();
    await act(async () => {
      await userEvent.click(screen.getByRole("button", { name: "Yeniden dene" }));
    });
    expect(await screen.findByText("Bu güne ait toplantı listesi ya da hikâye notu yok.")).toBeInTheDocument();
  });
});
