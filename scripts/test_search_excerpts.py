#!/usr/bin/env python3
from notes_mcp import db, service
from notes_mcp.search_excerpts import collect_excerpts, parse_highlight_terms

db.init_db()
note = db.create_note("API errors", "First paragraph about timeout.\n\nSecond mentions kubernetes pods.")
terms = parse_highlight_terms("timeout kubernetes")
excerpts = collect_excerpts(note, [], terms)
assert len(excerpts) == 2
assert any(e["source"] == "body" and "timeout" in e["paragraph"] for e in excerpts)
result = service.search_notes("timeout")
assert result["hits"][0]["excerpts"]
print("ok", len(result["hits"][0]["excerpts"]), "excerpts")
