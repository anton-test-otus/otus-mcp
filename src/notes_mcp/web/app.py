"""FastAPI app: web UI, REST API, and mounted MCP streamable-http."""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from notes_mcp.config import IMAGES_DIR
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from notes_mcp import db, service
from notes_mcp.db import ImageNotFoundError, NoteNotFoundError
from notes_mcp.ocr import OcrError
from notes_mcp.server import mcp
from notes_mcp.settings_store import AppSettings, load_settings, save_settings, update_settings, normalize_ocr_lang
from notes_mcp.storage import ImageValidationError

STATIC_DIR = Path(__file__).resolve().parent / "static"

# Initialize MCP session manager before mount (requires lifespan below).
mcp_http_app = mcp.streamable_http_app()


@asynccontextmanager
async def _app_lifespan(_app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(
    title="Notes Knowledge",
    description="Upload screenshots, OCR text, search, and connect MCP clients.",
    version="0.1.0",
    lifespan=_app_lifespan,
)

db.init_db()
app.mount("/mcp", mcp_http_app)


class SettingsUpdate(BaseModel):
    mcp_public_url: str | None = None
    model_provider: str | None = None
    model_name: str | None = None
    openai_api_key: str | None = None
    openai_base_url: str | None = None
    ocr_lang: str | None = None


class NoteCreate(BaseModel):
    title: str
    body: str = ""


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/settings")
def get_settings() -> dict[str, Any]:
    settings = load_settings()
    return {
        "settings": settings.to_public_dict(),
        "cursor_mcp": settings.cursor_mcp_config(),
    }


@app.put("/api/settings")
def put_settings(payload: SettingsUpdate) -> dict[str, Any]:
    data = payload.model_dump(exclude_unset=True)
    if "openai_api_key" in data and data["openai_api_key"] == "":
        data.pop("openai_api_key")
    settings = update_settings(**{k: v for k, v in data.items() if v is not None})
    return {
        "settings": settings.to_public_dict(),
        "cursor_mcp": settings.cursor_mcp_config(),
    }


@app.get("/api/notes")
def api_list_notes(limit: int = 50, offset: int = 0) -> dict[str, Any]:
    notes = db.list_notes(limit=limit, offset=offset)
    return {"count": len(notes), "notes": [service._note_dict(n) for n in notes]}


@app.get("/api/notes/{note_id}")
def api_get_note(note_id: str) -> dict[str, Any]:
    try:
        note, images = db.get_note(note_id)
        return service._note_dict(note, images)
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/notes")
def api_create_note(payload: NoteCreate) -> dict[str, Any]:
    return service.create_note(payload.title, payload.body)


@app.delete("/api/notes/{note_id}")
def api_delete_note(note_id: str) -> dict[str, str]:
    try:
        db.delete_note(note_id)
        return {"deleted": note_id}
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/search")
def api_search(q: str, limit: int = 20, offset: int = 0) -> dict[str, Any]:
    try:
        return service.search_notes(q, limit=limit, offset=offset)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_image_path(file_path: str) -> Path:
    path = Path(file_path).resolve()
    root = IMAGES_DIR.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Image file not found") from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image file not found")
    return path


@app.get("/api/images/{image_id}")
def api_get_image(image_id: str) -> FileResponse:
    try:
        image = db.get_image(image_id)
        path = _safe_image_path(image.file_path)
        return FileResponse(path, media_type=image.mime_type or "application/octet-stream")
    except ImageNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/upload")
async def api_upload(
    title: str = Form(...),
    body: str = Form(""),
    ocr_lang: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    content = await file.read()
    effective_ocr_lang = normalize_ocr_lang(ocr_lang or load_settings().ocr_lang)
    try:
        note = service.create_note(title, body, ocr_lang=effective_ocr_lang)
        image = service.ingest_upload(note["id"], file.filename, content, ocr_lang=effective_ocr_lang)
        note_full, images = db.get_note(note["id"])
        result = service._note_dict(note_full, images)
        result["upload"] = {
            "message": "Текст извлечён из изображения." if image.ocr_text else "На изображении текст не обнаружен.",
            "image": service._image_dict(image),
        }
        return result
    except (ImageValidationError, OcrError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/notes/{note_id}/images")
async def api_add_image(
    note_id: str,
    ocr_lang: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    if not file.filename:
        raise HTTPException(status_code=400, detail="Missing filename")
    content = await file.read()
    effective_ocr_lang = normalize_ocr_lang(ocr_lang or load_settings().ocr_lang)
    try:
        image = service.ingest_upload(note_id, file.filename, content, ocr_lang=effective_ocr_lang)
        return {
            "message": "Текст извлечён из изображения." if image.ocr_text else "На изображении текст не обнаружен.",
            "image": service._image_dict(image),
        }
    except NoteNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except (ImageValidationError, OcrError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


def main() -> None:
    import uvicorn

    from notes_mcp.config import WEB_HOST, WEB_PORT

    uvicorn.run(
        "notes_mcp.web.app:app",
        host=WEB_HOST,
        port=WEB_PORT,
        reload=False,
    )
