import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Meta, Settings } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { addClip: vi.fn() } };
});

import { api, ApiError } from "../api/client";
import { bookmarkletCode, ClipDialog } from "../components/ClipDialog";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { AppStateProvider } from "../state";
import { STORY_SETTINGS } from "./fixtures";

const mocked = vi.mocked(api, true);
const SETTINGS = { "ui.language": "tr", ...STORY_SETTINGS } as unknown as Settings;
const META = { regions: [], groups: [], kinds: [], home_region: null, languages: [], categories: [], ui_languages: ["tr", "en"], version: "0" } as unknown as Meta;

function wrap(ui: ReactNode) {
  return render(
    <AppStateProvider initialSettings={SETTINGS} initialMeta={META}>
      <I18nProvider lang="tr">
        <ToastProvider>{ui}</ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}

beforeEach(() => vi.resetAllMocks());

describe("Add a page", () => {
  it("explains the three steps and offers the bookmark as a draggable link", () => {
    wrap(<ClipDialog onClose={() => undefined} />);
    expect(screen.getByRole("dialog", { name: "Sayfa ekle" })).toBeInTheDocument();
    expect(screen.getByText(/yer imleri çubuğuna sürükleyin/)).toBeInTheDocument();
    const link = screen.getByText("World Signal'e kopyala").closest("a")!;
    expect(link.getAttribute("href")).toMatch(/^javascript:/);
    expect(decodeURIComponent(link.getAttribute("href")!.slice("javascript:".length))).toContain("ws:1");
  });

  it("adds the pasted page and says what was added", async () => {
    mocked.addClip.mockResolvedValue({ article_id: 5, source: "The Economist", title: "Why rates stay", chars: 5432, created: true });
    const onAdded = vi.fn();
    wrap(<ClipDialog onClose={() => undefined} onAdded={onAdded} />);
    const add = screen.getByRole("button", { name: "Ekle" });
    expect(add).toBeDisabled(); // nothing pasted yet
    await userEvent.click(screen.getByRole("textbox"));
    await userEvent.paste('{"ws":1,"url":"https://www.economist.com/x","html":"<p>hi</p>"}');
    await userEvent.click(add);
    expect(mocked.addClip).toHaveBeenCalledWith('{"ws":1,"url":"https://www.economist.com/x","html":"<p>hi</p>"}');
    expect(await screen.findByText(/Why rates stay/)).toBeInTheDocument();
    expect(screen.getByText(/karakter tam metin eklendi/).closest("p")).toHaveTextContent("The Economist");
    expect(screen.getByText(/5\.432 karakter tam metin eklendi/)).toBeInTheDocument();
    expect(onAdded).toHaveBeenCalled();
    expect(screen.getByRole("textbox")).toHaveValue(""); // ready for the next one
  });

  it("says why a page was not accepted", async () => {
    mocked.addClip.mockRejectedValue(new ApiError("clip_paywall", 422));
    wrap(<ClipDialog onClose={() => undefined} />);
    await userEvent.click(screen.getByRole("textbox"));
    await userEvent.paste("{}");
    await userEvent.click(screen.getByRole("button", { name: "Ekle" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Sayfada haberin tamamı yok");
    // Editing the box clears the message.
    await userEvent.type(screen.getByRole("textbox"), "x");
    await waitFor(() => expect(screen.queryByRole("alert")).not.toBeInTheDocument());
  });

  it("notes that a page which was already there had its text refreshed", async () => {
    mocked.addClip.mockResolvedValue({ article_id: 5, source: "Alpha", title: "Same", chars: 100, created: false });
    wrap(<ClipDialog onClose={() => undefined} />);
    await userEvent.click(screen.getByRole("textbox"));
    await userEvent.paste("{}");
    await userEvent.click(screen.getByRole("button", { name: "Ekle" }));
    expect(await screen.findByText(/metni yenilendi/)).toBeInTheDocument();
  });
});

describe("The bookmark", () => {
  it("copies the page's address, title, language and HTML to the clipboard as the server expects", async () => {
    document.head.innerHTML = '<meta property="og:title" content="A good headline"><title>A good headline | Site</title>';
    document.documentElement.lang = "en-GB";
    document.body.innerHTML = "<article><p>The text of the report.</p></article>";
    const written: string[] = [];
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText: (t: string) => { written.push(t); return Promise.resolve(); } } });
    const alerts: string[] = [];
    vi.spyOn(window, "alert").mockImplementation((m) => void alerts.push(String(m)));

    new Function(bookmarkletCode("DONE", "FAILED"))();
    await waitFor(() => expect(alerts).toEqual(["DONE"]));
    const clip = JSON.parse(written[0]!);
    expect(clip.ws).toBe(1);
    expect(clip.url).toBe(location.href);
    expect(clip.title).toBe("A good headline"); // og:title rather than the tab title with the site suffix
    expect(clip.lang).toBe("en-GB");
    expect(clip.html).toContain("The text of the report.");
  });

  it("falls back to selecting a hidden box when the clipboard interface is missing, and says when it fails", async () => {
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: undefined });
    document.body.innerHTML = "<p>page</p>";
    const alerts: string[] = [];
    vi.spyOn(window, "alert").mockImplementation((m) => void alerts.push(String(m)));
    (document as unknown as { execCommand: () => boolean }).execCommand = () => false;
    new Function(bookmarkletCode("DONE", "FAILED"))();
    expect(alerts).toEqual(["FAILED"]);
    (document as unknown as { execCommand: () => boolean }).execCommand = () => true;
    new Function(bookmarkletCode("DONE", "FAILED"))();
    expect(alerts).toEqual(["FAILED", "DONE"]);
    expect(document.querySelector("textarea")).toBeNull(); // the helper box is removed again
  });
});
