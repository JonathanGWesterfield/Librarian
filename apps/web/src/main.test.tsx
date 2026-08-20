import { act, cleanup, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { UI_CHAT_RETRIEVAL_LIMIT } from "./api";
import { App } from "./main";

vi.mock("./activity", () => ({
  ActivitySection: ({ onLibraryUpdated }: { onLibraryUpdated: () => Promise<void> }) =>
    <button type="button" onClick={() => void onLibraryUpdated()}>Test refresh library</button>,
}));

const books = [
  {
    id: "book-1",
    relative_path: "foundation.epub",
    title: "Foundation",
    authors: ["Isaac Asimov"],
    publisher: "Gnome Press",
    status: "ingested",
    error_message: null,
    chunk_count: 42,
    chunk_duration_seconds: 1.2,
  },
];

const authorBooks = [
  books[0],
  {
    ...books[0],
    id: "isaac asimov",
    relative_path: "caves-of-steel.epub",
    title: "The Caves of Steel",
    authors: ["isaac asimov"],
    chunk_count: 37,
  },
];

const chatResponse = {
  question: "What is psychohistory?",
  answer: "Psychohistory predicts the broad movements of large populations [S1].",
  embedding_provider: "ollama",
  embedding_model: "all-minilm",
  generation_provider: "ollama",
  generation_model: "qwen2.5:1.5b",
  retrieval_limit: 30,
  candidate_count: 1,
  filters: {},
  sources: [
    {
      source_id: "S1",
      score: 0.9,
      chunk_id: "book-1:7",
      book_id: "book-1",
      relative_path: "foundation.epub",
      title: "Foundation",
      authors: ["Isaac Asimov"],
      chunk_index: 7,
      text: "Psychohistory was the science of predicting human behavior in the mass.",
    },
  ],
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  HTMLElement.prototype.scrollIntoView = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Librarian live API interactions", () => {
  it("loads live books and renders their BookRecord details", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(books));

    render(<App />);

    expect(screen.getByRole("status").textContent).toContain("Loading your library");
    const heading = await screen.findByRole("heading", { name: "Foundation" });
    const card = heading.closest("article");
    if (!card) throw new Error("book card was not rendered");
    expect(within(card).getByText("Isaac Asimov", { exact: false })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/books", expect.any(Object));
  });

  it("shows an actionable empty-library state", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse([]));

    render(<App />);

    expect(await screen.findByText(/No books are available yet/)).toBeTruthy();
  });

  it("shows an actionable library error and retries loading", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Database unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse(books));
    const user = userEvent.setup();

    render(<App />);

    expect((await screen.findByRole("alert")).textContent).toContain("Database unavailable");
    await user.click(screen.getByRole("button", { name: "Retry loading library" }));

    expect(await screen.findByRole("heading", { name: "Foundation" })).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("sends a whole-library chat request, blocks duplicates, and renders expandable sources", async () => {
    const pendingChat = deferred<Response>();
    fetchMock
      .mockResolvedValueOnce(jsonResponse(books))
      .mockReturnValueOnce(pendingChat.promise);
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect(screen.getByRole("status").textContent).toContain("Searching your local library");
    expect(screen.getByRole("button", { name: "Asking…" }).hasAttribute("disabled")).toBe(true);
    await user.click(screen.getByRole("button", { name: "Asking…" }));
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/chat",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ question: chatResponse.question, retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT }),
      }),
    ]);

    pendingChat.resolve(jsonResponse(chatResponse));

    expect(await screen.findByText(chatResponse.answer)).toBeTruthy();
    const citation = screen.getByRole("button", { name: /S1.*Foundation.*Chunk 8/ });
    expect(screen.getByText("Isaac Asimov · Chunk 8")).toBeTruthy();
    await user.click(citation);
    expect(citation.className).toContain("open");
    expect(screen.getByText(chatResponse.sources[0].text)).toBeTruthy();
  });

  it("scopes chat to a selected book without automatically submitting", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(books))
      .mockResolvedValueOnce(jsonResponse(chatResponse));
    const user = userEvent.setup();

    render(<App />);
    const heading = await screen.findByRole("heading", { name: "Foundation" });
    const card = heading.closest("article");
    if (!card) throw new Error("book card was not rendered");

    await user.click(within(card).getByRole("button", { name: /Ask about this book/ }));

    expect(screen.getByText("Current: Foundation")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledTimes(1);

    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await screen.findByText(chatResponse.answer);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/chat",
      expect.objectContaining({
        body: JSON.stringify({ question: chatResponse.question, retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT, book_id: "book-1" }),
      }),
    ]);
  });

  it("offers normalized author choices and sends exactly an author-scoped request", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(authorBooks))
      .mockResolvedValueOnce(jsonResponse(chatResponse));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    const scope = screen.getByRole("combobox", { name: "Search scope" });
    await user.click(scope);
    await user.type(scope, "Asimov");
    const authorOption = screen.getByRole("option", { name: /Isaac Asimov.*2 books/ });
    const collidingBookOption = screen.getByRole("option", { name: /The Caves of Steel.*isaac asimov/i });

    expect(collidingBookOption).toBeTruthy();
    await user.click(authorOption);

    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Answers will use books credited to Isaac Asimov.")).toBeTruthy();
    expect(screen.getByRole("radio", { name: /All books by Isaac Asimov.*2 books/ })).toBeTruthy();

    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    await screen.findByText(chatResponse.answer);

    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/chat",
      expect.objectContaining({
        body: JSON.stringify({ question: chatResponse.question, retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT, author: "Isaac Asimov" }),
      }),
    ]);
  });

  it("keeps the last successful answer when a later chat request fails", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(books))
      .mockResolvedValueOnce(jsonResponse(chatResponse))
      .mockResolvedValueOnce(jsonResponse({ detail: "Generator unavailable" }, 503));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    const question = screen.getByLabelText("Ask a question about your library");
    await user.type(question, chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(chatResponse.answer)).toBeTruthy();

    await user.clear(question);
    await user.type(question, "What does the library say about empires?");
    await user.click(screen.getByRole("button", { name: "Ask" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Generator unavailable");
    expect(screen.getByText(chatResponse.answer)).toBeTruthy();
  });

  it("clears an existing answer and citations when the search scope changes", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse(books))
      .mockResolvedValueOnce(jsonResponse(chatResponse));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(chatResponse.answer)).toBeTruthy();

    await chooseScope(user, "Foundation", /Foundation.*Isaac Asimov/);

    expect(screen.queryByText(chatResponse.answer)).toBeNull();
    expect(screen.queryByText(chatResponse.sources[0].text)).toBeNull();
    expect(screen.getByText("Ask a question to receive an answer grounded in passages from your own library.")).toBeTruthy();
  });

  it("ignores a pending response after the scope changes and allows a new scoped request", async () => {
    const pendingWholeLibraryChat = deferred<Response>();
    const scopedChatResponse = {
      ...chatResponse,
      answer: "Within Foundation, psychohistory guides the Seldon Plan [S1].",
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(books))
      .mockReturnValueOnce(pendingWholeLibraryChat.promise)
      .mockResolvedValueOnce(jsonResponse(scopedChatResponse));
    const user = userEvent.setup();

    render(<App />);
    const heading = await screen.findByRole("heading", { name: "Foundation" });
    const card = heading.closest("article");
    if (!card) throw new Error("book card was not rendered");

    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(screen.getByRole("status").textContent).toContain("Searching your local library");

    await user.click(within(card).getByRole("button", { name: /Ask about this book/ }));
    expect(screen.getByText("Current: Foundation")).toBeTruthy();
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false);

    await act(async () => {
      pendingWholeLibraryChat.resolve(jsonResponse(chatResponse));
    });

    expect(screen.queryByText(chatResponse.answer)).toBeNull();
    expect(screen.queryByRole("button", { name: /S1.*Foundation.*Chunk 8/ })).toBeNull();
    expect(screen.getByText("Ask a question to receive an answer grounded in passages from your own library.")).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(scopedChatResponse.answer)).toBeTruthy();
  });

  it("ignores a pending old-scope response after switching to an author", async () => {
    const pendingWholeLibraryChat = deferred<Response>();
    const authorChatResponse = {
      ...chatResponse,
      answer: "Across Asimov's books, systems shape the choices available to individuals [S1].",
    };
    fetchMock
      .mockResolvedValueOnce(jsonResponse(authorBooks))
      .mockReturnValueOnce(pendingWholeLibraryChat.promise)
      .mockResolvedValueOnce(jsonResponse(authorChatResponse));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));

    await chooseScope(user, "Asimov", /Isaac Asimov.*2 books/);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.getByRole("button", { name: "Ask" }).hasAttribute("disabled")).toBe(false);

    await act(async () => pendingWholeLibraryChat.resolve(jsonResponse(chatResponse)));
    expect(screen.queryByText(chatResponse.answer)).toBeNull();

    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(authorChatResponse.answer)).toBeTruthy();
    expect(fetchMock.mock.calls[2][1]).toEqual(expect.objectContaining({
      body: JSON.stringify({ question: chatResponse.question, retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT, author: "Isaac Asimov" }),
    }));
  });

  it("falls back to the whole library and clears stale results when a refresh removes the active author", async () => {
    const refreshedBooks = [{ ...books[0], id: "earthsea", title: "A Wizard of Earthsea", authors: ["Ursula K. Le Guin"] }];
    fetchMock
      .mockResolvedValueOnce(jsonResponse(authorBooks))
      .mockResolvedValueOnce(jsonResponse(chatResponse))
      .mockResolvedValueOnce(jsonResponse(refreshedBooks));
    const user = userEvent.setup();

    render(<App />);
    await screen.findByRole("heading", { name: "Foundation" });
    await chooseScope(user, "Asimov", /Isaac Asimov.*2 books/);
    await user.type(screen.getByLabelText("Ask a question about your library"), chatResponse.question);
    await user.click(screen.getByRole("button", { name: "Ask" }));
    expect(await screen.findByText(chatResponse.answer)).toBeTruthy();

    await user.click(screen.getByRole("button", { name: "Test refresh library" }));

    await screen.findByRole("heading", { name: "A Wizard of Earthsea" });
    await waitFor(() => expect(screen.getByText("Current: Whole library")).toBeTruthy());
    expect(screen.queryByText(chatResponse.answer)).toBeNull();
    expect(screen.getByText("Answers search your entire local library.")).toBeTruthy();
  });
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((promiseResolve) => {
    resolve = promiseResolve;
  });
  return { promise, resolve };
}

async function chooseScope(user: ReturnType<typeof userEvent.setup>, query: string, optionName: RegExp) {
  const input = screen.getByRole("combobox", { name: "Search scope" });
  await user.click(input);
  await user.type(input, query);
  await user.click(screen.getByRole("option", { name: optionName }));
}
