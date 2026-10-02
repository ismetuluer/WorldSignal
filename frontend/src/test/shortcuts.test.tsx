import { fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useRef } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { updateSettings: vi.fn() } };
});

import { api } from "../api/client";
import { DEFAULT_SHORTCUTS, hintKeys, isAssignable, keyLabel, keyOf, resolveShortcuts, takenBy } from "../lib/shortcuts";
import { useListKeys } from "../pages/feedShared";
import { ShortcutSettings } from "../pages/ShortcutSettings";
import { renderWithApp } from "./render";

const mocked = vi.mocked(api, true);

beforeEach(() => {
  vi.resetAllMocks();
  mocked.updateSettings.mockImplementation(async (p) => p as never);
});

describe("shortcut helpers", () => {
  it("names keys the way settings store them, and refuses what cannot be given", () => {
    expect(keyOf({ key: " " })).toBe("space");
    expect(keyOf({ key: "J" })).toBe("j");
    expect(keyOf({ key: "Shift" })).toBeNull();
    for (const ok of ["j", "/", "ş", "enter", "arrowdown", "f5", "space", "1"]) expect(isAssignable(ok)).toBe(true);
    for (const bad of ["escape", "tab", "ab", "f13", "", null]) expect(isAssignable(bad)).toBe(false);
    expect(keyLabel("arrowup")).toBe("↑");
    expect(keyLabel("f5")).toBe("F5");
    expect(keyLabel("j")).toBe("J");
  });

  it("resolves the user's keys over the defaults and finds who owns a key", () => {
    const map = resolveShortcuts({ next: ["n"], prev: [] });
    expect(map.next).toEqual(["n"]);
    expect(map.prev).toEqual(DEFAULT_SHORTCUTS.prev); // an empty list falls back
    expect(takenBy(map, "n", "prev")).toBe("next");
    expect(takenBy(map, "n", "next")).toBeNull();
    expect(hintKeys(map).next).toBe("N");
  });
});

function Harness({ onMeeting, onOpen }: { onMeeting: (i: number) => void; onOpen: (i: number) => void }) {
  const ref = useRef<HTMLUListElement>(null);
  const [selected] = useListKeys(ref, 3, () => undefined, (_, i) => onOpen(i), { meeting: onMeeting });
  return (
    <ul ref={ref}>
      {[0, 1, 2].map((i) => <li key={i} data-index={i} data-selected={selected === i}>{i}</li>)}
    </ul>
  );
}
const selected = () => document.querySelector("[data-selected=true]")?.textContent;

describe("the list follows the user's keys", () => {
  it("uses the defaults when nothing is changed", () => {
    const open = vi.fn(), meeting = vi.fn();
    renderWithApp(<Harness onMeeting={meeting} onOpen={open} />);
    fireEvent.keyDown(window, { key: "j" });
    fireEvent.keyDown(window, { key: "j" });
    expect(selected()).toBe("1");
    fireEvent.keyDown(window, { key: "t" });
    fireEvent.keyDown(window, { key: "Enter" });
    expect(meeting).toHaveBeenCalledWith(1);
    expect(open).toHaveBeenCalledWith(1);
  });

  it("uses the user's keys, and the old ones stop working", () => {
    const open = vi.fn(), meeting = vi.fn();
    renderWithApp(<Harness onMeeting={meeting} onOpen={open} />, {
      "ui.shortcuts": { next: ["n"], prev: ["p", "arrowup"], meeting: ["m"], open: ["space"] },
    });
    fireEvent.keyDown(window, { key: "j" });
    expect(selected()).toBeUndefined();
    fireEvent.keyDown(window, { key: "n" });
    fireEvent.keyDown(window, { key: "n" });
    expect(selected()).toBe("1");
    fireEvent.keyDown(window, { key: "ArrowUp" });
    expect(selected()).toBe("0");
    fireEvent.keyDown(window, { key: "m" });
    fireEvent.keyDown(window, { key: "t" });
    fireEvent.keyDown(window, { key: " " });
    expect(meeting).toHaveBeenCalledTimes(1);
    expect(open).toHaveBeenCalledWith(0);
  });
});

describe("Shortcut settings", () => {
  it("adds a key by pressing it, and refuses one another action owns", async () => {
    const user = userEvent.setup();
    renderWithApp(<ShortcutSettings />);
    await user.click(screen.getByRole("button", { name: "Sonraki haber için tuş ekle" }));
    expect(screen.getByText(/Bir tuşa basın/)).toBeInTheDocument();
    fireEvent.keyDown(document, { key: "k" }); // K belongs to "previous"
    expect(await screen.findByRole("alert")).toHaveTextContent("K tuşu \"Önceki haber\" için kullanılıyor.");
    expect(mocked.updateSettings).not.toHaveBeenCalled();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(screen.getByRole("alert")).toHaveTextContent("verilemez");
    fireEvent.keyDown(document, { key: "ArrowDown" });
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.shortcuts": { next: ["j", "arrowdown"] } }));
  });

  it("removes a key but never the last one, and goes back to the default", async () => {
    const user = userEvent.setup();
    renderWithApp(<ShortcutSettings />, { "ui.shortcuts": { open: ["enter", "o", "space"], next: ["n"] } });
    expect(screen.getByRole("button", { name: "N tuşunu kaldır (Sonraki haber)" })).toBeDisabled();
    await user.click(screen.getByRole("button", { name: "Space tuşunu kaldır (Seçili haberi tarayıcıda aç)" }));
    // ["enter", "o"] is the default for "open", so the setting drops it instead of storing the same thing
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.shortcuts": { next: ["n"] } }));
    await user.click(screen.getByRole("button", { name: "Tüm kısayolları varsayılana döndür" }));
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ui.shortcuts": {} }));
  });

  it("Esc cancels the listening without changing anything", async () => {
    const user = userEvent.setup();
    renderWithApp(<ShortcutSettings />);
    await user.click(screen.getByRole("button", { name: "Aramaya git için tuş ekle" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByText(/Bir tuşa basın/)).not.toBeInTheDocument();
    expect(mocked.updateSettings).not.toHaveBeenCalled();
  });
});
