import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "../api/client";
import type { BrowserList, FullTextSite } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Banner, Spinner } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { fulltextErrorKey } from "../lib/fulltext";
import { useAppState } from "../state";

const POLL_MS = 4000;

/** The subscription sites on the Sources page: whether a site can be opened to sign in depends on the
 * browser found and the profile chosen in Settings → Full text. */
export function SubscriptionSitesSection() {
  const { settings } = useAppState();
  const [browsers, setBrowsers] = useState<BrowserList | null>(null);
  const browserPath = settings["fulltext.browser_path"];
  useEffect(() => {
    api.browsers().then(setBrowsers, () => setBrowsers(null));
  }, [browserPath]);
  return (
    <section className="section">
      <div className="settings-card">
        <SubscriptionSites canOpen={settings["fulltext.profile"] === "own" && !!browsers?.chosen} />
      </div>
    </section>
  );
}

/**
 * Subscription sites: open each one in World Signal's browser profile to sign in, then try it and
 * see whether its full text now arrives.
 */
export function SubscriptionSites({ canOpen }: { canOpen: boolean }) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status } = useAppState();
  const [sites, setSites] = useState<FullTextSite[] | null>(null);
  const [windowOpen, setWindowOpen] = useState(false);
  const [busy, setBusy] = useState<number | null>(null);

  const fail = useCallback(
    (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error"),
    [toast, i18n],
  );
  const load = useCallback(
    () =>
      api.fulltextSites().then((r) => {
        setSites(r.sites);
        setWindowOpen(r.login_window_open);
      }, fail),
    [fail],
  );

  useEffect(() => {
    void load();
  }, [load]);
  // Follow the queue: after "Try", and while the sign-in window is open.
  const ft = status?.fulltext;
  const tick = ft ? `${ft.done}-${ft.failed}-${ft.blocked}-${ft.state}-${ft.current_article_id}` : "";
  useEffect(() => {
    void load();
  }, [tick]);
  const waiting = windowOpen || (sites ?? []).some((s) => s.queued > 0);
  useEffect(() => {
    if (!waiting) return;
    const timer = window.setInterval(() => void load(), POLL_MS);
    return () => window.clearInterval(timer);
  }, [waiting, load]);

  const act = async <T,>(id: number, fn: () => Promise<T>, success: (result: T) => string) => {
    setBusy(id);
    try {
      toast.show(success(await fn()), "success");
      await load();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(null);
    }
  };

  const result = (s: FullTextSite) => {
    if (s.fulltext_paused_until && new Date(s.fulltext_paused_until) > new Date()) {
      return { kind: "warn", text: t("sites.paused", { time: i18n.time(s.fulltext_paused_until) }) };
    }
    if (s.queued > 0) return { kind: "", text: t("sites.queued") };
    if (!s.last) return { kind: "", text: t("sites.never") };
    const when = i18n.relative(s.last.at);
    if (s.last.status === "done") return { kind: "ok", text: t("sites.ok", { time: when }) };
    if (s.last.error_code === "paywall") return { kind: "warn", text: t("sites.paywall", { time: when }) };
    return { kind: "warn", text: t("sites.failed", { reason: t(fulltextErrorKey(s.last.error_code ?? "")), time: when }) };
  };

  return (
    <div className="settings-row settings-row-block">
      <div className="settings-row-text">
        <div className="settings-row-title">{t("sites.title")}</div>
        <ol className="settings-row-hint steps">
          <li>{canOpen ? t("sites.step1") : t("sites.step1Main")}</li>
          <li>{t("sites.step2")}</li>
          <li>{t("sites.step3")}</li>
        </ol>
      </div>
      {windowOpen ? <Banner icon="info" title={t("sites.windowOpen.title")} body={t("sites.windowOpen.body")} /> : null}
      {sites === null ? (
        <Spinner label={t("common.loading")} />
      ) : sites.length === 0 ? (
        <p className="settings-row-hint">{t("sites.none")}</p>
      ) : (
        <ul className="site-list" aria-label={t("sites.title")}>
          {sites.map((s) => {
            const r = result(s);
            return (
              <li key={s.id}>
                <span className="site-name">{s.name}</span>
                <span className={`site-result ${r.kind}`}>
                  {r.kind === "ok" ? <Icon name="check" size={13} /> : r.kind === "warn" ? <Icon name="alert" size={13} /> : null}
                  {r.text}
                </span>
                <span className="site-actions">
                  {canOpen ? (
                    <button
                      className="btn btn-sm"
                      disabled={busy !== null || !s.homepage}
                      aria-label={t("sites.openLabel", { name: s.name })}
                      onClick={() => void act(s.id, () => api.openLogin({ source_id: s.id }), () => t("sites.opened", { name: s.name }))}
                    >
                      <Icon name="external" size={14} />
                      {t("sites.open")}
                    </button>
                  ) : null}
                  <button
                    className="btn btn-sm"
                    disabled={busy !== null || s.queued > 0}
                    aria-label={t("sites.testLabel", { name: s.name })}
                    onClick={() =>
                      void act(s.id, () => api.testSite(s.id), (res) =>
                        t(res.status === "done" ? "sites.testDone" : "sites.testQueued", { name: s.name }),
                      )
                    }
                  >
                    {t("sites.test")}
                  </button>
                </span>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
