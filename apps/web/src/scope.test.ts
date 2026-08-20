import { describe, expect, it } from "vitest";
import type { LibraryBook } from "./api";
import { authorOptionsForBooks } from "./scope";

describe("authorOptionsForBooks", () => {
  it("trims, omits blanks, deduplicates case-insensitively, counts exact identities, and sorts", () => {
    const books = [
      book("one", ["  Ursula K. Le Guin  ", "Isaac Asimov", "", "Ann"]),
      book("two", ["ursula k. le guin", " ISAAC ASIMOV ", "Ann", "ann"]),
      book("three", ["Anne", "  "]),
    ];

    expect(authorOptionsForBooks(books)).toEqual([
      { name: "Ann", identity: "ann", bookCount: 2 },
      { name: "Anne", identity: "anne", bookCount: 1 },
      { name: "Isaac Asimov", identity: "isaac asimov", bookCount: 2 },
      { name: "Ursula K. Le Guin", identity: "ursula k. le guin", bookCount: 2 },
    ]);
  });
});

function book(id: string, authors: string[]): LibraryBook {
  return {
    id,
    relative_path: `${id}.epub`,
    title: id,
    authors,
    publisher: null,
    status: "ingested",
    error_message: null,
    chunk_count: 1,
    chunk_duration_seconds: null,
  };
}
