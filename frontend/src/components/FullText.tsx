import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { FullText, StoryMember } from "../api/types";
import { describeError, useI18n } from "../i18n";
import { textDirection } from "../lib/hooks";
import { fulltextErrorKey } from "../lib/fulltext";
import { useAppState } from "../state";
import { Dialog, Segmented, Spinner, StateView } from "./controls";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";
import { openableUrl } from "../lib/links";

/**
 * Full-text state of one report in a story, with the action that fits it:
 * fetch, wait, retry after a failure, or open the reader.
 */
export function MemberFullText({ member: m, onRequested }: { member: StoryMember; onRequested: () => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const [reading, setReading] = useState(false);
  const [busy, setBusy] = useState(false);

  const request = async () => {
    setBusy(true);
    try {
      await api.requestFulltext(m.id);
      toast.show(t("fulltext.requested"), "success");
      onRequested();
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const st = m.fulltext_status;
  return (
    <div className="member-fulltext">
      {st === "done" ? (
        <button type="button" className="link-btn" onClick={() => setReading(true)}>
          <Icon name="notebook" size={13} />
          {t("fulltext.read", { chars: i18n.number(m.fulltext_chars ?? 0) })}
        </button>
      ) : st === "pending" ? (
        <span className="fulltext-note" role="status">
          <Spinner />
          {t("fulltext.pending")}
        </span>
      ) : (
        <>
          {st === "failed" || st === "blocked" ? (
            <span className={`fulltext-note ${st === "blocked" ? "warn" : ""}`} role="note">
              <Icon name="alert" size={13} />
              {t(st === "blocked" ? "fulltext.blocked" : "fulltext.failed", {
                reason: t(fulltextErrorKey(m.fulltext_error ?? "")),
              })}
            </span>
          ) : null}
          <button type="button" className="link-btn" disabled={busy} onClick={() => void request()}>
            {st ? t("fulltext.retry") : t("fulltext.fetch")}
          </button>
        </>
      )}
      {reading ? <FullTextReader member={m} onClose={() => setReading(false)} /> : null}
    </div>
  );
}

type Tab = "original" | "tr" | "en";

export const TRANSLATION_POLL_MS = 3000;

/** Reading window: the extracted text, and on request its Turkish and English translations. */
export function FullTextReader({ member: m, onClose }: { member: StoryMember; onClose: () => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status } = useAppState();
  const [ft, setFt] = useState<FullText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const targets = (["tr", "en"] as const).filter((l) => l !== m.language);
  const [tab, setTab] = useState<Tab>(targets.includes(i18n.lang) ? i18n.lang : "original");

  const load = useCallback(async () => {
    try {
      const r = await api.fulltext(m.id);
      setFt(r.fulltext);
      setError(r.fulltext ? null : "not_found");
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, [m.id]);

  useEffect(() => {
    void load();
  }, [load]);

  // A translation in progress: look again every few seconds until it is done or failed.
  const translating = ft?.translate_status === "pending";
  useEffect(() => {
    if (!translating) return;
    const timer = window.setInterval(() => void load(), TRANSLATION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [translating, load]);

  const translate = async () => {
    try {
      await api.translateFulltext(m.id);
      setFt((f) => (f ? { ...f, translate_status: "pending" } : f));
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    }
  };

  let body: React.ReactNode;
  if (error) {
    body = <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)} />;
  } else if (!ft) {
    body = <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>;
  } else {
    const translated = tab === "tr" ? ft.text_tr : tab === "en" ? ft.text_en : null;
    const aiOff = !status || status.ai.state === "disabled" || status.ai.state === "no_model";
    body = (
      <>
        <div className="article-meta">
          <span className="article-source">{m.source_name}</span>
          <time dateTime={m.sort_at}>{i18n.dateTime(m.sort_at)}</time>
          {targets.length > 0 ? (
            <Segmented<Tab>
              label={t("fulltext.language")}
              value={tab}
              onChange={setTab}
              options={[
                { value: "original", label: t("fulltext.tab.original", { lang: i18n.languageName(m.language) }) },
                ...targets.map((l) => ({ value: l as Tab, label: t(`fulltext.tab.${l}`) })),
              ]}
            />
          ) : null}
        </div>
        <h3 className="story-headline" dir={textDirection(m.language)}>{m.title}</h3>
        <p className="field-hint">{t("fulltext.localOnly")}</p>
        {tab === "original" ? (
          <FullTextBody text={ft.text ?? ""} lang={m.language} />
        ) : translated ? (
          <>
            <p className="article-warning" role="note">
              <Icon name="info" size={13} />
              {t("fulltext.machineTranslation")}
            </p>
            <FullTextBody text={translated} lang={tab} />
          </>
        ) : ft.translate_status === "pending" ? (
          <StateView icon="info" title={t("fulltext.translating")} body={t("fulltext.translatingHint")} />
        ) : (
          <StateView
            icon="info"
            title={ft.translate_status === "failed" ? t("fulltext.translateFailed") : t("fulltext.notTranslated")}
            body={aiOff ? t("fulltext.translateNeedsAi") : t("fulltext.translateHint")}
            action={
              aiOff ? undefined : (
                <button className="btn btn-primary" onClick={() => void translate()}>
                  {ft.translate_status === "failed" ? t("common.retry") : t("fulltext.translate")}
                </button>
              )
            }
          />
        )}
      </>
    );
  }

  return (
    <Dialog
      wide
      title={t("fulltext.title")}
      onClose={onClose}
      footer={
        <>
          <a className="btn btn-sm" href={openableUrl(m.url, m.title)} target="_blank" rel="noopener noreferrer">
            <Icon name="external" size={15} />
            {t("feed.openOriginal")}
          </a>
          <span className="spacer" />
          <button className="btn btn-primary btn-sm" onClick={onClose}>{t("common.close")}</button>
        </>
      }
    >
      {body}
    </Dialog>
  );
}

function FullTextBody({ text, lang }: { text: string; lang: string }) {
  return (
    <div className="fulltext-body" dir={textDirection(lang)} lang={lang}>
      {text
        .split(/\n\s*\n|\n/)
        .map((p) => p.trim())
        .filter(Boolean)
        .map((p, i) => (
          <p key={i}>{p}</p>
        ))}
    </div>
  );
}
