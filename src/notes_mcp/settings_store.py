"""Persist UI / MCP connection settings."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, fields
from typing import Any

from notes_mcp.config import DEFAULT_OCR_LANG, PUBLIC_BASE_URL, SETTINGS_PATH

_OCR_LANG_ALIASES = {"ru": DEFAULT_OCR_LANG, "en": "eng"}


def normalize_ocr_lang(value: str | None) -> str:
    if not value or not value.strip():
        return DEFAULT_OCR_LANG
    normalized = _OCR_LANG_ALIASES.get(value.strip(), value.strip())
    return normalized or DEFAULT_OCR_LANG


@dataclass
class AppSettings:
    mcp_public_url: str = ""
    model_provider: str = "openai"
    model_name: str = "gpt-4o"
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    ocr_lang: str = DEFAULT_OCR_LANG

    def __post_init__(self) -> None:
        if not self.mcp_public_url:
            self.mcp_public_url = f"{PUBLIC_BASE_URL.rstrip('/')}/mcp"

    def to_public_dict(self) -> dict[str, Any]:
        data = asdict(self)
        if data["openai_api_key"]:
            key = data["openai_api_key"]
            data["openai_api_key_set"] = True
            data["openai_api_key"] = f"{key[:4]}...{key[-4:]}" if len(key) > 8 else "***"
        else:
            data["openai_api_key_set"] = False
            data["openai_api_key"] = ""
        return data

    def cursor_mcp_config(self) -> dict[str, Any]:
        return {
            "mcpServers": {
                "notes-knowledge": {
                    "url": self.mcp_public_url,
                    "transport": "streamable-http",
                }
            }
        }


def _ensure_parent() -> None:
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_settings() -> AppSettings:
    if not SETTINGS_PATH.exists():
        return AppSettings()
    raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    known = {f.name for f in fields(AppSettings)}
    filtered = {k: v for k, v in raw.items() if k in known}
    settings = AppSettings(**filtered)
    normalized = normalize_ocr_lang(settings.ocr_lang)
    if normalized != settings.ocr_lang:
        settings.ocr_lang = normalized
        save_settings(settings)
    return settings


def save_settings(settings: AppSettings) -> AppSettings:
    _ensure_parent()
    SETTINGS_PATH.write_text(
        json.dumps(asdict(settings), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return settings


def update_settings(**kwargs: str) -> AppSettings:
    current = load_settings()
    for key, value in kwargs.items():
        if hasattr(current, key) and value is not None:
            if key == "ocr_lang":
                value = normalize_ocr_lang(value)
            setattr(current, key, value)
    return save_settings(current)
