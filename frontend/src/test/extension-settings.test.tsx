import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Status } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      extension: vi.fn(), renewExtensionCode: vi.fn(), openExtensionDir: vi.fn(), updateSettings: vi.fn(),
      restartApp: vi.fn(), status: vi.fn(), browsers: vi.fn(),
    },
  };
});

import { api } from "../api/client";
import { CollectorFooter } from "../App";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { ExtensionSettings } from "../pages/ExtensionSettings";
import { FullTextSettings } from "../pages/FullTextSettings";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, STORY_WORKER } from "./fixtures";
import { renderWithApp } from "./render";

const mocked = vi.mocked(api, true);
const INFO = {
  code: "abc123", port: 47821, fixed_port: true,
  status: { connected: true, warn: false, last_seen: "2026-10-01T09:00:00Z", read_today: 4, reading: null, last_source: "WSJ", last_error: null },
};

beforeEach(() => {
  vi.resetAllMocks();
  mocked.extension.mockResolvedValue(INFO);
  mocked.updateSettings.mockImplementation(async (p) => p as never);
});

describe("Extension settings", () => {
  it("switches the reader and shows the steps, the code and the connection", async () => {
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Bağlı · bugün 4 haber/)).toBeInTheDocument();
    expect(screen.getByText(/Paketlenmemiş öğe yükle/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Kodu kopyala" }));
    mocked.renewExtensionCode.mockResolvedValue({ code: "new" });
    await userEvent.click(screen.getByRole("button", { name: "Yeni kod" }));
    await waitFor(() => expect(mocked.renewExtensionCode).toHaveBeenCalled());
  });

  it("copies the real code but never shows it", async () => {
    const user = userEvent.setup();
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    await screen.findByText(/Bağlı · bugün 4 haber/);
    expect(screen.queryByText(/abc123/)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Kodu kopyala" }));
    expect(await screen.findByText("Eşleşme kodu kopyalandı.")).toBeInTheDocument();
    expect(await navigator.clipboard.readText()).toBe("abc123");
    mocked.renewExtensionCode.mockResolvedValue({ code: "zzz999" });
    await user.click(screen.getByRole("button", { name: "Yeni kod" }));
    await user.click(screen.getByRole("button", { name: "Kodu kopyala" }));
    await waitFor(async () => expect(await navigator.clipboard.readText()).toBe("zzz999"));
    expect(screen.queryByText(/zzz999/)).not.toBeInTheDocument();
  });

  it("saves the reader choice and the browser switch", async () => {
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "automation" });
    expect(screen.queryByRole("button", { name: "Kodu kopyala" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Eklenti (önerilen)" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.reader": "extension" });
    const launch = await screen.findByRole("switch", { name: /Tarayıcı kapalıysa pencere açmadan başlat/ });
    await userEvent.click(launch);
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "fulltext.launch_browser": true });
  });

  it("opens the extension folder", async () => {
    mocked.openExtensionDir.mockResolvedValue({ ok: true });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    await userEvent.click(await screen.findByRole("button", { name: "Eklenti klasörünü aç" }));
    expect(mocked.openExtensionDir).toHaveBeenCalled();
  });

  it("asks for a restart when the program is not on a fixed port, and can restart it", async () => {
    mocked.extension.mockResolvedValue({ ...INFO, fixed_port: false, port: 51234 });
    mocked.restartApp.mockResolvedValue({ ok: true });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Programı yeniden başlatın/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Şimdi yeniden başlat" }));
    expect(mocked.restartApp).toHaveBeenCalled();
  });

  it("does not ask for a restart on a fixed port", async () => {
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    await screen.findByText(/Bağlı/);
    expect(screen.queryByText(/Programı yeniden başlatın/)).not.toBeInTheDocument();
  });

  it("shows when the extension was last heard from and its last error", async () => {
    const seen = new Date(Date.now() - 5 * 60_000).toISOString();
    mocked.extension.mockResolvedValue({
      ...INFO, status: { ...INFO.status, last_seen: seen, last_source: "WSJ", last_error: "tab_closed" },
    });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Son görülme: 5 dakika önce/)).toBeInTheDocument();
    expect(screen.getByText(/Son sorun: sekme kapatıldı/)).toBeInTheDocument();
  });

  it("explains a page that was too large to take", async () => {
    mocked.extension.mockResolvedValue({ ...INFO, status: { ...INFO.status, last_error: "too_large" } });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Son sorun: sayfa alınamayacak kadar büyük/)).toBeInTheDocument();
  });

  it("shows no last-error line when there is none", async () => {
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    await screen.findByText(/Bağlı · bugün 4 haber/);
    expect(screen.queryByText(/Son sorun/)).not.toBeInTheDocument();
  });

  it("says so when the extension state cannot be read, instead of silently showing steps without buttons", async () => {
    mocked.extension.mockRejectedValue(new Error("boom"));
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Eklenti durumu okunamadı/)).toBeInTheDocument();
  });

  it("does not let a poll that was in flight put the old code back after Yeni kod", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    try {
      const user = userEvent.setup({ advanceTimers: vi.advanceTimersByTime });
      renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
      await screen.findByText(/Bağlı · bugün 4 haber/);
      let finishPoll: (info: typeof INFO) => void = () => undefined;
      mocked.extension.mockImplementationOnce(() => new Promise((resolve) => { finishPoll = resolve; }));
      await act(async () => { await vi.advanceTimersByTimeAsync(15_000); });
      expect(mocked.extension).toHaveBeenCalledTimes(2);
      mocked.renewExtensionCode.mockResolvedValue({ code: "zzz999" });
      await user.click(screen.getByRole("button", { name: "Yeni kod" }));
      await act(async () => { finishPoll(INFO); });
      await user.click(screen.getByRole("button", { name: "Kodu kopyala" }));
      expect(await navigator.clipboard.readText()).toBe("zzz999");
    } finally {
      vi.useRealTimers();
    }
  });

  it("says when the extension has not been heard from", async () => {
    mocked.extension.mockResolvedValue({ ...INFO, status: { ...INFO.status, connected: false, last_seen: null } });
    renderWithApp(<ExtensionSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByText(/Eklenti bağlı değil/)).toBeInTheDocument();
  });
});

describe("Full-text settings with the extension reader", () => {
  const BROWSERS = {
    browsers: [{ name: "Brave", path: "C:\\brave.exe" }, { name: "Chrome", path: "C:\\chrome.exe" }],
    chosen: "C:\\brave.exe", own_profile: "C:\\p", main_profile_in_use: false,
  };

  it("keeps the browser choice (sign-in and launch use it) but hides the profile and window rows", async () => {
    mocked.browsers.mockResolvedValue(BROWSERS);
    renderWithApp(<FullTextSettings />, { "fulltext.reader": "extension" });
    expect(await screen.findByRole("button", { name: "Kodu kopyala" })).toBeInTheDocument();
    const select = await screen.findByRole("combobox", { name: "Tarayıcı" });
    expect(screen.getByText(/Eklentiyi yüklediğiniz tarayıcıyı seçin/)).toBeInTheDocument();
    await userEvent.selectOptions(select, "C:\\chrome.exe");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "fulltext.browser_path": "C:\\chrome.exe" });
    expect(screen.queryByText("Tarayıcı profili")).not.toBeInTheDocument();
    expect(screen.queryByRole("switch", { name: "Tarayıcı penceresini göster" })).not.toBeInTheDocument();
  });

  it("shows every browser row, without the extension hint, when the program's own browser reads", async () => {
    mocked.browsers.mockResolvedValue(BROWSERS);
    renderWithApp(<FullTextSettings />, { "fulltext.reader": "automation" });
    expect(await screen.findByText("Tarayıcı profili")).toBeInTheDocument();
    expect(screen.getByRole("combobox", { name: "Tarayıcı" })).toBeInTheDocument();
    expect(screen.getByRole("switch", { name: "Tarayıcı penceresini göster" })).toBeInTheDocument();
    expect(screen.queryByText(/Eklentiyi yüklediğiniz tarayıcıyı seçin/)).not.toBeInTheDocument();
  });
});

describe("Sidebar", () => {
  const STATUS: Status = {
    version: "0.7.0", ai: { running: true, state: "idle", busy_with: null, model: "m", url: "u", current_article_id: null,
      last_error: null, last_done_at: null, avg_seconds: null, pending: 0, done: 0, failed: 0, done_24h: 0 },
    stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
    collector: { running: true, busy: false, offline: false, last_cycle_at: null, last_cycle_new: 0, last_cycle_feeds: 0, last_cycle_errors: 0 },
    articles: { total: 0, recent: 0 }, extension: null,
  };
  const EXT = { connected: false, warn: false, last_seen: null, read_today: 0, reading: null, last_source: null, last_error: null };

  const footer = () => render(
    <AppStateProvider initialSettings={{} as never} initialMeta={{} as never}>
      <I18nProvider lang="tr"><ToastProvider><CollectorFooter /></ToastProvider></I18nProvider>
    </AppStateProvider>,
  );

  it("warns when the program says the extension has been silent too long", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, extension: { ...EXT, active: true, warn: true } });
    footer();
    expect(await screen.findByText(/Eklenti bağlı değil/)).toBeInTheDocument();
  });

  it("does not warn merely because the extension is not connected yet (start-up, a long wait)", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, extension: { ...EXT, active: true, connected: false, warn: false } });
    footer();
    await screen.findByText("Henüz tarama yapılmadı");
    expect(screen.queryByText(/Eklenti bağlı değil/)).not.toBeInTheDocument();
  });

  it("says nothing when the extension is connected or not in use", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, extension: { ...EXT, connected: true, active: true } });
    const { unmount } = footer();
    await screen.findByText("Henüz tarama yapılmadı");
    expect(screen.queryByText(/Eklenti bağlı değil/)).not.toBeInTheDocument();
    unmount();
    mocked.status.mockResolvedValue({ ...STATUS, extension: { ...EXT, active: false } });
    footer();
    await screen.findByText("Henüz tarama yapılmadı");
    expect(screen.queryByText(/Eklenti bağlı değil/)).not.toBeInTheDocument();
  });
});
