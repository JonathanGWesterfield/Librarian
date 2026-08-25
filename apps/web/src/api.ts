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

// Five retrieved chunks keep the default local Qwen model's grounded prompt
// within its context window while still providing multiple source passages.
export const UI_CHAT_RETRIEVAL_LIMIT = 5;

// The browser always uses the public same-origin API contract. During local
// development Vite routes this path to services.api_port from librarian.json.
const apiBaseUrl = "/api";

export async function getBooks(): Promise<LibraryBook[]> {
  return request<LibraryBook[]>("/books");
}

export async function getIngestionStatus(): Promise<IngestionStatusResponse> {
  return request<IngestionStatusResponse>("/ingestion/status");
}

export async function runIngestion(): Promise<IngestionRunResponse> {
  return request<IngestionRunResponse>("/ingestion/run", {
    method: "POST",
    body: JSON.stringify({ embed_chunks: true }),
  });
}

export async function refreshSearchIndex(): Promise<SearchIndexResponse> {
  return request<SearchIndexResponse>("/search/index", {
    method: "POST",
    body: JSON.stringify({}),
  });
}

export async function askChat(question: string, scope: ChatScopeFilter = {}): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      question,
      retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT,
      ...(scope.bookId ? { book_id: scope.bookId } : {}),
      ...(scope.author ? { author: scope.author } : {}),
    }),
  });
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
