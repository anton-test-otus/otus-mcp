#!/usr/bin/env python3
"""Smoke test for DB + search. OCR part requires Docker (Tesseract in image).

Run full stack test:
  docker compose exec notes-knowledge python -c "
from notes_mcp import db, service
db.init_db()
print(service.create_note('Docker', 'тест kubernetes'))
print(service.search_notes('kubernetes'))
"
"""

from notes_mcp import db, service

db.init_db()

note = service.create_note(
    title="Smoke test note",
    body="Plain body mentions kubernetes pods.",
)
print("created:", note["id"])

results = service.search_notes("kubernetes")
print("search kubernetes:", results)
print("ok (no OCR — use Docker for image upload tests)")
