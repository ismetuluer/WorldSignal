import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { CatalogGroup, Source } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { SearchField, Segmented, Spinner, StateView, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { AddSourceDialog } from "./AddSourceDialog";
import { SourceEditor } from "./SourceEditor";

type View = "all" | "errors" | "disabled";

const GROUP_ORDER: CatalogGroup[] = ["turkey", "agency", "western", "europe", "middle_east", "russia_ukraine", "asia", "other", "sports"];

export function SourcesPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status, refreshStatus } = useAppState();
  const [sources, setSources] = useState<Source[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [view, setView] = useState<View>("all");
  const [editingId, setEditingId] = useState<number | null>(null);
  const [adding, setAdding] = useState(false);

  const reload = useCallback(async () => {
    try {
      setSources(await api.sources());
      setError(null);
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, []);

  // Refresh the list whenever a background fetch finishes or is running.
  useEffect(() => {
    void reload();
  }, [reload, status?.collector.last_cycle_at, status?.collector.busy]);

  const replace = (updated: Source) =>
    setSources((list) => list?.map((s) => (s.id === updated.id ? updated : s)) ?? list);

  const toggle = async (source: Source, enabled: boolean) => {
    replace({ ...source, enabled, status: enabled ? "pending" : "disabled" });
    try {
      replace(await api.updateSource(source.id, { enabled }));
      toast.show(t(enabled ? "sources.enabledToast" : "sources.disabledToast", { name: source.name }), "success");
      if (enabled) refreshStatus();
    } catch (e) {
      replace(source);
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    }
  };

  const fetchAll = async () => {
    try {
      const r = await api.runCollector();
      toast.show(i18n.plural("status.scheduled", r.scheduled), "success");
      refreshStatus();
    } catch (e) {
      toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");
    }
  };

  const { verifiedGroups, unverified, counts, visibleCount } = useMemo(() => {
    const all = sources ?? [];
    const q = search.trim().toLocaleLowerCase(i18n.locale);
    const matches = (s: Source) =>
      (!q || s.name.toLocaleLowerCase(i18n.locale).includes(q) || (s.owner ?? "").toLocaleLowerCase(i18n.locale).includes(q)) &&
      (view === "all" || (view === "errors" ? s.status === "error" || s.status === "partial" : !s.enabled));
    const visible = all.filter(matches);
    const groups = GROUP_ORDER.map((g) => ({
      group: g,
      items: visible.filter((s) => s.catalog_group === g && (s.verified || s.origin === "user")),
    })).filter((g) => g.items.length > 0);
    return {
      verifiedGroups: groups,
      unverified: visible.filter((s) => !s.verified && s.origin === "catalog"),
      visibleCount: visible.length,
      counts: {
        enabled: all.filter((s) => s.enabled).length,
        errors: all.filter((s) => s.enabled && (s.status === "error" || s.status === "partial")).length,
        unverified: all.filter((s) => !s.verified).length,
      },
    };
  }, [sources, search, view, i18n.locale]);

  const editing = sources?.find((s) => s.id === editingId) ?? null;

  let content: React.ReactNode;
  if (sources === null && error) {
    content = (
      <StateView
        icon="alert"
        title={t("error.title")}
        body={describeError(i18n, error)}
        action={<button className="btn" onClick={() => void reload()}>{t("common.retry")}</button>}
      />
    );
  } else if (sources === null) {
    content = (
      <div className="state">
        <Spinner label={t("common.loading")} />
      </div>
    );
  } else if (visibleCount === 0) {
    content = (
      <StateView
        icon={view === "errors" ? "check" : "search"}
        title={t(search ? "sources.empty.search" : view === "errors" ? "sources.empty.errors" : "sources.empty.disabled")}
      />
    );
  } else {
    content = (
      <>
        {verifiedGroups.map(({ group, items }) => (
          <section key={group} className="section">
            <h2 className="section-title">
              {t(`group.${group}`)} <span className="count">{items.length}</span>
            </h2>
            <div className="group-card">
              {items.map((s) => (
                <SourceRow key={s.id} source={s} onToggle={toggle} onOpen={() => setEditingId(s.id)} />
              ))}
            </div>
          </section>
        ))}
        {unverified.length > 0 ? (
          <section className="section">
            <h2 className="section-title">
              {t("sources.unverified.title")} <span className="count">{unverified.length}</span>
            </h2>
            <p className="section-note">{t("sources.unverified.body")}</p>
            <div className="group-card">
              {unverified.map((s) => (
                <SourceRow key={s.id} source={s} onToggle={toggle} onOpen={() => setEditingId(s.id)} />
              ))}
            </div>
          </section>
        ) : null}
      </>
    );
  }

  return (
    <div className="page page-wide">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("sources.title")}</h1>
          <p className="page-subtitle">{sources ? t("sources.summary", counts) : t("common.loading")}</p>
        </div>
        <div className="header-actions">
          <button className="btn" onClick={() => void fetchAll()} disabled={status?.collector.busy}>
            {status?.collector.busy ? <Spinner /> : <Icon name="refresh" size={16} />}
            {status?.collector.busy ? t("status.fetching") : t("sources.fetchAll")}
          </button>
          <button className="btn btn-primary" onClick={() => setAdding(true)}>
            <Icon name="plus" size={16} />
            {t("sources.add")}
          </button>
        </div>
      </header>

      <div className="toolbar">
        <SearchField value={search} onChange={setSearch} placeholder={t("sources.searchPlaceholder")} />
        <Segmented
          label={t("sources.title")}
          value={view}
          onChange={setView}
          options={[
            { value: "all", label: t("sources.view.all") },
            { value: "errors", label: `${t("sources.view.errors")}${counts.errors ? ` (${counts.errors})` : ""}` },
            { value: "disabled", label: t("sources.view.disabled") },
          ]}
        />
      </div>

      {content}

      {editing ? (
        <SourceEditor
          source={editing}
          onClose={() => setEditingId(null)}
          onChanged={replace}
          onDeleted={(id) => {
            setEditingId(null);
            setSources((list) => list?.filter((s) => s.id !== id) ?? list);
          }}
        />
      ) : null}
      {adding ? (
        <AddSourceDialog
          onClose={() => setAdding(false)}
          onAdded={(s) => {
            setAdding(false);
            setSources((list) => (list ? [...list, s] : [s]));
            refreshStatus();
          }}
        />
      ) : null}
    </div>
  );
}

function SourceRow({
  source: s,
  onToggle,
  onOpen,
}: {
  source: Source;
  onToggle: (s: Source, enabled: boolean) => void;
  onOpen: () => void;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const failing = s.feeds.find((f) => f.enabled && f.last_status === "error");
  return (
    <div
      className="source-row"
      role="button"
      tabIndex={0}
      aria-label={t("sources.edit", { name: s.name })}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
    >
      <span className="status-dot" data-status={s.status} title={t(`sources.status.${s.status}`)} />
      <div style={{ minWidth: 0 }}>
        <div className="source-name">
          <span>{s.name}</span>
          {s.paywalled ? (
            <span className="badge badge-warning" title={t("sources.badge.paywalled")}>
              <Icon name="lock" size={11} strokeWidth={2.2} />
            </span>
          ) : null}
          {!s.verified ? <span className="badge badge-danger">{t("sources.badge.unverified")}</span> : null}
          {s.origin === "user" ? <span className="badge badge-accent">{t("sources.badge.user")}</span> : null}
        </div>
        <div className="source-sub">
          {t(`region.${s.region}`)} · {i18n.languageName(s.language)}
          {s.owner && s.owner !== s.name ? ` · ${s.owner}` : ""}
          {failing ? (
            <>
              {" · "}
              <span className="err">{describeError(i18n, failing.last_error_code)}</span>
            </>
          ) : null}
        </div>
      </div>
      <div className="source-stats">
        {s.enabled ? <div>{t("sources.articles24h", { count: s.articles_24h })}</div> : null}
        <div>
          {s.last_success_at ? t("sources.lastSuccess", { time: i18n.relative(s.last_success_at) }) : t("sources.neverSucceeded")}
        </div>
      </div>
      <Switch checked={s.enabled} onChange={(v) => onToggle(s, v)} label={t("sources.toggle", { name: s.name })} />
    </div>
  );
}
