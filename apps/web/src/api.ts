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

// Five retrieved chunks keep the default local Qwen model's grounded prompt
// within its context window while still providing multiple source passages.
export const UI_CHAT_RETRIEVAL_LIMIT = 5;

const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL || "/api").replace(/\/$/, "");

export async function getBooks(): Promise<LibraryBook[]> {
  return request<LibraryBook[]>("/books");
}

export async function askChat(question: string, bookId?: string): Promise<ChatResponse> {
  return request<ChatResponse>("/chat", {
    method: "POST",
    body: JSON.stringify({
      question,
      retrieval_limit: UI_CHAT_RETRIEVAL_LIMIT,
      ...(bookId ? { book_id: bookId } : {}),
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
