import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { FormEvent } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { LibraryBook } from "./api";
import { ScopePicker } from "./scope-picker";
import { authorOptionsForBooks, WHOLE_LIBRARY_SCOPE } from "./scope";

const books: LibraryBook[] = [
  book("foundation", "Foundation", ["Isaac Asimov", "Jane Doe"]),
  book("isaac asimov", "The Caves of Steel", ["isaac asimov"]),
  book("earthsea", "A Wizard of Earthsea", ["Ursula K. Le Guin"]),
];
const authors = authorOptionsForBooks(books);

beforeEach(() => {
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(cleanup);

describe("ScopePicker", () => {
  it("opens with every author and book in labelled groups", async () => {
    const user = userEvent.setup();
    render(<ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={vi.fn()} />);

    await user.click(screen.getByRole("combobox", { name: "Search scope" }));

    const listbox = screen.getByRole("listbox", { name: "Scope options" });
    expect(within(listbox).getByText("Library")).toBeTruthy();
    expect(within(listbox).getByText("Authors")).toBeTruthy();
    expect(within(listbox).getByText("Books")).toBeTruthy();
    expect(within(listbox).getAllByRole("option")).toHaveLength(1 + authors.length + books.length);
    expect(within(listbox).getByRole("option", { name: /Isaac Asimov.*2 books/ })).toBeTruthy();
    expect(within(listbox).getByRole("option", { name: /A Wizard of Earthsea.*Ursula K. Le Guin/ })).toBeTruthy();
  });

  it("filters case-insensitively by author metadata and book title", async () => {
    const user = userEvent.setup();
    render(<ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.type(input, "ASIMOV");

    expect(screen.getByRole("option", { name: /Isaac Asimov.*2 books/ })).toBeTruthy();
    expect(screen.getByRole("option", { name: /Foundation.*Isaac Asimov/ })).toBeTruthy();
    expect(screen.getByRole("option", { name: /The Caves of Steel.*isaac asimov/i })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /A Wizard of Earthsea/ })).toBeNull();

    await user.clear(input);
    await user.type(input, "earthSEA");
    expect(screen.getByRole("option", { name: /A Wizard of Earthsea/ })).toBeTruthy();
    expect(screen.queryByRole("option", { name: /Foundation/ })).toBeNull();
  });

  it("shows a useful empty state", async () => {
    const user = userEvent.setup();
    render(<ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={vi.fn()} />);

    await user.click(screen.getByRole("combobox", { name: "Search scope" }));
    await user.type(screen.getByRole("combobox", { name: "Search scope" }), "no such writer");

    expect(screen.getByRole("status").textContent).toContain("No authors or books match");
    expect(screen.queryByRole("option")).toBeNull();
  });

  it("selects an author with the mouse without submitting anything", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={onSelect} /></form>);

    await user.click(screen.getByRole("combobox", { name: "Search scope" }));
    await user.click(screen.getByRole("option", { name: /Isaac Asimov.*2 books/ }));

    expect(onSelect).toHaveBeenCalledWith({ kind: "author", authorIdentity: "isaac asimov" });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.queryByRole("listbox")).toBeNull();
    expect((screen.getByRole("combobox", { name: "Search scope" }) as HTMLInputElement).value).toBe("");
  });

  it("selects a collision-safe book scope with the keyboard", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    render(<ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={onSelect} />);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.type(input, "caves");
    await user.keyboard("{ArrowDown}{Enter}");

    expect(onSelect).toHaveBeenCalledWith({ kind: "book", bookId: "isaac asimov" });
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("closes on Escape and outside pointer interaction without trapping focus", async () => {
    const user = userEvent.setup();
    render(<ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={vi.fn()} />);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.keyboard("{Escape}");
    expect(input.getAttribute("aria-expanded")).toBe("false");
    expect(document.activeElement).toBe(input);

    await user.click(input);
    await user.click(document.body);
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("reopens instead of submitting the parent form when Enter follows Escape", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={vi.fn()} /></form>);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.keyboard("{Escape}");
    expect(input.getAttribute("aria-expanded")).toBe("false");

    await user.keyboard("{Enter}");

    expect(onSubmit).not.toHaveBeenCalled();
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByRole("listbox", { name: "Scope options" })).toBeTruthy();
  });

  it("reopens on ArrowDown with the first option active and selects it without submitting", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><ScopePicker books={books} authors={authors} scope={{ kind: "book", bookId: "foundation" }} onSelect={onSelect} /></form>);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.keyboard("{Escape}{ArrowDown}");

    const firstOption = screen.getAllByRole("option")[0];
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(firstOption.id);
    expect(document.getElementById(input.getAttribute("aria-activedescendant") ?? "")).toBe(firstOption);

    await user.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledWith(WHOLE_LIBRARY_SCOPE);
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });

  it("reopens on ArrowUp with the last option active and selects it without submitting", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onSubmit = vi.fn((event: FormEvent) => event.preventDefault());
    render(<form onSubmit={onSubmit}><ScopePicker books={books} authors={authors} scope={WHOLE_LIBRARY_SCOPE} onSelect={onSelect} /></form>);
    const input = screen.getByRole("combobox", { name: "Search scope" });

    await user.click(input);
    await user.keyboard("{Escape}{ArrowUp}");

    const options = screen.getAllByRole("option");
    const lastOption = options[options.length - 1];
    expect(input.getAttribute("aria-expanded")).toBe("true");
    expect(input.getAttribute("aria-activedescendant")).toBe(lastOption.id);
    expect(document.getElementById(input.getAttribute("aria-activedescendant") ?? "")).toBe(lastOption);

    await user.keyboard("{Enter}");

    expect(onSelect).toHaveBeenCalledWith({ kind: "book", bookId: "earthsea" });
    expect(onSubmit).not.toHaveBeenCalled();
    expect(input.getAttribute("aria-expanded")).toBe("false");
  });
});

function book(id: string, title: string, authorNames: string[]): LibraryBook {
  return {
    id,
    relative_path: `${id}.epub`,
    title,
    authors: authorNames,
    publisher: null,
    status: "ingested",
    error_message: null,
    chunk_count: 10,
    chunk_duration_seconds: null,
  };
}
