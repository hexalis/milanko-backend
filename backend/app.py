"""Milanko API — NASA Space Challenge backend.

The public edge (nginx) validates the ``X-API-Key`` header for data endpoints.
This application documents that contract in OpenAPI and keeps ``/health`` and
``/ping`` as small smoke-test endpoints.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import JSONResponse

from . import __version__
from .db import database_status

app = FastAPI(
    title="Milanko API",
    version=__version__,
    summary="NASA Earth observation data for the Milanko explorer",
    description=(
        "Backend for the Milanko public deliverable. Data endpoints require the "
        "`X-API-Key` header; `/health`, `/docs`, `/redoc` and `/openapi.json` are public."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health", tags=["system"], response_model=None)
def health() -> JSONResponse | dict[str, str]:
    """Liveness and database status."""

    database = database_status()
    payload = {
        "status": "ok" if database in ("ok", "not_configured") else "degraded",
        "version": __version__,
        "database": database,
    }
    if database == "error":
        return JSONResponse(status_code=503, content=payload)
    return payload


@app.get("/ping", tags=["system"])
def ping() -> dict[str, bool]:
    """Protected smoke-test endpoint used by the deployment pipeline."""

    return {"pong": True}


def custom_openapi() -> dict:
    """Document the nginx-level API key without duplicating the check in Python."""

    if app.openapi_schema:
        return app.openapi_schema
    schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        routes=app.routes,
    )
    components = schema.setdefault("components", {})
    components["securitySchemes"] = {
        "ApiKeyAuth": {
            "type": "apiKey",
            "in": "header",
            "name": "X-API-Key",
        }
    }
    schema["security"] = [{"ApiKeyAuth": []}]
    for path in ("/health", "/docs", "/redoc", "/openapi.json"):
        operations = schema.get("paths", {}).get(path, {})
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["security"] = []
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi
