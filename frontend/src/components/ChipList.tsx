import { useI18n } from "../i18n";
import { Icon } from "./Icon";

export interface Chip {
  value: string;
  label: string;
}

/** A row of removable chips (the user's languages, topics). ``minItems`` keeps the last ones from being removed. */
export function ChipList({
  items,
  onRemove,
  minItems = 0,
  label,
}: {
  items: Chip[];
  onRemove: (value: string) => void;
  minItems?: number;
  /** What the list is, for screen readers. */
  label: string;
}) {
  const { t } = useI18n();
  const canRemove = items.length > minItems;
  return (
    <ul className="chip-list" aria-label={label}>
      {items.map((c) => (
        <li key={c.value} className="chip">
          <span>{c.label}</span>
          {canRemove ? (
            <button
              type="button"
              className="chip-remove"
              aria-label={t("common.removeItem", { item: c.label })}
              title={t("common.removeItem", { item: c.label })}
              onClick={() => onRemove(c.value)}
            >
              <Icon name="close" size={12} strokeWidth={2.4} />
            </button>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
