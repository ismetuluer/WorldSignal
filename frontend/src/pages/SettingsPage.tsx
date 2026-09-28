import { api, ApiError } from "../api/client";
import type { Settings, ThemeSetting, UiLanguage } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Segmented } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { AiSettings } from "./AiSettings";
import { FullTextSettings } from "./FullTextSettings";
import { BackgroundSettings } from "./BackgroundSettings";
import { BackupSettings } from "./BackupSettings";
import { UpdateSettings } from "../components/Update";
import { HistorySettings } from "./HistorySettings";
import { StorySettings } from "./StorySettings";

const LANGUAGE_LABELS: Record<UiLanguage, string> = { tr: "Türkçe", en: "English" };

export function SettingsPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { settings, updateSettings, meta } = useAppState();

  const change = (patch: Partial<Settings>) => {
    updateSettings(patch).catch((e: unknown) =>
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    );
  };

  return (
    <div className="page">
      <header className="page-header">
        <h1 className="page-title">{t("settings.title")}</h1>
      </header>

      <section className="settings-group">
        <h2 className="section-title">{t("settings.appearance")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.theme")}</div>
            </div>
            <Segmented<ThemeSetting>
              label={t("settings.theme")}
              value={settings["ui.theme"]}
              onChange={(v) => change({ "ui.theme": v })}
              options={[
                { value: "system", label: t("settings.theme.system") },
                { value: "light", label: t("settings.theme.light") },
                { value: "dark", label: t("settings.theme.dark") },
              ]}
            />
          </div>
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.language")}</div>
              <div className="settings-row-hint">{t("settings.languageHint")}</div>
            </div>
            <Segmented<UiLanguage>
              label={t("settings.language")}
              value={settings["ui.language"]}
              onChange={(v) => change({ "ui.language": v })}
              options={meta.ui_languages.map((l) => ({ value: l, label: LANGUAGE_LABELS[l] ?? l }))}
            />
          </div>
        </div>
      </section>

      <AiSettings />
      <StorySettings />
      <FullTextSettings />
      <HistorySettings />
      <BackgroundSettings />
      <BackupSettings />
      <UpdateSettings />

      <section className="settings-group">
        <h2 className="section-title">{t("settings.data")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-text">
              <div className="settings-row-title">{t("settings.dataDir")}</div>
              <div className="path">{meta.data_dir}</div>
              <div className="settings-row-hint">{t("settings.dataDirHint")}</div>
            </div>
            <button
              className="btn"
              onClick={() =>
                api.openDataDir().catch((e: unknown) =>
                  toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
                )
              }
            >
              <Icon name="folder" size={16} />
              {t("settings.openDataDir")}
            </button>
          </div>
        </div>
      </section>

      <section className="settings-group">
        <h2 className="section-title">{t("settings.shortcuts")}</h2>
        <div className="settings-card">
          <dl className="shortcut-list">
            <dt><span className="kbd">/</span></dt>
            <dd>{t("settings.shortcut.search")}</dd>
            <dt><span className="kbd">J</span></dt>
            <dd>{t("settings.shortcut.next")}</dd>
            <dt><span className="kbd">K</span></dt>
            <dd>{t("settings.shortcut.prev")}</dd>
            <dt><span className="kbd">Enter</span> <span className="kbd">O</span></dt>
            <dd>{t("settings.shortcut.open")}</dd>
            <dt><span className="kbd">T</span></dt>
            <dd>{t("settings.shortcut.meeting")}</dd>
            <dt><span className="kbd">Esc</span></dt>
            <dd>{t("settings.shortcut.escape")}</dd>
          </dl>
        </div>
      </section>

      <section className="settings-group">
        <h2 className="section-title">{t("settings.about")}</h2>
        <div className="settings-card">
          <div className="settings-row">
            <div className="settings-row-title">{t("app.name")}</div>
            <span className="settings-row-hint">{t("settings.version", { version: meta.version })}</span>
          </div>
        </div>
      </section>
    </div>
  );
}
