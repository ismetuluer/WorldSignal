import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("../api/client", async (importOriginal) => {
  const original = await importOriginal<typeof import("../api/client")>();
  return { ...original, api: { updateSettings: vi.fn() } };
});

import { api } from "../api/client";
import { PromptSettings } from "../pages/PromptSettings";
import { renderWithApp } from "./render";

const mocked = vi.mocked(api, true);

beforeEach(() => {
  vi.resetAllMocks();
  mocked.updateSettings.mockImplementation(async (p) => p as never);
});

const editor = () => screen.getByRole("textbox", { name: "Haber özeti" }) as HTMLTextAreaElement;

describe("AI instruction settings", () => {
  it("shows the default text and says so", () => {
    renderWithApp(<PromptSettings />);
    expect(editor().value).toBe("Default article. {fields}");
    expect(screen.getAllByText("Varsayılan metin kullanılıyor.")).toHaveLength(2); // the instruction and the layout
    expect(screen.getAllByRole("button", { name: "Talimatı kaydet" })[0]!).toBeDisabled();
    expect(screen.getAllByRole("button", { name: "Talimatı varsayılana döndür" })[0]!).toBeDisabled();
  });

  it("saves an edited text for the chosen task only", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />);
    await user.type(editor(), " Be brief.");
    await user.click(screen.getAllByRole("button", { name: "Talimatı kaydet" })[0]!);
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.prompts": { article: "Default article. {fields} Be brief." } }));
    expect(await screen.findByText("Talimat kaydedildi.")).toBeInTheDocument();
  });

  it("shows the user's own text, keeps other tasks, and goes back to the default", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />, { "ai.prompts": { article: "Mine {fields}", translate: "Translate into {language}!" } });
    expect(editor().value).toBe("Mine {fields}");
    expect(screen.getAllByText("Kendi metniniz kullanılıyor.")).toHaveLength(1);
    await user.click(screen.getAllByRole("button", { name: "Talimatı varsayılana döndür" })[0]!);
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.prompts": { translate: "Translate into {language}!" } }));
  });

  it("refuses a text the model could not use, and tells why", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />);
    await user.click(screen.getByRole("button", { name: "Tam metin çevirisi" }));
    const box = screen.getByRole("textbox", { name: "Tam metin çevirisi" });
    await user.clear(box);
    await user.type(box, "Translate it");
    expect(screen.getByRole("alert")).toHaveTextContent("{language}");
    expect(screen.getAllByRole("button", { name: "Talimatı kaydet" })[0]!).toBeDisabled();
    await user.type(box, " into {{language}");  // "{{" types a literal "{"
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Talimatı kaydet" })[0]!).toBeEnabled();
  });

  it("mentions that {fields} is added when left out", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />);
    await user.clear(editor());
    await user.type(editor(), "Short rules.");
    expect(screen.getByText(/çıktı alanlarının açıklaması metnin sonuna programca eklenir/)).toBeInTheDocument();
  });

  it("saves a layout of the report and keeps the instructions apart", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />);
    const layout = screen.getByRole("textbox", { name: "Haberin istekteki düzeni" });
    await user.clear(layout);
    await user.type(layout, "{{title}: {{text}");
    await user.click(screen.getAllByRole("button", { name: "Talimatı kaydet" })[1]!);
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.inputs": { article: "{title}: {text}" } }));
  });

  it("refuses a layout without the headline", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />);
    const layout = screen.getByRole("textbox", { name: "Haberin istekteki düzeni" });
    await user.clear(layout);
    await user.type(layout, "only text");
    expect(screen.getByRole("alert")).toHaveTextContent("{title}");
    expect(screen.getAllByRole("button", { name: "Talimatı kaydet" })[1]).toBeDisabled();
  });

  it("saves an amount inside its range, refuses one outside it, and empty means the default", async () => {
    const user = userEvent.setup();
    renderWithApp(<PromptSettings />, { "ai.limits": { batch_size: 5 } });
    const size = screen.getByLabelText(/Tek istekte kaç haber/);
    expect((size as HTMLInputElement).value).toBe("5");
    await user.clear(size);
    await user.type(size, "99{Enter}");
    expect(mocked.updateSettings).not.toHaveBeenCalled();
    expect(size).toHaveAttribute("aria-invalid", "true");
    await user.clear(size);
    await user.type(size, "7{Enter}");
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenCalledWith({ "ai.limits": { batch_size: 7 } }));
    await user.clear(size);
    await user.tab();
    await waitFor(() => expect(mocked.updateSettings).toHaveBeenLastCalledWith({ "ai.limits": {} }));
  });
});
