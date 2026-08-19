import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "./main";

describe("Librarian sample interactions", () => {
  beforeEach(() => {
    HTMLElement.prototype.scrollIntoView = vi.fn();
  });

  afterEach(cleanup);

  it("shows the selected starter prompt in the grounded answer", async () => {
    const user = userEvent.setup();
    render(<App />);

    await user.click(screen.getByRole("button", { name: "A sea adventure" }));

    expect(screen.getByDisplayValue("Which book should I read for an adventure at sea?")).toBeTruthy();
    expect(screen.getByText("Start with Moby-Dick if you want an expedition", { exact: false })).toBeTruthy();
  });

  it("toggles a citation passage", async () => {
    const user = userEvent.setup();
    render(<App />);
    const citation = screen.getByRole("button", { name: /Frankenstein.*Chapter 4/ });

    await user.click(citation);

    expect(citation.className).toContain("open");
  });

  it("uses a book card to update the sample answer", async () => {
    const user = userEvent.setup();
    render(<App />);

    const book = screen.getByRole("heading", { name: "Moby-Dick" }).closest("article");
    if (!book) throw new Error("Moby-Dick book card was not rendered");

    await user.click(within(book).getByRole("button", { name: "Ask about this book →" }));

    expect(screen.getByText("Which book should I read for an adventure at sea?")).toBeTruthy();
    expect(HTMLElement.prototype.scrollIntoView).toHaveBeenCalled();
  });
});
