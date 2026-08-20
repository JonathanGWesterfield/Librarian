import { useEffect, useMemo, useRef, useState, type CSSProperties, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import { askChat, getBooks, type ChatResponse, type LibraryBook } from "./api";
import { ActivitySection } from "./activity";
import {
  WHOLE_LIBRARY_SCOPE,
  WHOLE_LIBRARY_SCOPE_VALUE,
  authorOptionsForBooks,
  authorScopeValue,
  bookScopeValue,
  sameScope,
  type SearchScope,
} from "./scope";
import "../styles.css";

const starterPrompts = [
  "What themes connect the books in my library?",
  "Which book should I read next?",
  "Find a passage about ambition and responsibility.",
];

const cardColors = [
  ["#d8e6c7", "#193e32"],
  ["#b8d6df", "#123e4b"],
  ["#f1cfbd", "#713727"],
  ["#ded4ed", "#453359"],
];

export function App() {
  const [books, setBooks] = useState<LibraryBook[]>([]);
  const [booksLoading, setBooksLoading] = useState(true);
  const [booksError, setBooksError] = useState<string | null>(null);
  const [scope, setScope] = useState<SearchScope>(WHOLE_LIBRARY_SCOPE);
  const [question, setQuestion] = useState("");
  const [chat, setChat] = useState<ChatResponse | null>(null);
  const [chatLoading, setChatLoading] = useState(false);
  const [chatError, setChatError] = useState<string | null>(null);
  const [openCitation, setOpenCitation] = useState<number | null>(null);
  const chatRequestGeneration = useRef(0);
  const booksRequestGeneration = useRef(0);
  const appMounted = useRef(true);
  const scopeRef = useRef<SearchScope>(WHOLE_LIBRARY_SCOPE);
  const authorOptions = useMemo(() => authorOptionsForBooks(books), [books]);
  const selectedBook = scope.kind === "book" ? books.find((book) => book.id === scope.bookId) ?? null : null;
  const selectedAuthor = scope.kind === "author" ? authorOptions.find((author) => author.identity === scope.authorIdentity) ?? null : null;

  const changeScope = (nextScope: SearchScope) => {
    if (sameScope(nextScope, scopeRef.current)) return;
    scopeRef.current = nextScope;
    chatRequestGeneration.current += 1;
    setScope(nextScope);
    setChat(null);
    setOpenCitation(null);
    setChatError(null);
    setChatLoading(false);
  };

  useEffect(() => {
    appMounted.current = true;
    void loadBooks();
    return () => {
      appMounted.current = false;
      booksRequestGeneration.current += 1;
      chatRequestGeneration.current += 1;
    };
  }, []);

  async function loadBooks() {
    const requestGeneration = ++booksRequestGeneration.current;
    setBooksLoading(true);
    setBooksError(null);
    try {
      const nextBooks = await getBooks();
      if (!appMounted.current || requestGeneration !== booksRequestGeneration.current) return;
      const nextAuthors = authorOptionsForBooks(nextBooks);
      const currentScope = scopeRef.current;
      const scopeStillExists = currentScope.kind === "library"
        || (currentScope.kind === "book" && nextBooks.some((book) => book.id === currentScope.bookId))
        || (currentScope.kind === "author" && nextAuthors.some((author) => author.identity === currentScope.authorIdentity));
      setBooks(nextBooks);
      if (!scopeStillExists) changeScope(WHOLE_LIBRARY_SCOPE);
    } catch (error) {
      if (appMounted.current && requestGeneration === booksRequestGeneration.current) {
        setBooksError(messageFor(error, "Unable to load your library."));
      }
    } finally {
      if (appMounted.current && requestGeneration === booksRequestGeneration.current) setBooksLoading(false);
    }
  }

  const chooseBook = (book: LibraryBook) => {
    changeScope({ kind: "book", bookId: book.id });
    document.getElementById("question")?.focus();
    document.getElementById("explore")?.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const selectScope = (value: string) => {
    if (value === WHOLE_LIBRARY_SCOPE_VALUE) {
      changeScope(WHOLE_LIBRARY_SCOPE);
      return;
    }
    const author = authorOptions.find((option) => authorScopeValue(option) === value);
    if (author) {
      changeScope({ kind: "author", authorIdentity: author.identity });
      return;
    }
    const book = books.find((option) => bookScopeValue(option) === value);
    if (book) changeScope({ kind: "book", bookId: book.id });
  };

  const choosePrompt = (prompt: string) => {
    setQuestion(prompt);
    document.getElementById("question")?.focus();
  };

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const submittedQuestion = question.trim();
    if (!submittedQuestion || chatLoading) return;

    const requestGeneration = ++chatRequestGeneration.current;
    setChatLoading(true);
    setChatError(null);
    try {
      const response = await askChat(
        submittedQuestion,
        selectedBook ? { bookId: selectedBook.id } : selectedAuthor ? { author: selectedAuthor.name } : {},
      );
      if (requestGeneration !== chatRequestGeneration.current) return;
      setChat(response);
      setOpenCitation(null);
      document.getElementById("workspace")?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (error) {
      if (requestGeneration !== chatRequestGeneration.current) return;
      setChatError(messageFor(error, "Unable to answer that question right now."));
    } finally {
      if (requestGeneration === chatRequestGeneration.current) {
        setChatLoading(false);
      }
    }
  };

  const selectedScopeValue = selectedBook
    ? bookScopeValue(selectedBook)
    : selectedAuthor
      ? authorScopeValue(selectedAuthor)
      : WHOLE_LIBRARY_SCOPE_VALUE;

  return <main className="app-shell">
    <nav className="topbar" aria-label="Primary navigation">
      <a className="brand" href="#explore" aria-label="Librarian home"><span className="brand-mark" aria-hidden="true">L</span><span>Librarian</span></a>
      <div className="nav-links"><a className="active" href="#explore">Explore</a><a href="#library">Library</a><a href="#activity">Activity</a><a href="#how-it-works">How it works</a></div>
      <a className="github-link" href="https://github.com/JonathanGWesterfield/Librarian" target="_blank" rel="noreferrer">View source <span aria-hidden="true">↗</span></a>
    </nav>

    <section id="explore" className="hero">
      <p className="eyebrow">Your local, evidence-first reading assistant</p>
      <h1>Ask the library.<br /><em>See the evidence.</em></h1>
      <p className="hero-copy">Explore your EPUB library with grounded answers that link directly back to the passages that support them.</p>
      <form className="question-form" onSubmit={submit} aria-busy={chatLoading}>
        <label className="sr-only" htmlFor="question">Ask a question about your library</label>
        <input id="question" autoComplete="off" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about your books" disabled={chatLoading} />
        <label className="scope-control"><span>Scope</span><select aria-label="Search scope" value={selectedScopeValue} onChange={(event) => selectScope(event.target.value)} disabled={booksLoading}>
          <option value={WHOLE_LIBRARY_SCOPE_VALUE}>Whole library</option>
          {authorOptions.length > 0 && <optgroup label="Authors">{authorOptions.map((author) => <option key={author.identity} value={authorScopeValue(author)}>{author.name} ({author.bookCount} {author.bookCount === 1 ? "book" : "books"})</option>)}</optgroup>}
          {books.length > 0 && <optgroup label="Books">{books.map((book) => <option key={book.id} value={bookScopeValue(book)}>{bookTitle(book)}</option>)}</optgroup>}
        </select></label>
        <button type="submit" disabled={chatLoading || !question.trim()}>{chatLoading ? "Asking…" : <>Ask <span aria-hidden="true">→</span></>}</button>
      </form>
      {chatLoading && <p className="request-status" role="status">Searching your local library and preparing an evidence-backed answer…</p>}
      {chatError && <p className="request-error" role="alert">{chatError} Try again after checking that the local API is running.</p>}
      <div className="starter-row" aria-label="Suggested questions"><span>Try a question</span>{starterPrompts.map((prompt) => <button type="button" key={prompt} onClick={() => choosePrompt(prompt)} disabled={chatLoading}>{prompt}</button>)}</div>
    </section>

    <section id="workspace" className="workspace" aria-labelledby="answer-heading">
      <aside className="filters">
        <div className="filter-heading"><span>Search scope</span>{scope.kind !== "library" && <button type="button" onClick={() => changeScope(WHOLE_LIBRARY_SCOPE)}>Whole library</button>}</div>
        <fieldset><legend>Current scope</legend>
          <label><input type="radio" name="scope" checked={scope.kind === "library"} onChange={() => changeScope(WHOLE_LIBRARY_SCOPE)} /> Whole library <span>{books.length}</span></label>
          {selectedAuthor && <label><input type="radio" name="scope" checked readOnly /> {selectedAuthor.name} <span>{selectedAuthor.bookCount} {selectedAuthor.bookCount === 1 ? "book" : "books"}</span></label>}
          {selectedBook && <label><input type="radio" name="scope" checked readOnly /> {bookTitle(selectedBook)} <span>{selectedBook.chunk_count} chunks</span></label>}
        </fieldset>
        <div className="demo-note"><span className="note-icon">i</span><p>{selectedBook ? `Answers will use passages from ${bookTitle(selectedBook)} only.` : selectedAuthor ? `Answers will use books credited to ${selectedAuthor.name}.` : "Answers search your entire local library."}</p></div>
      </aside>
      <div className="answer-area">
        <div className="answer-meta"><p id="answer-heading" className="eyebrow">Grounded answer</p><span>{chat ? `${chat.sources.length} supporting passages` : "Ask a question to begin"}</span></div>
        {chat ? <>
          <article className="answer-card" aria-live="polite"><div className="answer-number">01</div><div><p className="asked-question">{chat.question}</p><p className="answer-text">{chat.answer}</p><div className="tag-row"><span>{chat.candidate_count} retrieved chunks</span>{selectedBook && <span>{bookTitle(selectedBook)}</span>}{selectedAuthor && <span>{selectedAuthor.name}</span>}</div></div></article>
          <div className="citations-header"><div><p className="eyebrow">Traceable sources</p><h2>Read the passages</h2></div><span>{chat.sources.length} citations</span></div>
          {chat.sources.length ? <div className="citations">{chat.sources.map((source, index) => <button key={source.chunk_id} className={`citation${openCitation === index ? " open" : ""}`} type="button" onClick={() => setOpenCitation((current) => current === index ? null : index)}><span className="citation-summary"><span className="citation-number">{source.source_id}</span><span><span className="citation-title">{source.title || source.relative_path}</span><span className="citation-subtitle">{source.authors.join(", ") || "Unknown author"} · Chunk {source.chunk_index + 1}</span></span><span className="citation-toggle">+</span></span><span className="citation-quote">{source.text}</span></button>)}</div> : <p className="empty-answer">The library did not return supporting passages for this answer.</p>}
        </> : <article className="answer-card answer-empty"><div className="answer-number">01</div><div><p className="asked-question">Ready when you are</p><p className="answer-text">Ask a question to receive an answer grounded in passages from your own library.</p></div></article>}
      </div>
    </section>

    <section id="library" className="library-section"><div className="section-heading"><div><p className="eyebrow">Your collection</p><h2>Your books, made explorable.</h2></div><p>{booksLoading ? "Loading your local library…" : `${books.length} ${books.length === 1 ? "book" : "books"} available to search.`}</p></div><div className="book-grid">{booksLoading ? <p className="library-state" role="status">Loading your library…</p> : booksError ? <div className="library-state" role="alert"><p>{booksError}</p><button type="button" onClick={() => void loadBooks()}>Retry loading library</button></div> : books.length ? books.map((book, index) => <BookCard key={book.id} book={book} index={index} selected={scope.kind === "book" && book.id === scope.bookId} onChoose={chooseBook} />) : <p className="library-state">No books are available yet. Add EPUBs and run ingestion, then refresh this page.</p>}</div></section>

    <ActivitySection onLibraryUpdated={loadBooks} />

    <section id="how-it-works" className="how-section"><div><p className="eyebrow">Under the hood</p><h2>Designed for answers you can inspect.</h2></div><ol className="pipeline">{[["Ingest", "Parse EPUBs into structured, source-aware chunks."], ["Retrieve", "Find passages relevant to your question and selected scope."], ["Ground", "Build answers only from the passages the system found."], ["Inspect", "Open citations to read the source passages in full."]].map(([title, description], index) => <li key={title}><span>0{index + 1}</span><strong>{title}</strong><p>{description}</p></li>)}</ol></section>
    <footer><p>Built as an AI engineering portfolio project.</p><p>© 2026 Librarian <span aria-hidden="true">·</span> <a href="https://github.com/JonathanGWesterfield/Librarian" target="_blank" rel="noreferrer">GitHub ↗</a></p></footer>
  </main>;
}

function BookCard({ book, index, selected, onChoose }: { book: LibraryBook; index: number; selected: boolean; onChoose: (book: LibraryBook) => void }) {
  const [color, ink] = cardColors[index % cardColors.length];
  return <article className={`book${selected ? " selected-book" : ""}`} style={{ "--book-color": color, "--book-ink": ink } as CSSProperties}><div className="book-top"><span>{String(index + 1).padStart(2, "0")}</span><span>{book.chunk_count} chunks</span></div><h3>{bookTitle(book)}</h3><p>{book.authors.join(", ") || "Unknown author"}<br />{book.status}</p><button type="button" onClick={() => onChoose(book)}>Ask about this book <span aria-hidden="true">→</span></button></article>;
}

function bookTitle(book: LibraryBook): string {
  return book.title || book.relative_path;
}

function messageFor(error: unknown, fallback: string): string {
  return error instanceof Error && error.message ? error.message : fallback;
}

const root = document.getElementById("root");
if (root) {
  createRoot(root).render(<App />);
}
