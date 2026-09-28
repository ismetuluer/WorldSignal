import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { CatalogGroup, FeedTestResult, Region, Source } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Dialog, Spinner } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { LANGUAGE_CHOICES, isHttpUrl, suggestName } from "./sourceForm";

export function AddSourceDialog({ onClose, onAdded }: { onClose: () => void; onAdded: (s: Source) => void }) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const toast = useToast();
  const { meta } = useAppState();

  const [url, setUrl] = useState("");
  const [testing, setTesting] = useState(false);
  const [result, setResult] = useState<FeedTestResult | null>(null);
  const [testedUrl, setTestedUrl] = useState("");
  const [name, setName] = useState("");
  const [region, setRegion] = useState<Region>("global");
  const [group, setGroup] = useState<CatalogGroup>("other");
  const [language, setLanguage] = useState("en");
  const [saving, setSaving] = useState(false);

  const urlValid = isHttpUrl(url.trim());
  const canSave = result?.ok === true && testedUrl === url.trim() && name.trim() !== "" && !saving;

  const test = async () => {
    const target = url.trim();
    setTesting(true);
    setResult(null);
    try {
      const r = await api.testFeed(target);
      setResult(r);
      setTestedUrl(target);
      if (r.ok) {
        if (!name.trim()) setName(suggestName(r.title, r.final_url ?? target));
        if (r.language && /^[a-z]{2}$/.test(r.language)) {
          setLanguage(r.language);
          if (r.language === "tr") {
            setRegion("turkey");
            setGroup("turkey");
          }
        }
      }
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    } finally {
      setTesting(false);
    }
  };

  const save = async () => {
    setSaving(true);
    try {
      const source = await api.createSource({
        name: name.trim(),
        feed_url: testedUrl,
        catalog_group: group,
        region,
        language,
        reliability: 1,
        paywalled: false,
      });
      toast.show(t("add.added", { name: source.name }), "success");
      onAdded(source);
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog
      title={t("add.title")}
      onClose={onClose}
      footer={
        <>
          <span className="spacer" />
          <button className="btn" onClick={onClose}>{t("common.cancel")}</button>
          <button className="btn btn-primary" disabled={!canSave} onClick={() => void save()}>
            {saving ? t("common.saving") : t("add.submit")}
          </button>
        </>
      }
    >
      <form
        className="field"
        onSubmit={(e) => {
          e.preventDefault();
          if (urlValid && !testing) void test();
        }}
      >
        <span className="field-label">{t("add.url")}</span>
        <div style={{ display: "flex", gap: 8 }}>
          <input
            className="input"
            value={url}
            placeholder="https://…/rss"
            aria-invalid={url.trim() !== "" && !urlValid}
            onChange={(e) => setUrl(e.target.value)}
          />
          <button type="submit" className="btn" disabled={!urlValid || testing}>
            {testing ? <Spinner /> : null}
            {testing ? t("add.testing") : t("add.test")}
          </button>
        </div>
        <span className="field-hint">{url.trim() !== "" && !urlValid ? t("add.invalidUrl") : t("add.urlHint")}</span>
      </form>

      {result ? (
        result.ok ? (
          <div className="test-result ok" role="status">
            <strong>
              <Icon name="check" size={14} /> {plural("add.ok", result.item_count ?? 0)}
            </strong>
            {result.newest_at ? <div>{t("add.newest", { time: i18n.relative(result.newest_at) })}</div> : null}
            {result.sample_titles?.length ? (
              <>
                <div style={{ marginTop: 6 }}>{t("add.sample")}:</div>
                <ul>
                  {result.sample_titles.map((title) => (
                    <li key={title}>{title}</li>
                  ))}
                </ul>
              </>
            ) : null}
          </div>
        ) : (
          <div className="test-result fail" role="alert">
            {t("add.failed", { reason: describeError(i18n, result.error_code) })}
          </div>
        )
      ) : null}

      {result?.ok ? (
        <div className="field-row">
          <label className="field">
            <span className="field-label">{t("editor.name")}</span>
            <input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="field">
            <span className="field-label">{t("editor.language")}</span>
            <select className="select" value={language} onChange={(e) => setLanguage(e.target.value)}>
              {[...new Set([language, ...LANGUAGE_CHOICES])].map((l) => (
                <option key={l} value={l}>{i18n.languageName(l)}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{t("editor.region")}</span>
            <select className="select" value={region} onChange={(e) => setRegion(e.target.value as Region)}>
              {meta.regions.map((r) => (
                <option key={r} value={r}>{t(`region.${r}`)}</option>
              ))}
            </select>
          </label>
          <label className="field">
            <span className="field-label">{t("editor.group")}</span>
            <select className="select" value={group} onChange={(e) => setGroup(e.target.value as CatalogGroup)}>
              {meta.groups.map((g) => (
                <option key={g} value={g}>{t(`group.${g}`)}</option>
              ))}
            </select>
          </label>
        </div>
      ) : null}
    </Dialog>
  );
}
