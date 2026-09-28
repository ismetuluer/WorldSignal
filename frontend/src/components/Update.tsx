import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { UpdateStatus } from "../api/types";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { useAppState } from "../state";
import { Banner, Dialog, Spinner, Switch } from "./controls";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";

const POLL_MS = 60_000;
const POLL_BUSY_MS = 1_000;

/** The updater's state, refreshed every minute (every second while something is happening). */
export function useUpdate(): [UpdateStatus | null, (next?: UpdateStatus) => void] {
  const [status, setStatus] = useState<UpdateStatus | null>(null);
  const refresh = useCallback((next?: UpdateStatus) => {
    if (next) setStatus(next);
    else api.update().then(setStatus, () => undefined);
  }, []);
  const busy = status?.state === "checking" || status?.state === "downloading";
  useEffect(() => {
    refresh();
    const timer = window.setInterval(() => refresh(), busy ? POLL_BUSY_MS : POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh, busy]);
  return [status, refresh];
}

function errorText(t: (k: MessageKey) => string, code: string | null): string {
  const known = ["offline", "rate_limited", "no_release", "checksum_mismatch", "no_checksum", "bad_package", "download_failed",
    "too_large", "http_error", "bad_answer"];
  return t(`update.error.${code && known.includes(code) ? code : "other"}` as MessageKey);
}

function NotesDialog({ title, notes, onClose }: { title: string; notes: string; onClose: () => void }) {
  return (
    <Dialog title={title} onClose={onClose}>
      <div className="release-notes">{notes}</div>
    </Dialog>
  );
}

/** Shown on every page: a downloaded update waits for a restart, or the program was just updated. */
export function UpdateBanner() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const [u, refresh] = useUpdate();
  const [notes, setNotes] = useState<{ title: string; text: string } | null>(null);
  const [busy, setBusy] = useState(false);
  if (!u) return null;

  const apply = async () => {
    setBusy(true);
    try {
      await api.applyUpdate();
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
      setBusy(false);
    }
  };
  const dismiss = () => api.dismissUpdateResult().then(() => refresh(), () => undefined);

  let banner = null;
  if (u.last_update) {
    const r = u.last_update;
    banner = r.ok ? (
      <Banner
        icon="check"
        title={t("update.done", { version: r.to ?? u.current })}
        action={
          <div className="inline-row">
            {r.notes ? (
              <button className="btn btn-sm" onClick={() => setNotes({ title: t("update.notesTitle", { version: r.to ?? "" }), text: r.notes! })}>
                {t("update.whatsNew")}
              </button>
            ) : null}
            <button className="btn btn-ghost btn-sm" onClick={() => void dismiss()}>{t("common.close")}</button>
          </div>
        }
      />
    ) : (
      <Banner
        kind="error"
        icon="alert"
        title={t("update.failedTitle")}
        body={t(r.error === "in_use" ? "update.failed.in_use" : "update.failed.copy")}
        action={<button className="btn btn-ghost btn-sm" onClick={() => void dismiss()}>{t("common.close")}</button>}
      />
    );
  } else if (u.state === "ready" && u.latest && !u.unsupported) {
    banner = (
      <Banner
        icon="download"
        title={t("update.ready", { version: u.latest.version })}
        body={t("update.readyBody")}
        action={
          <div className="inline-row">
            <button className="btn btn-sm" onClick={() => setNotes({ title: t("update.notesTitle", { version: u.latest!.version }), text: u.latest!.notes })}>
              {t("update.whatsNew")}
            </button>
            {u.can_quit ? (
              <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void apply()}>
                {busy ? <Spinner /> : null}
                {t("update.restartNow")}
              </button>
            ) : null}
          </div>
        }
      />
    );
  }
  if (!banner && !notes) return null;
  return (
    <div className="page" style={{ paddingBottom: 0 }}>
      {banner}
      {notes ? <NotesDialog title={notes.title} notes={notes.text} onClose={() => setNotes(null)} /> : null}
    </div>
  );
}

/** Settings → Updates. */
export function UpdateSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const [u, refresh] = useUpdate();
  const [busy, setBusy] = useState(false);
  const [notes, setNotes] = useState(false);

  const fail = (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
  const act = async (fn: () => Promise<UpdateStatus>) => {
    setBusy(true);
    try {
      refresh(await fn());
    } catch (e) {
      fail(e);
      refresh();
    } finally {
      setBusy(false);
    }
  };

  let line: string;
  if (!u) line = t("common.loading");
  else if (u.state === "checking") line = t("update.state.checking");
  else if (u.state === "downloading") line = t("update.state.downloading", { percent: Math.round((u.progress ?? 0) * 100) });
  else if (u.state === "error") line = errorText(t, u.error);
  else if (u.state === "up_to_date") line = t("update.state.upToDate");
  else if ((u.state === "available" || u.state === "ready") && u.latest)
    line = t(u.state === "ready" ? "update.state.ready" : "update.state.available", { version: u.latest.version });
  else line = t("update.state.idle");

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.update")}</h2>
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("update.current", { version: u?.current ?? "…" })}</div>
            <div className={`settings-row-hint ${u?.state === "error" ? "warn" : ""}`} role="status">
              {line}
              {u?.checked_at ? ` · ${t("update.checkedAt", { time: i18n.dateTime(u.checked_at) })}` : ""}
            </div>
            {u?.unsupported ? (
              <div className="settings-row-hint warn">{t(`update.unsupported.${u.unsupported}` as MessageKey)}</div>
            ) : null}
          </div>
          <div className="inline-row">
            {u?.latest && (u.state === "available" || u.state === "ready") ? (
              <button className="btn btn-sm" onClick={() => setNotes(true)}>{t("update.whatsNew")}</button>
            ) : null}
            {u?.state === "available" && !u.unsupported ? (
              <button className="btn btn-sm" disabled={busy} onClick={() => void act(() => api.downloadUpdate())}>
                <Icon name="download" size={15} />
                {t("update.download")}
              </button>
            ) : u?.unsupported && u.latest && u.state === "available" ? (
              <a className="btn btn-sm" href={u.releases_url} target="_blank" rel="noopener noreferrer">
                <Icon name="external" size={15} />
                {t("update.openReleases")}
              </a>
            ) : null}
            {u?.state === "ready" && !u.unsupported && u.can_quit ? (
              <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void api.applyUpdate().catch(fail)}>
                {t("update.restartNow")}
              </button>
            ) : null}
            <button className="btn btn-sm" disabled={busy || u?.state === "checking" || u?.state === "downloading"}
              onClick={() => void act(() => api.checkUpdate())}>
              {busy || u?.state === "checking" ? <Spinner /> : <Icon name="refresh" size={15} />}
              {t("update.checkNow")}
            </button>
          </div>
        </div>
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("update.autoCheck")}</div>
            <div className="settings-row-hint">{t("update.autoCheckHint")}</div>
          </div>
          <Switch checked={settings["update.auto_check"]} label={t("update.autoCheck")}
            onChange={(v) => void updateSettings({ "update.auto_check": v }).catch(fail)} />
        </div>
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("update.autoDownload")}</div>
            <div className="settings-row-hint">{t("update.autoDownloadHint")}</div>
          </div>
          <Switch checked={settings["update.auto_download"]} label={t("update.autoDownload")}
            onChange={(v) => void updateSettings({ "update.auto_download": v }).catch(fail)} />
        </div>
      </div>
      {notes && u?.latest ? (
        <NotesDialog title={t("update.notesTitle", { version: u.latest.version })} notes={u.latest.notes} onClose={() => setNotes(false)} />
      ) : null}
    </section>
  );
}
