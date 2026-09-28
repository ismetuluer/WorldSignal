import { useState } from "react";
import type { MeetingItem } from "../api/types";
import { Spinner, StateView } from "../components/controls";
import { Icon } from "../components/Icon";
import { useMeeting } from "../components/meeting";
import { OutputDialog } from "../components/OutputDialog";
import { StoryDetail } from "../components/StoryDetail";
import { describeError, useI18n } from "../i18n";
import { useAutosave } from "../lib/autosave";
import { meetingOutput } from "../lib/outputs";

/** Today's meeting list: order by drag (or the arrow buttons), a short reason per proposal, output. */
export function MeetingPage() {
  const i18n = useI18n();
  const { t, plural } = i18n;
  const meeting = useMeeting();
  const [dragId, setDragId] = useState<number | null>(null);
  const [overId, setOverId] = useState<number | null>(null);
  const [openId, setOpenId] = useState<number | null>(null);
  const [output, setOutput] = useState(false);
  const items = meeting.items;
  const ids = items.map((i) => i.id);

  const move = (id: number, to: number) => {
    const from = ids.indexOf(id);
    if (from < 0 || to < 0 || to >= ids.length || from === to) return;
    const next = [...ids];
    next.splice(from, 1);
    next.splice(to, 0, id);
    void meeting.reorder(next);
  };

  const longDay = meeting.day
    ? new Intl.DateTimeFormat(i18n.locale, { dateStyle: "full" }).format(new Date(`${meeting.day}T12:00:00`))
    : "";

  let content: React.ReactNode;
  if (!meeting.loaded) {
    content = <div className="dialog-loading"><Spinner label={t("common.loading")} /></div>;
  } else if (meeting.error && items.length === 0) {
    content = (
      <StateView
        icon="alert"
        title={t("error.title")}
        body={describeError(i18n, meeting.error)}
        action={<button className="btn" onClick={() => void meeting.reload()}>{t("common.retry")}</button>}
      />
    );
  } else if (items.length === 0) {
    content = <StateView icon="meeting" title={t("meeting.empty.title")} body={t("meeting.empty.body")} />;
  } else {
    content = (
      <ol className="meeting-list" aria-label={t("meeting.title")}>
        {items.map((item, index) => (
          <li
            key={item.id}
            className="meeting-item"
            data-dragging={dragId === item.id}
            data-over={overId === item.id && dragId !== item.id}
            onDragOver={(e) => {
              if (dragId === null) return;
              e.preventDefault();
              setOverId(item.id);
            }}
            onDrop={(e) => {
              e.preventDefault();
              if (dragId !== null) move(dragId, index);
              setDragId(null);
              setOverId(null);
            }}
          >
            <span
              className="meeting-grip"
              draggable
              title={t("meeting.drag")}
              aria-hidden="true"
              onDragStart={(e) => {
                setDragId(item.id);
                e.dataTransfer.effectAllowed = "move";
                e.dataTransfer.setData("text/plain", String(item.id));
              }}
              onDragEnd={() => {
                setDragId(null);
                setOverId(null);
              }}
            >
              <Icon name="grip" size={16} strokeWidth={3} />
            </span>
            <span className="meeting-number">{index + 1}</span>
            <MeetingRow item={item} onOpen={setOpenId} />
            <div className="meeting-actions">
              <button type="button" className="icon-btn" aria-label={t("meeting.moveUp")} title={t("meeting.moveUp")}
                disabled={index === 0} onClick={() => move(item.id, index - 1)}>
                <Icon name="up" size={16} />
              </button>
              <button type="button" className="icon-btn" aria-label={t("meeting.moveDown")} title={t("meeting.moveDown")}
                disabled={index === items.length - 1} onClick={() => move(item.id, index + 1)}>
                <Icon name="chevronDown" size={16} />
              </button>
              <button type="button" className="icon-btn" aria-label={t("meeting.remove")} title={t("meeting.remove")}
                onClick={() => void meeting.remove(item.id)}>
                <Icon name="trash" size={16} />
              </button>
            </div>
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div className="page">
      <header className="page-header">
        <div>
          <h1 className="page-title">{t("meeting.title")}</h1>
          <p className="page-subtitle">{meeting.loaded ? `${longDay} · ${plural("meeting.count", items.length)}` : t("common.loading")}</p>
        </div>
        <div className="header-actions">
          <button className="btn btn-primary" disabled={items.length === 0} onClick={() => setOutput(true)}>
            <Icon name="print" size={16} />
            {t("output.open")}
          </button>
        </div>
      </header>
      {content}
      {openId !== null ? <StoryDetail storyId={openId} onClose={() => setOpenId(null)} onChanged={() => void meeting.reload()} /> : null}
      {output && meeting.day ? (
        <OutputDialog build={(l, out) => meetingOutput(out, meeting.day!, items, l)} onClose={() => setOutput(false)} />
      ) : null}
    </div>
  );
}

function MeetingRow({ item, onOpen }: { item: MeetingItem; onOpen: (storyId: number) => void }) {
  const { t, plural } = useI18n();
  const meeting = useMeeting();
  return (
    <div className="meeting-body">
      <div className="article-meta">
        {item.category ? <span className="badge">{t(`category.${item.category}`)}</span> : null}
        <span>{plural("output.sourceCount", item.sources.length)}</span>
        {item.story_id === null ? <span className="badge badge-warning">{t("meeting.storyGone")}</span> : null}
      </div>
      {item.story_id !== null ? (
        <button type="button" className="meeting-title story-open-inline" onClick={() => onOpen(item.story_id!)} title={t("meeting.openStory")}>
          {item.title}
        </button>
      ) : (
        <p className="meeting-title">{item.title}</p>
      )}
      {item.summary ? <p className="article-summary">{item.summary}</p> : null}
      <CommentField key={item.id} item={item} save={(c) => meeting.setComment(item.id, c)} />
      {item.why ? <p className="field-hint">{t("meeting.aiWhy", { why: item.why })}</p> : null}
    </div>
  );
}

function CommentField({ item, save }: { item: MeetingItem; save: (comment: string) => Promise<void> }) {
  const { t } = useI18n();
  const { value, setValue, status, flush } = useAutosave(item.comment, save, `meeting-comment-${item.id}`);
  return (
    <div className="meeting-comment">
      <input
        className="input"
        value={value}
        maxLength={300}
        aria-label={t("meeting.comment")}
        placeholder={t("meeting.commentPlaceholder")}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void flush()}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.currentTarget.blur();
        }}
      />
      {status === "error" ? <span className="note-status" data-status="error">{t("notes.status.error")}</span> : null}
    </div>
  );
}
