import { describe, expect, it } from "vitest";
import { createI18n, describeError } from "../i18n";
import { en } from "../i18n/en";
import { tr } from "../i18n/tr";

const NOW = new Date("2026-09-27T12:00:00Z");

describe("dictionaries", () => {
  it("have identical keys and no empty values", () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(tr).sort());
    for (const [key, value] of [...Object.entries(tr), ...Object.entries(en)]) {
      expect(value.trim(), key).not.toBe("");
    }
  });

  it("use the same placeholders in every language", () => {
    const names = (s: string) => [...s.matchAll(/\{(\w+)\}/g)].map((m) => m[1]).sort();
    for (const key of Object.keys(tr) as (keyof typeof tr)[]) {
      expect(names(en[key]), key).toEqual(names(tr[key]));
    }
  });

  it("define both plural forms", () => {
    for (const key of Object.keys(tr)) {
      if (key.endsWith(".one")) expect(tr).toHaveProperty(key.replace(/\.one$/, ".other"));
    }
  });
});

describe("createI18n", () => {
  it("interpolates and formats numbers per locale", () => {
    expect(createI18n("tr").t("feed.count.other", { count: 1234 })).toBe("1.234 haber");
    expect(createI18n("en").t("feed.count.other", { count: 1234 })).toBe("1,234 articles");
  });

  it("chooses plural forms", () => {
    const i = createI18n("en");
    expect(i.plural("feed.count", 1)).toBe("1 article");
    expect(i.plural("feed.count", 2)).toBe("2 articles");
    expect(createI18n("tr").plural("feed.count", 1)).toBe("1 haber");
  });

  it("formats relative times", () => {
    const i = createI18n("tr", () => NOW);
    expect(i.relative("2026-09-27T11:59:50Z")).toBe("az önce");
    expect(i.relative("2026-09-27T11:55:00Z")).toBe("5 dakika önce");
    expect(i.relative("2026-09-27T09:00:00Z")).toBe("3 saat önce");
    expect(i.relative(null)).toBe("");
    expect(createI18n("en", () => NOW).relative("2026-09-27T11:55:00Z")).toBe("5 minutes ago");
  });

  it("labels today and yesterday", () => {
    const i = createI18n("tr", () => new Date(2026, 8, 27, 12));
    expect(i.dayLabel(new Date(2026, 8, 27, 1).toISOString())).toBe("Bugün");
    expect(i.dayLabel(new Date(2026, 8, 26, 23).toISOString())).toBe("Dün");
  });

  it("names languages in the UI language", () => {
    expect(createI18n("tr").languageName("en")).toBe("İngilizce");
    expect(createI18n("en").languageName("tr")).toBe("Turkish");
    expect(createI18n("en").languageName("xx")).toBe("XX");
  });
});

describe("turkeyLink", () => {
  it("explains relevance codes with localized country and topic names", () => {
    const trI = createI18n("tr");
    expect(trI.turkeyLink("turkey_mentioned")).toBe("Metinde Türkiye geçiyor");
    expect(trI.turkeyLink("neighbour:GR")).toBe("Komşu ülke: Yunanistan");
    expect(trI.turkeyLink("turkic:KZ")).toBe("Türk devleti: Kazakistan");
    expect(trI.turkeyLink("topic:black_sea")).toBe("Konu: Karadeniz");
    expect(createI18n("en").turkeyLink("neighbour:IR")).toBe("Neighbouring country: Iran");
    expect(trI.turkeyLink("unknown")).toBe("unknown");
  });
});

describe("describeError", () => {
  const i = createI18n("tr");
  it("maps API and feed codes", () => {
    expect(describeError(i, "feed_exists")).toBe("Bu RSS adresi zaten ekli.");
    expect(describeError(i, "http_403")).toContain("403");
    expect(describeError(i, "http_502")).toBe("Sitede sunucu hatası (502)");
    expect(describeError(i, "http_418")).toBe("Site hata döndürdü (418)");
    expect(describeError(i, "something_new")).toBe("Beklenmeyen bir hata oluştu (something_new).");
    expect(describeError(i, null)).toBe("");
  });
});
