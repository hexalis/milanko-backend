#!/usr/bin/env python3
"""Export the OpenAPI schema to docs/03-backend/openapi.json.

Usage:
  .venv/bin/python api/export_openapi.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.app import app  # noqa: E402

OUT = ROOT / "docs" / "03-backend" / "openapi.json"


def main() -> None:
    schema = app.openapi()
    schema["servers"] = [{"url": "/api/v1", "description": "Canonical version"}]
    payload = json.dumps(schema, ensure_ascii=False, indent=2)
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != payload:
            print(f"OUTDATED -> {OUT}; run api/export_openapi.py")
            raise SystemExit(1)
        print(f"OK -> {OUT} ({len(schema.get('paths', {}))} documented routes)")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    print(f"OK -> {OUT} ({len(schema.get('paths', {}))} documented routes)")


if __name__ == "__main__":
    main()
