import { act, cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ActivitySection } from "./activity";
import type { IngestionRunResponse, IngestionStatusResponse, SearchIndexResponse } from "./api";

const inactiveStage = {
  status: "complete" as const,
  total_books: 4,
  completed_books: 4,
  pending_books: 0,
  running_books: 0,
  failed_books: 0,
  percent_complete: 100,
  details: {},
  active_jobs: [],
};

const statusResponse: IngestionStatusResponse = {
  database_url: "sqlite:////data/librarian.db",
  total_books: 4,
  chunking: inactiveStage,
  summarizing: {
    ...inactiveStage,
    status: "running" as const,
    completed_books: 2,
    pending_books: 1,
    running_books: 1,
    failed_books: 1,
    percent_complete: 50,
    active_jobs: [{
      job_id: "summary-1",
      book_id: "book-1",
      relative_path: "foundation.epub",
      title: "Foundation",
      authors: ["Isaac Asimov"],
      provider: "ollama",
      model: "qwen2.5:1.5b",
      attempts: 1,
      stage: "chapters",
      current: 2,
      total: 5,
      message: "Summarizing chapter 2 of 5.",
      updated_at: "2026-08-20T12:00:00Z",
      started_at: "2026-08-20T11:59:00Z",
      duration_seconds: 60,
    }],
  },
  tagging: { ...inactiveStage, completed_books: 3, pending_books: 1, percent_complete: 75 },
};

const ingestionResponse: IngestionRunResponse = {
  books_dir: "/books",
  database_url: "sqlite:////data/librarian.db",
  embedding_provider: "ollama",
  embedding_model: "all-minilm",
  found: 3,
  parsed: 1,
  skipped_unchanged: 1,
  skipped_duplicates: 0,
  failed: 1,
  stored_chunks: 12,
  stored_embeddings: 12,
  summary_jobs_enqueued: 0,
  total_books: 5,
  total_chunks: 80,
  total_embeddings: 80,
  books: [
    { relative_path: "new.epub", file_hash: "new", status: "ingested", chunk_count: 12, message: null },
    { relative_path: "broken.epub", file_hash: "broken", status: "failed", chunk_count: 0, message: "Invalid EPUB" },
  ],
  discovered: [],
};

const indexResponse: SearchIndexResponse = {
  database_url: "sqlite:////data/librarian.db",
  opensearch_url: "http://opensearch:9200",
  index_name: "librarian-chunks",
  embedding_provider: "ollama",
  embedding_model: "all-minilm",
  dimensions: 384,
  documents_seen: 80,
  documents_indexed: 12,
  reset: false,
};

let fetchMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ActivitySection", () => {
  it("loads and displays accessible stage progress, counts, failures, and active work", async () => {
    const pendingStatus = deferred<Response>();
    fetchMock.mockReturnValueOnce(pendingStatus.promise);

    render(<ActivitySection onLibraryUpdated={vi.fn()} />);

    expect(screen.getByText("Loading processing status…")).toBeTruthy();
    await act(async () => pendingStatus.resolve(jsonResponse(statusResponse)));

    const progress = await screen.findByRole("progressbar", { name: "Summarizing progress" }) as HTMLProgressElement;
    expect(progress.value).toBe(50);
    const card = screen.getByRole("heading", { name: "Summarizing" }).closest("article");
    if (!card) throw new Error("summarizing status card was not rendered");
    expect(within(card).getByText("2 of 4 complete")).toBeTruthy();
    expect(within(card).getByText("Summarizing chapter 2 of 5.")).toBeTruthy();
    expect(within(card).getAllByText("1", { selector: "dd" })).toHaveLength(3);
  });

  it("runs ingestion before indexing, blocks duplicates, gates readiness, and refreshes the UI", async () => {
    const pendingIngestion = deferred<Response>();
    const pendingIndex = deferred<Response>();
    const onLibraryUpdated = vi.fn().mockResolvedValue(undefined);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(statusResponse))
      .mockReturnValueOnce(pendingIngestion.promise)
      .mockReturnValueOnce(pendingIndex.promise)
      .mockResolvedValueOnce(jsonResponse(statusResponse));
    const user = userEvent.setup();

    render(<ActivitySection onLibraryUpdated={onLibraryUpdated} />);
    await screen.findByRole("progressbar", { name: "Chunking progress" });
    await user.click(screen.getByRole("button", { name: "Update library" }));
    await user.click(screen.getByRole("button", { name: "Processing books…" }));

    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(fetchMock.mock.calls[1]).toEqual([
      "/api/ingestion/run",
      expect.objectContaining({ method: "POST", body: JSON.stringify({ embed_chunks: true }) }),
    ]);

    await act(async () => pendingIngestion.resolve(jsonResponse(ingestionResponse)));

    expect(await screen.findByText(/new books are not search-ready yet/i)).toBeTruthy();
    expect(screen.queryByText(/Search ready/)).toBeNull();
    expect(screen.getByText(/1 book failed during ingestion/)).toBeTruthy();
    expect(fetchMock.mock.calls[2]).toEqual([
      "/api/search/index",
      expect.objectContaining({ method: "POST", body: JSON.stringify({}) }),
    ]);

    await act(async () => pendingIndex.resolve(jsonResponse(indexResponse)));

    expect(await screen.findByText("Search ready. 80 documents seen; 12 documents indexed.")).toBeTruthy();
    expect(onLibraryUpdated).toHaveBeenCalledTimes(1);
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual([
      "/api/ingestion/status",
      "/api/ingestion/run",
      "/api/search/index",
      "/api/ingestion/status",
    ]);
  });

  it("offers an index-only retry after indexing fails and gates readiness until it succeeds", async () => {
    const pendingRetry = deferred<Response>();
    const onLibraryUpdated = vi.fn().mockResolvedValue(undefined);
    fetchMock
      .mockResolvedValueOnce(jsonResponse(statusResponse))
      .mockResolvedValueOnce(jsonResponse({ ...ingestionResponse, failed: 0 }))
      .mockResolvedValueOnce(jsonResponse({ detail: "OpenSearch unavailable" }, 503))
      .mockReturnValueOnce(pendingRetry.promise)
      .mockResolvedValueOnce(jsonResponse(statusResponse));
    const user = userEvent.setup();

    render(<ActivitySection onLibraryUpdated={onLibraryUpdated} />);
    await screen.findByRole("progressbar", { name: "Chunking progress" });
    await user.click(screen.getByRole("button", { name: "Update library" }));

    const retry = await screen.findByRole("button", { name: "Retry search index" });
    expect(screen.getByRole("alert").textContent).toContain("New books may not be searchable");
    expect(screen.queryByText(/Search ready/)).toBeNull();
    await user.click(retry);

    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/ingestion/run")).toHaveLength(1);
    expect(fetchMock.mock.calls.filter(([url]) => url === "/api/search/index")).toHaveLength(2);
    expect(screen.queryByText(/Search ready/)).toBeNull();

    await act(async () => pendingRetry.resolve(jsonResponse(indexResponse)));

    expect(await screen.findByText("Search ready. 80 documents seen; 12 documents indexed.")).toBeTruthy();
    expect(onLibraryUpdated).toHaveBeenCalledTimes(1);
  });

  it("shows a status error and retries status without starting ingestion", async () => {
    fetchMock
      .mockResolvedValueOnce(jsonResponse({ detail: "Database unavailable" }, 503))
      .mockResolvedValueOnce(jsonResponse(statusResponse));
    const user = userEvent.setup();

    render(<ActivitySection onLibraryUpdated={vi.fn()} />);

    expect((await screen.findByRole("alert")).textContent).toContain("Database unavailable");
    await user.click(screen.getByRole("button", { name: "Retry status" }));

    expect(await screen.findByRole("progressbar", { name: "Tagging progress" })).toBeTruthy();
    expect(fetchMock.mock.calls.map(([url]) => url)).toEqual(["/api/ingestion/status", "/api/ingestion/status"]);
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
