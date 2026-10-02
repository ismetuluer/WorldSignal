import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useToast } from "../components/Toasts";
import { describeError, useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import {
  ACTIONS, DEFAULT_SHORTCUTS, MAX_KEYS, isAssignable, keyLabel, keyOf, resolveShortcuts, takenBy, type ShortcutAction,
} from "../lib/shortcuts";
import { useAppState } from "../state";

const NAMES: Record<ShortcutAction, MessageKey> = {
  search: "settings.shortcut.search",
  next: "settings.shortcut.next",
  prev: "settings.shortcut.prev",
  open: "settings.shortcut.open",
  meeting: "settings.shortcut.meeting",
};

/** Settings → Keyboard shortcuts: every action's keys can be added, removed and put back to the default. */
export function ShortcutSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const custom = settings["ui.shortcuts"];
  const map = resolveShortcuts(custom);
  const [listening, setListening] = useState<ShortcutAction | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );

  const save = useCallback(
    (action: ShortcutAction, keys: string[]) => {
      const rest = { ...custom };
      if (JSON.stringify(keys) === JSON.stringify(DEFAULT_SHORTCUTS[action])) delete rest[action];
      else rest[action] = keys;
      return updateSettings({ "ui.shortcuts": rest }).then(() => undefined, fail);
    },
    [custom, updateSettings, fail],
  );

  // While an action is waiting for a key, the next key press (before any other handler) is the answer; Esc cancels.
  useEffect(() => {
    if (!listening) return;
    const onKey = (e: KeyboardEvent) => {
      e.preventDefault();
      e.stopPropagation();
      const key = keyOf(e);
      if (key === null) return;
      if (key === "escape") {
        setListening(null);
        setMessage(null);
        return;
      }
      if (!isAssignable(key)) {
        setMessage(t("settings.shortcut.notAllowed", { key: keyLabel(key) }));
        return;
      }
      const owner = takenBy(map, key, listening);
      if (owner) {
        setMessage(t("settings.shortcut.taken", { key: keyLabel(key), action: t(NAMES[owner]) }));
        return;
      }
      setListening(null);
      setMessage(null);
      if (!map[listening].includes(key)) void save(listening, [...map[listening], key]);
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [listening, map, save, t]);

  const changed = Object.keys(custom).length > 0;

  return (
    <section className="settings-group">
      <h2 className="section-title">{t("settings.shortcuts")}</h2>
      <div className="settings-card">
        <div className="settings-row settings-row-block">
          <div className="settings-row-text">
            <div className="settings-row-hint">{t("settings.shortcut.hint")}</div>
          </div>
          <dl className="shortcut-list shortcut-edit">
            {ACTIONS.map((action) => (
              <div className="shortcut-row" key={action}>
                <dt>
                  {map[action].map((key) => (
                    <span className="kbd kbd-removable" key={key}>
                      {keyLabel(key)}
                      <button
                        type="button"
                        className="kbd-x"
                        aria-label={t("settings.shortcut.remove", { key: keyLabel(key), action: t(NAMES[action]) })}
                        disabled={map[action].length === 1}
                        onClick={() => void save(action, map[action].filter((k) => k !== key))}
                      >
                        ×
                      </button>
                    </span>
                  ))}
                  {listening === action ? (
                    <span className="kbd kbd-listening" role="status">{t("settings.shortcut.press")}</span>
                  ) : (
                    <button
                      type="button"
                      className="btn btn-small"
                      disabled={map[action].length >= MAX_KEYS}
                      aria-label={t("settings.shortcut.add", { action: t(NAMES[action]) })}
                      onClick={() => {
                        setMessage(null);
                        setListening(action);
                      }}
                    >
                      +
                    </button>
                  )}
                </dt>
                <dd>{t(NAMES[action])}</dd>
                <dd className="shortcut-reset">
                  <button
                    type="button"
                    className="btn btn-small"
                    disabled={custom[action] === undefined}
                    onClick={() => void save(action, DEFAULT_SHORTCUTS[action])}
                  >
                    {t("settings.shortcut.reset")}
                  </button>
                </dd>
              </div>
            ))}
            <div className="shortcut-row">
              <dt><span className="kbd">Esc</span></dt>
              <dd>{t("settings.shortcut.escape")}</dd>
              <dd className="shortcut-reset"><span className="settings-row-hint">{t("settings.shortcut.fixed")}</span></dd>
            </div>
          </dl>
          {message ? <p className="field-hint warn" role="alert">{message}</p> : null}
          <div className="settings-actions">
            <button
              type="button"
              className="btn"
              disabled={!changed}
              onClick={() => void updateSettings({ "ui.shortcuts": {} }).then(() => setListening(null), fail)}
            >
              {t("settings.shortcut.resetAll")}
            </button>
          </div>
        </div>
      </div>
    </section>
  );
}
