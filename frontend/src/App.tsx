import { useCallback, useEffect, useState } from "react";
import { api, ApiError } from "./api/client";
import type { Meta, Settings } from "./api/types";
import { Icon, type IconName } from "./components/Icon";
import { ToastProvider, useToast } from "./components/Toasts";
import { Spinner, StateView } from "./components/controls";
import { I18nProvider, describeError, useI18n, type MessageKey } from "./i18n";
import { MeetingProvider } from "./components/meeting";
import { StoryDetail } from "./components/StoryDetail";
import { UpdateBanner } from "./components/Update";
import { FeedPage } from "./pages/FeedPage";
import { HistoryPage } from "./pages/HistoryPage";
import { MeetingPage } from "./pages/MeetingPage";
import { NotebookPage } from "./pages/NotebookPage";
import { SettingsPage } from "./pages/SettingsPage";
import { SourcesPage } from "./pages/SourcesPage";
import { StatsPage } from "./pages/StatsPage";
import { navigate, useLinkedStory, useRoute, type Route } from "./router";
import { AppStateProvider, useAppState } from "./state";

const NAV: { route: Route; icon: IconName; label: MessageKey }[] = [
  { route: "feed", icon: "feed", label: "nav.feed" },
  { route: "meeting", icon: "meeting", label: "nav.meeting" },
  { route: "notebook", icon: "notebook", label: "nav.notebook" },
  { route: "history", icon: "history", label: "nav.history" },
  { route: "stats", icon: "chart", label: "nav.stats" },
  { route: "sources", icon: "sources", label: "nav.sources" },
  { route: "settings", icon: "settings", label: "nav.settings" },
];

/** Loads settings + meta, then renders the app in the chosen language. */
export function App({ hasToken }: { hasToken: boolean }) {
  const [boot, setBoot] = useState<{ settings: Settings; meta: Meta } | null>(null);
  const [error, setError] = useState<string | null>(hasToken ? null : "no_token");

  const start = useCallback(async () => {
    setError(null);
    try {
      const [settings, meta] = await Promise.all([api.settings(), api.meta()]);
      setBoot({ settings, meta });
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, []);

  useEffect(() => {
    if (hasToken) void start();
  }, [hasToken, start]);

  if (!boot) {
    return (
      <I18nProvider lang="tr">
        <BootScreen error={error} onRetry={hasToken ? () => void start() : undefined} />
      </I18nProvider>
    );
  }
  return (
    <AppStateProvider initialSettings={boot.settings} initialMeta={boot.meta}>
      <LocalizedShell />
    </AppStateProvider>
  );
}

function BootScreen({ error, onRetry }: { error: string | null; onRetry?: () => void }) {
  const i18n = useI18n();
  if (!error) {
    return (
      <div className="state" style={{ height: "100%", justifyContent: "center" }}>
        <Spinner label={i18n.t("common.loading")} />
      </div>
    );
  }
  return (
    <div style={{ height: "100%", display: "grid", placeItems: "center" }}>
      <StateView
        icon="alert"
        title={i18n.t("error.title")}
        body={describeError(i18n, error)}
        action={onRetry ? <button className="btn" onClick={onRetry}>{i18n.t("common.retry")}</button> : undefined}
      />
    </div>
  );
}

function LocalizedShell() {
  const { settings, meta } = useAppState();
  return (
    <I18nProvider lang={settings["ui.language"]} home={settings["home.country"] || meta.system_country}>
      <ToastProvider>
        <MeetingProvider>
          <Shell />
        </MeetingProvider>
      </ToastProvider>
    </I18nProvider>
  );
}

function Shell() {
  const route = useRoute();
  const { t } = useI18n();
  const { connectionError } = useAppState();
  const [linkedStory, clearLinkedStory] = useLinkedStory();

  useEffect(() => {
    document.title = `${t(`nav.${route}`)} · ${t("app.name")}`;
  }, [route, t]);

  return (
    <div className="shell">
      <nav className="sidebar" aria-label={t("nav.label")}>
        <div className="brand">
          <span className="brand-mark">
            <Icon name="signal" size={17} strokeWidth={2.4} />
          </span>
          <span>{t("app.name")}</span>
        </div>
        {NAV.map((item) => (
          <button
            key={item.route}
            className="nav-item"
            aria-current={route === item.route ? "page" : undefined}
            title={t(item.label)}
            onClick={() => navigate(item.route)}
          >
            <Icon name={item.icon} />
            <span>{t(item.label)}</span>
          </button>
        ))}
        <CollectorFooter />
      </nav>
      <main className="main">
        {connectionError ? <ConnectionLost code={connectionError} /> : null}
        <UpdateBanner />
        {route === "feed" ? <FeedPage />
          : route === "meeting" ? <MeetingPage />
          : route === "notebook" ? <NotebookPage />
          : route === "history" ? <HistoryPage />
          : route === "stats" ? <StatsPage />
          : route === "sources" ? <SourcesPage />
          : <SettingsPage />}
      </main>
      {linkedStory !== null ? (
        <StoryDetail key={linkedStory} storyId={linkedStory} onClose={clearLinkedStory} onChanged={() => undefined} />
      ) : null}
    </div>
  );
}

function ConnectionLost({ code }: { code: string }) {
  const i18n = useI18n();
  return (
    <div className="page" style={{ paddingBottom: 0 }}>
      <div className="banner banner-error" role="alert">
        <Icon name="alert" />
        <div>
          <p className="banner-title">{i18n.t("error.title")}</p>
          <p className="banner-body">{describeError(i18n, code)}</p>
        </div>
      </div>
    </div>
  );
}

export function CollectorFooter() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status, refreshStatus } = useAppState();
  const c = status?.collector;

  const fetchNow = async () => {
    try {
      const r = await api.runCollector();
      toast.show(i18n.plural("status.scheduled", r.scheduled), "success");
      refreshStatus();
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    }
  };

  let line: React.ReactNode;
  if (!c) line = null;
  else if (c.offline)
    line = (
      <>
        <Icon name="offline" size={14} />
        <span className="collector-text">{t("status.offline.title")}</span>
      </>
    );
  else if (c.busy)
    line = (
      <>
        <Spinner />
        <span className="collector-text">{t("status.fetching")}</span>
      </>
    );
  else
    line = (
      <span className="collector-text" title={c.last_cycle_at ? i18n.dateTime(c.last_cycle_at) : undefined}>
        {c.last_cycle_at ? t("status.lastCycle", { time: i18n.relative(c.last_cycle_at) }) : t("status.notYet")}
      </span>
    );

  return (
    <div className="sidebar-footer">
      <div className="collector-line" aria-live="polite">{line}</div>
      {status?.ai ? <AiLine /> : null}
      {status?.extension?.active && status.extension.warn ? (
        <button type="button" className="collector-line link-btn" title={t("extension.notConnected")} onClick={() => navigate("settings")}>
          <Icon name="alert" size={14} />
          <span className="collector-text">{t("extension.sidebarWarning")}</span>
        </button>
      ) : null}
      {c && !c.busy && c.last_cycle_errors > 0 ? (
        <span className="collector-text">{i18n.plural("status.cycleErrors", c.last_cycle_errors)}</span>
      ) : null}
      <button
        className="btn btn-sm"
        onClick={() => void fetchNow()}
        disabled={!c || c.busy}
        title={t("status.fetchNow")}
        aria-label={t("status.fetchNow")}
      >
        <Icon name="refresh" size={14} />
        <span className="collector-text">{t("status.fetchNow")}</span>
      </button>
    </div>
  );
}

function AiLine() {
  const i18n = useI18n();
  const { status } = useAppState();
  const ai = status!.ai;
  const title = i18n.t(`ai.state.${ai.state}`);
  let content: React.ReactNode;
  if (ai.state === "disabled" || ai.state === "starting") {
    content = <span className="collector-text">{i18n.t("ai.sidebar.disabled")}</span>;
  } else if (ai.state === "ok" || (ai.state === "idle" && ai.pending > 0)) {
    content = (
      <>
        <Spinner />
        <span className="collector-text">{i18n.plural("ai.sidebar.working", ai.pending)}</span>
      </>
    );
  } else if (ai.state === "idle") {
    content = <span className="collector-text">{i18n.t("ai.sidebar.idle")}</span>;
  } else {
    content = (
      <>
        <Icon name="alert" size={14} />
        <span className="collector-text">{i18n.t("ai.sidebar.paused")}</span>
      </>
    );
  }
  return (
    <button type="button" className="collector-line link-btn" title={title} onClick={() => navigate("settings")}>
      {content}
    </button>
  );
}
