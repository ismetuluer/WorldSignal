import { useState } from "react";
import { api, ApiError } from "../api/client";
import type { CatalogGroup, Feed, FullTextMode, Region, Source, SourcePatch } from "../api/types";
import { Icon } from "../components/Icon";
import { useToast } from "../components/Toasts";
import { Dialog, Spinner, Switch } from "../components/controls";
import { describeError, useI18n } from "../i18n";
import { useAppState } from "../state";
import { LANGUAGE_CHOICES, isHttpUrl } from "./sourceForm";

const INTERVALS = [5, 10, 15, 30, 60, 120, 360, 1440];
const FULLTEXT_MODES: FullTextMode[] = ["off", "http", "browser"];

export function SourceEditor({
  source,
  onClose,
  onChanged,
  onDeleted,
}: {
  source: Source;
  onClose: () => void;
  onChanged: (s: Source) => void;
  onDeleted: (id: number) => void;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { meta, refreshStatus } = useAppState();

  const [draft, setDraft] = useState({
    name: source.name,
    homepage: source.homepage ?? "",
    catalog_group: source.catalog_group,
    owner: source.owner ?? "",
    region: source.region,
    language: source.language,
    reliability: source.reliability,
    paywalled: source.paywalled,
    fulltext_mode: source.fulltext_mode,
  });
  const [saving, setSaving] = useState(false);
  const [newFeedUrl, setNewFeedUrl] = useState("");
  const [newFeedLabel, setNewFeedLabel] = useState("");
  const [addingFeed, setAddingFeed] = useState(false);

  const fail = (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");

  const changes: SourcePatch = {};
  if (draft.name.trim() !== source.name) changes.name = draft.name.trim();
  if ((draft.homepage.trim() || null) !== source.homepage) changes.homepage = draft.homepage.trim() || null;
  if (draft.catalog_group !== source.catalog_group) changes.catalog_group = draft.catalog_group;
  if ((draft.owner.trim() || null) !== source.owner) changes.owner = draft.owner.trim() || null;
  if (draft.region !== source.region) changes.region = draft.region;
  if (draft.language !== source.language) changes.language = draft.language;
  if (draft.reliability !== source.reliability) changes.reliability = draft.reliability;
  if (draft.paywalled !== source.paywalled) changes.paywalled = draft.paywalled;
  if (draft.fulltext_mode !== source.fulltext_mode) changes.fulltext_mode = draft.fulltext_mode;
  const dirty = Object.keys(changes).length > 0;
  const nameInvalid = draft.name.trim() === "";
  const homepageInvalid = draft.homepage.trim() !== "" && !isHttpUrl(draft.homepage.trim());

  const save = async () => {
    setSaving(true);
    try {
      onChanged(await api.updateSource(source.id, changes));
      toast.show(t("common.saved"), "success");
      onClose();
    } catch (e) {
      fail(e);
    } finally {
      setSaving(false);
    }
  };

  const close = () => {
    if (dirty && !window.confirm(`${t("editor.unsaved")}\n\n${t("common.close")}?`)) return;
    onClose();
  };

  const run = async (fn: () => Promise<Source | void>) => {
    try {
      const result = await fn();
      if (result) onChanged(result);
    } catch (e) {
      fail(e);
    }
  };

  const deleteSource = async () => {
    const message = [
      t("editor.deleteConfirm", { name: source.name }),
      source.origin === "catalog" ? t("editor.deleteConfirmCatalog") : "",
    ].filter(Boolean).join("\n\n");
    if (!window.confirm(message)) return;
    try {
      await api.deleteSource(source.id);
      toast.show(t("editor.deleted", { name: source.name }), "success");
      onDeleted(source.id);
    } catch (e) {
      fail(e);
    }
  };

  const addFeed = async () => {
    setAddingFeed(true);
    try {
      const test = await api.testFeed(newFeedUrl.trim());
      if (!test.ok) {
        toast.show(t("add.failed", { reason: describeError(i18n, test.error_code) }), "error");
        return;
      }
      onChanged(await api.addFeed(source.id, newFeedUrl.trim(), newFeedLabel.trim() || null));
      setNewFeedUrl("");
      setNewFeedLabel("");
      refreshStatus();
    } catch (e) {
      fail(e);
    } finally {
      setAddingFeed(false);
    }
  };

  return (
    <Dialog
      title={source.name}
      onClose={close}
      footer={
        <>
          <button className="btn btn-danger" onClick={() => void deleteSource()}>
            <Icon name="trash" size={15} />
            {t("editor.delete")}
          </button>
          <button
            className="btn"
            onClick={() =>
              void run(async () => {
                await api.refreshSource(source.id);
                toast.show(t("editor.refreshed"), "success");
                refreshStatus();
              })
            }
            disabled={!source.enabled}
          >
            <Icon name="refresh" size={15} />
            {t("editor.refresh")}
          </button>
          <span className="spacer" />
          <button className="btn" onClick={close}>{t("common.cancel")}</button>
          <button
            className="btn btn-primary"
            disabled={!dirty || saving || nameInvalid || homepageInvalid}
            onClick={() => void save()}
          >
            {saving ? t("common.saving") : t("common.save")}
          </button>
        </>
      }
    >
      <div className="inline-row">
        <span className="field-label">{t("editor.enabled")}</span>
        <Switch
          checked={source.enabled}
          label={t("sources.toggle", { name: source.name })}
          onChange={(enabled) => void run(() => api.updateSource(source.id, { enabled }).finally(refreshStatus))}
        />
      </div>

      {source.note ? (
        <div className="banner" style={{ margin: 0 }}>
          <Icon name="info" />
          <p className="banner-body" style={{ margin: 0 }}>{source.note}</p>
        </div>
      ) : null}

      <h3 className="subsection-title">{t("editor.general")}</h3>
      <div className="field-row">
        <label className="field">
          <span className="field-label">{t("editor.name")}</span>
          <input
            className="input"
            value={draft.name}
            maxLength={120}
            aria-invalid={nameInvalid}
            onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field-label">{t("editor.homepage")}</span>
          <input
            className="input"
            value={draft.homepage}
            placeholder="https://"
            aria-invalid={homepageInvalid}
            onChange={(e) => setDraft({ ...draft, homepage: e.target.value })}
          />
        </label>
        <label className="field">
          <span className="field-label">{t("editor.group")}</span>
          <select
            className="select"
            value={draft.catalog_group}
            onChange={(e) => setDraft({ ...draft, catalog_group: e.target.value as CatalogGroup })}
          >
            {meta.groups.map((g) => (
              <option key={g} value={g}>{t(`group.${g}`)}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t("editor.region")}</span>
          <select
            className="select"
            value={draft.region}
            onChange={(e) => setDraft({ ...draft, region: e.target.value as Region })}
          >
            {meta.regions.map((r) => (
              <option key={r} value={r}>{t(`region.${r}`)}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t("editor.language")}</span>
          <select className="select" value={draft.language} onChange={(e) => setDraft({ ...draft, language: e.target.value })}>
            {[...new Set([draft.language, ...LANGUAGE_CHOICES])].map((l) => (
              <option key={l} value={l}>{i18n.languageName(l)}</option>
            ))}
          </select>
        </label>
        <label className="field">
          <span className="field-label">{t("editor.owner")}</span>
          <input
            className="input"
            value={draft.owner}
            maxLength={120}
            onChange={(e) => setDraft({ ...draft, owner: e.target.value })}
          />
        </label>
      </div>
      <p className="field-hint" style={{ marginTop: -8 }}>{t("editor.ownerHint")}</p>

      <label className="field">
        <span className="inline-row">
          <span className="field-label">{t("editor.reliability")}</span>
          <strong>{draft.reliability.toLocaleString(i18n.locale, { minimumFractionDigits: 1 })}</strong>
        </span>
        <input
          className="range"
          type="range"
          min={0}
          max={2}
          step={0.1}
          value={draft.reliability}
          onChange={(e) => setDraft({ ...draft, reliability: Math.round(Number(e.target.value) * 10) / 10 })}
        />
        <span className="field-hint">{t("editor.reliabilityHint")}</span>
      </label>

      <div className="inline-row">
        <span className="field-label">{t("editor.paywalled")}</span>
        <Switch
          checked={draft.paywalled}
          label={t("editor.paywalled")}
          onChange={(paywalled) => setDraft({ ...draft, paywalled })}
        />
      </div>

      <label className="field">
        <span className="field-label">{t("editor.fulltext")}</span>
        <select
          className="select"
          aria-label={t("editor.fulltext")}
          value={draft.fulltext_mode}
          onChange={(e) => setDraft({ ...draft, fulltext_mode: e.target.value as FullTextMode })}
        >
          {FULLTEXT_MODES.map((mode) => (
            <option key={mode} value={mode}>{t(`editor.fulltext.${mode}`)}</option>
          ))}
        </select>
        <span className="field-hint">{t(`editor.fulltext.${draft.fulltext_mode}Hint`)}</span>
        {source.fulltext_paused_until && new Date(source.fulltext_paused_until) > new Date() ? (
          <span className="field-hint warn" role="status">
            {t("editor.fulltext.paused", { time: i18n.dateTime(source.fulltext_paused_until) })}
          </span>
        ) : null}
      </label>

      <h3 className="subsection-title">{t("editor.feeds")}</h3>
      {source.feeds.map((f) => (
        <FeedItem
          key={f.id}
          feed={f}
          onPatch={(patch) => void run(() => api.updateFeed(f.id, patch))}
          onDelete={() => {
            if (!window.confirm(t("editor.feed.deleteConfirm"))) return;
            void run(async () => {
              await api.deleteFeed(f.id);
              onChanged({ ...source, feeds: source.feeds.filter((x) => x.id !== f.id) });
            });
          }}
        />
      ))}
      <div className="feed-item">
        <div className="field-row">
          <input
            className="input"
            value={newFeedUrl}
            placeholder="https://…/rss"
            aria-label={t("add.url")}
            onChange={(e) => setNewFeedUrl(e.target.value)}
          />
          <input
            className="input"
            value={newFeedLabel}
            maxLength={80}
            placeholder={`${t("editor.feed.label")} (${t("common.optional")})`}
            aria-label={t("editor.feed.label")}
            onChange={(e) => setNewFeedLabel(e.target.value)}
          />
        </div>
        <div>
          <button className="btn btn-sm" disabled={!isHttpUrl(newFeedUrl.trim()) || addingFeed} onClick={() => void addFeed()}>
            {addingFeed ? <Spinner /> : <Icon name="plus" size={14} />}
            {addingFeed ? t("add.testing") : t("editor.feed.add")}
          </button>
        </div>
      </div>
    </Dialog>
  );
}

function FeedItem({
  feed: f,
  onPatch,
  onDelete,
}: {
  feed: Feed;
  onPatch: (patch: { enabled?: boolean; fetch_interval_min?: number }) => void;
  onDelete: () => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const statusClass =
    !f.enabled ? "" : f.last_status === "error" ? "badge-danger" : f.last_status === "pending" ? "badge-accent" : "badge-success";
  return (
    <div className="feed-item">
      <div className="inline-row">
        <div style={{ minWidth: 0 }}>
          <strong>{f.label || "RSS"}</strong>{" "}
          <span className={`badge ${statusClass}`}>
            {f.enabled ? t(`editor.feed.status.${f.last_status}`) : t("sources.status.disabled")}
          </span>
          <div className="feed-url">{f.url}</div>
        </div>
        <Switch checked={f.enabled} label={t("editor.feed.enabled")} onChange={(enabled) => onPatch({ enabled })} />
      </div>
      {f.last_status === "error" && f.enabled ? (
        <div className="source-sub" style={{ whiteSpace: "normal" }}>
          <span className="err">{describeError(i18n, f.last_error_code)}</span>
          {f.consecutive_failures > 0 ? ` · ${plural("editor.feed.failures", f.consecutive_failures)}` : ""}
        </div>
      ) : null}
      <div className="feed-meta">
        {f.last_item_count !== null ? <span>{plural("editor.feed.items", f.last_item_count)}</span> : null}
        {f.last_attempt_at ? <span>{t("editor.feed.lastAttempt", { time: i18n.relative(f.last_attempt_at) })}</span> : null}
        {f.enabled && f.next_fetch_at ? <span>{t("editor.feed.nextFetch", { time: i18n.relative(f.next_fetch_at) })}</span> : null}
        <label style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
          {t("editor.feed.interval")}
          <select
            className="select"
            style={{ width: "auto", height: 28 }}
            value={f.fetch_interval_min}
            onChange={(e) => onPatch({ fetch_interval_min: Number(e.target.value) })}
          >
            {[...new Set([f.fetch_interval_min, ...INTERVALS])].sort((a, b) => a - b).map((n) => (
              <option key={n} value={n}>{t("editor.feed.minutes", { n })}</option>
            ))}
          </select>
        </label>
        <button className="btn btn-ghost btn-sm btn-danger" onClick={onDelete} style={{ marginLeft: "auto" }}>
          <Icon name="trash" size={14} />
          {t("editor.feed.delete")}
        </button>
      </div>
    </div>
  );
}
