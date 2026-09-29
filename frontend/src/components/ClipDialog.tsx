import { useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { ClipResult } from "../api/types";
import { describeError, useI18n } from "../i18n";
import { Dialog, Spinner } from "./controls";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";

/**
 * The code of the bookmark that copies the open page (its HTML, address and title) to the clipboard.
 * clip.py reads the article text from it, as for a page it downloaded itself. ``done`` / ``failed`` are the texts
 * the page shows in an alert.
 */
export function bookmarkletCode(done: string, failed: string): string {
  return (
    "(function(){try{" +
    "var m=function(p){var e=document.querySelector('meta[property=\"'+p+'\"]');return e&&e.content};" +
    "var d=JSON.stringify({ws:1,url:location.href,title:m('og:title')||document.title," +
    "lang:document.documentElement.lang||'',html:document.documentElement.outerHTML});" +
    `var ok=function(){alert(${JSON.stringify(done)})};` +
    "var fb=function(){var a=document.createElement('textarea');a.value=d;a.style.cssText='position:fixed;opacity:0';" +
    "document.body.appendChild(a);a.select();var r=false;try{r=document.execCommand('copy')}catch(e){}a.remove();" +
    `r?ok():alert(${JSON.stringify(failed)})};` +
    "if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(d).then(ok,fb)}else{fb()}" +
    `}catch(e){alert(${JSON.stringify(failed)}+' '+e)}})();`
  );
}

/**
 * "Send a page": for sites that refuse programs (The Economist, WSJ ...). The user reads the article in their own
 * browser, clicks the bookmark, and pastes here; nothing is fetched from the site.
 */
export function ClipDialog({ onClose, onAdded }: { onClose: () => void; onAdded?: () => void }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<ClipResult | null>(null);
  const linkRef = useRef<HTMLAnchorElement>(null);
  const code = useMemo(() => bookmarkletCode(t("clip.bookmark.done"), t("clip.bookmark.failed")), [t]);

  // A "javascript:" address is set on the element itself: the framework does not write such an address.
  useEffect(() => {
    linkRef.current?.setAttribute("href", `javascript:${encodeURIComponent(code)}`);
  }, [code]);

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(`javascript:${code}`);
      toast.show(t("clip.codeCopied"), "success");
    } catch {
      toast.show(t("clip.codeNotCopied"), "error");
    }
  };

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await api.addClip(text.trim());
      setAdded(result);
      setText("");
      onAdded?.();
    } catch (e) {
      setError(describeError(i18n, e instanceof ApiError ? e.code : "generic"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog
      wide
      title={t("clip.title")}
      onClose={onClose}
      footer={
        <>
          <span className="spacer" />
          <button className="btn btn-sm" onClick={onClose}>{t("common.close")}</button>
        </>
      }
    >
      <p className="field-hint">{t("clip.intro")}</p>
      <ol className="clip-steps">
        <li>
          <span>{t("clip.step1")}</span>{" "}
          {/* eslint-disable-next-line jsx-a11y/anchor-is-valid */}
          <a ref={linkRef} className="btn btn-sm clip-bookmark" draggable="true" onClick={(e) => e.preventDefault()}>
            <Icon name="plus" size={14} />
            {t("clip.bookmarkName")}
          </a>{" "}
          <button type="button" className="link-btn" onClick={() => void copyCode()}>{t("clip.copyCode")}</button>
        </li>
        <li>{t("clip.step2")}</li>
        <li>{t("clip.step3")}</li>
      </ol>

      <label className="field">
        <span className="field-label">{t("clip.paste")}</span>
        <textarea
          className="textarea clip-paste"
          rows={4}
          value={text}
          placeholder={t("clip.placeholder")}
          spellCheck={false}
          onChange={(e) => {
            setText(e.target.value);
            setAdded(null);
            setError(null);
          }}
        />
      </label>
      <div className="clip-actions">
        <button className="btn btn-primary" disabled={busy || !text.trim()} onClick={() => void send()}>
          {busy ? <Spinner /> : <Icon name="download" size={15} />}
          {t("clip.add")}
        </button>
        {text ? <span className="field-hint">{t("clip.size", { kb: i18n.number(Math.round(text.length / 1024)) })}</span> : null}
      </div>

      {error ? <p className="article-warning" role="alert"><Icon name="alert" size={13} />{error}</p> : null}
      {added ? (
        <p className="clip-done" role="status">
          <Icon name="check" size={14} strokeWidth={2.2} />
          <span>
            <strong>{added.title}</strong> — {added.source} · {t("clip.added", { chars: i18n.number(added.chars) })}
            {added.created ? "" : ` · ${t("clip.updated")}`}
          </span>
        </p>
      ) : null}
      <p className="field-hint">{t("clip.privacy")}</p>
    </Dialog>
  );
}
