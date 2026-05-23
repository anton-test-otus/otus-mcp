"""SQLite persistence and FTS5 full-text search."""

from __future__ import annotations

import re
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from notes_mcp.config import DB_PATH, IMAGES_DIR


class NoteNotFoundError(LookupError):
    pass


class ImageNotFoundError(LookupError):
    pass


@dataclass
class NoteRow:
    id: str
    title: str
    body: str
    created_at: str
    updated_at: str


@dataclass
class ImageRow:
    id: str
    note_id: str
    file_path: str
    mime_type: str | None
    ocr_text: str
    ocr_lang: str
    created_at: str


@dataclass
class SearchHit:
    note_id: str
    title: str
    score: float
    snippets: list[dict[str, Any]]


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    _ensure_dirs()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS notes (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS images (
                id TEXT PRIMARY KEY,
                note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE,
                file_path TEXT NOT NULL,
                mime_type TEXT,
                ocr_text TEXT NOT NULL DEFAULT '',
                ocr_lang TEXT NOT NULL DEFAULT 'rus+eng',
                created_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_images_note_id ON images(note_id);

            CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
                note_id UNINDEXED,
                title,
                body,
                ocr_text,
                tokenize='unicode61'
            );
            """
        )


def _aggregate_ocr(conn: sqlite3.Connection, note_id: str) -> str:
    rows = conn.execute(
        "SELECT ocr_text FROM images WHERE note_id = ? ORDER BY created_at",
        (note_id,),
    ).fetchall()
    return "\n\n".join(r["ocr_text"] for r in rows if r["ocr_text"])


def _upsert_fts(conn: sqlite3.Connection, note_id: str) -> None:
    row = conn.execute(
        "SELECT id, title, body FROM notes WHERE id = ?",
        (note_id,),
    ).fetchone()
    if row is None:
        return
    ocr_text = _aggregate_ocr(conn, note_id)
    conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
    conn.execute(
        "INSERT INTO notes_fts (note_id, title, body, ocr_text) VALUES (?, ?, ?, ?)",
        (note_id, row["title"], row["body"], ocr_text),
    )


def create_note(title: str, body: str = "") -> NoteRow:
    note_id = str(uuid.uuid4())
    now = _utc_now()
    with connect() as conn:
        conn.execute(
            "INSERT INTO notes (id, title, body, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
            (note_id, title, body, now, now),
        )
        _upsert_fts(conn, note_id)
    return NoteRow(id=note_id, title=title, body=body, created_at=now, updated_at=now)


def update_note(
    note_id: str,
    *,
    title: str | None = None,
    body: str | None = None,
) -> NoteRow:
    with connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NoteNotFoundError(f"Note not found: {note_id}")
        new_title = title if title is not None else row["title"]
        new_body = body if body is not None else row["body"]
        now = _utc_now()
        conn.execute(
            "UPDATE notes SET title = ?, body = ?, updated_at = ? WHERE id = ?",
            (new_title, new_body, now, note_id),
        )
        _upsert_fts(conn, note_id)
        return NoteRow(
            id=note_id,
            title=new_title,
            body=new_body,
            created_at=row["created_at"],
            updated_at=now,
        )


def delete_note(note_id: str) -> None:
    with connect() as conn:
        row = conn.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NoteNotFoundError(f"Note not found: {note_id}")
        images = conn.execute(
            "SELECT file_path FROM images WHERE note_id = ?",
            (note_id,),
        ).fetchall()
        conn.execute("DELETE FROM notes WHERE id = ?", (note_id,))
        conn.execute("DELETE FROM notes_fts WHERE note_id = ?", (note_id,))
    note_dir = IMAGES_DIR / note_id
    if note_dir.exists():
        for path in note_dir.iterdir():
            path.unlink(missing_ok=True)
        note_dir.rmdir()
    for img in images:
        Path(img["file_path"]).unlink(missing_ok=True)


def get_note(note_id: str) -> tuple[NoteRow, list[ImageRow]]:
    with connect() as conn:
        row = conn.execute("SELECT * FROM notes WHERE id = ?", (note_id,)).fetchone()
        if row is None:
            raise NoteNotFoundError(f"Note not found: {note_id}")
        images = conn.execute(
            "SELECT * FROM images WHERE note_id = ? ORDER BY created_at",
            (note_id,),
        ).fetchall()
        note = NoteRow(
            id=row["id"],
            title=row["title"],
            body=row["body"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        image_rows = [
            ImageRow(
                id=i["id"],
                note_id=i["note_id"],
                file_path=i["file_path"],
                mime_type=i["mime_type"],
                ocr_text=i["ocr_text"],
                ocr_lang=i["ocr_lang"],
                created_at=i["created_at"],
            )
            for i in images
        ]
        return note, image_rows


def list_notes(limit: int = 50, offset: int = 0) -> list[NoteRow]:
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM notes
            ORDER BY updated_at DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [
            NoteRow(
                id=r["id"],
                title=r["title"],
                body=r["body"],
                created_at=r["created_at"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


def add_image_record(
    note_id: str,
    file_path: str,
    *,
    mime_type: str | None,
    ocr_text: str,
    ocr_lang: str,
) -> ImageRow:
    image_id = str(uuid.uuid4())
    now = _utc_now()
    with connect() as conn:
        note = conn.execute("SELECT id FROM notes WHERE id = ?", (note_id,)).fetchone()
        if note is None:
            raise NoteNotFoundError(f"Note not found: {note_id}")
        conn.execute(
            """
            INSERT INTO images (id, note_id, file_path, mime_type, ocr_text, ocr_lang, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (image_id, note_id, file_path, mime_type, ocr_text, ocr_lang, now),
        )
        _upsert_fts(conn, note_id)
    return ImageRow(
        id=image_id,
        note_id=note_id,
        file_path=file_path,
        mime_type=mime_type,
        ocr_text=ocr_text,
        ocr_lang=ocr_lang,
        created_at=now,
    )


def update_image_ocr(image_id: str, ocr_text: str, ocr_lang: str) -> ImageRow:
    with connect() as conn:
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            raise ImageNotFoundError(f"Image not found: {image_id}")
        conn.execute(
            "UPDATE images SET ocr_text = ?, ocr_lang = ? WHERE id = ?",
            (ocr_text, ocr_lang, image_id),
        )
        conn.execute(
            "UPDATE notes SET updated_at = ? WHERE id = ?",
            (_utc_now(), row["note_id"]),
        )
        _upsert_fts(conn, row["note_id"])
        return ImageRow(
            id=row["id"],
            note_id=row["note_id"],
            file_path=row["file_path"],
            mime_type=row["mime_type"],
            ocr_text=ocr_text,
            ocr_lang=ocr_lang,
            created_at=row["created_at"],
        )


def get_image(image_id: str) -> ImageRow:
    with connect() as conn:
        row = conn.execute("SELECT * FROM images WHERE id = ?", (image_id,)).fetchone()
        if row is None:
            raise ImageNotFoundError(f"Image not found: {image_id}")
        return ImageRow(
            id=row["id"],
            note_id=row["note_id"],
            file_path=row["file_path"],
            mime_type=row["mime_type"],
            ocr_text=row["ocr_text"],
            ocr_lang=row["ocr_lang"],
            created_at=row["created_at"],
        )


def sanitize_fts_query(query: str) -> str:
    """Escape FTS5 special chars; keep phrases in double quotes."""
    query = query.strip()
    if not query:
        raise ValueError("Search query cannot be empty")
    if query.startswith('"') and query.endswith('"'):
        inner = query[1:-1].replace('"', '""')
        return f'"{inner}"'
    tokens = re.findall(r'"[^"]+"|\S+', query)
    cleaned: list[str] = []
    for token in tokens:
        if token.startswith('"') and token.endswith('"'):
            inner = token[1:-1].replace('"', '""')
            cleaned.append(f'"{inner}"')
        else:
            safe = re.sub(r'[^\w\-.@]', '', token, flags=re.UNICODE)
            if safe:
                cleaned.append(f"{safe}*")
    if not cleaned:
        raise ValueError("Search query has no valid terms")
    return " ".join(cleaned)


def search_notes(query: str, limit: int = 20, offset: int = 0) -> list[SearchHit]:
    fts_query = sanitize_fts_query(query)
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT
                note_id,
                title,
                snippet(notes_fts, 1, '[[', ']]', '...', 48) AS title_snippet,
                snippet(notes_fts, 2, '[[', ']]', '...', 64) AS body_snippet,
                snippet(notes_fts, 3, '[[', ']]', '...', 64) AS ocr_snippet,
                bm25(notes_fts) AS rank
            FROM notes_fts
            WHERE notes_fts MATCH ?
            ORDER BY rank
            LIMIT ? OFFSET ?
            """,
            (fts_query, limit, offset),
        ).fetchall()

    hits: list[SearchHit] = []
    for row in rows:
        snippets: list[dict[str, Any]] = []
        if row["title_snippet"] and "[[" in row["title_snippet"]:
            snippets.append({"source": "title", "text": row["title_snippet"]})
        if row["body_snippet"] and "[[" in row["body_snippet"]:
            snippets.append({"source": "body", "text": row["body_snippet"]})
        if row["ocr_snippet"] and "[[" in row["ocr_snippet"]:
            snippets.append({"source": "ocr", "text": row["ocr_snippet"]})
        hits.append(
            SearchHit(
                note_id=row["note_id"],
                title=row["title"],
                score=round(-float(row["rank"]), 4),
                snippets=snippets,
            )
        )
    return hits


def note_to_markdown(note: NoteRow, images: list[ImageRow]) -> str:
    lines = [f"# {note.title}", "", note.body or "_(empty body)_", ""]
    if images:
        lines.append("## Images (OCR)")
        for img in images:
            lines.append(f"### Image `{img.id}`")
            lines.append(f"- Path: `{img.file_path}`")
            lines.append(f"- Language: `{img.ocr_lang}`")
            if img.ocr_text.strip():
                lines.append("")
                lines.append("```")
                lines.append(img.ocr_text.strip())
                lines.append("```")
            else:
                lines.append("")
                lines.append("_(no text detected)_")
            lines.append("")
    return "\n".join(lines).strip() + "\n"
