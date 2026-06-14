from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class TextChunk:
    chunk_index: int
    text: str
    character_count: int
    token_estimate: int


def clean_text(text: str) -> str:
    paragraphs = [
        re.sub(r"[ \t]+", " ", paragraph).strip()
        for paragraph in re.split(r"\n\s*\n", text)
    ]
    return "\n\n".join(paragraph for paragraph in paragraphs if paragraph)


def chunk_text(
    text: str,
    *,
    target_size: int = 2_000,
    overlap: int = 250,
) -> list[TextChunk]:
    if target_size <= 0:
        raise ValueError("target_size must be greater than 0")
    if overlap < 0:
        raise ValueError("overlap must be greater than or equal to 0")
    if overlap >= target_size:
        raise ValueError("overlap must be smaller than target_size")

    cleaned = clean_text(text)
    if not cleaned:
        return []

    chunks: list[TextChunk] = []
    start = 0

    while start < len(cleaned):
        end = min(start + target_size, len(cleaned))
        if end < len(cleaned):
            paragraph_break = cleaned.rfind("\n\n", start, end)
            sentence_break = cleaned.rfind(". ", start, end)
            split_at = max(paragraph_break, sentence_break)
            if split_at > start + target_size // 2:
                end = split_at + (2 if split_at == paragraph_break else 1)

        chunk = cleaned[start:end].strip()
        if chunk:
            chunks.append(
                TextChunk(
                    chunk_index=len(chunks),
                    text=chunk,
                    character_count=len(chunk),
                    token_estimate=estimate_tokens(chunk),
                )
            )

        if end >= len(cleaned):
            break
        start = max(0, end - overlap)

    return chunks


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4) if text else 0

