/* This file is generated from schemas/librarian/answer/v1/answer_event.schema.json. Do not edit it directly. */

/**
 * The public v1 event envelope for progressive answer delivery.
 */
export type AnswerEvent =
  | StartedEvent
  | EvidenceCandidatesEvent
  | GenerationStartedEvent
  | ValidationStartedEvent
  | AnswerValidatedEvent
  | CompletedEvent
  | FailedEvent
  | CancelledEvent;

export interface StartedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "started";
}
export interface EvidenceCandidatesEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "evidence_candidates";
  candidate_count: number;
  /**
   * @maxItems 32
   */
  candidates: EvidenceCandidateProgress[];
}
export interface EvidenceCandidateProgress {
  candidate_id: string;
  book_id: string;
  book_title: string | null;
}
export interface GenerationStartedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "generation_started";
  attempt: number;
}
export interface ValidationStartedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "validation_started";
  attempt: number;
}
export interface AnswerValidatedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "answer_validated";
  result: AnswerResult;
}
export interface AnswerResult {
  outcome: "answered" | "insufficient_evidence" | "generation_unavailable" | "source_changed";
  minimum_citation_count: number;
  citation_count: number;
  question: string;
  answer: string;
  embedding_provider: string;
  embedding_model: string;
  generation_provider: string;
  generation_model: string;
  answer_capability: "quality" | "lightweight";
  retrieval_limit: number;
  candidate_count: number;
  filters: {
    [k: string]: string;
  };
  retrieval_backend: "opensearch" | "sqlite";
  /**
   * @maxItems 128
   */
  sources: ChatSource[];
  timings: AnswerTimings;
}
export interface ChatSource {
  source_id: string;
  score: number;
  chunk_id: string;
  book_id: string;
  relative_path: string;
  title: string | null;
  /**
   * @maxItems 64
   */
  authors: string[];
  chunk_index: number;
  content_type: "body" | "front_matter" | "back_matter";
  text: string;
}
export interface AnswerTimings {
  query_embedding_seconds: number;
  retrieval_seconds: number;
  prompt_construction_seconds: number;
  generation_seconds: number;
  validation_seconds: number;
  repair_seconds: number;
  total_seconds: number;
}
export interface CompletedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "completed";
  result: AnswerResult;
}
export interface FailedEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "failed";
  error: SafeError;
}
export interface SafeError {
  code:
    | "generation_unavailable"
    | "broker_unavailable"
    | "deadline_exceeded"
    | "admission_full"
    | "contract_mismatch"
    | "internal_error";
  message: string;
  retryable: boolean;
}
export interface CancelledEvent {
  schema_version: "v1";
  request_id: string;
  sequence: number;
  event: "cancelled";
}
