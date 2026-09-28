import { forwardRef, useEffect, useId, useRef, type ReactNode } from "react";
import { useI18n } from "../i18n";
import { Icon, type IconName } from "./Icon";

export function Switch({
  checked,
  onChange,
  label,
  disabled,
}: {
  checked: boolean;
  onChange: (value: boolean) => void;
  label: string;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      role="switch"
      className="switch"
      aria-checked={checked}
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={(e) => {
        e.stopPropagation();
        onChange(!checked);
      }}
    />
  );
}

export function Segmented<T extends string | number>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div className="segmented" role="group" aria-label={label}>
      {options.map((o) => (
        <button key={String(o.value)} type="button" aria-pressed={o.value === value} onClick={() => onChange(o.value)}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

export const SearchField = forwardRef<
  HTMLInputElement,
  { value: string; onChange: (v: string) => void; placeholder: string; shortcut?: string }
>(function SearchField({ value, onChange, placeholder, shortcut }, ref) {
  const { t } = useI18n();
  return (
    <div className="search">
      <Icon name="search" size={16} />
      <input
        ref={ref}
        className="input"
        type="search"
        value={value}
        placeholder={placeholder}
        aria-label={placeholder}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            if (value) onChange("");
            else e.currentTarget.blur();
          }
        }}
      />
      {value ? (
        <button type="button" className="icon-btn search-clear" aria-label={t("feed.searchClear")} onClick={() => onChange("")}>
          <Icon name="close" size={14} />
        </button>
      ) : shortcut ? (
        <span className="kbd search-kbd" aria-hidden="true">
          {shortcut}
        </span>
      ) : null}
    </div>
  );
});

export function Spinner({ label }: { label?: string }) {
  return <span className="spinner" role={label ? "status" : undefined} aria-label={label} />;
}

export function StateView({
  icon,
  title,
  body,
  action,
}: {
  icon: IconName;
  title: string;
  body?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="state">
      <div className="state-icon">
        <Icon name={icon} size={24} />
      </div>
      <p className="state-title">{title}</p>
      {body ? <p className="state-body">{body}</p> : null}
      {action}
    </div>
  );
}

export function Banner({
  kind = "warning",
  icon,
  title,
  body,
  action,
}: {
  kind?: "warning" | "error";
  icon: IconName;
  title: string;
  body?: string;
  action?: ReactNode;
}) {
  return (
    <div className={`banner${kind === "error" ? " banner-error" : ""}`} role={kind === "error" ? "alert" : "status"}>
      <Icon name={icon} />
      <div style={{ flex: 1 }}>
        <p className="banner-title">{title}</p>
        {body ? <p className="banner-body">{body}</p> : null}
      </div>
      {action}
    </div>
  );
}

/** Open dialogs, innermost last: Escape closes only the top one (dialogs can open dialogs). */
const openDialogs: object[] = [];

/** Modal dialog with focus trap-lite: focuses itself, closes on Escape / backdrop click. */
export function Dialog({
  title,
  onClose,
  children,
  footer,
  wide,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
  footer?: ReactNode;
  /** Reading-sized dialog (story details) instead of a form-sized one. */
  wide?: boolean;
}) {
  const { t } = useI18n();
  const ref = useRef<HTMLDivElement>(null);
  const titleId = useId();
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    const self = {};
    openDialogs.push(self);
    const previouslyFocused = document.activeElement as HTMLElement | null;
    const first = ref.current?.querySelector<HTMLElement>("input, select, textarea, button:not(.dialog-close)");
    (first ?? ref.current)?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape" && openDialogs[openDialogs.length - 1] === self) {
        e.stopPropagation();
        onCloseRef.current();
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => {
      openDialogs.splice(openDialogs.indexOf(self), 1);
      document.removeEventListener("keydown", onKey, true);
      previouslyFocused?.focus?.();
    };
  }, []);

  return (
    <div
      className="backdrop"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div ref={ref} className={`dialog${wide ? " dialog-wide" : ""}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}>
        <div className="dialog-header">
          <h2 className="dialog-title" id={titleId}>
            {title}
          </h2>
          <button type="button" className="icon-btn dialog-close" aria-label={t("common.close")} onClick={onClose}>
            <Icon name="close" />
          </button>
        </div>
        <div className="dialog-body">{children}</div>
        {footer ? <div className="dialog-footer">{footer}</div> : null}
      </div>
    </div>
  );
}
