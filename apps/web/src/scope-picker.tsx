import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";
import type { LibraryBook } from "./api";
import {
  WHOLE_LIBRARY_SCOPE,
  authorScopeValue,
  bookScopeValue,
  normalizeScopeText,
  sameScope,
  type AuthorOption,
  type SearchScope,
} from "./scope";

type ScopePickerProps = {
  books: LibraryBook[];
  authors: AuthorOption[];
  scope: SearchScope;
  disabled?: boolean;
  onSelect: (scope: SearchScope) => void;
};

type PickerResult = {
  key: string;
  group: "library" | "authors" | "books";
  label: string;
  detail: string;
  scope: SearchScope;
};

export function ScopePicker({ books, authors, scope, disabled = false, onSelect }: ScopePickerProps) {
  const id = useId().replace(/:/g, "");
  const inputId = `${id}-scope-search`;
  const listboxId = `${id}-scope-options`;
  const currentId = `${id}-current-scope`;
  const rootRef = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(-1);

  const selectedAuthor = scope.kind === "author" ? authors.find((author) => author.identity === scope.authorIdentity) : undefined;
  const selectedBook = scope.kind === "book" ? books.find((book) => book.id === scope.bookId) : undefined;
  const currentLabel = selectedAuthor?.name ?? (selectedBook ? bookTitle(selectedBook) : "Whole library");
  const results = useMemo(() => pickerResults(books, authors, query), [authors, books, query]);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) closePicker();
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  useEffect(() => {
    closePicker();
  }, [scope.kind, scope.kind === "author" ? scope.authorIdentity : scope.kind === "book" ? scope.bookId : "library"]);

  useEffect(() => {
    if (disabled) closePicker();
  }, [disabled]);

  useEffect(() => {
    if (!open || activeIndex < 0) return;
    document.getElementById(optionId(id, activeIndex))?.scrollIntoView({ block: "nearest" });
  }, [activeIndex, id, open]);

  function openPicker(initialActiveIndex = -1) {
    if (disabled || open) return;
    setQuery("");
    setActiveIndex(initialActiveIndex);
    setOpen(true);
  }

  function closePicker() {
    setOpen(false);
    setQuery("");
    setActiveIndex(-1);
  }

  function selectResult(result: PickerResult) {
    onSelect(result.scope);
    closePicker();
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      closePicker();
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (!open) {
        openPicker();
        return;
      }
      const result = results[activeIndex >= 0 ? activeIndex : 0];
      if (result) selectResult(result);
      return;
    }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        openPicker(event.key === "ArrowDown" ? 0 : Math.max(results.length - 1, -1));
        return;
      }
      if (!results.length) return;
      setActiveIndex((current) => {
        if (event.key === "ArrowDown") return current < results.length - 1 ? current + 1 : 0;
        return current > 0 ? current - 1 : results.length - 1;
      });
      return;
    }
  }

  return <div className="scope-control" ref={rootRef}>
    <label className="scope-label" htmlFor={inputId}>Scope</label>
    <div className="scope-picker">
      <span className="current-scope" id={currentId}>Current: {currentLabel}</span>
      <input
        id={inputId}
        type="search"
        role="combobox"
        aria-label="Search scope"
        aria-describedby={currentId}
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listboxId}
        aria-activedescendant={open && activeIndex >= 0 ? optionId(id, activeIndex) : undefined}
        autoComplete="off"
        disabled={disabled}
        placeholder="Search authors or books"
        value={query}
        onFocus={() => openPicker()}
        onClick={() => openPicker()}
        onChange={(event) => {
          setQuery(event.target.value);
          setActiveIndex(-1);
          if (!open) setOpen(true);
        }}
        onKeyDown={onKeyDown}
      />
      {open && <div className="scope-options" id={listboxId} role="listbox" aria-label="Scope options">
        {results.length === 0 ? <p className="scope-empty" role="status">No authors or books match “{query.trim()}”.</p> : <>
          <ResultGroup group="library" label="Library" results={results} allResults={results} componentId={id} activeIndex={activeIndex} selectedScope={scope} onSelect={selectResult} />
          <ResultGroup group="authors" label="Authors" results={results} allResults={results} componentId={id} activeIndex={activeIndex} selectedScope={scope} onSelect={selectResult} />
          <ResultGroup group="books" label="Books" results={results} allResults={results} componentId={id} activeIndex={activeIndex} selectedScope={scope} onSelect={selectResult} />
        </>}
      </div>}
    </div>
  </div>;
}

function ResultGroup({ group, label, results, allResults, componentId, activeIndex, selectedScope, onSelect }: {
  group: PickerResult["group"];
  label: string;
  results: PickerResult[];
  allResults: PickerResult[];
  componentId: string;
  activeIndex: number;
  selectedScope: SearchScope;
  onSelect: (result: PickerResult) => void;
}) {
  const groupedResults = results.filter((result) => result.group === group);
  if (!groupedResults.length) return null;
  const headingId = `${componentId}-${group}-heading`;
  return <div className="scope-option-group" role="group" aria-labelledby={headingId}>
    <p id={headingId}>{label}</p>
    {groupedResults.map((result) => {
      const index = allResults.indexOf(result);
      return <button
        key={result.key}
        id={optionId(componentId, index)}
        type="button"
        role="option"
        tabIndex={-1}
        aria-selected={sameScope(result.scope, selectedScope)}
        className={index === activeIndex ? "active" : ""}
        onMouseDown={(event) => event.preventDefault()}
        onClick={() => onSelect(result)}
      >
        <span>{result.label}</span>
        <small>{result.detail}</small>
      </button>;
    })}
  </div>;
}

function pickerResults(books: LibraryBook[], authors: AuthorOption[], query: string): PickerResult[] {
  const normalizedQuery = normalizeScopeText(query);
  const includesQuery = (value: string) => normalizeScopeText(value).includes(normalizedQuery);
  const results: PickerResult[] = [];

  if (!normalizedQuery || includesQuery("Whole library")) {
    results.push({ key: "library", group: "library", label: "Whole library", detail: `${books.length} ${plural(books.length, "book")}`, scope: WHOLE_LIBRARY_SCOPE });
  }
  for (const author of authors) {
    if (!normalizedQuery || includesQuery(author.name)) {
      results.push({ key: authorScopeValue(author), group: "authors", label: author.name, detail: `${author.bookCount} ${plural(author.bookCount, "book")}`, scope: { kind: "author", authorIdentity: author.identity } });
    }
  }
  for (const book of books) {
    if (!normalizedQuery || [bookTitle(book), ...book.authors].some(includesQuery)) {
      results.push({ key: bookScopeValue(book), group: "books", label: bookTitle(book), detail: book.authors.map((author) => author.trim()).filter(Boolean).join(", ") || "Unknown author", scope: { kind: "book", bookId: book.id } });
    }
  }
  return results;
}

function optionId(componentId: string, index: number): string {
  return `${componentId}-scope-option-${index}`;
}

function bookTitle(book: LibraryBook): string {
  return book.title?.trim() || book.relative_path;
}

function plural(count: number, singular: string): string {
  return count === 1 ? singular : `${singular}s`;
}
