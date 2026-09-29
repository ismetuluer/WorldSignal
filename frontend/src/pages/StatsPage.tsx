import { useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { StatsHours, StatsOverview, StatsShares, TopicStats } from "../api/types";
import { ColumnChart, ShareBars, StatTile, type Column, type Share } from "../components/charts";
import { SearchLanguagesNote } from "../components/SearchLanguages";
import { SearchField, Segmented, Spinner, StateView } from "../components/controls";
import { describeError, useI18n, type I18n } from "../i18n";
import { storyTitle } from "../lib/aiText";
import { useDebounced } from "../lib/hooks";
import { useSearchTranslations } from "../lib/searchTranslations";
import { useAppState } from "../state";

const PERIODS: StatsHours[] = [24, 168, 720];
const SOURCES_SHOWN = 15;

/** Statistics: how the news is spread over topics, categories, regions and sources, and what is rising. */
export function StatsPage() {
  const i18n = useI18n();
  const { t, plural, number } = i18n;
  const { status } = useAppState();
  const [hours, setHours] = useState<StatsHours>(24);
  const [data, setData] = useState<StatsOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const q = useDebounced(search.trim(), 250);
  const languages = useSearchTranslations(q);
  const [topic, setTopic] = useState<{ q: string; data: TopicStats } | null>(null);
  const [allSources, setAllSources] = useState(false);

  const reload = () => {
    setLoading(true);
    api.stats(hours).then(
      (d) => {
        setData(d);
        setError(null);
        setLoading(false);
      },
      (e) => {
        setError(e instanceof ApiError ? e.code : "generic");
        setLoading(false);
      },
    );
  };
  // New reports arrive all the time: refresh after each collection round.
  useEffect(reload, [hours, status?.collector.last_cycle_at]);

  useEffect(() => {
    if (!q) {
      setTopic(null);
      return;
    }
    let current = true;
    api.topicStats(hours, q, languages.phrases).then(
      (d) => current && setTopic({ q, data: d }),
      (e) => current && setError(e instanceof ApiError ? e.code : "generic"),
    );
    return () => {
      current = false;
    };
  }, [q, hours, languages.phrases, data]);

  const periodLabel = (h: StatsHours) => (h === 24 ? t("feed.window.hours", { n: 24 }) : t("feed.window.days", { n: h / 24 }));
  const bucketLabel = (iso: string) => {
    const d = new Date(iso);
    return hours === 24 ? i18n.time(iso) : d.toLocaleDateString(i18n.locale, { day: "numeric", month: "short" });
  };

  const columns = useMemo<Column[]>(() => {
    if (!data) return [];
    if (topic && topic.q === q) {
      return topic.data.buckets.map((b) => ({
        key: b.start,
        label: bucketLabel(b.start),
        value: b.articles,
        title: plural("stats.reports", b.articles),
        details: [plural("stats.sources", b.sources), t("stats.shareOfAll", { share: percent(i18n, b.share) })],
      }));
    }
    return data.timeline.map((b) => ({
      key: b.start,
      label: bucketLabel(b.start),
      value: b.articles,
      title: plural("stats.reports", b.articles),
      details: [],
    }));
  }, [data, topic, q, i18n]);

  if (!data) {
    return (
      <div className="page page-wide">
        <Header />
        {error ? (
          <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)}
            action={<button className="btn" onClick={reload}>{t("common.retry")}</button>} />
        ) : (
          <div className="state"><Spinner label={t("common.loading")} /></div>
        )}
      </div>
    );
  }

  const comparable = data.period.comparable;
  const change = (now: number, before: number) => {
    if (!comparable) return undefined;
    if (before === 0) return now === 0 ? t("stats.noChange") : t("stats.new");
    const pctChange = Math.round(((now - before) / before) * 100);
    return pctChange === 0 ? t("stats.noChange") : t(pctChange > 0 ? "stats.up" : "stats.down", { n: number(Math.abs(pctChange)) });
  };
  const topicReady = !!(q && topic && topic.q === q);
  const sources = allSources ? data.sources : data.sources.slice(0, SOURCES_SHOWN);

  return (
    <div className="page page-wide stats-page" data-loading={loading}>
      <Header>
        <p className="page-subtitle">
          {periodLabel(hours)}
          {comparable
            ? ` · ${t("stats.comparedWith")}`
            : ` · ${t("stats.notComparable", { day: data.period.collecting_since ? i18n.dateTime(data.period.collecting_since) : "—" })}`}
        </p>
      </Header>

      <div className="toolbar">
        <Segmented label={t("stats.period")} value={hours} onChange={setHours}
          options={PERIODS.map((h) => ({ value: h, label: periodLabel(h) }))} />
      </div>

      <div className="stat-row">
        <StatTile label={t("stats.tile.reports")} value={number(data.totals.articles)}
          change={change(data.totals.articles, data.totals.previous.articles)} />
        <StatTile label={t("stats.tile.stories")} value={number(data.totals.stories)}
          change={change(data.totals.stories, data.totals.previous.stories)} />
        <StatTile label={t("stats.tile.sources")} value={number(data.totals.sources)} hint={t("stats.tile.sourcesHint")}
          change={change(data.totals.sources, data.totals.previous.sources)} />
      </div>

      <section className="section stats-card">
        <h2 className="section-title">{t("stats.topic.title")}</h2>
        <p className="section-note">{t("stats.topic.note")}</p>
        <div className="stats-topic-search">
          <SearchField value={search} onChange={setSearch} placeholder={t("stats.topic.placeholder")} />
        </div>
        <SearchLanguagesNote languages={languages} />
        {q && !topicReady ? <Spinner label={t("common.loading")} /> : null}
        {topicReady && topic ? (
          <p className="stats-summary" role="status">
            {t("stats.topic.summary", {
              reports: plural("stats.reports", topic.data.articles),
              sources: plural("stats.sources", topic.data.sources),
              share: percent(i18n, data.totals.articles ? topic.data.articles / data.totals.articles : 0),
            })}
            {comparable ? ` ${t("stats.topic.previous", { reports: plural("stats.reports", topic.data.previous) })}` : ""}
          </p>
        ) : null}
        <ColumnChart
          columns={columns}
          label={topicReady ? t("stats.topic.chartLabel", { q }) : t("stats.allReports")}
          format={(n) => number(Math.round(n))}
        />
        {!topicReady ? <p className="field-hint">{t("stats.allReportsHint")}</p> : null}
      </section>

      <div className="stats-grid">
        <section className="section stats-card">
          <h2 className="section-title">{t("stats.categories.title")}</h2>
          <p className="section-note">
            {t("stats.categories.note", {
              known: number(data.categories.known),
              share: percent(i18n, data.categories.total ? data.categories.known / data.categories.total : 0),
            })}
          </p>
          {data.categories.known ? (
            <ShareBars label={t("stats.categories.title")}
              items={shares(data.categories, comparable, (k) => i18n.tryT(`category.${k}`) ?? k, i18n)} />
          ) : (
            <p className="field-hint">{t("stats.categories.none")}</p>
          )}
        </section>
        <section className="section stats-card">
          <h2 className="section-title">{t("stats.regions.title")}</h2>
          <p className="section-note">{t("stats.regions.note")}</p>
          <ShareBars label={t("stats.regions.title")}
            items={shares({ ...data.regions, known: data.regions.total }, comparable,
              (k) => i18n.tryT(`region.${k}`) ?? k, i18n)} />
        </section>
      </div>

      <section className="section stats-card">
        <h2 className="section-title">{t("stats.rising.title")}</h2>
        <p className="section-note">{t("stats.rising.note", { hours: data.rising.window_hours })}</p>
        {data.rising.items.length === 0 ? (
          <p className="field-hint">{t("stats.rising.none")}</p>
        ) : (
          <ol className="rising-list">
            {data.rising.items.map((r) => (
              <li key={r.story.id}>
                <button type="button" className="rising-title" onClick={() => (window.location.hash = `/stats?story=${r.story.id}`)}>
                  {storyTitle(r.story, i18n.lang).text}
                </button>
                <span className="rising-numbers">
                  {t("stats.rising.numbers", {
                    reports: plural("stats.reports", r.recent),
                    before: number(r.previous),
                    sources: plural("stats.sources", r.sources),
                  })}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>

      <div className="stats-grid">
        <section className="section stats-card">
          <h2 className="section-title">{t("stats.sources.title")}</h2>
          <table className="stats-table">
            <thead>
              <tr>
                <th scope="col">{t("stats.sources.name")}</th>
                <th scope="col" className="num">{t("stats.sources.reports")}</th>
                {comparable ? <th scope="col" className="num">{t("stats.sources.change")}</th> : null}
                <th scope="col" className="num">{t("stats.sources.stories")}</th>
                <th scope="col">{t("stats.sources.last")}</th>
              </tr>
            </thead>
            <tbody>
              {sources.map((s) => (
                <tr key={s.id} data-silent={s.articles === 0}>
                  <th scope="row">{s.name}</th>
                  <td className="num">{number(s.articles)}</td>
                  {comparable ? <td className="num">{change(s.articles, s.previous) ?? ""}</td> : null}
                  <td className="num">{number(s.stories)}</td>
                  <td>{s.last_at ? i18n.relative(s.last_at) : t("stats.sources.silent")}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {data.sources.length > SOURCES_SHOWN ? (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setAllSources((v) => !v)}>
              {allSources ? t("stats.sources.fewer") : t("stats.sources.all", { n: data.sources.length })}
            </button>
          ) : null}
        </section>
        <section className="section stats-card">
          <h2 className="section-title">{t("stats.countries.title")}</h2>
          <p className="section-note">{t("stats.countries.note", { read: number(data.countries.read) })}</p>
          {data.countries.items.length ? (
            <ShareBars label={t("stats.countries.title")}
              items={data.countries.items.map((c) => ({
                key: c.key,
                label: i18n.countryName(c.key),
                share: data.countries.read ? c.articles / data.countries.read : 0,
                change: null,
                detail: plural("stats.reports", c.articles),
              }))} />
          ) : (
            <p className="field-hint">{t("stats.countries.none")}</p>
          )}
        </section>
      </div>
    </div>
  );
}

function Header({ children }: { children?: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <header className="page-header">
      <div>
        <h1 className="page-title">{t("stats.title")}</h1>
        {children}
      </div>
    </header>
  );
}

function percent(i18n: I18n, x: number): string {
  return i18n.t("stats.percent", { n: i18n.number(Math.round(x * 1000) / 10) });
}

/** Shares of the known reports, with the change in percentage points when the previous period can be compared. */
function shares(s: StatsShares, comparable: boolean, name: (key: string) => string, i18n: I18n): Share[] {
  return s.items
    .filter((i) => i.articles > 0)
    .map((i) => {
      const share = s.known ? i.articles / s.known : 0;
      const before = s.known_previous ? i.previous / s.known_previous : 0;
      return {
        key: i.key,
        label: name(i.key),
        share,
        change: comparable && s.known_previous ? share - before : null,
        detail: i18n.plural("stats.reports", i.articles),
      };
    });
}
