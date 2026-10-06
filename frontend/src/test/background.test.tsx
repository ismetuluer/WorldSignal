import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AiStatus, BackupList, Meta, Settings, Status } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      status: vi.fn(),
      updateSettings: vi.fn(),
      backups: vi.fn(),
      makeBackup: vi.fn(),
      scheduleRestore: vi.fn(),
      cancelRestore: vi.fn(),
      restartApp: vi.fn(),
      testNotification: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { BackgroundSettings } from "../pages/BackgroundSettings";
import { BackupSettings } from "../pages/BackupSettings";
import { useLinkedStory } from "../router";
import { AppStateProvider } from "../state";
import { FULLTEXT_WORKER, MAINTENANCE, NOTIFY, STORY_SETTINGS, STORY_WORKER } from "./fixtures";

const mocked = vi.mocked(api, true);

const SETTINGS: Settings = {
  "ui.language": "tr", "ui.theme": "light", "feed.window_hours": 24, "feed.view": "stories", "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false }, "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.labels": true, "work.limited": false, "work.start": 7, "work.end": 23, "home.country": "", "home.related": null, "home.topics": null, "home.keywords": [], "ai.languages": null, "ai.enabled": true,
  "ai.url": "http://localhost:11434", "ai.model": "m", "ai.max_age_hours": 24, "ai.yield_gpu": true, ...STORY_SETTINGS,
};
const META: Meta = {
  regions: ["turkey"], home_region: "turkey", groups: ["turkey"], kinds: ["exclusive", "opinion"], languages: ["tr"], categories: ["politics"], ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR", ai_output_languages: ["tr", "en", "pt", "ar"], ai_prompt_defaults: { article: "Default article. {fields}", translate: "Into {language}." }, ai_input_defaults: { article: "Source: {source}\nHeadline: {title}" }, ai_limit_ranges: { batch_size: [10, 2, 25], article_chars: [6000, 200, 60000], batch_chars: [600, 100, 6000], story_reports: [8, 2, 30], story_report_chars: [700, 100, 6000] },
  data_dir: "C:\\data", version: "0.7.0",
};
const AI: AiStatus = {
  running: true, state: "idle", busy_with: null, model: "m", url: "u", current_article_id: null, last_error: null,
  last_done_at: null, avg_seconds: null, pending: 0, done: 0, failed: 0, done_24h: 0,
};
const STATUS: Status = {
  version: "0.7.0", ai: AI, stories: STORY_WORKER, fulltext: FULLTEXT_WORKER, maintenance: MAINTENANCE, notify: NOTIFY,
  collector: { running: true, busy: false, offline: false, last_cycle_at: null, last_cycle_new: 0, last_cycle_feeds: 0, last_cycle_errors: 0 },
  articles: { total: 0, recent: 0 }, extension: null,
};
const LIST: BackupList = {
  backups: [
    { name: "worldsignal-20260927-080000-daily.db", label: "daily", created: "2026-09-27T08:00:00", bytes: 45_000_000 },
    { name: "worldsignal-20260926-080000-pre-migration-v5.db", label: "pre-migration-v5", created: "2026-09-26T08:00:00", bytes: 40_000_000 },
  ],
  pending_restore: null,
  last_restore: null,
  can_restart: true,
};

function wrap(ui: ReactNode, settings: Settings = SETTINGS) {
  return render(
    <AppStateProvider initialSettings={settings} initialMeta={META}>
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
  mocked.backups.mockResolvedValue(LIST);
});

describe("Background and notifications", () => {
  it("saves the tray behaviour, thresholds and quiet hours", async () => {
    wrap(<BackgroundSettings />);
    await userEvent.click(screen.getByRole("switch", { name: "Pencereyi kapatınca arka planda çalışsın" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "app.close_to_tray": false });
    await userEvent.click(screen.getByRole("switch", { name: "Çökerse kendiliğinden yeniden aç" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "system.restart_on_crash": true });
    await userEvent.click(screen.getByRole("button", { name: "8 kaynak" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.min_sources": 8 });
    await userEvent.click(screen.getByRole("button", { name: "Skor 75+" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.min_score": 75 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sessiz saatlerin başlangıcı" }), "22");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.quiet_start": 22 });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Sessiz saatlerin bitişi" }), "8");
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.quiet_end": 8 });
  });

  it("announces breaking news at once, with its own source threshold", async () => {
    wrap(<BackgroundSettings />);
    const group = screen.getByRole("group", { name: "Son 1 saatte en az" });
    await userEvent.click(within(group).getByRole("button", { name: "2 kaynak" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.breaking_min_sources": 2 });
    await userEvent.click(screen.getByRole("switch", { name: "Son dakika haberlerini hemen bildir" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "notify.breaking": false });
  });

  it("works all day by default and limits the working hours on request", async () => {
    wrap(<BackgroundSettings />);
    expect(screen.getByText(/gece gündüz sürekli çalışıyor/)).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Çalışmanın başlangıcı" })).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("switch", { name: "Çalışma saatlerini sınırla" }));
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "work.limited": true });
  });

  it("saves the working hours", async () => {
    wrap(<BackgroundSettings />, { ...SETTINGS, "work.limited": true });
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Çalışmanın bitişi" }), "20");
    expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "work.end": 20 });
    expect(screen.getByText(/dinlenir; elle istedikleriniz/)).toBeInTheDocument();
  });

  it("sends a test notification", async () => {
    mocked.testNotification.mockResolvedValue({ ok: true });
    wrap(<BackgroundSettings />);
    const button = screen.getByRole("button", { name: "Deneme bildirimi gönder" });
    await waitFor(() => expect(button).toBeEnabled());
    await userEvent.click(button);
    expect(await screen.findByText(/Deneme bildirimi gönderildi/)).toBeInTheDocument();
  });

  it("explains that notifications need the program window", async () => {
    mocked.status.mockResolvedValue({ ...STATUS, notify: { ...NOTIFY, available: false } });
    wrap(<BackgroundSettings />);
    expect(await screen.findByText("Bildirimler yalnızca program penceresiyle çalışırken gösterilebilir.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Deneme bildirimi gönder" })).toBeDisabled();
  });

  it("hides the details when notifications are off", () => {
    wrap(<BackgroundSettings />, { ...SETTINGS, "notify.enabled": false });
    expect(screen.queryByText("Ne zaman bildirilsin")).not.toBeInTheDocument();
  });
});

describe("Backups", () => {
  it("lists backups with their kind and size and makes one now", async () => {
    mocked.makeBackup.mockResolvedValue(LIST.backups[0]!);
    wrap(<BackupSettings />);
    const list = await screen.findByRole("list", { name: "Yedekler" });
    expect(within(list).getByText("Günlük")).toBeInTheDocument();
    expect(within(list).getByText("Güncelleme öncesi")).toBeInTheDocument();
    expect(within(list).getByText("45 MB")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yedekle" }));
    expect(mocked.makeBackup).toHaveBeenCalled();
    expect(await screen.findByText("Yedek alındı.")).toBeInTheDocument();
  });

  it("schedules a restore after confirmation and offers the restart", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    mocked.scheduleRestore.mockResolvedValue({ scheduled: LIST.backups[0]!, can_restart: true });
    mocked.restartApp.mockResolvedValue({ ok: true });
    wrap(<BackupSettings />);
    const list = await screen.findByRole("list", { name: "Yedekler" });
    mocked.backups.mockResolvedValue({ ...LIST, pending_restore: LIST.backups[0]!.name });
    await userEvent.click(within(list).getAllByRole("button", { name: "Geri yükle" })[0]!);
    expect(confirm).toHaveBeenCalled();
    expect(mocked.scheduleRestore).toHaveBeenCalledWith(LIST.backups[0]!.name);
    expect(await screen.findByText("Geri yükleme bekliyor")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Şimdi yeniden başlat" }));
    expect(mocked.restartApp).toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("does nothing when the restore is not confirmed", async () => {
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    wrap(<BackupSettings />);
    const list = await screen.findByRole("list", { name: "Yedekler" });
    await userEvent.click(within(list).getAllByRole("button", { name: "Geri yükle" })[0]!);
    expect(mocked.scheduleRestore).not.toHaveBeenCalled();
    confirm.mockRestore();
  });

  it("asks for a manual restart when the program cannot restart itself, and can cancel", async () => {
    mocked.backups.mockResolvedValue({ ...LIST, pending_restore: LIST.backups[0]!.name, can_restart: false });
    mocked.cancelRestore.mockResolvedValue(undefined);
    wrap(<BackupSettings />);
    expect(await screen.findByText("Programı kapatıp yeniden açın.")).toBeInTheDocument();
    mocked.backups.mockResolvedValue(LIST);
    await userEvent.click(screen.getByRole("button", { name: "Vazgeç" }));
    expect(mocked.cancelRestore).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText("Geri yükleme bekliyor")).not.toBeInTheDocument());
  });

  it("reports the result of the last restore and refusals", async () => {
    const recent = new Date(Date.now() - 3600_000).toISOString().slice(0, 19);
    mocked.backups.mockResolvedValue({ ...LIST, last_restore: { name: "x", at: recent, ok: false, error: "too_new" } });
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    mocked.scheduleRestore.mockRejectedValue(new ApiError("backup_corrupt", 422));
    wrap(<BackupSettings />);
    expect(await screen.findByText(/yedek daha yeni bir program sürümünden/)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: "Geri yükle" })[0]!);
    expect(await screen.findByText("Bu yedek dosyası bozuk; geri yüklenemez.")).toBeInTheDocument();
    confirm.mockRestore();
  });
});

it("no longer mentions a restore from long ago", async () => {
  mocked.backups.mockResolvedValue({ ...LIST, last_restore: { name: "x", at: "2020-01-01T09:00:00", ok: true } });
  wrap(<BackupSettings />);
  await screen.findByRole("list", { name: "Yedekler" });
  expect(screen.queryByText(/yedek geri yüklendi/)).not.toBeInTheDocument();
});

describe("Story linked from a notification", () => {
  function Probe() {
    const [id, clear] = useLinkedStory();
    return <button onClick={clear}>{id === null ? "none" : `story ${id}`}</button>;
  }

  afterEach(() => {
    window.location.hash = "";
  });

  it("reads the story from the address and removes it again", async () => {
    window.location.hash = "#/feed?story=12";
    render(<Probe />);
    expect(screen.getByRole("button", { name: "story 12" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button"));
    await waitFor(() => expect(screen.getByRole("button", { name: "none" })).toBeInTheDocument());
    expect(window.location.hash).toBe("#/feed");
    act(() => {
      window.location.hash = "#/history?story=abc";
      window.dispatchEvent(new HashChangeEvent("hashchange"));
    });
    expect(screen.getByRole("button", { name: "none" })).toBeInTheDocument();
  });
});
