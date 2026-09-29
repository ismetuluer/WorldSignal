import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReleaseNotes } from "../components/Update";
import { parseInline, parseNotes } from "../lib/releaseNotes";

// The CHANGELOG wraps its lines at ~120 characters; a bullet continues on indented lines.
const NOTES = [
  "### Düzeltildi",
  "- **Güncelleme başarısız oluyordu.** World Signal Dosya",
  "  Gezgini'nden açıldığında klasör kullanımda kalıyordu.",
  "  - İç madde `bge-m3` ile",
  "    devam ediyor.",
  "",
  "Serbest paragraf",
  "ikinci satır.",
  "### Eklendi",
  "* Yıldızlı madde",
].join("\n");

describe("release notes", () => {
  it("joins wrapped lines into one bullet or paragraph", () => {
    expect(parseNotes(NOTES)).toEqual([
      { kind: "heading", text: "Düzeltildi" },
      {
        kind: "item",
        level: 0,
        text: "**Güncelleme başarısız oluyordu.** World Signal Dosya Gezgini'nden açıldığında klasör kullanımda kalıyordu.",
      },
      { kind: "item", level: 1, text: "İç madde `bge-m3` ile devam ediyor." },
      { kind: "paragraph", text: "Serbest paragraf ikinci satır." },
      { kind: "heading", text: "Eklendi" },
      { kind: "item", level: 0, text: "Yıldızlı madde" },
    ]);
  });

  it("reads Windows line endings and empty notes", () => {
    expect(parseNotes("- a\r\n  b\r\n")).toEqual([{ kind: "item", level: 0, text: "a b" }]);
    expect(parseNotes("")).toEqual([]);
  });

  it("finds bold and code, and leaves a lone asterisk as text", () => {
    expect(parseInline("**Kalın** ve `kod` ile 2 * 3")).toEqual([
      { text: "Kalın", bold: true },
      { text: " ve " },
      { text: "kod", code: true },
      { text: " ile 2 * 3" },
    ]);
  });

  it("shows headings, bullets and bold text without markdown characters", () => {
    const { container } = render(<ReleaseNotes notes={NOTES} />);
    expect(screen.getByRole("heading", { name: "Düzeltildi" })).toBeInTheDocument();
    expect(screen.getByText("Güncelleme başarısız oluyordu.").tagName).toBe("STRONG");
    expect(screen.getByText("bge-m3").tagName).toBe("CODE");
    expect(container.querySelectorAll(".release-item")).toHaveLength(3);
    expect(container.querySelector(".release-item.level-1")).not.toBeNull();
    expect(container.textContent).not.toMatch(/###|\*\*|`/);
  });
});
