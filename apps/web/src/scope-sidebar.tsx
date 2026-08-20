import type { LibraryBook } from "./api";
import {
  WHOLE_LIBRARY_SCOPE,
  normalizeAuthorIdentity,
  type AuthorOption,
  type SearchScope,
} from "./scope";

type ScopeSidebarProps = {
  books: LibraryBook[];
  authors: AuthorOption[];
  scope: SearchScope;
  onSelect: (scope: SearchScope) => void;
};

export function ScopeSidebar({ books, authors, scope, onSelect }: ScopeSidebarProps) {
  const selectedAuthor = scope.kind === "author" ? authors.find((author) => author.identity === scope.authorIdentity) : undefined;
  const selectedBook = scope.kind === "book" ? books.find((book) => book.id === scope.bookId) : undefined;
  const authorBooks = selectedAuthor
    ? books.filter((book) => book.authors.some((author) => normalizeAuthorIdentity(author) === selectedAuthor.identity))
    : [];
  const creditedAuthorIdentities = new Set(selectedBook?.authors.map(normalizeAuthorIdentity).filter(Boolean) ?? []);
  const creditedAuthors = selectedBook ? authors.filter((author) => creditedAuthorIdentities.has(author.identity)) : [];

  return <aside className="filters">
    <div className="filter-heading"><span>Search scope</span>{scope.kind !== "library" && <button type="button" onClick={() => onSelect(WHOLE_LIBRARY_SCOPE)}>Whole library</button>}</div>
    <fieldset><legend>Current scope</legend>
      <label><input type="radio" name="scope" checked={scope.kind === "library"} onChange={() => onSelect(WHOLE_LIBRARY_SCOPE)} /> Whole library <span>{books.length} {plural(books.length, "book")}</span></label>
      {selectedAuthor && <>
        <label><input type="radio" name="scope" checked readOnly /> All books by {selectedAuthor.name} <span>{selectedAuthor.bookCount} {plural(selectedAuthor.bookCount, "book")}</span></label>
        <p className="scope-subheading">Books by {selectedAuthor.name}</p>
        {authorBooks.map((book) => <label key={book.id}><input type="radio" name="scope" checked={false} onChange={() => onSelect({ kind: "book", bookId: book.id })} /> {bookTitle(book)} <span>{book.chunk_count} chunks</span></label>)}
      </>}
      {selectedBook && <>
        <label><input type="radio" name="scope" checked readOnly /> {bookTitle(selectedBook)} <span>{selectedBook.chunk_count} chunks</span></label>
        {creditedAuthors.length > 0 && <p className="scope-subheading">Widen to an author</p>}
        {creditedAuthors.map((author) => <label key={author.identity}><input type="radio" name="scope" checked={false} onChange={() => onSelect({ kind: "author", authorIdentity: author.identity })} /> All books by {author.name} <span>{author.bookCount} {plural(author.bookCount, "book")}</span></label>)}
      </>}
    </fieldset>
    <div className="demo-note"><span className="note-icon">i</span><p>{selectedBook ? `Answers will use passages from ${bookTitle(selectedBook)} only.` : selectedAuthor ? `Answers will use books credited to ${selectedAuthor.name}.` : "Answers search your entire local library."}</p></div>
  </aside>;
}

function bookTitle(book: LibraryBook): string {
  return book.title?.trim() || book.relative_path;
}

function plural(count: number, singular: string): string {
  return count === 1 ? singular : `${singular}s`;
}
