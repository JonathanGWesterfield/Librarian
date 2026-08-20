import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { LibraryBook } from "./api";
import { authorOptionsForBooks } from "./scope";
import { ScopeSidebar } from "./scope-sidebar";

afterEach(cleanup);

describe("ScopeSidebar", () => {
  it("lists only books credited to the exact active author and narrows to one book", async () => {
    const books = [
      book("annals", "Annals", ["Ann"], 10),
      book("more-ann", "More by Ann", ["ann"], 12),
      book("anne", "Anne's Book", ["Anne"], 14),
    ];
    const authors = authorOptionsForBooks(books);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<ScopeSidebar books={books} authors={authors} scope={{ kind: "author", authorIdentity: "ann" }} onSelect={onSelect} />);

    expect(screen.getByRole("radio", { name: /All books by Ann.*2 books/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /Annals.*10 chunks/ })).toBeTruthy();
    expect(screen.getByRole("radio", { name: /More by Ann.*12 chunks/ })).toBeTruthy();
    expect(screen.queryByRole("radio", { name: /Anne's Book/ })).toBeNull();

    await user.click(screen.getByRole("radio", { name: /Annals.*10 chunks/ }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "book", bookId: "annals" });
  });

  it("offers every exact credited author on a multi-author book as a widening action", async () => {
    const books = [
      book("shared", "Shared Worlds", ["Isaac Asimov", "Jane Doe", "ISAAC ASIMOV"], 20),
      book("other", "Another Asimov", ["isaac asimov"], 9),
    ];
    const authors = authorOptionsForBooks(books);
    const onSelect = vi.fn();
    const user = userEvent.setup();
    render(<ScopeSidebar books={books} authors={authors} scope={{ kind: "book", bookId: "shared" }} onSelect={onSelect} />);

    expect(screen.getAllByRole("radio", { name: /All books by Isaac Asimov.*2 books/ })).toHaveLength(1);
    expect(screen.getByRole("radio", { name: /All books by Jane Doe.*1 book/ })).toBeTruthy();

    await user.click(screen.getByRole("radio", { name: /All books by Jane Doe.*1 book/ }));
    expect(onSelect).toHaveBeenCalledWith({ kind: "author", authorIdentity: "jane doe" });
  });
});

function book(id: string, title: string, authors: string[], chunks: number): LibraryBook {
  return {
    id,
    relative_path: `${id}.epub`,
    title,
    authors,
    publisher: null,
    status: "ingested",
    error_message: null,
    chunk_count: chunks,
    chunk_duration_seconds: null,
  };
}
