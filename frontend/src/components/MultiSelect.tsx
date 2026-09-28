import { useEffect, useMemo, useRef, useState } from "react";
import { useI18n } from "../i18n";
import { Icon } from "./Icon";

export interface Option<T> {
  value: T;
  label: string;
  hint?: string;
}

/** A filter chip that opens a checkbox list. Empty selection means "all". */
export function MultiSelect<T extends string | number>({
  label,
  options,
  selected,
  onChange,
  searchable = false,
  searchPlaceholder,
}: {
  label: string;
  options: Option<T>[];
  selected: T[];
  onChange: (next: T[]) => void;
  searchable?: boolean;
  searchPlaceholder?: string;
}) {
  const i18n = useI18n();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey, true);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey, true);
    };
  }, [open]);

  const visible = useMemo(() => {
    const q = query.trim().toLocaleLowerCase(i18n.locale);
    if (!q) return options;
    return options.filter((o) => o.label.toLocaleLowerCase(i18n.locale).includes(q));
  }, [options, query, i18n.locale]);

  const selectedSet = new Set(selected);
  const active = selected.length > 0;
  const summary =
    selected.length === 1
      ? (options.find((o) => o.value === selected[0])?.label ?? label)
      : active
        ? `${label}: ${i18n.plural("filter.selected", selected.length)}`
        : label;

  const toggle = (value: T) => {
    onChange(selectedSet.has(value) ? selected.filter((v) => v !== value) : [...selected, value]);
  };

  return (
    <div ref={rootRef} style={{ position: "relative" }}>
      <button
        type="button"
        className="chip"
        data-active={active}
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen((o) => !o)}
      >
        {summary}
        <Icon name="chevronDown" size={14} />
      </button>
      {open ? (
        <div className="popover">
          {searchable ? (
            <input
              className="input"
              autoFocus
              value={query}
              placeholder={searchPlaceholder}
              aria-label={searchPlaceholder}
              onChange={(e) => setQuery(e.target.value)}
            />
          ) : null}
          <div className="popover-list" role="listbox" aria-multiselectable="true" aria-label={label}>
            {active ? (
              <button type="button" className="option" onClick={() => onChange([])}>
                <span className="checkbox" />
                <span>{i18n.t("filter.any")}</span>
              </button>
            ) : null}
            {visible.map((o) => {
              const checked = selectedSet.has(o.value);
              return (
                <button
                  key={String(o.value)}
                  type="button"
                  className="option"
                  role="option"
                  aria-selected={checked}
                  onClick={() => toggle(o.value)}
                >
                  <span className="checkbox" data-checked={checked}>
                    {checked ? <Icon name="check" size={12} strokeWidth={3} /> : null}
                  </span>
                  <span>{o.label}</span>
                  {o.hint ? <span className="option-count">{o.hint}</span> : null}
                </button>
              );
            })}
            {visible.length === 0 ? <div className="option" aria-disabled="true">{i18n.t("filter.noMatch")}</div> : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}
