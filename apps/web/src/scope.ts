import type { LibraryBook } from "./api";

export type SearchScope =
  | { kind: "library" }
  | { kind: "author"; authorIdentity: string }
  | { kind: "book"; bookId: string };

export type AuthorOption = {
  name: string;
  identity: string;
  bookCount: number;
};

export const WHOLE_LIBRARY_SCOPE: SearchScope = { kind: "library" };

export function authorOptionsForBooks(books: LibraryBook[]): AuthorOption[] {
  const authors = new Map<string, AuthorOption>();

  for (const book of books) {
    const identitiesInBook = new Set<string>();
    for (const rawName of book.authors) {
      const name = rawName.trim();
      if (!name) continue;
      const identity = normalizeAuthorIdentity(name);
      if (identitiesInBook.has(identity)) continue;
      identitiesInBook.add(identity);

      const existing = authors.get(identity);
      if (existing) {
        existing.bookCount += 1;
      } else {
        authors.set(identity, { name, identity, bookCount: 1 });
      }
    }
  }

  return [...authors.values()].sort((left, right) =>
    left.identity < right.identity ? -1 : left.identity > right.identity ? 1 : 0
  );
}

export function normalizeAuthorIdentity(name: string): string {
  return normalizeScopeText(name);
}

export function normalizeScopeText(value: string): string {
  return value.trim().normalize("NFKC").toLocaleLowerCase("en-US");
}

export function sameScope(left: SearchScope, right: SearchScope): boolean {
  if (left.kind !== right.kind) return false;
  if (left.kind === "author" && right.kind === "author") return left.authorIdentity === right.authorIdentity;
  if (left.kind === "book" && right.kind === "book") return left.bookId === right.bookId;
  return left.kind === "library" && right.kind === "library";
}

export function authorScopeValue(author: AuthorOption): string {
  return `scope:author:${encodeURIComponent(author.identity)}`;
}

export function bookScopeValue(book: LibraryBook): string {
  return `scope:book:${encodeURIComponent(book.id)}`;
}

export const WHOLE_LIBRARY_SCOPE_VALUE = "scope:library";
