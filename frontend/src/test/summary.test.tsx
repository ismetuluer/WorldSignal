import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { ExpandableSummary } from "../components/ExpandableSummary";
import { renderWithApp } from "./render";

describe("A card's summary", () => {
  it("opens to its whole text when pressed, with the mouse or the keyboard, and shortens again", async () => {
    renderWithApp(<ExpandableSummary text="Uzun bir özet metni." />);
    const summary = screen.getByRole("button", { name: "Uzun bir özet metni." });
    expect(summary).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(summary);
    expect(summary).toHaveAttribute("aria-expanded", "true");
    expect(summary).toHaveClass("expanded");
    summary.focus();
    await userEvent.keyboard("{Enter}");
    expect(summary).toHaveAttribute("aria-expanded", "false");
  });
});
