import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { Meta, Settings, UpdateStatus } from "../api/types";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return {
    ...original,
    api: {
      update: vi.fn(),
      checkUpdate: vi.fn(),
      downloadUpdate: vi.fn(),
      applyUpdate: vi.fn(),
      dismissUpdateResult: vi.fn(),
      updateSettings: vi.fn(),
      status: vi.fn(),
    },
  };
});

import { api, ApiError } from "../api/client";
import { ToastProvider } from "../components/Toasts";
import { UpdateBanner, UpdateSettings } from "../components/Update";
import { I18nProvider } from "../i18n";
import { AppStateProvider } from "../state";
import { UPDATE_IDLE } from "./fixtures";

const mocked = vi.mocked(api, true);

const SETTINGS = { "ui.language": "tr", "update.auto_check": true, "update.auto_download": true } as unknown as Settings;
const META = { regions: [], groups: [], languages: [], categories: [], ui_languages: ["tr", "en"], data_dir: "C:\\d", version: "0.8.0" } as unknown as Meta;
const RELEASE = { version: "0.9.0", tag: "v0.9.0", notes: "### Eklendi\n- Spor kaynakları", published_at: null, page: null, size: 1 };

function wrap(ui: ReactNode) {
  return render(
    <AppStateProvider initialSettings={SETTINGS} initialMeta={META}>
      <I18nProvider lang="tr">
        <ToastProvider>{ui}</ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}

const status = (extra: Partial<UpdateStatus>): UpdateStatus => ({ ...UPDATE_IDLE, ...extra });

beforeEach(() => {
  vi.clearAllMocks();
  mocked.updateSettings.mockImplementation(async (p) => ({ ...SETTINGS, ...p }));
});

describe("Update banner", () => {
  it("stays out of the way while nothing is waiting", async () => {
    mocked.update.mockResolvedValue(UPDATE_IDLE);
    const { container } = wrap(<UpdateBanner />);
    await waitFor(() => expect(mocked.update).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("offers a downloaded update with its notes and restarts into it", async () => {
    mocked.update.mockResolvedValue(status({ state: "ready", latest: RELEASE }));
    mocked.applyUpdate.mockResolvedValue({ ok: true });
    wrap(<UpdateBanner />);
    expect(await screen.findByText("World Signal 0.9.0 hazır")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Yenilikler" }));
    expect(await screen.findByText(/Spor kaynakları/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Kapat" }));
    await userEvent.click(screen.getByRole("button", { name: "Yeniden başlat ve güncelle" }));
    expect(mocked.applyUpdate).toHaveBeenCalledTimes(1);
  });

  it("does not offer to install where the program cannot replace itself", async () => {
    mocked.update.mockResolvedValue(status({ state: "ready", latest: RELEASE, unsupported: "readonly" }));
    const { container } = wrap(<UpdateBanner />);
    await waitFor(() => expect(mocked.update).toHaveBeenCalled());
    expect(container.textContent).toBe("");
  });

  it("says once that the program was updated, and forgets it when closed", async () => {
    mocked.update.mockResolvedValue(status({ last_update: { ok: true, from: "0.8.0", to: "0.9.0", at: "2026-09-28T10:00:00Z", notes: "- Yeni" } }));
    mocked.dismissUpdateResult.mockResolvedValue(undefined);
    wrap(<UpdateBanner />);
    expect(await screen.findByText("World Signal 0.9.0 sürümüne güncellendi.")).toBeInTheDocument();
    mocked.update.mockResolvedValue(UPDATE_IDLE);
    await userEvent.click(screen.getByRole("button", { name: "Kapat" }));
    expect(mocked.dismissUpdateResult).toHaveBeenCalled();
    await waitFor(() => expect(screen.queryByText(/sürümüne güncellendi/)).not.toBeInTheDocument());
  });

  it("explains a failed update", async () => {
    mocked.update.mockResolvedValue(status({ last_update: { ok: false, from: "0.8.0", to: "0.9.0", at: "x", error: "in_use" } }));
    wrap(<UpdateBanner />);
    expect(await screen.findByText("Güncelleme yapılamadı; önceki sürüm çalışıyor")).toBeInTheDocument();
    expect(screen.getByText(/kullanımdaydı/)).toBeInTheDocument();
  });
});

describe("Update settings", () => {
  it("checks now and shows what it found", async () => {
    mocked.update.mockResolvedValue(UPDATE_IDLE);
    mocked.checkUpdate.mockResolvedValue(status({ state: "available", latest: RELEASE, checked_at: "2026-09-28T10:00:00Z" }));
    mocked.downloadUpdate.mockResolvedValue(status({ state: "ready", latest: RELEASE }));
    wrap(<UpdateSettings />);
    expect(await screen.findByText("Bu bilgisayardaki sürüm: 0.8.0")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Şimdi denetle" }));
    expect(await screen.findByText(/Yeni sürüm var: 0.9.0/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "İndir" }));
    expect(await screen.findByText(/indirildi ve doğrulandı/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Yeniden başlat ve güncelle" })).toBeInTheDocument();
  });

  it("names a problem in plain words", async () => {
    mocked.update.mockResolvedValue(status({ state: "error", error: "offline" }));
    wrap(<UpdateSettings />);
    expect(await screen.findByText(/GitHub'a ulaşılamadı/)).toBeInTheDocument();
  });

  it("explains a network copy and links the download page instead", async () => {
    mocked.update.mockResolvedValue(status({ state: "available", latest: RELEASE, unsupported: "network" }));
    wrap(<UpdateSettings />);
    expect(await screen.findByText(/ağ klasöründen çalışıyor/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "İndirme sayfasını aç" })).toHaveAttribute("href", UPDATE_IDLE.releases_url);
    expect(screen.queryByRole("button", { name: "İndir" })).not.toBeInTheDocument();
  });

  it("saves the automatic check switches and reports errors", async () => {
    mocked.update.mockResolvedValue(UPDATE_IDLE);
    mocked.checkUpdate.mockRejectedValue(new ApiError("server_unreachable", 0));
    wrap(<UpdateSettings />);
    await userEvent.click(await screen.findByRole("switch", { name: "Yeni sürümü kendiliğinden indir" }));
    expect(mocked.updateSettings).toHaveBeenCalledWith({ "update.auto_download": false });
    await userEvent.click(screen.getByRole("button", { name: "Şimdi denetle" }));
    expect(mocked.checkUpdate).toHaveBeenCalled();
  });
});
