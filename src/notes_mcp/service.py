"""Business logic shared by MCP tools."""

from __future__ import annotations

from typing import Any

from notes_mcp import db, ocr, storage
from notes_mcp.config import DEFAULT_OCR_LANG


def _note_dict(note: db.NoteRow, images: list[db.ImageRow] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": note.id,
        "title": note.title,
        "body": note.body,
        "created_at": note.created_at,
        "updated_at": note.updated_at,
    }
    if images is not None:
        payload["images"] = [_image_dict(img) for img in images]
    return payload


def _image_dict(image: db.ImageRow) -> dict[str, Any]:
    return {
        "id": image.id,
        "note_id": image.note_id,
        "file_path": image.file_path,
        "mime_type": image.mime_type,
        "ocr_text": image.ocr_text,
        "ocr_lang": image.ocr_lang,
        "ocr_char_count": len(image.ocr_text),
        "created_at": image.created_at,
    }


def create_note(
    title: str,
    body: str = "",
    image_paths: list[str] | None = None,
    ocr_lang: str = DEFAULT_OCR_LANG,
) -> dict[str, Any]:
    note = db.create_note(title=title, body=body)
    images: list[db.ImageRow] = []
    for path in image_paths or []:
        images.append(ingest_image(note.id, path, ocr_lang=ocr_lang))
    return _note_dict(note, images)


def ingest_image(note_id: str, image_path: str, ocr_lang: str = DEFAULT_OCR_LANG) -> db.ImageRow:
    source = storage.validate_source_image(image_path)
    vault_path, mime_type = storage.store_image(note_id, source)
    text = ocr.extract_text(vault_path, lang=ocr_lang)
    return db.add_image_record(
        note_id,
        vault_path,
        mime_type=mime_type,
        ocr_text=text,
        ocr_lang=ocr_lang,
    )


def ingest_upload(
    note_id: str,
    filename: str,
    content: bytes,
    ocr_lang: str = DEFAULT_OCR_LANG,
) -> db.ImageRow:
    temp_path = storage.save_upload(note_id, filename, content)
    try:
        return ingest_image(note_id, str(temp_path), ocr_lang=ocr_lang)
    finally:
        temp_path.unlink(missing_ok=True)


def reprocess_image(image_id: str, ocr_lang: str = DEFAULT_OCR_LANG) -> db.ImageRow:
    image = db.get_image(image_id)
    text = ocr.extract_text(image.file_path, lang=ocr_lang)
    return db.update_image_ocr(image_id, text, ocr_lang)


def search_notes(query: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    from notes_mcp.search_excerpts import enrich_search_hits, parse_highlight_terms

    hits = db.search_notes(query, limit=limit, offset=offset)
    terms = parse_highlight_terms(query)
    enriched = enrich_search_hits(
        hits,
        terms,
        get_note_with_images=db.get_note,
    )
    return {
        "query": query,
        "count": len(enriched),
        "hits": enriched,
    }
