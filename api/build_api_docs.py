#!/usr/bin/env python3
"""Build a human-readable Markdown reference from the versioned OpenAPI schema.

The API's Swagger UI (/docs) and ReDoc (/redoc) stay the interactive source of
truth. This file is for the repository and for the Notion sync, and it is
generated so the endpoint index cannot drift from the code.

Usage:
  .venv/bin/python api/build_api_docs.py
  .venv/bin/python api/build_api_docs.py --check
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "docs" / "03-backend" / "openapi.json"
OUT = ROOT / "docs" / "03-backend" / "api-reference.md"
BASE_URL = "https://milanko.hexalis.org/api/v1"
METHODS = ("get", "post", "put", "patch", "delete")


def resolve(schema: dict[str, Any], doc: dict[str, Any]) -> dict[str, Any]:
    """Resolve a local $ref (OpenAPI files here only use local refs)."""
    seen = set()
    while isinstance(schema, dict) and "$ref" in schema and schema["$ref"] not in seen:
        seen.add(schema["$ref"])
        node: Any = doc
        for part in schema["$ref"].lstrip("#/").split("/"):
            node = node[part]
        schema = node
    return schema


def type_of(schema: dict[str, Any] | bool, doc: dict[str, Any]) -> str:
    if not isinstance(schema, dict):
        return "any"
    schema = resolve(schema, doc)
    if "anyOf" in schema:
        return " | ".join(type_of(part, doc) for part in schema["anyOf"])
    if "oneOf" in schema:
        return " | ".join(type_of(part, doc) for part in schema["oneOf"])
    kind = schema.get("type", "object")
    if kind == "array":
        return f"array[{type_of(schema.get('items', {}), doc)}]"
    if "enum" in schema:
        return f"{kind} ({', '.join(str(value) for value in schema['enum'])})"
    if kind == "object" and "additionalProperties" in schema:
        return f"object<string, {type_of(schema['additionalProperties'], doc)}>"
    return kind


def escape(text: Any) -> str:
    return str(text or "").replace("|", "\\|").replace("\n", " ").strip()


def param_rows(operation: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    rows = ["| Name | In | Required | Type | Description |", "|---|---|---|---|---|"]
    for param in operation.get("parameters", []):
        param = resolve(param, doc)
        schema = resolve(param.get("schema", {}), doc)
        rows.append(
            "| `{name}` | {where} | {required} | `{kind}` | {description} |".format(
                name=param.get("name", ""),
                where=param.get("in", ""),
                required="yes" if param.get("required") else "no",
                kind=escape(type_of(schema, doc)),
                description=escape(param.get("description", "")),
            )
        )
    return rows


def body_rows(operation: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    body = operation.get("requestBody")
    if not body:
        return []
    body = resolve(body, doc)
    content = body.get("content", {}).get("application/json", {})
    schema = resolve(content.get("schema", {}), doc)
    name = schema.get("title") or schema.get("$ref", "").split("/")[-1] or "object"
    required = set(schema.get("required", []))
    rows = [
        "",
        f"**JSON body** (`{name}`):",
        "",
        "| Field | Type | Required | Description |",
        "|---|---|---|---|",
    ]
    for key, value in schema.get("properties", {}).items():
        value = resolve(value, doc)
        rows.append(
            "| `{key}` | `{kind}` | {required} | {description} |".format(
                key=key,
                kind=escape(type_of(value, doc)),
                required="yes" if key in required else "no",
                description=escape(value.get("description", "")),
            )
        )
    return rows


def response_rows(operation: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    rows = ["", "**Responses**", "", "| Code | Description | Schema |", "|---|---|---|"]
    for code, response in operation.get("responses", {}).items():
        response = resolve(response, doc)
        content = response.get("content", {})
        schema = ""
        if content:
            first = next(iter(content.values()), {})
            if first.get("schema"):
                schema = f"`{escape(type_of(first['schema'], doc))}`"
        rows.append(f"| `{code}` | {escape(response.get('description', ''))} | {schema} |")
    return rows


def curl_example(method: str, path: str, operation: dict[str, Any]) -> list[str]:
    if method != "get":
        return []
    query = []
    for param in operation.get("parameters", []):
        if param.get("in") == "query" and param.get("required"):
            query.append(f"{param['name']}=<{param['name']}>")
    url = f"{BASE_URL}{path}" + (f"?{'&'.join(query)}" if query else "")
    return ["", "```bash", f'curl "{url}"', "```"]


def operation_section(method: str, path: str, operation: dict[str, Any], doc: dict[str, Any]) -> list[str]:
    title = operation.get("summary") or f"{method.upper()} {path}"
    lines = [f"### `{method.upper()} {path}`", "", title, ""]
    if operation.get("description"):
        lines += [escape(operation["description"]), ""]
    params = param_rows(operation, doc)
    if len(params) > 2:
        lines += params + [""]
    lines += body_rows(operation, doc)
    lines += response_rows(operation, doc)
    lines += curl_example(method, path, operation)
    lines.append("")
    return lines


def build() -> str:
    doc = json.loads(SCHEMA.read_text(encoding="utf-8"))
    info = doc.get("info", {})
    tag_titles = {tag["name"]: tag.get("description", "") for tag in doc.get("tags", [])}
    groups: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for path, operations in doc.get("paths", {}).items():
        for method, operation in operations.items():
            if method not in METHODS:
                continue
            tag = (operation.get("tags") or ["other"])[0]
            groups.setdefault(tag, []).append((method, path, operation))

    lines = [
        "# API reference — Earth Trend Detective",
        "",
        "> Generated from `docs/03-backend/openapi.json` (OpenAPI 3.1). Do not edit by hand:",
        "> change the code or the schemas and re-run `api/build_api_docs.py`.",
        "",
        f"**Version:** {info.get('version', '')}<br>",
        f"**Swagger UI:** [{BASE_URL}/docs]({BASE_URL}/docs)<br>",
        f"**ReDoc:** [{BASE_URL}/redoc]({BASE_URL}/redoc)<br>",
        f"**OpenAPI:** [{BASE_URL}/openapi.json]({BASE_URL}/openapi.json)",
        "",
        f"**Base URL:** `{BASE_URL}` (production). Each environment uses its own subdomain:",
        "`https://dev-milanko.hexalis.org/api/v1`, `https://qa-milanko.hexalis.org/api/v1`.",
        "",
        "## Index",
        "",
        "| Method | Path | What it returns |",
        "|---|---|---|",
    ]
    for tag in sorted(groups):
        for method, path, operation in groups[tag]:
            lines.append(
                f"| `{method.upper()}` | `{path}` | {escape(operation.get('summary', ''))} |"
            )
    lines.append("")
    for tag in sorted(groups):
        lines += [f"## {tag}", ""]
        if tag_titles.get(tag):
            lines += [escape(tag_titles[tag]), ""]
        for method, path, operation in groups[tag]:
            lines += operation_section(method, path, operation, doc)
    return "\n".join(lines).rstrip() + "\n"


def main() -> None:
    content = build()
    if "--check" in sys.argv:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != content:
            print(f"OUTDATED -> {OUT}; run api/build_api_docs.py")
            raise SystemExit(1)
        print(f"OK -> {OUT}")
        return
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content)
    print(f"OK -> {OUT} ({content.count('### `')} endpoints)")


if __name__ == "__main__":
    main()
