import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { FullText, StoryMember } from "../api/types";
import { describeError, useI18n } from "../i18n";
import { textDirection } from "../lib/hooks";
import { fulltextErrorKey } from "../lib/fulltext";
import { useAppState } from "../state";
import { aiLanguages } from "../lib/aiText";
import { Dialog, Segmented, Spinner, StateView } from "./controls";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";
import { openableUrl } from "../lib/links";

/** What the full-text controls need to know of a report: a member of a story or an article of the feed. */
export type Reportish = Pick<StoryMember, "id" | "url" | "title" | "source_name" | "sort_at" | "language"> &
  Partial<Pick<StoryMember, "fulltext_status" | "fulltext_error" | "fulltext_chars">>;

const CARD_POLL_MS = 4000;

/**
 * The same controls on a card of the feed: asking for the text there keeps the state here (no list reload) and
 * looks again every few seconds until the text arrived or failed.
 */
export function CardFullText({ report }: { report: Reportish }) {
  const [state, setState] = useState<Pick<Reportish, "fulltext_status" | "fulltext_error" | "fulltext_chars">>({
    fulltext_status: report.fulltext_status ?? null,
    fulltext_error: report.fulltext_error ?? null,
    fulltext_chars: report.fulltext_chars ?? null,
  });
  const pending = state.fulltext_status === "pending";

  const look = useCallback(async () => {
    try {
      const { fulltext } = await api.fulltext(report.id);
      if (fulltext) {
        setState({ fulltext_status: fulltext.status, fulltext_error: fulltext.error_code, fulltext_chars: fulltext.chars });
      }
    } catch {
      // The next look tries again; the card stays as it is.
    }
  }, [report.id]);

  useEffect(() => {
    if (!pending) return;
    const timer = window.setInterval(() => void look(), CARD_POLL_MS);
    return () => window.clearInterval(timer);
  }, [pending, look]);

  return (
    <MemberFullText
      member={{ ...report, ...state }}
      onRequested={() => setState((s) => ({ ...s, fulltext_status: "pending", fulltext_error: null }))}
    />
  );
}

/**
 * Full-text state of one report in a story, with the action that fits it:
 * fetch, wait, retry after a failure, or open the reader.
 */
export function MemberFullText({ member: m, onRequested }: { member: Reportish; onRequested: () => void }) {
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

const EMPTY_FULLTEXT: FullText = {
  article_id: 0, status: "pending", reason: "user", attempts: 0, method: null, text: null, chars: null,
  error_code: null, fetched_at: null, translate_status: null, translations: {},
};

/** "original", or a language code of the user's AI languages. */
type Tab = string;

export const TRANSLATION_POLL_MS = 3000;

/**
 * Reading window: the extracted text, and on request its translations into the user's AI languages.
 * Opened for a report whose text is not there yet (clicking a headline), it asks for it, shows the summary
 * meanwhile and looks again until the text has arrived or the site refused.
 */
export function FullTextReader({
  member: m,
  onClose,
  summary,
}: {
  member: Reportish;
  onClose: () => void;
  /** Shown while the full text is on its way or could not be read. */
  summary?: string;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status, settings } = useAppState();
  const [ft, setFt] = useState<FullText | null>(null);
  const [error, setError] = useState<string | null>(null);
  const targets = aiLanguages(settings).filter((l) => l !== m.language);
  const [tab, setTab] = useState<Tab>(targets.includes(i18n.lang) ? i18n.lang : "original");
  // A text without a translation in the interface language opens on the original: the text itself, not "not
  // translated yet" (translating stays one click away).
  const firstText = useRef(true);
  useEffect(() => {
    if (!firstText.current || ft?.status !== "done") return;
    firstText.current = false;
    if (tab !== "original" && !ft.translations[tab]) setTab("original");
  }, [ft, tab]);

  const [loaded, setLoaded] = useState(false);
  const fetchText = useCallback(async () => {
    try {
      await api.requestFulltext(m.id);
      setFt((f) => ({ ...(f ?? EMPTY_FULLTEXT), article_id: m.id, status: "pending", error_code: null }));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, [m.id]);

  const load = useCallback(async () => {
    try {
      const r = await api.fulltext(m.id);
      setFt(r.fulltext);
      setError(null);
      return r.fulltext;
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
      return undefined;
    } finally {
      setLoaded(true);
    }
  }, [m.id]);

  // Opening a report that was never asked for is the request itself.
  useEffect(() => {
    void load().then((got) => {
      if (got === null) void fetchText();
    });
  }, [load, fetchText]);

  // The text is on its way: look again every few seconds.
  const waiting = ft?.status === "pending";
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => void load(), TRANSLATION_POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, load]);

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

  const summaryBlock = summary ? <p className="reader-summary" dir={textDirection(m.language)}>{summary}</p> : null;
  let body: React.ReactNode;
  if (error) {
    body = <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)} />;
  } else if (!loaded || !ft) {
    body = <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>;
  } else if (ft.status !== "done") {
    body = (
      <>
        <div className="article-meta">
          <span className="article-source">{m.source_name}</span>
          <time dateTime={m.sort_at}>{i18n.dateTime(m.sort_at)}</time>
        </div>
        <h3 className="story-headline" dir={textDirection(m.language)}>{m.title}</h3>
        {summaryBlock}
        {ft.status === "pending" ? (
          <p className="fulltext-note" role="status">
            <Spinner />
            {t("fulltext.fetching")}
          </p>
        ) : (
          <StateView
            icon="alert"
            title={t(ft.status === "blocked" ? "fulltext.blocked" : "fulltext.failed", {
              reason: t(fulltextErrorKey(ft.error_code ?? "")),
            })}
            body={t("fulltext.goToSourceHint")}
            action={<button className="btn" onClick={() => void fetchText()}>{t("fulltext.retry")}</button>}
          />
        )}
      </>
    );
  } else {
    const translated = tab === "original" ? null : ft.translations[tab];
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
                ...targets.map((l) => ({ value: l, label: i18n.languageName(l) })),
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
            {t("feed.goToSource")}
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
