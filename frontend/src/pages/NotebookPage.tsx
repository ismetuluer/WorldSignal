import { useCallback, useEffect, useMemo, useState } from "react";
import { api, ApiError } from "../api/client";
import type { NotebookDay, NotebookMonth, Story, StoryNote } from "../api/types";
import { Calendar, longDay } from "../components/Calendar";
import { Spinner, StateView } from "../components/controls";
import { Icon } from "../components/Icon";
import { NoteEditor } from "../components/NoteEditor";
import { OutputDialog } from "../components/OutputDialog";
import { StoryDetail } from "../components/StoryDetail";
import { describeError, useI18n } from "../i18n";
import { meetingText } from "../lib/aiText";
import { localDay } from "../lib/hooks";
import { entryFromStory, notesOutput } from "../lib/outputs";
import { navigate } from "../router";

/** Notebook: a calendar of days; each day holds a free note, that day's meeting list and story notes. */
export function NotebookPage() {
  const i18n = useI18n();
  const { t } = i18n;
  const today = localDay();
  const [day, setDay] = useState(today);
  const [month, setMonth] = useState(today.slice(0, 7));
  const [calendar, setCalendar] = useState<NotebookMonth | null>(null);
  const [data, setData] = useState<NotebookDay | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [openId, setOpenId] = useState<number | null>(null);
  const [output, setOutput] = useState<{ notes: { title: string; body: string; story: Story | null }[] | null; error: string | null } | null>(null);

  const loadMonth = useCallback(() => {
    api.notebookMonth(month).then(setCalendar, () => setCalendar({ month, today, days: [] }));
  }, [month, today]);

  const loadDay = useCallback(async () => {
    setError(null);
    try {
      setData(await api.notebookDay(day));
    } catch (e) {
      setError(e instanceof ApiError ? e.code : "generic");
    }
  }, [day]);

  useEffect(loadMonth, [loadMonth]);
  useEffect(() => {
    setData(null);
    setSelected(new Set());
    void loadDay();
  }, [loadDay]);

  const marks = useMemo(
    () => new Map((calendar?.days ?? []).map((d) => [d.day, t("notebook.hasEntries")])),
    [calendar, t],
  );

  const pick = (d: string) => {
    setDay(d);
    setMonth(d.slice(0, 7));
  };

  const openOutput = async (notes: StoryNote[]) => {
    setOutput({ notes: null, error: null });
    try {
      const withStories = await Promise.all(
        notes.map(async (n) => {
          const story = n.story_id !== null && n.story_exists ? await api.story(n.story_id).catch(() => null) : null;
          return { title: n.title, body: n.body, story };
        }),
      );
      setOutput({ notes: withStories, error: null });
    } catch (e) {
      setOutput({ notes: null, error: describeError(i18n, e instanceof ApiError ? e.code : "generic") });
    }
  };

  const chosen = (data?.notes ?? []).filter((n) => selected.has(n.id));
  const empty = data && !data.day_note && data.meeting.length === 0 && data.notes.length === 0;

  return (
    <div className="page page-wide">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("notebook.title")}</h1>
          <p className="page-subtitle">{longDay(i18n, day)}</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-primary" disabled={chosen.length === 0} onClick={() => void openOutput(chosen)}>
            <Icon name="print" size={16} />
            {t("notebook.outputSelected", { count: chosen.length })}
          </button>
        </div>
      </header>

      <div className="notebook">
        <Calendar
          label={t("notebook.calendar")}
          month={month}
          onMonth={setMonth}
          day={day}
          today={today}
          onPick={pick}
          marks={marks}
          footer={day !== today ? <button className="btn btn-sm" onClick={() => pick(today)}>{t("notebook.today")}</button> : null}
        />

        <div className="notebook-day">
          {error ? (
            <StateView icon="alert" title={t("error.title")} body={describeError(i18n, error)}
              action={<button className="btn" onClick={() => void loadDay()}>{t("common.retry")}</button>} />
          ) : !data ? (
            <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>
          ) : (
            <>
              <section>
                <h2 className="subsection-title">{t("notebook.dayNote")}</h2>
                <NoteEditor
                  key={day}
                  initial={data.day_note?.body ?? ""}
                  draftKey={`day-note-${day}`}
                  save={(body) => api.saveDayNote(day, body).then(loadMonth)}
                  label={t("notebook.dayNote")}
                  placeholder={t("notebook.dayNotePlaceholder")}
                  rows={4}
                />
              </section>

              {data.meeting.length > 0 || day === data.today ? (
                <section>
                  <div className="inline-row">
                    <h2 className="subsection-title">{t("notebook.meeting")}</h2>
                    {day === data.today ? (
                      <button className="link-btn" onClick={() => navigate("meeting")}>{t("notebook.openMeeting")}</button>
                    ) : null}
                  </div>
                  {data.meeting.length ? (
                    <ol className="notebook-meeting">
                      {data.meeting.map((m) => (
                        <li key={m.id}>
                          <span className="meeting-title">{meetingText(m, i18n.lang).title}</span>
                          {m.comment || meetingText(m, i18n.lang).why ? (
                            <span className="field-hint"> — {m.comment || meetingText(m, i18n.lang).why}</span>
                          ) : null}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="field-hint">{t("meeting.empty.title")}</p>
                  )}
                </section>
              ) : null}

              {data.notes.length ? (
                <section>
                  <h2 className="subsection-title">{t("notebook.notes")}</h2>
                  <ul className="member-list">
                    {data.notes.map((n) => (
                      <li key={n.id} className="notebook-note">
                        <label className="notebook-select">
                          <input
                            type="checkbox"
                            checked={selected.has(n.id)}
                            aria-label={`${t("notebook.selectForOutput")}: ${n.title}`}
                            onChange={(e) =>
                              setSelected((s) => {
                                const next = new Set(s);
                                if (e.target.checked) next.add(n.id);
                                else next.delete(n.id);
                                return next;
                              })
                            }
                          />
                        </label>
                        <div className="notebook-note-body">
                          {n.story_id !== null && n.story_exists ? (
                            <button type="button" className="meeting-title story-open-inline" onClick={() => setOpenId(n.story_id)}>
                              {n.title}
                            </button>
                          ) : (
                            <p className="meeting-title">{n.title}</p>
                          )}
                          <p className="notebook-note-text">{n.body}</p>
                          {!n.story_exists ? <p className="field-hint">{t("notebook.storyGone")}</p> : null}
                        </div>
                      </li>
                    ))}
                  </ul>
                </section>
              ) : null}

              {empty ? <p className="field-hint">{t("notebook.empty")}</p> : null}
            </>
          )}
        </div>
      </div>

      {openId !== null ? (
        <StoryDetail storyId={openId} onClose={() => { setOpenId(null); void loadDay(); }} onChanged={() => void loadDay()} />
      ) : null}
      {output ? (
        <OutputDialog
          build={output.notes ? (l, out) => notesOutput(out, day, output.notes!.map((n) => ({
            title: n.title, body: n.body, entry: n.story ? entryFromStory(n.story, l) : null,
          }))) : null}
          error={output.error}
          onClose={() => setOutput(null)}
        />
      ) : null}
    </div>
  );
}
