export type LibraryBook = {
  id: string;
  relative_path: string;
  title: string | null;
  authors: string[];
  publisher: string | null;
  status: string;
  error_message: string | null;
  chunk_count: number;
  chunk_duration_seconds: number | null;
};

export type ChatSource = {
  source_id: string;
  score: number;
  chunk_id: string;
  book_id: string;
  relative_path: string;
  title: string | null;
  authors: string[];
  chunk_index: number;
  text: string;
};

export type ChatResponse = {
  question: string;
  answer: string;
  embedding_provider: string;
  embedding_model: string;
  generation_provider: string;
  generation_model: string;
  retrieval_limit: number;
  candidate_count: number;
  filters: Record<string, string>;
  sources: ChatSource[];
};

export type ChatStreamRetrieval = Omit<ChatResponse, "answer"> & {
  timings: {
    query_embedding_seconds: number;
    retrieval_seconds: number;
    prompt_construction_seconds: number;
    time_to_first_event_seconds: number;
  };
};

export type ChatStreamCompletion = ChatResponse & {
  timings: {
    query_embedding_seconds: number;
    retrieval_seconds: number;
    prompt_construction_seconds: number;
    generation_seconds: number;
    total_seconds: number;
    time_to_first_event_seconds: number | null;
    time_to_first_token_seconds: number | null;
  };
};

export type ChatStreamHandlers = {
  onRetrieval: (event: ChatStreamRetrieval) => void;
  onToken: (text: string) => void;
};

export type ChatScopeFilter =
  | { bookId: string; author?: never }
  | { author: string; bookId?: never }
  | { bookId?: never; author?: never };

export type IngestionActiveJob = {
  job_id: string;
  book_id: string;
  relative_path: string;
  title: string | null;
  authors: string[];
  provider: string;
  model: string;
  detail?: string;
  job_type?: string;
  source_summary_provider?: string;
  source_summary_model?: string;
  source_summary_detail?: string;
  attempts: number;
  stage: string;
  current: number;
  total: number;
  message: string | null;
  updated_at: string | null;
  started_at: string | null;
  duration_seconds: number;
};

export type IngestionStageStatus = {
  status: "empty" | "running" | "failed" | "complete" | "not_started" | "in_progress";
  total_books: number;
  completed_books: number;
  pending_books: number;
  running_books: number;
  failed_books: number;
  percent_complete: number;
  details: Record<string, unknown>;
  active_jobs: IngestionActiveJob[];
};

export type IngestionStatusResponse = {
  database_url: string;
  total_books: number;
  chunking: IngestionStageStatus;
  summarizing: IngestionStageStatus;
  tagging: IngestionStageStatus;
};

export type IngestionBookResult = {
  relative_path: string;
  file_hash: string;
  status: "ingested" | "skipped_unchanged" | "duplicate" | "failed";
  chunk_count: number;
  message: string | null;
};

export type DiscoveredEpub = {
  relative_path: string;
  size_bytes: number;
  sha256: string;
};

export type IngestionRunResponse = {
  books_dir: string;
  database_url: string;
  embedding_provider: string;
  embedding_model: string;
  found: number;
  parsed: number;
  skipped_unchanged: number;
  skipped_duplicates: number;
  failed: number;
  stored_chunks: number;
  stored_embeddings: number;
  summary_jobs_enqueued: number;
  total_books: number;
  total_chunks: number;
  total_embeddings: number;
  books: IngestionBookResult[];
  discovered: DiscoveredEpub[];
};

export type SearchIndexResponse = {
  database_url: string;
  opensearch_url: string;
  index_name: string;
  embedding_provider: string;
  embedding_model: string;
  dimensions: number;
  documents_seen: number;
  documents_indexed: number;
  reset: boolean;
};

// The browser always uses the public same-origin API contract. During local
// development Vite routes this path to services.api_port from librarian.json.
const apiBaseUrl = "/api";

export async function getBooks(): Promise<LibraryBook[]> {
  return request<LibraryBook[]>("/books");
}

export async function getIngestionStatus(): Promise<IngestionStatusResponse> {
  return request<IngestionStatusResponse>("/ingestion/status");
}

export async function runIngestion(
  { reprocessUnchanged = false }: { reprocessUnchanged?: boolean } = {},
): Promise<IngestionRunResponse> {
  return request<IngestionRunResponse>("/ingestion/run", {
    method: "POST",
    body: JSON.stringify({
      embed_chunks: true,
      ...(reprocessUnchanged ? { reprocess_unchanged: true } : {}),
    }),
  });
}

export async function refreshSearchIndex(
  { reset = false }: { reset?: boolean } = {},
): Promise<SearchIndexResponse> {
  return request<SearchIndexResponse>("/search/index", {
    method: "POST",
    body: JSON.stringify(reset ? { reset: true } : {}),
  });
}

export async function streamChat(
  question: string,
  scope: ChatScopeFilter,
  handlers: ChatStreamHandlers,
  signal?: AbortSignal,
): Promise<ChatStreamCompletion> {
  const response = await fetch(`${apiBaseUrl}/chat/stream`, {
    method: "POST",
    signal,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      question,
      ...(scope.bookId ? { book_id: scope.bookId } : {}),
      ...(scope.author ? { author: scope.author } : {}),
    }),
  });
  if (!response.ok) throw new Error(await errorMessage(response));
  if (!response.body) throw new Error("The API did not provide a readable answer stream.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let completed: ChatStreamCompletion | null = null;
  while (true) {
    const { value, done } = await reader.read();
    buffered += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    let boundary = buffered.indexOf("\n\n");
    while (boundary >= 0) {
      const rawEvent = buffered.slice(0, boundary);
      buffered = buffered.slice(boundary + 2);
      const event = parseSseEvent(rawEvent);
      if (event) {
        if (event.name === "retrieval") handlers.onRetrieval(event.data as ChatStreamRetrieval);
        else if (event.name === "token") {
          const text = event.data.text;
          if (typeof text !== "string") throw new Error("The API sent an invalid answer fragment.");
          handlers.onToken(text);
        } else if (event.name === "complete") completed = event.data as ChatStreamCompletion;
        else if (event.name === "error") {
          const detail = event.data.detail;
          throw new Error(typeof detail === "string" ? detail : "The answer stream failed.");
        }
      }
      boundary = buffered.indexOf("\n\n");
    }
    if (done) break;
  }
  if (!completed) throw new Error("The API ended before completing the answer stream.");
  return completed;
}

function parseSseEvent(raw: string): { name: string; data: Record<string, unknown> } | null {
  const eventLine = raw.split("\n").find((line) => line.startsWith("event:"));
  const data = raw.split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trimStart())
    .join("\n");
  if (!eventLine || !data) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(data);
  } catch {
    throw new Error("The API sent malformed answer-stream data.");
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("The API sent an invalid answer-stream event.");
  }
  return { name: eventLine.slice("event:".length).trim(), data: parsed as Record<string, unknown> };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init?.headers,
    },
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const payload: unknown = await response.json();
    if (typeof payload === "object" && payload !== null && "detail" in payload) {
      const detail = payload.detail;
      if (typeof detail === "string") return detail;
    }
  } catch {
    // Use the status message when the API has no JSON error body.
  }
  return `The API request failed (${response.status}).`;
}
