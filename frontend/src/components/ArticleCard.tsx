import { useState } from "react";
import type { Article } from "../api/types";
import { useI18n } from "../i18n";
import { aiLanguages, articleSummary, articleTitle, languagesOf, type AiLang } from "../lib/aiText";
import { useAppState } from "../state";
import { textDirection } from "../lib/hooks";
import { Icon } from "./Icon";
import { LangToggle } from "./StoryCard";
import { openableUrl } from "../lib/links";
import { BreakingBadge, ExclusiveBadge } from "./Badges";
import { CardFullText } from "./FullText";

/** One article in the feed. AI output is labelled and the original is always one click away. */
export function ArticleCard({
  article: a,
  index,
  selected,
  onSelect,
  onRequestAi,
  aiAvailable,
}: {
  article: Article;
  /** False when AI is switched off or no model is chosen: no point offering "Translate". */
  aiAvailable: boolean;
  index: number;
  selected: boolean;
  onSelect: (i: number) => void;
  onRequestAi: (a: Article) => void;
}) {
  const i18n = useI18n();
  const { t } = i18n;
  const [showOriginal, setShowOriginal] = useState(false);

  const [lang, setLang] = useState<AiLang>(i18n.lang);
  const { settings } = useAppState();
  const languages = a.ai_status === "done" ? languagesOf(a.ai_texts, aiLanguages(settings)) : [];
  const hasAi = languages.length > 0;
  const useAi = hasAi && !showOriginal;
  const shown = articleTitle(a, lang);
  const headline = useAi ? shown.text : a.title;
  const summary = useAi ? articleSummary(a, lang) : a.summary;
  const dir = textDirection(useAi ? shown.lang : a.language);
  const showOriginalTitle = useAi && a.language !== shown.lang && a.title !== headline;
  const numbers = a.ai_issues
    .filter((i) => i.startsWith("number_not_in_source:"))
    .map((i) => i.split(":")[1])
    .join(", ");

  return (
    <li className="article" data-index={index} aria-selected={selected} dir={dir} onMouseDown={() => onSelect(index)}>
      <div className="article-meta" dir="ltr">
        <span className="article-source">{a.source_name}</span>
        <time dateTime={a.sort_at} title={i18n.dateTime(a.sort_at)}>
          {i18n.relative(a.sort_at)}
        </time>
        {a.breaking ? <BreakingBadge /> : null}
        {a.exclusive ? <ExclusiveBadge source={a.source_name} /> : null}
        {a.language !== i18n.lang ? <span className="badge">{i18n.languageName(a.language)}</span> : null}
        {a.paywalled ? (
          <span className="badge badge-warning" title={t("feed.paywalled")}>
            <Icon name="lock" size={11} strokeWidth={2.2} />
            {t("feed.paywalled")}
          </span>
        ) : null}
        {hasAi && a.category ? <span className="badge">{t(`category.${a.category}`)}</span> : null}
        {useAi ? <LangToggle current={shown.lang} languages={languages} onChange={setLang} /> : null}
        {hasAi && settings["home.enabled"] && settings["home.labels"] && a.turkey_relevance && a.turkey_relevance !== "none" ? (
          <span
            className={`badge ${a.turkey_relevance === "direct" ? "badge-danger" : "badge-accent"}`}
            title={a.turkey_links.map(i18n.turkeyLink).join(" · ")}
          >
            {t(a.turkey_relevance === "direct" ? "ai.turkey.direct" : "ai.turkey.indirect")}
          </span>
        ) : null}
      </div>

      <h2 className="article-title">
        <a href={openableUrl(a.url, a.title)} target="_blank" rel="noopener noreferrer" title={t("feed.openOriginal")}>
          {headline}
        </a>
      </h2>
      {showOriginalTitle ? (
        <p className="article-original">
          <span>{t("ai.original")}:</span> <span dir={textDirection(a.language)}>{a.title}</span>
        </p>
      ) : null}
      {summary && summary !== headline ? <p className="article-summary">{summary}</p> : null}

      {numbers && useAi ? (
        <p className="article-warning" role="note">
          <Icon name="alert" size={13} />
          {t("ai.issue.number", { numbers })}
        </p>
      ) : null}

      <div className="article-actions" dir="ltr">
        {settings["fulltext.enabled"] ? <CardFullText report={a} /> : null}
        {hasAi ? (
          <>
            <button type="button" className="link-btn" onClick={() => setShowOriginal((v) => !v)}>
              {showOriginal ? t("ai.showAi") : t("ai.showOriginal")}
            </button>
            {a.ai_brief && aiAvailable ? (
              <button type="button" className="link-btn" onClick={() => onRequestAi(a)} title={t("ai.summarizeHint")}>
                {t("ai.translate")}
              </button>
            ) : null}
          </>
        ) : a.ai_status === "pending" ? (
          <span className="badge">{t("ai.queued")}</span>
        ) : aiAvailable ? (
          <>
            {a.ai_status === "failed" ? <span className="badge badge-danger">{t("ai.failed")}</span> : null}
            <button type="button" className="link-btn" onClick={() => onRequestAi(a)}>
              {t("ai.translate")}
            </button>
          </>
        ) : null}
      </div>
    </li>
  );
}
