import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { MeetingItem, Story, StoryMember } from "../api/types";
import { createI18n } from "../i18n";
import { AUTOSAVE_DELAY_MS, RETRY_DELAY_MS, useAutosave } from "../lib/autosave";
import { bulletinOutput, meetingOutput, notesOutput, printDocument, storyOutput } from "../lib/outputs";
import { NO_FULLTEXT } from "./fixtures";

const tr = createI18n("tr");
const DAY = "2026-09-27";

function item(id: number, extra: Partial<MeetingItem> = {}): MeetingItem {
  return {
    id, day: DAY, story_id: id, position: id - 1, comment: "", title: `Başlık ${id}`, texts: { tr: { title: `Başlık ${id}`, summary: `Özet ${id}.`, why: `YZ gerekçe ${id}` } },
    category: "politics", sources: [{ name: "Reuters", url: "https://r.example/1" }, { name: "BBC", url: "https://b.example/1" }],
    created_at: DAY, updated_at: DAY, ...extra,
  };
}

function member(id: number, source: string, extra: Partial<StoryMember> = {}): StoryMember {
  return {
    id, url: `https://x.example/${id}`, title: `Original ${id}`, summary: "Publisher's own text", sort_at: `2026-09-27T0${id}:00:00Z`,
    language: "en", source_id: id, source_name: source, paywalled: true, exclusive: false, region: "europe", similarity: 1, assigned_by: "auto",
    ai_texts: {}, ...NO_FULLTEXT, ...extra,
  };
}

function story(id: number, extra: Partial<Story> = {}): Story {
  const members = [member(1, "Reuters"), member(2, "FT")];
  return {
    id, breaking: false, exclusive: false, first_seen_at: DAY, last_seen_at: DAY, article_count: 2, source_count: 2, score: 50, score_parts: {},
    turkey_relevance: "none", category: "economy", representative_id: 1, representative: members[0]!, ai_status: "done",
    ai_texts: { tr: { title: `Hikâye ${id}`, summary: "Türkçe özet.", why: "Neden önemli." } }, ai_issues: [], ai_article_count: 2,
    ai_model: "m", sources: ["FT", "Reuters"], members, timeline: [], ...extra,
  };
}

describe("output templates", () => {
  it("meeting list: numbered, the user's reason wins over the AI's, links kept", () => {
    const points = "Başbakan Burnham\n%20 kesinti\nMacron: \"Kapı açık\"";
    const many = ["Reuters", "BBC", "AP", "AFP"].map((name) => ({ name, url: `https://${name.toLowerCase()}.example/1` }));
    const doc = meetingOutput(tr, DAY, [
      item(1, { comment: "Açılışta", texts: { tr: { title: "Başlık 1", summary: "Özet 1.", why: "YZ gerekçe 1", points } }, sources: many }),
      item(2),
    ]);
    expect(doc.title).toBe("Toplantı öneri listesi");
    // What happened, then the key points as bullets, then the user's own note.
    expect(doc.text).toContain("*1. Başlık 1*\nÖzet 1.\n• Başbakan Burnham\n• %20 kesinti\n• Macron: \"Kapı açık\"\nNotum: Açılışta");
    expect(doc.html).toContain("<li style=\"margin:1pt 0\">%20 kesinti</li>");
    expect(doc.text).toContain("*2. Başlık 2*\nÖzet 2.");
    expect(doc.text).not.toContain("YZ gerekçe"); // "why it is in the meeting" says nothing the presenter can use
    expect(doc.text).toContain("27 Eylül 2026 Pazar");
    expect(doc.html).toContain('<a href="https://reuters.example/1"');
    expect(doc.html).toContain(">AP</a> +1"); // only the closest three sources
    expect(doc.html).not.toContain("afp.example");
  });

  it("leaves out a summary that is not written yet", () => {
    const doc = meetingOutput(tr, DAY, [item(1, { texts: {} })]);
    expect(doc.text).not.toContain("Özet henüz hazır değil");
  });

  it("escapes markup and drops non-http links", () => {
    const doc = meetingOutput(tr, DAY, [item(1, { title: '<img src=x onerror="alert(1)">', texts: {}, sources: [{ name: "Evil", url: "javascript:alert(1)" }] })]);
    expect(doc.html).not.toContain("<img");
    expect(doc.html).toContain("&lt;img");
    expect(doc.html).not.toContain("javascript:");
    expect(doc.text).toContain("Evil");
    expect(doc.text).not.toContain("javascript:");
  });

  it("story details never carry the publisher's own text", () => {
    const withAi = storyOutput(tr, story(1), DAY);
    expect(withAi.text).toContain("Türkçe özet.");
    const noAi = storyOutput(tr, story(2, { ai_status: null, ai_texts: {} }), DAY);
    expect(noAi.text).toContain("*Original 1*");
    expect(noAi.text).toContain("Özet henüz hazır değil.");
    expect(noAi.text + noAi.html).not.toContain("Publisher's own text");
    expect(noAi.text).toContain("FT (https://x.example/2)");
  });

  it("bulletin groups by category in score order, uncategorised last", () => {
    const doc = bulletinOutput(tr, DAY, 24, [
      story(1, { category: null, ai_texts: { tr: { title: "Kategorisiz", summary: "Türkçe özet." } } }),
      story(2, { category: "conflict_defense", ai_texts: { tr: { title: "Savunma haberi", summary: "Türkçe özet." } } }),
      story(3, { category: "economy", ai_texts: { tr: { title: "Ekonomi haberi", summary: "Türkçe özet." } } }),
      story(4, { category: "conflict_defense", ai_texts: { tr: { title: "İkinci savunma", summary: "Türkçe özet." } } }),
    ]);
    const order = ["— ÇATIŞMA VE SAVUNMA —", "Savunma haberi", "İkinci savunma", "— EKONOMİ —", "Ekonomi haberi", "— DİĞER —", "Kategorisiz"];
    let last = -1;
    for (const needle of order) {
      const at = doc.text.indexOf(needle, last + 1);
      expect(at, needle).toBeGreaterThan(last);
      last = at;
    }
    expect(doc.text).toContain("Son 24 saat");
  });

  it("notebook selection includes the note; a vanished story still prints its saved title", () => {
    const doc = notesOutput(tr, DAY, [{ title: "Eski hikâye", body: "Satır 1\nSatır 2", entry: null }]);
    expect(doc.text).toContain("*Eski hikâye*\nNotum: Satır 1\nSatır 2");
    expect(doc.html).toContain("Satır 1<br>Satır 2");
  });

  it("print page is a full A4 document", () => {
    const page = printDocument(meetingOutput(tr, DAY, [item(1)]), "World Signal · 27.09.2026", "tr");
    expect(page).toMatch(/^<!doctype html>/);
    expect(page).toContain("@page { size: A4");
    expect(page).toContain("World Signal · 27.09.2026");
  });
});

function Field({ save, draftKey = "k" }: { save: (v: string) => Promise<unknown>; draftKey?: string }) {
  const { value, setValue, status } = useAutosave("başlangıç", save, draftKey);
  return (
    <>
      <input aria-label="f" value={value} onChange={(e) => setValue(e.target.value)} />
      <span data-testid="status">{status}</span>
    </>
  );
}

describe("autosave", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    localStorage.clear();
  });
  afterEach(() => vi.useRealTimers());

  it("saves once after typing stops and clears the draft", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    render(<Field save={save} />);
    const input = screen.getByLabelText("f");
    act(() => {
      input.focus();
    });
    for (const v of ["a", "ab", "abc"]) {
      await act(async () => {
        const { fireEvent } = await import("@testing-library/react");
        fireEvent.change(input, { target: { value: v } });
      });
    }
    expect(localStorage.getItem("worldsignal.draft.k")).toBe("abc");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS + 10);
    });
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith("abc");
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
    expect(localStorage.getItem("worldsignal.draft.k")).toBeNull();
  });

  it("keeps the text and retries after a failure", async () => {
    const save = vi.fn().mockRejectedValueOnce(new Error("down")).mockResolvedValue(undefined);
    render(<Field save={save} />);
    const { fireEvent } = await import("@testing-library/react");
    await act(async () => {
      fireEvent.change(screen.getByLabelText("f"), { target: { value: "önemli not" } });
      await vi.advanceTimersByTimeAsync(AUTOSAVE_DELAY_MS + 10);
    });
    expect(screen.getByTestId("status")).toHaveTextContent("error");
    expect(screen.getByLabelText("f")).toHaveValue("önemli not");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RETRY_DELAY_MS + 10);
    });
    expect(save).toHaveBeenCalledTimes(2);
    expect(screen.getByTestId("status")).toHaveTextContent("saved");
  });

  it("restores an unsaved draft from a previous session and saves it", async () => {
    localStorage.setItem("worldsignal.draft.k", "kapanmadan önce yazılan");
    const save = vi.fn().mockResolvedValue(undefined);
    render(<Field save={save} />);
    expect(screen.getByLabelText("f")).toHaveValue("kapanmadan önce yazılan");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10);
    });
    expect(save).toHaveBeenCalledWith("kapanmadan önce yazılan");
  });

  it("saves pending text when the field goes away", async () => {
    const save = vi.fn().mockResolvedValue(undefined);
    const view = render(<Field save={save} />);
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(screen.getByLabelText("f"), { target: { value: "hemen kapattım" } });
    view.unmount();
    expect(save).toHaveBeenCalledWith("hemen kapattım");
  });
});

describe("English outputs", () => {
  const en = createI18n("en");
  it("uses the English AI texts and English labels", () => {
    const doc = meetingOutput(en, DAY, [item(1, { comment: "Lead", texts: { tr: { title: "Başlık 1", summary: "Özet 1.", why: "YZ gerekçe 1" }, en: { title: "Proposal one", summary: "What happened.", why: "AI reason one", points: "Two ministers" } } })], "en");
    expect(doc.title).toBe("Meeting proposals");
    expect(doc.text).toContain("*1. Proposal one*\nWhat happened.\n• Two ministers\nMy note: Lead");
    expect(doc.text).toContain("Sunday, 27 September 2026");
    expect(doc.text).toContain("Sources:");
  });

  it("falls back to Turkish text where English is missing, and never to the publisher's text", () => {
    const s = story(1);
    const doc = storyOutput(en, s, DAY, "en");
    expect(doc.text).toContain("*Hikâye 1*");
    expect(doc.text).toContain("Türkçe özet.");
    expect(doc.text).not.toContain("Publisher's own text");
  });
});
