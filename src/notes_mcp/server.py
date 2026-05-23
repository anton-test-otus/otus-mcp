"""MCP server entrypoint."""

from __future__ import annotations

import json
from typing import Any

from mcp.server.fastmcp import FastMCP

from notes_mcp import db, service, storage
from notes_mcp.config import DEFAULT_OCR_LANG
from notes_mcp.db import ImageNotFoundError, NoteNotFoundError
from notes_mcp.ocr import OcrError
from notes_mcp.storage import ImageValidationError

mcp = FastMCP(
    "notes-knowledge",
    instructions=(
        "Local notes knowledge base with image OCR (Tesseract) and full-text search. "
        "Use create_note and add_image for screenshots; search_notes finds text in bodies and OCR."
    ),
    streamable_http_path="/",
)

db.init_db()


def _json(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False)


@mcp.tool()
def create_note(
    title: str,
    body: str = "",
    image_paths: list[str] | None = None,
    ocr_lang: str = DEFAULT_OCR_LANG,
) -> str:
    """Create a note. Optionally attach images by absolute paths; OCR runs on each image."""
    try:
        result = service.create_note(title, body, image_paths, ocr_lang=ocr_lang)
        return _json(result)
    except (ValueError, NoteNotFoundError, ImageValidationError, OcrError) as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def update_note(
    note_id: str,
    title: str | None = None,
    body: str | None = None,
) -> str:
    """Update note title and/or body."""
    try:
        note = db.update_note(note_id, title=title, body=body)
        return _json(service._note_dict(note))
    except NoteNotFoundError as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def add_image(
    note_id: str,
    image_path: str,
    ocr_lang: str = DEFAULT_OCR_LANG,
) -> str:
    """Attach an image to a note, run OCR, and index extracted text for search."""
    try:
        image = service.ingest_image(note_id, image_path, ocr_lang=ocr_lang)
        message = "Text extracted from image." if image.ocr_text else "No text detected in image."
        return _json({"message": message, "image": service._image_dict(image)})
    except (NoteNotFoundError, ImageValidationError, OcrError) as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def reprocess_image(image_id: str, ocr_lang: str = DEFAULT_OCR_LANG) -> str:
    """Re-run Tesseract OCR on a stored image."""
    try:
        image = service.reprocess_image(image_id, ocr_lang=ocr_lang)
        message = "Text extracted from image." if image.ocr_text else "No text detected in image."
        return _json({"message": message, "image": service._image_dict(image)})
    except (ImageNotFoundError, OcrError) as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def search_notes(query: str, limit: int = 20, offset: int = 0) -> str:
    """Full-text search across note titles, bodies, and OCR text from images."""
    try:
        return _json(service.search_notes(query, limit=limit, offset=offset))
    except ValueError as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def get_note(note_id: str, include_images: bool = True) -> str:
    """Fetch a note by id."""
    try:
        note, images = db.get_note(note_id)
        imgs = images if include_images else None
        return _json(service._note_dict(note, imgs))
    except NoteNotFoundError as exc:
        return _json({"error": str(exc)})


@mcp.tool()
def list_notes(limit: int = 50, offset: int = 0) -> str:
    """List notes ordered by most recently updated."""
    notes = db.list_notes(limit=limit, offset=offset)
    return _json({"count": len(notes), "notes": [service._note_dict(n) for n in notes]})


@mcp.tool()
def delete_note(note_id: str) -> str:
    """Delete a note, its images, and FTS index entries."""
    try:
        db.delete_note(note_id)
        return _json({"deleted": note_id})
    except NoteNotFoundError as exc:
        return _json({"error": str(exc)})


@mcp.resource("note://{note_id}")
def note_resource(note_id: str) -> str:
    """Markdown view of a note including OCR text from images."""
    try:
        note, images = db.get_note(note_id)
        return db.note_to_markdown(note, images)
    except NoteNotFoundError:
        return f"Note not found: {note_id}"


@mcp.resource("notes://recent")
def recent_notes_resource() -> str:
    """List of recent notes (id, title, updated_at)."""
    notes = db.list_notes(limit=20, offset=0)
    lines = ["# Recent notes", ""]
    for note in notes:
        lines.append(f"- **{note.title}** (`{note.id}`) — updated {note.updated_at}")
    if not notes:
        lines.append("_No notes yet._")
    return "\n".join(lines) + "\n"


@mcp.prompt()
def summarize_search_results(query: str) -> str:
    """Search notes and summarize matching content for the user."""
    try:
        result = service.search_notes(query, limit=10)
    except ValueError as exc:
        return f"Invalid search query: {exc}"
    if not result["hits"]:
        return f"No notes found for query: {query}"
    return (
        f"Search the knowledge base for '{query}' and summarize these hits:\n\n"
        f"{_json(result)}"
    )


def main() -> None:
    mcp.run(transport="stdio")


def main_http() -> None:
    import os

    host = os.environ.get("NOTES_MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("NOTES_MCP_PORT", "8000"))
    mcp.settings.host = host
    mcp.settings.port = port
    mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main()
