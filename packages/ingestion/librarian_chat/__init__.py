from __future__ import annotations

from dataclasses import asdict, dataclass

from librarian_chat.generation import (
    ChatMessage,
    create_configured_generator,
)
from librarian_search import SearchOptions, SearchResult, search_chunks


@dataclass(frozen=True)
class ChatOptions:
    question: str
    database_url: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    ollama_base_url: str | None = None
    retrieval_limit: int = 30


@dataclass(frozen=True)
class ChatSource:
    source_id: str
    score: float
    chunk_id: str
    book_id: str
    relative_path: str
    title: str | None
    authors: list[str]
    chunk_index: int
    text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ChatResponse:
    question: str
    answer: str
    embedding_provider: str
    embedding_model: str
    generation_provider: str
    generation_model: str
    retrieval_limit: int
    candidate_count: int
    sources: list[ChatSource]

    def to_dict(self) -> dict[str, object]:
        return {
            "question": self.question,
            "answer": self.answer,
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "generation_provider": self.generation_provider,
            "generation_model": self.generation_model,
            "retrieval_limit": self.retrieval_limit,
            "candidate_count": self.candidate_count,
            "sources": [source.to_dict() for source in self.sources],
        }


def answer_question(options: ChatOptions) -> ChatResponse:
    question = options.question.strip()
    if not question:
        raise ValueError("question must not be empty")

    retrieval_limit = max(1, options.retrieval_limit)
    search_response = search_chunks(
        SearchOptions(
            query=question,
            database_url=options.database_url,
            embedding_provider=options.embedding_provider,
            embedding_model=options.embedding_model,
            ollama_base_url=options.ollama_base_url,
            limit=retrieval_limit,
        )
    )
    sources = _to_sources(search_response.results)

    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    answer = generator.generate(_build_messages(question, sources))

    return ChatResponse(
        question=question,
        answer=answer,
        embedding_provider=search_response.embedding_provider,
        embedding_model=search_response.embedding_model,
        generation_provider=generator.provider,
        generation_model=generator.model,
        retrieval_limit=retrieval_limit,
        candidate_count=search_response.candidate_count,
        sources=sources,
    )


def _to_sources(results: list[SearchResult]) -> list[ChatSource]:
    sources: list[ChatSource] = []
    for index, result in enumerate(results, start=1):
        sources.append(
            ChatSource(
                source_id=f"S{index}",
                score=result.score,
                chunk_id=result.chunk_id,
                book_id=result.book_id,
                relative_path=result.relative_path,
                title=result.title,
                authors=result.authors,
                chunk_index=result.chunk_index,
                text=result.text,
            )
        )
    return sources


def _build_messages(question: str, sources: list[ChatSource]) -> list[ChatMessage]:
    source_text = _format_sources(sources)
    return [
        ChatMessage(
            role="system",
            content=(
                "You are Librarian, a local reading assistant. Answer only from "
                "the provided source chunks. If the chunks do not support an "
                "answer, say that the local library context is insufficient. "
                "Cite source IDs like [S1] when using a source."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Question:\n{question}\n\n"
                f"Source chunks:\n{source_text}\n\n"
                "Write a concise answer grounded in the source chunks."
            ),
        ),
    ]


def _format_sources(sources: list[ChatSource]) -> str:
    if not sources:
        return "No source chunks were retrieved."

    formatted: list[str] = []
    for source in sources:
        title = source.title or source.relative_path
        authors = ", ".join(source.authors) if source.authors else "Unknown author"
        formatted.append(
            "\n".join(
                [
                    f"[{source.source_id}] {title} by {authors}",
                    f"Path: {source.relative_path}",
                    f"Chunk: {source.chunk_index}",
                    f"Text: {source.text}",
                ]
            )
        )
    return "\n\n".join(formatted)
