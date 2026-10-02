import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../api/client";
import { useToast } from "../components/Toasts";
import { describeError, useI18n } from "../i18n";
import type { MessageKey } from "../i18n";
import { useAppState } from "../state";

const OTHER = "__other__";
const PRESETS: { value: string; label: MessageKey }[] = [
  { value: "", label: "settings.look.fontDefault" },
  { value: "Georgia, 'Times New Roman', serif", label: "settings.look.fontSerif" },
  { value: "'Cascadia Mono', Consolas, monospace", label: "settings.look.fontMono" },
  { value: "'Trebuchet MS', 'Segoe UI', sans-serif", label: "settings.look.fontRounded" },
];
const SIZES = [80, 90, 100, 110, 125, 140];
const NAME = /^[\w \-,.'"]*$/;

/** Font, text size and text colour of the whole interface (applied in state.tsx: applyLook). */
export function LookSettings() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings } = useAppState();
  const font = settings["ui.font"];
  const preset = PRESETS.some((p) => p.value === font) ? font : OTHER;
  const [custom, setCustom] = useState(preset === OTHER ? font : "");
  useEffect(() => setCustom(preset === OTHER ? font : ""), [preset, font]);
  const [otherOpen, setOtherOpen] = useState(preset === OTHER);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const change = (patch: Parameters<typeof updateSettings>[0]) => updateSettings(patch).then(() => undefined, fail);

  const saveCustom = () => {
    const value = custom.trim();
    if (!NAME.test(value) || value === font) return;
    void change({ "ui.font": value });
  };
  const shown = otherOpen || preset === OTHER ? OTHER : preset;

  return (
    <>
      <div className="settings-row settings-row-block">
        <div className="settings-row-text">
          <div className="settings-row-title">{t("settings.look.font")}</div>
          <div className="settings-row-hint">{t("settings.look.fontHint")}</div>
        </div>
        <div className="look-controls">
          <select
            className="select"
            aria-label={t("settings.look.font")}
            value={shown}
            onChange={(e) => {
              if (e.target.value === OTHER) setOtherOpen(true);
              else {
                setOtherOpen(false);
                void change({ "ui.font": e.target.value });
              }
            }}
          >
            {PRESETS.map((p) => <option key={p.label} value={p.value}>{t(p.label)}</option>)}
            <option value={OTHER}>{t("settings.look.fontOther")}</option>
          </select>
          {shown === OTHER ? (
            <input
              className="input"
              aria-label={t("settings.look.fontCustom")}
              placeholder={t("settings.look.fontCustom")}
              value={custom}
              aria-invalid={!NAME.test(custom)}
              onChange={(e) => setCustom(e.target.value)}
              onBlur={saveCustom}
              onKeyDown={(e) => e.key === "Enter" && saveCustom()}
            />
          ) : null}
        </div>
      </div>

      <div className="settings-row">
        <div className="settings-row-text">
          <div className="settings-row-title">{t("settings.look.size")}</div>
          <div className="settings-row-hint">{t("settings.look.sizeHint")}</div>
        </div>
        <select
          className="select look-size"
          aria-label={t("settings.look.size")}
          value={SIZES.includes(settings["ui.font_scale"]) ? settings["ui.font_scale"] : 100}
          onChange={(e) => void change({ "ui.font_scale": Number(e.target.value) })}
        >
          {SIZES.map((n) => <option key={n} value={n}>{n}%</option>)}
        </select>
      </div>

      <div className="settings-row settings-row-block">
        <div className="settings-row-text">
          <div className="settings-row-title">{t("settings.look.color")}</div>
          <div className="settings-row-hint">{t("settings.look.colorHint")}</div>
        </div>
        <div className="look-controls">
          {(["light", "dark"] as const).map((mode) => {
            const key = mode === "light" ? "ui.text_color_light" : "ui.text_color_dark";
            const label = t(mode === "light" ? "settings.look.colorLight" : "settings.look.colorDark");
            const value = settings[key];
            return (
              <label key={mode} className="look-color">
                <span>{label}</span>
                <input
                  type="color"
                  aria-label={label}
                  value={value || (mode === "light" ? "#1d1d1f" : "#f5f5f7")}
                  onChange={(e) => void change({ [key]: e.target.value })}
                />
                <button type="button" className="btn" disabled={!value} onClick={() => void change({ [key]: "" })}>
                  {t("settings.look.colorReset")}
                </button>
              </label>
            );
          })}
        </div>
        <div className="look-preview">{t("settings.look.preview")}</div>
      </div>
    </>
  );
}
