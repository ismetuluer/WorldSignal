import type { ScoreTag, Story } from "../api/types";
import { useState } from "react";
import { useI18n, type I18n, type MessageKey } from "../i18n";
import { aiLanguages, storyLanguages, storySummaryText, storyConflict, storyTitle, storyWhy, type AiLang, type ShownText } from "../lib/aiText";
import { useAppState } from "../state";
import { textDirection } from "../lib/hooks";
import { Icon } from "./Icon";
import { useMeeting } from "./meeting";
import { BreakingBadge, ExclusiveBadge } from "./Badges";
import { CardFullText } from "./FullText";

const MAX_SOURCE_NAMES = 4;

/** Best available headline in ``lang``: story AI title, the representative's AI title, the original. */
export function storyHeadline(s: Story, lang: AiLang = "tr"): ShownText {
  return storyTitle(s, lang);
}

export function storySummary(s: Story, lang: AiLang = "tr"): string {
  return storySummaryText(s, lang);
}

/** Steps the AI texts of one card through the languages they exist in (the user's AI languages). Shows the
 * next language's code; hidden when there is only one language. */
export function LangToggle({ current, languages, onChange }: { current: AiLang; languages: string[]; onChange: (l: AiLang) => void }) {
  const i18n = useI18n();
  if (languages.length < 2) return null;
  const next = languages[(languages.indexOf(current) + 1) % languages.length]!;
  const label = i18n.t("ai.showIn", { language: i18n.languageName(next) });
  return (
    <button
      type="button"
      className="lang-toggle"
      title={label}
      aria-label={label}
      onClick={(e) => {
        e.stopPropagation();
        onChange(next);
      }}
    >
      {next.toUpperCase()}
    </button>
  );
}

/** Numbers the fidelity check could not find in the reports ("" when none). */
export function issueNumbers(issues: string[]): string {
  return issues
    .filter((i) => i.startsWith("number_not_in_source:"))
    .map((i) => i.split(":")[1])
    .join(", ");
}

function interestLabel(i18n: I18n, match: string): string {
  const [kind, value] = match.includes(":") ? match.split(":", 2) : ["keyword", match];
  if (kind === "category") return i18n.t(`category.${value}` as MessageKey);
  if (kind === "region") return i18n.t(`region.${value}` as MessageKey);
  return match;
}

/** Human-readable explanation tags; the reasons behind the score. */
export function ScoreTags({ story: s, i18n }: { story: Story; i18n: I18n }) {
  const { t, plural } = i18n;
  const { settings } = useAppState();
  const homeOn = settings["home.enabled"] && settings["home.labels"];
  const tags: ScoreTag[] = s.score_parts.tags ?? [];
  return (
    <div className="story-tags" dir="ltr">
      {s.breaking ? <BreakingBadge /> : null}
      {s.exclusive ? <ExclusiveBadge /> : null}
      {tags.map((tag) => {
        switch (tag.kind) {
          case "sources":
            return (
              <span key="sources" className={`badge${tag.count >= 3 ? " badge-accent" : ""}`}>
                {plural("stories.sources", tag.count)}
              </span>
            );
          case "age":
            return (
              <span key="age" className="badge">
                <time dateTime={s.last_seen_at} title={i18n.dateTime(s.last_seen_at)}>{i18n.relative(s.last_seen_at)}</time>
              </span>
            );
          case "spreading":
            return (
              <span key="spreading" className="badge badge-warning">
                <Icon name="signal" size={11} strokeWidth={2.2} />
                {t("stories.tag.spreading", { count: tag.count, hours: tag.hours })}
              </span>
            );
          case "turkey":
            if (!homeOn) return null;
            return (
              <span key="turkey" className={`badge ${tag.level === "direct" ? "badge-danger" : "badge-accent"}`}>
                {t(tag.level === "direct" ? "stories.tag.turkeyDirect" : "stories.tag.turkeyIndirect")}
              </span>
            );
          case "interest":
            return (
              <span key="interest" className="badge badge-success">
                {t("stories.tag.interest", { matches: tag.matches.map((m) => interestLabel(i18n, m)).join(", ") })}
              </span>
            );
          default:
            return null;
        }
      })}
    </div>
  );
}

/** Who reported it first, and where the outlets contradict each other (the model names the difference). */
export function StoryFirstAndConflict({ story: s, conflict, i18n }: { story: Story; conflict: string | null; i18n: I18n }) {
  const { t } = i18n;
  if (!s.first && !conflict) return null;
  return (
    <>
      {s.first ? (
        <p className="story-first" dir="ltr">
          <span>{t("stories.first")}:</span> {s.first.source} · {i18n.relative(s.first.at)}
        </p>
      ) : null}
      {conflict ? (
        <p className="story-conflict" role="note">
          <Icon name="alert" size={13} />
          <span><strong>{t("stories.conflict")}:</strong> {conflict}</span>
        </p>
      ) : null}
    </>
  );
}

export function ScorePill({ score, i18n }: { score: number; i18n: I18n }) {
  const level = score >= 60 ? "high" : score >= 35 ? "mid" : "low";
  return (
    <span className="score-pill" data-level={level} title={i18n.t("stories.score", { score: Math.round(score) })}>
      {Math.round(score)}
    </span>
  );
}

function sourceLine(sources: string[]): { names: string[]; more: number } {
  const names = sources.slice(0, MAX_SOURCE_NAMES);
  return { names, more: sources.length - names.length };
}

/** One story (a cluster of reports about the same event) in the feed. Opens the detail view on click. */
export function StoryCard({
  story: s,
  index,
  selected,
  onSelect,
  onOpen,
}: {
  story: Story;
  index: number;
  selected: boolean;
  onSelect: (i: number) => void;
  onOpen: (s: Story) => void;
}) {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const [lang, setLang] = useState<AiLang>(i18n.lang);
  const headline = storyHeadline(s, lang);
  const summary = storySummary(s, lang);
  const why = storyWhy(s, lang);
  const conflict = storyConflict(s, lang);
  const { settings } = useAppState();
  const languages = storyLanguages(s, aiLanguages(settings));
  const { names, more } = sourceLine(s.sources);
  const numbers = s.ai_status === "done" ? issueNumbers(s.ai_issues) : "";
  const dir = textDirection(headline.lang);
  const meeting = useMeeting();
  const inMeeting = meeting.has(s.id);

  return (
    <li className="article story" data-index={index} aria-selected={selected} onMouseDown={() => onSelect(index)}>
      {meeting.available ? (
        <button
          type="button"
          className="meeting-toggle"
          data-active={inMeeting}
          aria-pressed={inMeeting}
          title={inMeeting ? t("meeting.remove") : `${t("meeting.add")} (T)`}
          onClick={() => void meeting.toggle(s.id)}
        >
          <Icon name={inMeeting ? "check" : "plus"} size={14} strokeWidth={2.2} />
          <span>{inMeeting ? t("meeting.inList") : t("meeting.add")}</span>
        </button>
      ) : null}
      <div className="article-meta">
        <ScorePill score={s.score} i18n={i18n} />
        <span className="article-source">
          {names.join(" · ")}
          {more > 0 ? <span className="story-more"> {t("stories.moreSources", { count: more })}</span> : null}
        </span>
        {s.article_count > s.source_count ? <span>{plural("stories.articles", s.article_count)}</span> : null}
        {s.category ? <span className="badge">{t(`category.${s.category}`)}</span> : null}
        <LangToggle current={headline.lang} languages={languages} onChange={setLang} />
      </div>

      <h2 className="article-title" dir={dir}>
        <button type="button" className="story-open" onClick={() => onOpen(s)} title={t("stories.open")}>
          {headline.text}
        </button>
      </h2>
      {summary && summary !== headline.text ? (
        <p className="article-summary story-summary" dir={headline.translated ? "ltr" : dir}>{summary}</p>
      ) : null}
      {why ? (
        <p className="story-why">
          <span>{t("stories.why")}:</span> {why}
        </p>
      ) : null}
      <StoryFirstAndConflict story={s} conflict={conflict} i18n={i18n} />
      {numbers ? (
        <p className="article-warning" role="note">
          <Icon name="alert" size={13} />
          {t("stories.aiIssue", { numbers })}
        </p>
      ) : null}

      <ScoreTags story={s} i18n={i18n} />
      {s.representative && settings["fulltext.enabled"] ? (
        <div className="article-actions" dir="ltr">
          <CardFullText report={s.representative} />
        </div>
      ) : null}
    </li>
  );
}
