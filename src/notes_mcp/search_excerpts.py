"""Build paragraph excerpts with highlighted match spans for search results."""

from __future__ import annotations

import re
from typing import Any

from notes_mcp.db import ImageRow, NoteRow


def parse_highlight_terms(query: str) -> list[str]:
    """Terms to highlight in excerpts (raw user query, not FTS syntax)."""
    query = query.strip()
    if not query:
        return []
    quoted = re.findall(r'"([^"]+)"', query)
    if quoted:
        return [q for q in quoted if q]
    return [t for t in re.findall(r"[^\s\"]+", query) if t]


def split_paragraphs(text: str) -> list[str]:
    if not text or not text.strip():
        return []
    parts = re.split(r"\n\s*\n+", text.strip())
    paragraphs: list[str] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "\n" in part:
            paragraphs.extend(line.strip() for line in part.splitlines() if line.strip())
        else:
            paragraphs.append(part)
    return paragraphs


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return []
    sorted_ranges = sorted(ranges)
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def _find_match_ranges(text: str, terms: list[str]) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for term in terms:
        if len(term) < 1:
            continue
        pattern = re.compile(re.escape(term), re.IGNORECASE | re.UNICODE)
        ranges.extend((m.start(), m.end()) for m in pattern.finditer(text))
    return _merge_ranges(ranges)


def build_segments(text: str, terms: list[str]) -> list[dict[str, Any]] | None:
    ranges = _find_match_ranges(text, terms)
    if not ranges:
        return None
    segments: list[dict[str, Any]] = []
    pos = 0
    for start, end in ranges:
        if start > pos:
            segments.append({"text": text[pos:start], "match": False})
        segments.append({"text": text[start:end], "match": True})
        pos = end
    if pos < len(text):
        segments.append({"text": text[pos:], "match": False})
    return segments


def _excerpt(
    *,
    source: str,
    label: str,
    paragraph: str,
    terms: list[str],
    image_id: str | None = None,
) -> dict[str, Any] | None:
    segments = build_segments(paragraph, terms)
    if not segments:
        return None
    return {
        "source": source,
        "label": label,
        "image_id": image_id,
        "paragraph": paragraph,
        "segments": segments,
    }


def collect_excerpts(
    note: NoteRow,
    images: list[ImageRow],
    terms: list[str],
) -> list[dict[str, Any]]:
    if not terms:
        return []

    excerpts: list[dict[str, Any]] = []

    if note.title.strip():
        ex = _excerpt(
            source="title",
            label="Заголовок",
            paragraph=note.title.strip(),
            terms=terms,
        )
        if ex:
            excerpts.append(ex)

    for para in split_paragraphs(note.body):
        ex = _excerpt(
            source="body",
            label="Текст заметки",
            paragraph=para,
            terms=terms,
        )
        if ex:
            excerpts.append(ex)

    for image in images:
        if not image.ocr_text.strip():
            continue
        for para in split_paragraphs(image.ocr_text):
            ex = _excerpt(
                source="ocr",
                label="Скриншот (OCR)",
                paragraph=para,
                terms=terms,
                image_id=image.id,
            )
            if ex:
                excerpts.append(ex)

    return excerpts


def enrich_search_hits(
    hits: list[Any],
    terms: list[str],
    *,
    get_note_with_images,
) -> list[dict[str, Any]]:
    """Attach paragraph excerpts to FTS hits."""
    enriched: list[dict[str, Any]] = []
    for hit in hits:
        note, images = get_note_with_images(hit.note_id)
        excerpts = collect_excerpts(note, images, terms)
        enriched.append(
            {
                "note_id": hit.note_id,
                "title": hit.title,
                "score": hit.score,
                "excerpts": excerpts,
            }
        )
    return enriched
