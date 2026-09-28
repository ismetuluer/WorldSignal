import { useMemo, useRef, useState, type ReactNode } from "react";
import { createI18n, describeError, useI18n, type I18n } from "../i18n";
import type { AiLang } from "../lib/aiText";
import { api, ApiError } from "../api/client";
import { printDocument, type OutputDoc } from "../lib/outputs";
import { Dialog, Segmented, Spinner, StateView } from "./controls";
import { Icon } from "./Icon";
import { useToast } from "./Toasts";

/** Formatted (HTML + plain text fallback) copy. Falls back to a selection copy where the async API is refused. */
export async function copyRich(html: string, text: string): Promise<void> {
  try {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([text], { type: "text/plain" }),
      }),
    ]);
    return;
  } catch {
    // Older WebView2 or no permission: copy a rendered selection instead.
  }
  const holder = document.createElement("div");
  holder.contentEditable = "true";
  holder.style.cssText = "position:fixed;left:-10000px;top:0;opacity:0;";
  holder.innerHTML = html;
  document.body.appendChild(holder);
  const range = document.createRange();
  range.selectNodeContents(holder);
  const sel = window.getSelection();
  sel?.removeAllRanges();
  sel?.addRange(range);
  const ok = document.execCommand("copy");
  sel?.removeAllRanges();
  holder.remove();
  if (!ok) throw new Error("copy_failed");
}

export async function copyText(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch {
    // fall through
  }
  const area = document.createElement("textarea");
  area.value = text;
  area.style.cssText = "position:fixed;left:-10000px;top:0;opacity:0;";
  document.body.appendChild(area);
  area.select();
  const ok = document.execCommand("copy");
  area.remove();
  if (!ok) throw new Error("copy_failed");
}

/**
 * Preview of an output with copy (formatted / plain) and print. Printing uses the system print
 * dialog, which also offers "Save as PDF". The output can be made in Turkish or English (default:
 * the interface language). ``build`` null = still loading; ``error`` = a load error.
 */
export function OutputDialog({
  build,
  error,
  empty,
  options,
  onClose,
}: {
  /** Makes the output in the chosen language, with labels from that language's dictionary. */
  build: ((lang: AiLang, i18n: I18n) => OutputDoc) | null;
  error?: string | null;
  /** Nothing to show (e.g. no stories in the range). */
  empty?: boolean;
  /** Template options shown above the preview (bulletin range, …). */
  options?: ReactNode;
  onClose: () => void;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const frame = useRef<HTMLIFrameElement>(null);
  const [busy, setBusy] = useState(false);
  const [lang, setLang] = useState<AiLang>(i18n.lang);
  const outI18n = useMemo(() => (lang === i18n.lang ? i18n : createI18n(lang, undefined, i18n.home)), [lang, i18n]);
  const doc = useMemo(() => (build && !error && !empty ? build(lang, outI18n) : null), [build, error, empty, lang, outI18n]);

  const page = doc ? printDocument(doc, outI18n.t("output.generated", { date: outI18n.dateTime(new Date().toISOString()) }), lang) : "";

  const run = async (action: () => Promise<void>) => {
    setBusy(true);
    try {
      await action();
      toast.show(t("output.copied"), "success");
    } catch {
      toast.show(t("output.copyFailed"), "error");
    } finally {
      setBusy(false);
    }
  };

  // A draft in the user's mail program (Outlook: formatted; otherwise the default program: plain text).
  // The formatted output goes to the clipboard first, so a long text cut by the mail link can be pasted.
  const mail = async () => {
    if (!doc) return;
    setBusy(true);
    try {
      await copyRich(doc.html, doc.text).catch(() => undefined);
      const r = await api.mailDraft({
        subject: `${doc.title} · ${outI18n.dateTime(new Date().toISOString())}`,
        html: doc.html,
        text: doc.text,
        cut_note: outI18n.t("output.mailCutNote"),
      });
      toast.show(t(r.method === "outlook" ? "output.mailOutlook" : r.cut ? "output.mailDefaultCut" : "output.mailDefault"), "success");
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    } finally {
      setBusy(false);
    }
  };

  const print = () => {
    const win = frame.current?.contentWindow;
    if (!win) return;
    win.focus();
    win.print();
  };

  const ready = !!doc;
  return (
    <Dialog
      wide
      title={doc?.title ?? t("output.open")}
      onClose={onClose}
      footer={
        <>
          <button className="btn btn-sm" disabled={!ready || busy} onClick={() => void run(() => copyRich(doc!.html, doc!.text))} title={t("output.copyRichHint")}>
            <Icon name="copy" size={15} />
            {t("output.copyRich")}
          </button>
          <button className="btn btn-sm" disabled={!ready || busy} onClick={() => void run(() => copyText(doc!.text))} title={t("output.copyTextHint")}>
            {t("output.copyText")}
          </button>
          <button className="btn btn-sm" disabled={!ready || busy} onClick={() => void mail()} title={t("output.mailHint")}>
            <Icon name="mail" size={15} />
            {t("output.mail")}
          </button>
          <span className="spacer" />
          <button className="btn btn-primary btn-sm" disabled={!ready} onClick={print} title={t("output.printHint")}>
            <Icon name="print" size={15} />
            {t("output.print")}
          </button>
        </>
      }
    >
      <div className="output-options">
        <Segmented
          label={t("output.language")}
          value={lang}
          onChange={setLang}
          options={[
            { value: "tr" as const, label: "Türkçe" },
            { value: "en" as const, label: "English" },
          ]}
        />
        {options}
      </div>
      {error ? (
        <StateView icon="alert" title={t("error.title")} body={error} />
      ) : empty ? (
        <StateView icon="inbox" title={t("output.empty")} />
      ) : !doc ? (
        <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>
      ) : (
        <iframe ref={frame} className="output-preview" title={t("output.preview")} srcDoc={page} sandbox="allow-same-origin allow-modals allow-popups allow-popups-to-escape-sandbox" />
      )}
      <p className="field-hint">{t("output.copyrightNote")} {t("output.printHint")}</p>
    </Dialog>
  );
}
