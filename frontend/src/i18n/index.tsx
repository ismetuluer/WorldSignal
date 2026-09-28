import { createContext, useContext, useMemo, type ReactNode } from "react";
import type { UiLanguage } from "../api/types";
import { en } from "./en";
import { tr, type MessageKey } from "./tr";

export type { MessageKey };

const DICTIONARIES: Record<UiLanguage, Record<MessageKey, string>> = { tr, en };

/** Keys that have ".one"/".other" variants, addressed without the suffix. */
type PluralBase<K> = K extends `${infer B}.one` ? B : never;
export type PluralKey = PluralBase<MessageKey>;

type Params = Record<string, string | number>;

const LOCALES: Record<UiLanguage, string> = { tr: "tr-TR", en: "en-GB" };

function interpolate(template: string, params?: Params, locale?: string): string {
  if (!params) return template;
  return template.replace(/\{(\w+)\}/g, (match, name: string) => {
    const value = params[name];
    if (value === undefined) return match;
    return typeof value === "number" ? value.toLocaleString(locale) : value;
  });
}

export interface I18n {
  lang: UiLanguage;
  locale: string;
  t: (key: MessageKey, params?: Params) => string;
  plural: (key: PluralKey, count: number, params?: Params) => string;
  /** Translate a code-based key that may not exist (e.g. server error codes). */
  tryT: (key: string, params?: Params) => string | null;
  relative: (iso: string | null | undefined) => string;
  dateTime: (iso: string) => string;
  time: (iso: string) => string;
  dayLabel: (iso: string) => string;
  languageName: (code: string) => string;
  countryName: (code: string) => string;
  /** The user's country (ISO code); its name fills "{home}" in every text. */
  home: string;
  /** Human sentence for one "related to my country" link code. */
  turkeyLink: (link: string) => string;
  number: (n: number) => string;
}

export function createI18n(lang: UiLanguage, now: () => Date = () => new Date(), home = "TR"): I18n {
  const dict = DICTIONARIES[lang];
  const locale = LOCALES[lang];
  const pluralRules = new Intl.PluralRules(locale);
  const rtf = new Intl.RelativeTimeFormat(locale, { numeric: "auto" });
  const dtf = new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" });
  const tf = new Intl.DateTimeFormat(locale, { hour: "2-digit", minute: "2-digit" });
  const dayFmt = new Intl.DateTimeFormat(locale, { weekday: "long", day: "numeric", month: "long" });
  let languageNames: Intl.DisplayNames | null = null;
  let regionNames: Intl.DisplayNames | null = null;
  try {
    languageNames = new Intl.DisplayNames(locale, { type: "language" });
    regionNames = new Intl.DisplayNames(locale, { type: "region" });
  } catch {
    languageNames = null;
    regionNames = null;
  }
  const countryName = (code: string) => {
    try {
      return regionNames?.of(code) ?? code;
    } catch {
      return code;
    }
  };

  const homeName = countryName(home);
  const t = (key: MessageKey, params?: Params) => interpolate(dict[key] ?? key, { home: homeName, ...params }, locale);

  const i18n: I18n = {
    lang,
    locale,
    t,
    plural: (key, count, params) => {
      const form = pluralRules.select(count) === "one" ? "one" : "other";
      return t(`${key}.${form}` as MessageKey, { count, ...params });
    },
    tryT: (key, params) => {
      const template = (dict as Record<string, string>)[key];
      return template === undefined ? null : interpolate(template, { home: homeName, ...params }, locale);
    },
    relative: (iso) => {
      if (!iso) return "";
      const diffSec = (new Date(iso).getTime() - now().getTime()) / 1000;
      const abs = Math.abs(diffSec);
      if (abs < 45) return t("common.justNow");
      if (abs < 3600) return rtf.format(Math.round(diffSec / 60), "minute");
      if (abs < 86400) return rtf.format(Math.round(diffSec / 3600), "hour");
      if (abs < 86400 * 7) return rtf.format(Math.round(diffSec / 86400), "day");
      return dtf.format(new Date(iso));
    },
    dateTime: (iso) => dtf.format(new Date(iso)),
    time: (iso) => tf.format(new Date(iso)),
    dayLabel: (iso) => {
      const d = new Date(iso);
      const today = now();
      const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
      const days = Math.round((startOf(today) - startOf(d)) / 86400000);
      if (days === 0) return t("feed.today");
      if (days === 1) return t("feed.yesterday");
      return dayFmt.format(d);
    },
    languageName: (code) => {
      try {
        const name = languageNames?.of(code);
        if (name && name !== code) return name.charAt(0).toLocaleUpperCase(locale) + name.slice(1);
      } catch {
        /* unknown code: fall through */
      }
      return code.toUpperCase();
    },
    number: (n) => n.toLocaleString(locale),
    countryName,
    home,
    turkeyLink: (link) => {
      const [kind, value = ""] = link.split(":");
      if (kind === "home_mentioned") return t("ai.link.home_mentioned");
      if (kind === "neighbour") return t("ai.link.neighbour", { country: countryName(value) });
      if (kind === "related") return t("ai.link.related", { country: countryName(value) });
      if (kind === "topic") {
        const label = (dict as Record<string, string>)[`topic.${value}`] ?? value;
        return t("ai.link.topic", { topic: label });
      }
      return link;
    },
  };
  return i18n;
}

const I18nContext = createContext<I18n>(createI18n("tr"));

export function I18nProvider({ lang, home, children }: { lang: UiLanguage; home?: string; children: ReactNode }) {
  const value = useMemo(() => createI18n(lang, undefined, home), [lang, home]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18n {
  return useContext(I18nContext);
}

/** Translate an API or feed error code into a sentence. */
export function describeError(i18n: I18n, code: string | null | undefined): string {
  if (!code) return "";
  const direct = i18n.tryT(`error.${code}`) ?? i18n.tryT(`feedError.${code}`);
  if (direct) return direct;
  const http = /^http_(\d{3})$/.exec(code);
  if (http) {
    const status = http[1] ?? "";
    return i18n.t(status.startsWith("5") ? "feedError.http_5xx" : "feedError.http_other", { code: status });
  }
  return i18n.t("error.generic", { code });
}
