import os
from pathlib import Path

_PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = _PACKAGE_DIR.parent.parent

DATA_DIR = Path(os.environ.get("NOTES_MCP_DATA_DIR", PROJECT_ROOT / "data"))
DB_PATH = DATA_DIR / "notes.db"
IMAGES_DIR = DATA_DIR / "images"

MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_OCR_CHARS = 50_000
# Russian + English for mixed UI screenshots (Tesseract multi-lang syntax)
DEFAULT_OCR_LANG = os.environ.get("NOTES_MCP_OCR_LANG", "rus+eng")
ALLOWED_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif"}

WEB_HOST = os.environ.get("NOTES_MCP_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("NOTES_MCP_PORT", "8080"))
PUBLIC_BASE_URL = os.environ.get("NOTES_MCP_PUBLIC_URL", f"http://localhost:{WEB_PORT}")
SETTINGS_PATH = DATA_DIR / "settings.json"
