import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Story, StoryMember } from "../api/types";
import { describeError, useI18n } from "../i18n";
import { localDay, textDirection, useDebounced } from "../lib/hooks";
import { storyOutput } from "../lib/outputs";
import { useAppState } from "../state";
import { Dialog, SearchField, Spinner, StateView } from "./controls";
import { Icon } from "./Icon";
import { useMeeting } from "./meeting";
import { NoteEditor } from "./NoteEditor";
import { OutputDialog } from "./OutputDialog";
import { issueNumbers, LangToggle, ScorePill, ScoreTags, storyHeadline, storySummary } from "./StoryCard";
import { storyWhy, type AiLang } from "../lib/aiText";
import { useToast } from "./Toasts";
import { MemberFullText } from "./FullText";
import { openableUrl } from "../lib/links";

const COMPONENTS = ["sources", "freshness", "turkey", "interest"] as const;

/**
 * Everything about one story: AI summary, why the score is what it is, the day-by-day
 * timeline and every report. The user can correct the clustering here (detach / merge).
 */
export function StoryDetail({
  storyId,
  onClose,
  onChanged,
}: {
  storyId: number;
  onClose: () => void;
  /** The story list must be reloaded (a correction changed stories). */
  onChanged: () => void;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const toast = useToast();
  const { status, refreshStatus } = useAppState();
  const [story, setStory] = useState<Story | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [merging, setMerging] = useState(false);
  const [output, setOutput] = useState(false);
  const meeting = useMeeting();

  const load = useCallback(async () => {
    setError(null);
    try {
      setStory(await api.story(storyId));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, [storyId]);

  useEffect(() => {
    void load();
  }, [load]);

  const fail = (e: unknown) => toast.show(describeError(i18n, e instanceof ApiError ? e.code : "generic"), "error");

  const detach = async (m: StoryMember) => {
    setBusy(true);
    try {
      const res = await api.detachArticle(m.id);
      toast.show(t("stories.detached"), "success");
      onChanged();
      if (res.previous_story_id === null) onClose();
      else await load();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const mergeFrom = async (other: Story) => {
    setBusy(true);
    try {
      setStory(await api.mergeStories(other.id, storyId));
      setMerging(false);
      toast.show(t("stories.merged"), "success");
      onChanged();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  const resummarize = async () => {
    setBusy(true);
    try {
      await api.summarizeStory(storyId);
      setStory((s) => (s ? { ...s, ai_status: "pending" } : s));
      toast.show(t("stories.resummarizeQueued"), "success");
      refreshStatus();
    } catch (e) {
      fail(e);
    } finally {
      setBusy(false);
    }
  };

  // Refresh when the AI finished something while a summary is pending.
  const aiDone = status?.ai.done ?? 0;
  useEffect(() => {
    if (story?.ai_status === "pending") void load();
    // Only react to AI progress.
  }, [aiDone]);

  // Refresh while a report's full text is on its way (the queue counts move when one finishes).
  const ft = status?.fulltext;
  const ftTick = ft ? `${ft.done}-${ft.failed}-${ft.blocked}-${ft.current_article_id}` : "";
  useEffect(() => {
    if (story?.members.some((m) => m.fulltext_status === "pending")) void load();
    // Only react to full-text progress.
  }, [ftTick]);

  const aiAvailable = !!status && status.ai.state !== "disabled" && status.ai.state !== "no_model";

  let body: React.ReactNode;
  if (error) {
    body = (
      <StateView
        icon="alert"
        title={t("error.title")}
        body={describeError(i18n, error)}
        action={<button className="btn" onClick={() => void load()}>{t("common.retry")}</button>}
      />
    );
  } else if (!story) {
    body = <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>;
  } else if (merging) {
    body = <MergePicker current={story} busy={busy} onPick={(s) => void mergeFrom(s)} onCancel={() => setMerging(false)} />;
  } else {
    body = (
      <StoryBody
        story={story}
        busy={busy}
        onDetach={(m) => void detach(m)}
        onFulltext={() => {
          void load();
          refreshStatus();
        }}
      />
    );
  }

  return (
    <Dialog
      wide
      title={merging ? t("stories.merge.title") : t("stories.detail.title")}
      onClose={onClose}
      footer={
        story && !merging ? (
          <>
            <button className="btn btn-sm" disabled={busy} onClick={() => setMerging(true)}>
              {t("stories.merge")}
            </button>
            {aiAvailable ? (
              <button className="btn btn-sm" disabled={busy || story.ai_status === "pending"} onClick={() => void resummarize()}>
                {story.ai_status === "pending" ? t("stories.summaryPending") : t("stories.resummarize")}
              </button>
            ) : null}
            <span className="spacer" />
            <button className="btn btn-sm" onClick={() => setOutput(true)}>
              <Icon name="print" size={15} />
              {t("output.open")}
            </button>
            {meeting.available ? (
              <button className="btn btn-sm" aria-pressed={meeting.has(storyId)} onClick={() => void meeting.toggle(storyId)}>
                <Icon name={meeting.has(storyId) ? "check" : "plus"} size={15} />
                {meeting.has(storyId) ? t("meeting.inList") : t("meeting.add")}
              </button>
            ) : null}
            <button className="btn btn-primary btn-sm" onClick={onClose}>{t("common.close")}</button>
          </>
        ) : undefined
      }
    >
      {body}
      {output && story ? (
        <OutputDialog build={(l, out) => storyOutput(out, story, meeting.day ?? localDay(), l)} onClose={() => setOutput(false)} />
      ) : null}
    </Dialog>
  );
}

/** The user's own note on the story (saves itself). */
function StoryNotes({ storyId }: { storyId: number }) {
  const { t } = useI18n();
  const [initial, setInitial] = useState<string | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    api.storyNote(storyId).then(
      (r) => alive && setInitial(r.note?.body ?? ""),
      () => alive && setError(true),
    );
    return () => {
      alive = false;
    };
  }, [storyId]);
  return (
    <section>
      <h4 className="subsection-title">{t("notes.title")}</h4>
      {error ? (
        <p className="article-warning" role="alert"><Icon name="alert" size={13} />{t("notes.loadFailed")}</p>
      ) : initial === null ? (
        <Spinner label={t("common.loading")} />
      ) : (
        <NoteEditor
          key={storyId}
          initial={initial}
          draftKey={`story-note-${storyId}`}
          save={(body) => api.saveStoryNote(storyId, body)}
          label={t("notes.title")}
          placeholder={t("notes.placeholder")}
          rows={3}
        />
      )}
    </section>
  );
}

function StoryBody({
  story: s,
  busy,
  onDetach,
  onFulltext,
}: {
  story: Story;
  busy: boolean;
  onDetach: (m: StoryMember) => void;
  onFulltext: () => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const { settings } = useAppState();
  const [lang, setLang] = useState<AiLang>(i18n.lang);
  const headline = storyHeadline(s, lang);
  const summary = storySummary(s, lang);
  const why = storyWhy(s, lang);
  const numbers = s.ai_status === "done" ? issueNumbers(s.ai_issues) : "";
  const rep = s.representative;
  const components = s.score_parts.components;

  // Articles per local calendar day (the backend groups by UTC date).
  const timeline = useMemo(() => {
    const days = new Map<string, { label: string; count: number; sources: Set<string> }>();
    for (const m of [...s.members].reverse()) {
      const label = i18n.dayLabel(m.sort_at);
      const day = days.get(label) ?? { label, count: 0, sources: new Set<string>() };
      day.count += 1;
      day.sources.add(m.source_name);
      days.set(label, day);
    }
    return [...days.values()];
  }, [s.members, i18n]);
  const maxDay = Math.max(1, ...timeline.map((d) => d.count));
  const milestones = s.milestones ?? [];

  return (
    <>
      <section className="story-head">
        <div className="article-meta">
          <ScorePill score={s.score} i18n={i18n} />
          {s.category ? <span className="badge">{t(`category.${s.category}`)}</span> : null}
          <span>{plural("stories.sources", s.source_count)}</span>
          <LangToggle lang={lang} onChange={setLang} available={s.ai_status === "done" && !!s.ai_title_tr && !!s.ai_title_en} />
          <span>{plural("stories.articles", s.article_count)}</span>
        </div>
        <h3 className="story-headline" dir={headline.translated ? "ltr" : textDirection(headline.lang)}>{headline.text}</h3>
        {headline.translated && rep && rep.language !== headline.lang ? (
          <p className="article-original">
            <span>{t("ai.original")}:</span> <span dir={textDirection(rep.language)}>{rep.title}</span>
          </p>
        ) : null}
        {summary && summary !== headline.text ? <p className="story-full-summary">{summary}</p> : null}
        {why ? (
          <p className="story-why">
            <span>{t("stories.why")}:</span> {why}
          </p>
        ) : null}
        {numbers ? (
          <p className="article-warning" role="note">
            <Icon name="alert" size={13} />
            {t("stories.aiIssue", { numbers })}
          </p>
        ) : null}
        <ScoreTags story={s} i18n={i18n} />
        <p className="field-hint">
          {t("stories.detail.firstSeen", { time: i18n.dateTime(s.first_seen_at) })} ·{" "}
          {t("stories.detail.lastSeen", { time: i18n.dateTime(s.last_seen_at) })}
        </p>
      </section>

      <StoryNotes storyId={s.id} />

      {components ? (
        <section>
          <h4 className="subsection-title">{t("stories.detail.scoreBreakdown")}</h4>
          <dl className="score-breakdown">
            {COMPONENTS.map((k) => {
              const weight = settings[`score.w_${k}`];
              return (
                <div key={k} className="score-row">
                  <dt>{t(`stories.component.${k}`)}</dt>
                  <dd>
                    <span className="meter" aria-hidden="true">
                      <span style={{ width: `${Math.round(components[k] * 100)}%` }} />
                    </span>
                    <span className="score-num">
                      {Math.round(components[k] * 100)} × {Math.round(weight * 100)}%
                    </span>
                  </dd>
                </div>
              );
            })}
          </dl>
        </section>
      ) : null}

      {timeline.length > 1 || milestones.length > 1 ? (
        <section>
          <h4 className="subsection-title">{t("stories.detail.timeline")}</h4>
          {timeline.length > 1 ? (
            <ol className="timeline">
              {timeline.map((d) => (
                <li key={d.label}>
                  <span className="timeline-day">{d.label}</span>
                  <span className="meter" aria-hidden="true">
                    <span style={{ width: `${Math.round((d.count / maxDay) * 100)}%` }} />
                  </span>
                  <span className="score-num">
                    {plural("stories.articles", d.count)} · {plural("stories.sources", d.sources.size)}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
          {milestones.length > 1 ? (
            <ol className="milestones" aria-label={t("stories.milestones")}>
              {milestones.map((ms, i) => (
                <li key={i} data-kind={ms.kind}>
                  <time dateTime={ms.at}>{i18n.dateTime(ms.at)}</time>
                  <span>
                    {ms.kind === "sources"
                      ? t("stories.milestone.sources", { count: ms.count, source: ms.source })
                      : t(`stories.milestone.${ms.kind}`, { source: ms.source })}
                  </span>
                </li>
              ))}
            </ol>
          ) : null}
        </section>
      ) : null}

      <section>
        <h4 className="subsection-title">{t("stories.detail.reports")}</h4>
        <ul className="member-list">
          {s.members.map((m) => (
            <li key={m.id} className="member" dir="ltr">
              <div className="article-meta">
                <span className="article-source">{m.source_name}</span>
                <time dateTime={m.sort_at} title={i18n.dateTime(m.sort_at)}>{i18n.relative(m.sort_at)}</time>
                {m.language !== i18n.lang ? <span className="badge">{i18n.languageName(m.language)}</span> : null}
                {m.paywalled ? (
                  <span className="badge badge-warning">
                    <Icon name="lock" size={11} strokeWidth={2.2} />
                    {t("feed.paywalled")}
                  </span>
                ) : null}
                {m.assigned_by === "user" ? <span className="badge badge-accent">{t("stories.userPlaced")}</span> : null}
              </div>
              <a className="member-title" href={openableUrl(m.url, m.title)} target="_blank" rel="noopener noreferrer" title={t("feed.openOriginal")}>
                <span dir={memberTitle(m, lang) !== m.title ? "ltr" : textDirection(m.language)}>{memberTitle(m, lang)}</span>
                <Icon name="external" size={12} />
              </a>
              {memberTitle(m, lang) !== m.title && m.language !== lang ? (
                <p className="article-original">
                  <span>{t("ai.original")}:</span> <span dir={textDirection(m.language)}>{m.title}</span>
                </p>
              ) : null}
              <div className="member-actions">
                <MemberFullText member={m} onRequested={onFulltext} />
                {s.members.length > 1 ? (
                  <button type="button" className="link-btn" disabled={busy} onClick={() => onDetach(m)}>
                    {t("stories.detach")}
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      </section>
    </>
  );
}

function MergePicker({
  current,
  busy,
  onPick,
  onCancel,
}: {
  current: Story;
  busy: boolean;
  onPick: (s: Story) => void;
  onCancel: () => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 250);
  const [items, setItems] = useState<Story[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    setError(null);
    api.stories({ hours: 72, q: q || undefined, sort: q ? "score" : "recent", limit: 30 }).then(
      (page) => alive && setItems(page.items.filter((s) => s.id !== current.id)),
      (e) => alive && setError(e instanceof ApiError ? e.code : "generic"),
    );
    return () => {
      alive = false;
    };
  }, [q, current.id]);

  return (
    <>
      <p className="field-hint">{t("stories.merge.hint")}</p>
      <SearchField value={search} onChange={setSearch} placeholder={t("stories.merge.search")} />
      {error ? (
        <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)} />
      ) : items === null ? (
        <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>
      ) : items.length === 0 ? (
        <p className="field-hint">{t("stories.merge.none")}</p>
      ) : (
        <ul className="member-list">
          {items.map((s) => {
            const h = storyHeadline(s);
            return (
              <li key={s.id}>
                <button type="button" className="merge-option" disabled={busy} onClick={() => onPick(s)}>
                  <span className="article-meta">
                    <ScorePill score={s.score} i18n={i18n} />
                    <span>{plural("stories.sources", s.source_count)}</span>
                    <span>{i18n.relative(s.last_seen_at)}</span>
                  </span>
                  <span className="member-title" dir={h.translated ? "ltr" : textDirection(h.lang)}>{h.text}</span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
      <div>
        <button className="btn btn-sm" onClick={onCancel}>{t("common.cancel")}</button>
      </div>
    </>
  );
}

function memberTitle(m: StoryMember, lang: AiLang): string {
  return (lang === "en" ? m.title_en || m.title_tr : m.title_tr || m.title_en) || m.title;
}
