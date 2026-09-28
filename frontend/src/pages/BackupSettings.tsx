import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BackupInfo, BackupList } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Banner, Segmented, Spinner } from "../components/controls";
import { describeError, useI18n, type MessageKey } from "../i18n";
import { useAppState } from "../state";

const KEEP = [7, 14, 30];
const RECENT_RESTORE_MS = 3 * 24 * 3600 * 1000;
const LABELS: Record<string, MessageKey> = {
  daily: "backup.label.daily",
  manual: "backup.label.manual",
  "pre-restore": "backup.label.preRestore",
};

/** Daily database copies: list, make one now, restore one (takes effect after a restart). */
export function BackupSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const [data, setData] = useState<BackupList | null>(null);
  const [busy, setBusy] = useState(false);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const load = useCallback(() => api.backups().then(setData, fail), [fail]);
  useEffect(() => {
    void load();
  }, [load]);

  const run = async (fn: () => Promise<unknown>, success?: string) => {
    setBusy(true);
    try {
      await fn();
      if (success) toast.show(success, "success");
      await load();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const restore = (b: BackupInfo) => {
    if (!window.confirm(t("backup.restoreConfirm", { time: i18n.dateTime(b.created) }))) return;
    void run(() => api.scheduleRestore(b.name));
  };

  const label = (b: BackupInfo) =>
    LABELS[b.label] ? t(LABELS[b.label]!) : b.label.startsWith("pre-migration") ? t("backup.label.preMigration") : b.label;
  const pending = data?.backups.find((b) => b.name === data.pending_restore);
  // The outcome of a restore is news for a few days, not forever.
  const last = data?.last_restore && Date.now() - new Date(data.last_restore.at).getTime() < RECENT_RESTORE_MS
    ? data.last_restore
    : null;

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.backup")}</h2>
      {data?.pending_restore ? (
        <Banner
          icon="info"
          title={t("backup.pending.title")}
          body={t("backup.pending.body", { time: pending ? i18n.dateTime(pending.created) : data.pending_restore })}
          action={
            <div className="inline-row">
              {data.can_restart ? (
                <button className="btn btn-primary btn-sm" disabled={busy} onClick={() => void run(() => api.restartApp())}>
                  {t("backup.restartNow")}
                </button>
              ) : (
                <span className="field-hint">{t("backup.restartManually")}</span>
              )}
              <button className="btn btn-sm" disabled={busy} onClick={() => void run(() => api.cancelRestore())}>
                {t("common.cancel")}
              </button>
            </div>
          }
        />
      ) : null}
      {last ? (
        <p className={`field-hint ${last.ok ? "" : "warn"}`} role="status">
          {last.ok
            ? t("backup.lastRestore.ok", { time: i18n.dateTime(last.at) })
            : t("backup.lastRestore.failed", { time: i18n.dateTime(last.at), reason: t(`backup.error.${last.error === "too_new" || last.error === "corrupt" || last.error === "not_found" ? last.error : "io"}`) })}
        </p>
      ) : null}
      <div className="settings-card">
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("backup.keep")}</div>
            <div className="settings-row-hint">{t("backup.keepHint")}</div>
          </div>
          <Segmented
            label={t("backup.keep")}
            value={settings["backup.keep_daily"]}
            onChange={(v) => void updateSettings({ "backup.keep_daily": v }).catch(fail)}
            options={KEEP.map((n) => ({ value: n, label: t("settings.history.days", { n }) }))}
          />
        </div>
        <div className="settings-row">
          <div className="settings-row-text">
            <div className="settings-row-title">{t("backup.now")}</div>
            <div className="settings-row-hint">{t("backup.nowHint")}</div>
          </div>
          <button className="btn" disabled={busy} onClick={() => void run(() => api.makeBackup(), t("backup.made"))}>
            {busy ? <Spinner /> : <Icon name="plus" size={16} />}
            {t("backup.nowButton")}
          </button>
        </div>
        {data === null ? (
          <div className="settings-row"><Spinner label={t("common.loading")} /></div>
        ) : data.backups.length === 0 ? (
          <div className="settings-row"><span className="settings-row-hint">{t("backup.none")}</span></div>
        ) : (
          <ul className="backup-list" aria-label={t("settings.backup")}>
            {data.backups.map((b) => (
              <li key={b.name}>
                <span className="backup-time">{i18n.dateTime(b.created)}</span>
                <span className="badge">{label(b)}</span>
                <span className="backup-size">{t("backup.size", { size: i18n.number(Math.max(0.1, Math.round(b.bytes / 100_000) / 10)) })}</span>
                <button className="btn btn-sm" disabled={busy || data.pending_restore === b.name} onClick={() => restore(b)}>
                  {t("backup.restore")}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}
