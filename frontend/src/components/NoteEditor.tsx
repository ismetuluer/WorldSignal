import { useI18n } from "../i18n";
import { useAutosave } from "../lib/autosave";

/** A self-saving note field with a visible save state. Remount (``key``) for another record. */
export function NoteEditor({
  initial,
  save,
  draftKey,
  label,
  placeholder,
  rows = 4,
}: {
  initial: string;
  save: (body: string) => Promise<unknown>;
  draftKey: string;
  label: string;
  placeholder: string;
  rows?: number;
}) {
  const { t } = useI18n();
  const { value, setValue, status, flush, recovered } = useAutosave(initial, save, draftKey);
  const statusText =
    status === "saving" ? t("notes.status.saving")
    : status === "saved" ? t("notes.status.saved")
    : status === "error" ? t("notes.status.error")
    : recovered ? t("notes.recovered")
    : "";
  return (
    <div className="note-editor">
      <textarea
        className="textarea"
        rows={rows}
        value={value}
        aria-label={label}
        placeholder={placeholder}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => void flush()}
        maxLength={20000}
      />
      <span className="note-status" data-status={status} role="status" aria-live="polite">
        {statusText}
      </span>
    </div>
  );
}
