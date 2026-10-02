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
  ai_output_languages: ["tr", "en", "pt", "ar"], ai_prompt_defaults: { article: "Default article. {fields}", translate: "Into {language}." }, ai_input_defaults: { article: "Source: {source}\nHeadline: {title}" }, ai_limit_ranges: { batch_size: [10, 2, 25], article_chars: [6000, 200, 60000], batch_chars: [600, 100, 6000], story_reports: [8, 2, 30], story_report_chars: [700, 100, 6000] }, data_dir: "C:\\data", version: "0.7.0",
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
