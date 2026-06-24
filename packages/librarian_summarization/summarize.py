from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Callable

from librarian_chat.generation import (
    ChatMessage,
    CodexGenerator,
    create_configured_generator,
)
from librarian_config.config import (
    resolve_chunk_summary_timeout_seconds,
    resolve_database_url,
    resolve_max_parallel_chunk_summaries,
)
from librarian_storage.storage import (
    BookSummaryRecord,
    ChapterSummaryRecord,
    StoredSummaryBookRecord,
    SummaryChunkRecord,
    create_ingestion_store,
)


@dataclass(frozen=True)
class SummaryProgress:
    stage: str
    current: int
    total: int
    message: str


@dataclass(frozen=True)
class SummarizeBookOptions:
    database_url: str | None = None
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    ollama_base_url: str | None = None
    detail: str = "medium"
    chunks_per_section: int = 8
    max_section_chars: int = 12000
    force_refresh: bool = False
    reset: bool = False
    include_chapter_summaries: bool = True
    max_reduce_inputs: int = 12
    chunk_summary_timeout_seconds: float | None = None
    max_parallel_chunk_summaries: int | None = None
    progress_callback: Callable[[SummaryProgress], None] | None = None


@dataclass(frozen=True)
class DeleteSummariesOptions:
    database_url: str | None = None
    book_id: str | None = None
    book_title: str | None = None
    author: str | None = None
    generation_provider: str | None = None
    generation_model: str | None = None
    detail: str | None = None


@dataclass(frozen=True)
class ChapterSummary:
    chapter_key: str
    chapter_title: str | None
    chunk_start_index: int
    chunk_end_index: int
    summary: str
    source_hash: str
    cached: bool

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class BookSummary:
    book_id: str
    title: str | None
    authors: list[str]
    provider: str
    model: str
    detail: str
    summary: str
    source_hash: str
    chapter_summary_count: int
    cached_chapter_summaries: int
    generated_chapter_summaries: int
    deleted_summaries: int
    chapter_summaries: list[ChapterSummary]

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["chapter_summaries"] = [
            summary.to_dict() for summary in self.chapter_summaries
        ]
        return payload


@dataclass(frozen=True)
class DeleteSummariesResult:
    deleted_summaries: int
    book_id: str | None
    provider: str | None
    model: str | None
    detail: str | None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class _Section:
    key: str
    title: str | None
    chunks: list[SummaryChunkRecord]

    @property
    def chunk_start_index(self) -> int:
        return self.chunks[0].chunk_index

    @property
    def chunk_end_index(self) -> int:
        return self.chunks[-1].chunk_index

    @property
    def text(self) -> str:
        return "\n\n".join(chunk.text for chunk in self.chunks)


@dataclass(frozen=True)
class _SectionGenerationTask:
    section_index: int
    section: _Section
    source_hash: str
    messages: list[ChatMessage]


@dataclass(frozen=True)
class _SectionGenerationResult:
    section_index: int
    section: _Section
    source_hash: str
    summary: str


def summarize_book(options: SummarizeBookOptions) -> BookSummary:
    detail = _normalize_detail(options.detail)
    database_url = resolve_database_url(options.database_url)
    generator = create_configured_generator(
        provider=options.generation_provider,
        model=options.generation_model,
        ollama_base_url=options.ollama_base_url,
    )
    chunk_summary_timeout_seconds = resolve_chunk_summary_timeout_seconds(
        options.chunk_summary_timeout_seconds
    )
    max_parallel_chunk_summaries = resolve_max_parallel_chunk_summaries(
        options.max_parallel_chunk_summaries
    )
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        book = _resolve_single_book(
            store,
            book_id=options.book_id,
            book_title=options.book_title,
            author=options.author,
        )
        if options.reset:
            deleted_summaries = store.delete_summaries(
                book_id=book.id,
                provider=generator.provider,
                model=generator.model,
                detail=detail,
            )
        else:
            deleted_summaries = 0

        chunks = store.list_book_summary_chunks(book.id)
        if not chunks:
            raise ValueError(f"book has no chunks to summarize: {book.id}")

        sections = _build_sections(
            chunks,
            chunks_per_section=options.chunks_per_section,
            max_section_chars=options.max_section_chars,
        )
        _emit_progress(
            options.progress_callback,
            stage="plan",
            current=0,
            total=len(sections),
            message=(
                f"Selected {len(sections)} section(s) from {len(chunks)} chunks "
                f"with max {options.max_section_chars} source chars per section."
            ),
        )
        chapter_summaries: list[ChapterSummary | None] = [None] * len(sections)
        generation_tasks: list[_SectionGenerationTask] = []
        cached_count = 0
        for section_index, section in enumerate(sections, start=1):
            source_hash = _section_source_hash(section)
            cached = store.get_chapter_summary(
                book_id=book.id,
                chapter_key=section.key,
                provider=generator.provider,
                model=generator.model,
                detail=detail,
            )
            if (
                cached is not None
                and cached.source_hash == source_hash
                and not options.force_refresh
            ):
                _emit_progress(
                    options.progress_callback,
                    stage="chapter",
                    current=section_index,
                    total=len(sections),
                    message=f"Reusing cached summary for {section.title or section.key}.",
                )
                summary_text = cached.summary
                cached_count += 1
                chapter_summaries[section_index - 1] = ChapterSummary(
                    chapter_key=section.key,
                    chapter_title=section.title,
                    chunk_start_index=section.chunk_start_index,
                    chunk_end_index=section.chunk_end_index,
                    summary=summary_text,
                    source_hash=source_hash,
                    cached=True,
                )
            else:
                _emit_progress(
                    options.progress_callback,
                    stage="chapter",
                    current=section_index,
                    total=len(sections),
                    message=(
                        f"Generating summary for {section.title or section.key} "
                        f"({len(section.text)} source chars)."
                    ),
                )
                generation_tasks.append(
                    _SectionGenerationTask(
                        section_index=section_index,
                        section=section,
                        source_hash=source_hash,
                        messages=_chapter_summary_messages(
                            book=book,
                            section=section,
                            detail=detail,
                        ),
                    )
                )

        generated_results = _generate_chunk_summary_tasks(
            generator,
            generation_tasks,
            timeout_seconds=chunk_summary_timeout_seconds,
            max_parallel=max_parallel_chunk_summaries,
            progress_callback=options.progress_callback,
            result_callback=lambda result: _save_generated_chapter_summary(
                store=store,
                book_id=book.id,
                provider=generator.provider,
                model=generator.model,
                detail=detail,
                chapter_summaries=chapter_summaries,
                result=result,
            ),
        )

        visible_chapter_summary_inputs = [
            summary for summary in chapter_summaries if summary is not None
        ]

        final_inputs = _condense_until_fits(
            generator=generator,
            book=book,
            summaries=visible_chapter_summary_inputs,
            detail=detail,
            max_reduce_inputs=max(2, options.max_reduce_inputs),
            progress_callback=options.progress_callback,
        )
        book_source_hash = _book_source_hash(final_inputs)
        cached_book = store.get_book_summary(
            book_id=book.id,
            provider=generator.provider,
            model=generator.model,
            detail=detail,
        )
        if (
            cached_book is not None
            and cached_book.source_hash == book_source_hash
            and not options.force_refresh
            and len(generated_results) == 0
        ):
            book_summary_text = cached_book.summary
        else:
            _emit_progress(
                options.progress_callback,
                stage="book",
                current=1,
                total=1,
                message=f"Synthesizing final book summary from {len(final_inputs)} input summaries.",
            )
            book_summary_text = generator.generate(
                _book_summary_messages(book=book, summaries=final_inputs, detail=detail)
            )
            store.save_book_summary(
                BookSummaryRecord(
                    id=_summary_id(book.id, "book", generator.provider, generator.model, detail),
                    book_id=book.id,
                    provider=generator.provider,
                    model=generator.model,
                    detail=detail,
                    source_hash=book_source_hash,
                    summary=book_summary_text,
                    chapter_summary_count=len(visible_chapter_summary_inputs),
                )
            )

        visible_chapter_summaries = (
            visible_chapter_summary_inputs if options.include_chapter_summaries else []
        )
        return BookSummary(
            book_id=book.id,
            title=book.title,
            authors=book.authors,
            provider=generator.provider,
            model=generator.model,
            detail=detail,
            summary=book_summary_text,
            source_hash=book_source_hash,
            chapter_summary_count=len(visible_chapter_summary_inputs),
            cached_chapter_summaries=cached_count,
            generated_chapter_summaries=len(generated_results),
            deleted_summaries=deleted_summaries,
            chapter_summaries=visible_chapter_summaries,
        )
    finally:
        store.close()


def delete_summaries(options: DeleteSummariesOptions) -> DeleteSummariesResult:
    database_url = resolve_database_url(options.database_url)
    provider = options.generation_provider.strip().casefold() if options.generation_provider else None
    model = options.generation_model.strip() if options.generation_model else None
    detail = _normalize_detail(options.detail) if options.detail else None
    store = create_ingestion_store(database_url)
    store.initialize()
    try:
        book_id = options.book_id
        if not book_id and (options.book_title or options.author):
            book_id = _resolve_single_book(
                store,
                book_id=None,
                book_title=options.book_title,
                author=options.author,
            ).id
        deleted = store.delete_summaries(
            book_id=book_id,
            provider=provider,
            model=model,
            detail=detail,
        )
        return DeleteSummariesResult(
            deleted_summaries=deleted,
            book_id=book_id,
            provider=provider,
            model=model,
            detail=detail,
        )
    finally:
        store.close()


def _generate_chunk_summary(
    generator,
    messages: list[ChatMessage],
    *,
    timeout_seconds: float,
) -> str:
    if isinstance(generator, CodexGenerator):
        return generator.generate(messages, timeout_seconds=timeout_seconds)
    return generator.generate(messages)


def _generate_chunk_summary_tasks(
    generator,
    tasks: list[_SectionGenerationTask],
    *,
    timeout_seconds: float,
    max_parallel: int,
    progress_callback: Callable[[SummaryProgress], None] | None,
    result_callback: Callable[[_SectionGenerationResult], None] | None = None,
) -> list[_SectionGenerationResult]:
    if not tasks:
        return []

    _emit_progress(
        progress_callback,
        stage="chapter",
        current=0,
        total=len(tasks),
        message=(
            f"Generating {len(tasks)} uncached section summary/summaries "
            f"with up to {max_parallel} parallel worker(s)."
        ),
    )

    if max_parallel == 1:
        results = []
        for completed, task in enumerate(tasks, start=1):
            results.append(
                result := _run_section_generation_task(
                    generator,
                    task,
                    timeout_seconds=timeout_seconds,
                )
            )
            if result_callback is not None:
                result_callback(result)
            _emit_progress(
                progress_callback,
                stage="chapter",
                current=completed,
                total=len(tasks),
                message=f"Completed summary for {task.section.title or task.section.key}.",
            )
        return results

    results: list[_SectionGenerationResult] = []
    worker_count = min(max_parallel, len(tasks))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _run_section_generation_task,
                generator,
                task,
                timeout_seconds=timeout_seconds,
            ): task
            for task in tasks
        }
        for completed, future in enumerate(as_completed(futures), start=1):
            task = futures[future]
            result = future.result()
            results.append(result)
            if result_callback is not None:
                result_callback(result)
            _emit_progress(
                progress_callback,
                stage="chapter",
                current=completed,
                total=len(tasks),
                message=f"Completed summary for {task.section.title or task.section.key}.",
            )
    return results


def _save_generated_chapter_summary(
    *,
    store,
    book_id: str,
    provider: str,
    model: str,
    detail: str,
    chapter_summaries: list[ChapterSummary | None],
    result: _SectionGenerationResult,
) -> None:
    section = result.section
    chapter_summaries[result.section_index - 1] = ChapterSummary(
        chapter_key=section.key,
        chapter_title=section.title,
        chunk_start_index=section.chunk_start_index,
        chunk_end_index=section.chunk_end_index,
        summary=result.summary,
        source_hash=result.source_hash,
        cached=False,
    )
    store.save_chapter_summary(
        ChapterSummaryRecord(
            id=_summary_id(
                book_id,
                section.key,
                provider,
                model,
                detail,
            ),
            book_id=book_id,
            chapter_key=section.key,
            chapter_title=section.title,
            chunk_start_index=section.chunk_start_index,
            chunk_end_index=section.chunk_end_index,
            provider=provider,
            model=model,
            detail=detail,
            source_hash=result.source_hash,
            summary=result.summary,
        )
    )


def _run_section_generation_task(
    generator,
    task: _SectionGenerationTask,
    *,
    timeout_seconds: float,
) -> _SectionGenerationResult:
    summary_text = _generate_chunk_summary(
        generator,
        task.messages,
        timeout_seconds=timeout_seconds,
    )
    return _SectionGenerationResult(
        section_index=task.section_index,
        section=task.section,
        source_hash=task.source_hash,
        summary=summary_text,
    )


def _resolve_single_book(
    store,
    *,
    book_id: str | None,
    book_title: str | None,
    author: str | None,
) -> StoredSummaryBookRecord:
    if book_id:
        book = store.get_summary_book(book_id.strip())
        if book is None:
            raise ValueError(f"book not found: {book_id}")
        return book

    title_filter = _clean_filter(book_title)
    author_filter = _clean_filter(author)
    matches = []
    for book in store.list_summary_books(limit=1000):
        title_matches = (
            not title_filter
            or title_filter.casefold() in (book.title or book.relative_path).casefold()
        )
        author_matches = not author_filter or any(
            author_filter.casefold() in stored_author.casefold()
            for stored_author in book.authors
        )
        if title_matches and author_matches:
            matches.append(book)

    if not matches:
        raise ValueError("no ingested book matched the requested summary filters")
    if len(matches) > 1:
        titles = ", ".join(
            (match.title or match.relative_path) for match in matches[:5]
        )
        raise ValueError(
            "summary requires one book, but filters matched "
            f"{len(matches)} books: {titles}"
        )
    return matches[0]


def _build_sections(
    chunks: list[SummaryChunkRecord],
    *,
    chunks_per_section: int,
    max_section_chars: int,
) -> list[_Section]:
    max_section_chars = max(1000, max_section_chars)
    if any(chunk.chapter_title for chunk in chunks):
        sections: list[_Section] = []
        current_title = chunks[0].chapter_title
        current_chunks: list[SummaryChunkRecord] = []
        current_chars = 0
        for chunk in chunks:
            next_chars = current_chars + len(chunk.text)
            title_changed = chunk.chapter_title != current_title
            section_full = (
                len(current_chunks) >= max(1, chunks_per_section)
                or next_chars > max_section_chars
            )
            if current_chunks and (title_changed or section_full):
                sections.append(
                    _Section(
                        key=f"chapter-{len(sections) + 1:03d}",
                        title=current_title,
                        chunks=current_chunks,
                    )
                )
                current_chunks = []
                current_chars = 0
                current_title = chunk.chapter_title
            current_chunks.append(chunk)
            current_chars += len(chunk.text)
        if current_chunks:
            sections.append(
                _Section(
                    key=f"chapter-{len(sections) + 1:03d}",
                    title=current_title,
                    chunks=current_chunks,
                )
            )
        return sections

    page_size = max(1, chunks_per_section)
    sections = []
    window: list[SummaryChunkRecord] = []
    window_chars = 0
    for chunk in chunks:
        next_chars = window_chars + len(chunk.text)
        if window and (len(window) >= page_size or next_chars > max_section_chars):
            sections.append(
                _Section(
                    key=f"chunk-window-{len(sections) + 1:03d}",
                    title=f"Chunks {window[0].chunk_index}-{window[-1].chunk_index}",
                    chunks=window,
                )
            )
            window = []
            window_chars = 0
        window.append(chunk)
        window_chars += len(chunk.text)
    if window:
        sections.append(
            _Section(
                key=f"chunk-window-{len(sections) + 1:03d}",
                title=f"Chunks {window[0].chunk_index}-{window[-1].chunk_index}",
                chunks=window,
            )
        )
    return sections


def _chapter_summary_messages(
    *,
    book: StoredSummaryBookRecord,
    section: _Section,
    detail: str,
) -> list[ChatMessage]:
    return [
        ChatMessage(
            role="system",
            content=(
                "You summarize book sections for a local personal library. "
                "Use only the supplied text. Preserve important names, events, "
                "claims, themes, and unresolved questions."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Book: {book.title or book.relative_path}\n"
                f"Authors: {', '.join(book.authors) or 'Unknown'}\n"
                f"Section: {section.title or section.key}\n"
                f"Detail level: {detail}\n\n"
                f"Target size: {_chapter_detail_guidance(detail)}\n\n"
                "Summarize this section in a way that can later be combined "
                "into a full book summary.\n\n"
                f"Section text:\n{section.text}"
            ),
        ),
    ]


def _book_summary_messages(
    *,
    book: StoredSummaryBookRecord,
    summaries: list[ChapterSummary],
    detail: str,
) -> list[ChatMessage]:
    joined = "\n\n".join(
        f"[{summary.chapter_key}] {summary.chapter_title or summary.chapter_key}\n"
        f"{summary.summary}"
        for summary in summaries
    )
    return [
        ChatMessage(
            role="system",
            content=(
                "You synthesize book summaries for a local personal library. "
                "Use only the supplied section summaries. Do not invent details."
            ),
        ),
        ChatMessage(
            role="user",
            content=(
                f"Book: {book.title or book.relative_path}\n"
                f"Authors: {', '.join(book.authors) or 'Unknown'}\n"
                f"Detail level: {detail}\n\n"
                f"Target size: {_book_detail_guidance(detail)}\n\n"
                "Create a coherent whole-book summary. Include the main arc, "
                "major ideas or plot points, important characters where relevant, "
                "and overall themes.\n\n"
                f"Section summaries:\n{joined}"
            ),
        ),
    ]


def _condense_until_fits(
    *,
    generator,
    book: StoredSummaryBookRecord,
    summaries: list[ChapterSummary],
    detail: str,
    max_reduce_inputs: int,
    progress_callback: Callable[[SummaryProgress], None] | None,
) -> list[ChapterSummary]:
    current = summaries
    round_number = 1
    while len(current) > max_reduce_inputs:
        condensed: list[ChapterSummary] = []
        groups = list(range(0, len(current), max_reduce_inputs))
        for index, start in enumerate(groups, start=1):
            group = current[start : start + max_reduce_inputs]
            _emit_progress(
                progress_callback,
                stage="reduce",
                current=index,
                total=len(groups),
                message=(
                    f"Condensing summary group {index}/{len(groups)} "
                    f"for reduce round {round_number}."
                ),
            )
            summary_text = generator.generate(
                _book_summary_messages(book=book, summaries=group, detail=detail)
            )
            condensed.append(
                ChapterSummary(
                    chapter_key=f"condensed-{round_number:02d}-{index:03d}",
                    chapter_title=f"Condensed summaries {start + 1}-{start + len(group)}",
                    chunk_start_index=group[0].chunk_start_index,
                    chunk_end_index=group[-1].chunk_end_index,
                    summary=summary_text,
                    source_hash=_book_source_hash(group),
                    cached=False,
                )
            )
        current = condensed
        round_number += 1
    return current


def _section_source_hash(section: _Section) -> str:
    digest = hashlib.sha256()
    for chunk in section.chunks:
        digest.update(chunk.id.encode("utf-8"))
        digest.update(str(chunk.chunk_index).encode("utf-8"))
        digest.update(chunk.text.encode("utf-8"))
    return digest.hexdigest()


def _book_source_hash(summaries: list[ChapterSummary]) -> str:
    digest = hashlib.sha256()
    for summary in summaries:
        digest.update(summary.chapter_key.encode("utf-8"))
        digest.update(summary.source_hash.encode("utf-8"))
        digest.update(summary.summary.encode("utf-8"))
    return digest.hexdigest()


def _summary_id(*parts: str) -> str:
    return hashlib.sha256(":".join(parts).encode("utf-8")).hexdigest()


def _normalize_detail(detail: str) -> str:
    normalized = detail.strip().casefold()
    if normalized not in {"short", "medium", "detailed"}:
        raise ValueError("detail must be one of: short, medium, detailed")
    return normalized


def _chapter_detail_guidance(detail: str) -> str:
    if detail == "short":
        return "1 concise paragraph, roughly 80-140 words."
    if detail == "detailed":
        return "5-8 paragraphs or bullets, roughly 500-900 words."
    return "2-4 paragraphs or bullets, roughly 200-400 words."


def _book_detail_guidance(detail: str) -> str:
    if detail == "short":
        return "3-5 paragraphs, roughly 500-800 words."
    if detail == "detailed":
        return "10-16 paragraphs with themes and arcs, roughly 1800-3000 words."
    return "6-10 paragraphs with major plot points and themes, roughly 900-1500 words."


def _emit_progress(
    callback: Callable[[SummaryProgress], None] | None,
    *,
    stage: str,
    current: int,
    total: int,
    message: str,
) -> None:
    if callback is None:
        return
    callback(
        SummaryProgress(
            stage=stage,
            current=current,
            total=total,
            message=message,
        )
    )


def _clean_filter(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None
