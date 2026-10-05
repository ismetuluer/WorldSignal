import { useState } from "react";
import { useI18n } from "../i18n";

/** A card's summary, shortened to a few lines; pressing it shows the whole text (and again to shorten it). */
export function ExpandableSummary({ text, className = "", dir }: { text: string; className?: string; dir?: "ltr" | "rtl" }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  const toggle = () => {
    if (window.getSelection()?.toString()) return; // selecting text to copy is not a press
    setOpen((v) => !v);
  };
  return (
    <p
      className={`article-summary summary-toggle ${className} ${open ? "expanded" : ""}`.trim()}
      dir={dir}
      role="button"
      tabIndex={0}
      aria-expanded={open}
      title={open ? t("feed.summaryLess") : t("feed.summaryMore")}
      onClick={toggle}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          setOpen((v) => !v);
        }
      }}
    >
      {text}
    </p>
  );
}
