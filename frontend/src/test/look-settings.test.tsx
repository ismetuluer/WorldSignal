import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { updateSettings: vi.fn() } };
});

import { api } from "../api/client";
import { LookSettings } from "../pages/LookSettings";
import { applyLook } from "../state";
import { renderWithApp } from "./render";

const mocked = vi.mocked(api, true);

beforeEach(() => {
  vi.resetAllMocks();
  mocked.updateSettings.mockImplementation(async (p) => p as never);
});

describe("applyLook", () => {
  it("sets the font, the colour (with matching greys) and the zoom, and takes them off again", () => {
    const root = document.createElement("html");
    applyLook(root, { font: "Georgia, serif", scale: 125, color: "#112233" });
    expect(root.style.getPropertyValue("--font")).toBe("Georgia, serif, sans-serif");
    expect(root.style.getPropertyValue("--text")).toBe("#112233");
    expect(root.style.getPropertyValue("--text-2")).toContain("#112233 72%");
    expect(root.style.getPropertyValue("zoom")).toBe("1.25");
    applyLook(root, { font: "", scale: 100, color: "" });
    for (const name of ["--font", "--font-display", "--text", "--text-2", "--text-3", "zoom"]) {
      expect(root.style.getPropertyValue(name)).toBe("");
    }
  });
});

describe("Look settings", () => {
  it("picks a preset font, a size and a colour", async () => {
    const user = userEvent.setup();
    renderWithApp(<LookSettings />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Yazı tipi" }), "Georgia, 'Times New Roman', serif");
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.font": "Georgia, 'Times New Roman', serif" }));
    await user.selectOptions(screen.getByRole("combobox", { name: "Yazı boyutu" }), "125");
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.font_scale": 125 }));
    const colour = screen.getByLabelText("Açık tema") as HTMLInputElement;
    colour.focus();
    // a colour input takes its value from the script, not from typing
    const { fireEvent } = await import("@testing-library/react");
    fireEvent.change(colour, { target: { value: "#336699" } });
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.text_color_light": "#336699" }));
  });

  it("takes any installed font by name and refuses characters CSS could abuse", async () => {
    const user = userEvent.setup();
    renderWithApp(<LookSettings />);
    await user.selectOptions(screen.getByRole("combobox", { name: "Yazı tipi" }), "__other__");
    const name = screen.getByRole("textbox", { name: "Yazı tipi adı" });
    await user.type(name, "Calibri{Enter}");
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.font": "Calibri" }));
    await user.clear(name);
    await user.type(name, "a;b{{c}");
    await user.tab();
    expect(name).toHaveAttribute("aria-invalid", "true");
    expect(mocked.updateSettings).toHaveBeenCalledTimes(1);
  });

  it("goes back to the theme's own colour", async () => {
    const user = userEvent.setup();
    renderWithApp(<LookSettings />, { "ui.text_color_dark": "#ffeecc" });
    const buttons = screen.getAllByRole("button", { name: "Temanınki" });
    expect(buttons[0]).toBeDisabled();
    await user.click(buttons[1]!);
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ui.text_color_dark": "" }));
  });
});
