import { render } from "@testing-library/react";
import type { ReactNode } from "react";
import type { Meta, Settings } from "../api/types";
import { ToastProvider } from "../components/Toasts";
import { I18nProvider } from "../i18n";
import { AppStateProvider } from "../state";
import { STORY_SETTINGS } from "./fixtures";

const BASE_SETTINGS: Settings = {
  "ui.language": "tr", "ui.theme": "light", "feed.window_hours": 24, "feed.view": "stories",
  "feed.filters": { regions: [], groups: [], langs: [], sources: [], categories: [], turkey: false },
  "update.auto_check": true, "update.auto_download": true, "home.enabled": true, "home.labels": true,
  "work.limited": false, "work.start": 7, "work.end": 23, "home.country": "", "home.related": null,
  "home.topics": null, "home.keywords": [], "ai.languages": null, "ai.enabled": true,
  "ai.url": "http://localhost:11434", "ai.model": "m", "ai.max_age_hours": 24, "ai.yield_gpu": true,
  ...STORY_SETTINGS,
};

const META: Meta = {
  regions: ["turkey"], home_region: "turkey", groups: ["turkey"], kinds: ["exclusive", "opinion"], languages: ["tr"],
  categories: ["politics"], ui_languages: ["tr", "en"], home_country: "TR", system_country: "TR",
  ai_output_languages: ["tr", "en", "pt", "ar"], data_dir: "C:\\data", version: "0.7.0",
};

/** Renders `ui` inside the app's providers (Turkish), with the default test settings overridden by `settings`. */
export function renderWithApp(ui: ReactNode, settings: Partial<Settings> = {}) {
  return render(
    <AppStateProvider initialSettings={{ ...BASE_SETTINGS, ...settings }} initialMeta={META}>
      <I18nProvider lang="tr">
        <ToastProvider>{ui}</ToastProvider>
      </I18nProvider>
    </AppStateProvider>,
  );
}
