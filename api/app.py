"""FastAPI application — NASA Space Challenge research API.

Run:
  .venv/bin/uvicorn api.app:app --reload --port 8000
Docs:
  Swagger UI  -> http://127.0.0.1:8000/docs
  ReDoc       -> http://127.0.0.1:8000/redoc
  OpenAPI     -> http://127.0.0.1:8000/openapi.json
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import Depends, FastAPI, HTTPException, Path, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response

from core.nasa_events import EonetClient, PowerClient
from core.nasa_events.analysis import CATEGORY_PROFILES, anomaly_series, trends_by_variable
from core.nasa_events.catalog import core_codes
from core.nasa_events.sources.eonet import EonetApiError
from core.nasa_events.sources.power import PowerApiError

from core import __version__, db
from . import regions_service, service, world_service
from .deps import get_db_session, get_eonet_client, get_gibs_client, get_power_client
from .schemas import (
    AnomaliesResponse,
    CatalogResponse,
    CategoriesResponse,
    CorrelationsResponse,
    CoverageResponse,
    RegionLatestResponse,
    RegionSnapshotResponse,
    RegionRankingsResponse,
    RegionEventsResponse,
    EventAnalysisResponse,
    EventOut,
    EventStatsResponse,
    EventsResponse,
    HealthResponse,
    HexbinEventsResponse,
    HexbinPointsRequest,
    HexbinPointsResponse,
    ObservationsResponse,
    RegionObservationOut,
    RegionObservationsResponse,
    RegionOut,
    RegionsResponse,
    PointAnalysisRequest,
    PointAnalysisResponse,
    TrendsResponse,
    VariableInfo,
    WorldCellsResponse,
)

TAGS = [
    {"name": "system", "description": "Service status and metadata."},
    {
        "name": "catalog",
        "description": "Master catalog variables (208) with their disposition and EONET categories.",
    },
    {"name": "events", "description": "Normalized EONET v3 catalog (ISO dates, geometries, magnitudes)."},
    {"name": "observations", "description": "Normalized NASA POWER daily series."},
    {
        "name": "analysis",
        "description": (
            "Anomalies (empirical baseline by day of the year), trends (Mann–Kendall + Sen "
            "on seasonally adjusted monthly anomalies), lagged correlations with FDR, and "
            "per-event analysis with adaptive windows. **Correlation ≠ causation.**"
        ),
    },
    {
        "name": "world",
        "description": (
            "Base world of the planet (ETDW binaries: biome, elevation, color, water, "
            "lakes) + configuration to render the 3D globe and GIBS imagery."
        ),
    },
    {
        "name": "regions",
        "description": "Milanko geodesic regions and series persisted in PostgreSQL.",
    },
    {
        "name": "hexbin",
        "description": (
            "Hexagonal binning over the Milanko geodesic grid (same face,i,j encoding): "
            "EONET events or generic points, in JSON or GeoJSON."
        ),
    },
]

app = FastAPI(
    title="Milanko API",
    version=__version__,
    summary="Natural events + environmental variables for research",
    description=(
        "Research API built on **NASA POWER**, **EONET v3**, and **NASA GIBS** "
        "(with FIRMS/AERONET/DONKI as complements).\n\n"
        "### Method\n"
        "- **Anomalies**: empirical percentiles by day of the year (±7 days, 2006+).\n"
        "- **Event windows**: adaptive by category and duration, capped at 90 days.\n"
        "- **Trends**: Mann–Kendall + Sen on seasonally adjusted monthly anomalies.\n"
        "- **Correlations**: events/month vs monthly anomalies, lags −6…+6 and FDR (BH).\n\n"
        "### Limits and notes\n"
        "- POWER: max. 20 variables per request (the server splits them), **local solar time (LST)**.\n"
        "- GIBS: quantifiable via WMS; thermal layers are vectorial (MVT).\n"
        "- **Exploratory** results; the tool does not determine causality.\n\n"
        "### Documentation\n"
        "- Swagger UI: [`/docs`](/docs)\n- ReDoc: [`/redoc`](/redoc)\n"
        "- OpenAPI JSON: [`/openapi.json`](/openapi.json)\n\n"
        "Python code: `core/nasa_events/` · Phase 0 results: `docs/00-recon/` · "
        "Analysis methodology: `docs/02-analysis/methodology.md`."
    ),
    openapi_tags=TAGS,
    contact={"name": "Milanko — NASA Space Challenge"},
    license_info={"name": "NASA data (public domain)"},
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
    schema["servers"] = [{"url": "/api/v1", "description": "Canonical version"}]
    for path in ("/health", "/docs", "/redoc", "/openapi.json"):
        operations = schema.get("paths", {}).get(path, {})
        for operation in operations.values():
            if isinstance(operation, dict):
                operation["security"] = []
    app.openapi_schema = schema
    return schema


app.openapi = custom_openapi


# ---------------------------------------------------------------- error mapping
@app.exception_handler(PowerApiError)
async def _power_error_handler(_request, exc: PowerApiError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "source": "NASA POWER", "upstream_status": exc.status},
    )


@app.exception_handler(EonetApiError)
async def _eonet_error_handler(_request, exc: EonetApiError):
    return JSONResponse(
        status_code=502,
        content={"detail": str(exc), "source": "EONET", "upstream_status": exc.status},
    )


@app.exception_handler(ValueError)
async def _value_error_handler(_request, exc: ValueError):
    return JSONResponse(status_code=422, content={"detail": str(exc)})


def _split_codes(variables: str) -> list[str]:
    return service.validate_power_codes(variables.split(","))


def _split_categories(category: str | None) -> list[str] | None:
    if not category:
        return None
    categories = [part.strip() for part in category.split(",") if part.strip()]
    return categories or None


# ---------------------------------------------------------------------- sistema
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="docs")


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Service status and core size",
)
def health() -> dict:
    database = db.health()
    return {
        "status": "ok" if database in {"ok", "not_configured"} else "degraded",
        "version": __version__,
        "core_variables": len(core_codes()),
        "database": database,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


@app.get(
    "/ping",
    tags=["system"],
    summary="Protected smoke-test endpoint",
)
def ping() -> dict[str, bool]:
    """Used by the deployment pipeline; nginx requires the API key."""
    return {"pong": True}


# -------------------------------------------------------------------- regiones
@app.get(
    "/regions",
    response_model=RegionsResponse,
    tags=["regions"],
    summary="Lists the 162 Milanko geodesic regions",
)
def regions(session=Depends(get_db_session)) -> dict:
    rows = regions_service.list_regions(session)
    return {"count": len(rows), "regions": rows}


@app.get(
    "/regions/rankings",
    response_model=RegionRankingsResponse,
    tags=["regions"],
    summary="Global ranking of regions by value, anomaly, or trend",
)
def regions_rankings(
    variable: str = Query(..., description="Variable code, e.g. T2M"),
    metric: Literal["value", "anomaly", "trend"] = Query("anomaly"),
    order: Literal["desc", "asc"] = Query("desc"),
    date_: str | None = Query(None, alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(10, ge=1, le=162),
    source: str | None = Query(None, description="Source; inferred from the catalog"),
    session=Depends(get_db_session),
) -> dict:
    result = regions_service.region_rankings(
        session,
        variable=variable,
        metric=metric,
        order=order,
        as_of=date.fromisoformat(date_) if date_ else None,
        start=date.fromisoformat(start),
        limit=limit,
        source=source,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variable not found: {variable}")
    return result


@app.get(
    "/regions/snapshot",
    response_model=RegionSnapshotResponse,
    tags=["regions"],
    summary="Value or anomaly of a variable across the 162 regions",
)
def regions_snapshot(
    variable: str = Query(..., description="Variable code, e.g. T2M"),
    date_: str = Query(..., alias="date", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    metric: Literal["value", "anomaly"] = Query("value"),
    source: str | None = Query(None, description="Source; inferred from the catalog"),
    session=Depends(get_db_session),
) -> dict:
    result = regions_service.region_snapshot(
        session,
        variable=variable,
        date=date.fromisoformat(date_),
        metric=metric,
        source=source,
    )
    if result is None:
        raise HTTPException(status_code=404, detail=f"Variable not found: {variable}")
    return result


@app.get(
    "/regions/{region_code}/observations",
    response_model=RegionObservationsResponse,
    tags=["regions"],
    summary="Persisted series for a region",
)
def region_observations(
    region_code: int = Path(..., ge=0, le=161),
    variables: str | None = Query(
        None, description="Comma-separated codes (e.g. LST_DAY,SST)"
    ),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(5000, ge=1, le=20000),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    if start_date > end_date:
        raise ValueError("start must be less than or equal to end")
    codes = [item.strip() for item in variables.split(",") if item.strip()] if variables else None
    result = regions_service.region_observations(
        session,
        region_code,
        variables=codes,
        start=start_date,
        end=end_date,
        limit=limit,
    )
    if result is None:
        raise HTTPException(status_code=404, detail="Region not found")
    # A 20-year daily series is ~7.6k dicts; skip Pydantic re-validation on the
    # hot path and serialize the already-normalized payload directly.
    return JSONResponse(content=result)


@app.get(
    "/regions/{region_code}/latest",
    response_model=RegionLatestResponse,
    tags=["regions"],
    summary="Last valid value of each variable in a region",
)
def region_latest(
    region_code: int = Path(..., ge=0, le=161),
    source: str | None = Query(None, description="E.g. NASA POWER, NASA GIBS"),
    session=Depends(get_db_session),
) -> dict:
    result = regions_service.latest_for_region(session, region_code, source)
    if result is None:
        raise HTTPException(status_code=404, detail="Region not found")
    return result


@app.get(
    "/regions/{region_code}/events",
    response_model=RegionEventsResponse,
    tags=["regions"],
    summary="EONET events associated with a region",
)
def region_events(
    region_code: int = Path(..., ge=0, le=161),
    category: str | None = Query(None, description="Comma-separated categories"),
    status: Literal["open", "closed", "all"] = Query("all"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(100, ge=1, le=500),
    session=Depends(get_db_session),
) -> dict:
    region = regions_service.get_region(session, region_code)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    categories = [item.strip() for item in category.split(",") if item.strip()] if category else None
    rows = regions_service.region_events(
        session,
        region_code,
        categories=categories,
        status=status,
        start=start_date,
        end=end_date,
        limit=limit,
    )
    return {"region": region, "count": len(rows), "events": rows}


@app.get(
    "/regions/{region_code}/trends",
    tags=["regions"],
    summary="Trends for a region using persisted data",
)
def region_trends(
    region_code: int = Path(..., ge=0, le=161),
    variables: str | None = Query(None, description="Comma-separated codes"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    alpha: float = Query(0.05, gt=0, lt=0.5),
    source: str = Query("NASA POWER"),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    region = regions_service.get_region(session, region_code)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")
    codes = [item.strip() for item in variables.split(",") if item.strip()] if variables else None
    series = regions_service.series_for_region(
        session,
        region_code,
        variables=codes,
        start=start_date,
        end=end_date,
        source=source,
    )
    return {
        "region": region,
        "source": source,
        "start": start_date.isoformat(),
        "end": end_date.isoformat(),
        "variables": len(series),
        "trends": trends_by_variable(series, alpha=alpha),
    }


@app.get(
    "/regions/{region_code}/anomalies",
    tags=["regions"],
    summary="Anomalies for a region using persisted data",
)
def region_anomalies(
    region_code: int = Path(..., ge=0, le=161),
    variables: str | None = Query(None, description="Comma-separated codes"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    window_days: int = Query(7, ge=1, le=30),
    source: str = Query("NASA POWER"),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    region = regions_service.get_region(session, region_code)
    if region is None:
        raise HTTPException(status_code=404, detail="Region not found")
    codes = [item.strip() for item in variables.split(",") if item.strip()] if variables else None
    series = regions_service.series_for_region(
        session,
        region_code,
        variables=codes,
        start=start_date,
        end=end_date,
        source=source,
    )
    return {
        "region": region,
        "source": source,
        "baseline_window_days": window_days,
        "variables": {
            code: anomaly_series(values, window_days) for code, values in series.items()
        },
    }


@app.get(
    "/data/coverage",
    response_model=CoverageResponse,
    tags=["system"],
    summary="Coverage of persisted data by variable",
)
def data_coverage(
    source: str | None = Query(None),
    session=Depends(get_db_session),
) -> dict:
    rows = regions_service.coverage(session, source)
    return {"count": len(rows), "variables": rows}


# --------------------------------------------------------------------- catálogo
@app.get(
    "/catalog/variables",
    response_model=CatalogResponse,
    tags=["catalog"],
    summary="Lists the master catalog variables",
)
def catalog_variables(
    source: str | None = Query(
        None, description="Filter by source: NASA POWER, EONET v3, NASA GIBS…"
    ),
    section: str | None = Query(None, description="Filter by section/topic of the master CSV"),
    q: str | None = Query(None, description="Text search in code, name, and definition"),
    limit: int = Query(300, ge=1, le=500, description="Maximum number of results"),
) -> dict:
    items = service.catalog_variables(source, section, q)[:limit]
    return {"count": len(items), "variables": items}


@app.get(
    "/catalog/variables/{code}",
    response_model=VariableInfo,
    tags=["catalog"],
    summary="Details of a variable or layer",
)
def catalog_variable(code: str) -> dict:
    item = service.catalog_variable(code)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Variable not found: {code}")
    return item


@app.get(
    "/catalog/events/categories",
    response_model=CategoriesResponse,
    tags=["catalog"],
    summary="EONET event categories (live)",
)
def event_categories(eonet: EonetClient = Depends(get_eonet_client)) -> dict:
    payload = eonet.categories()
    categories = [
        {"id": item.get("id", ""), "title": item.get("title", "")}
        for item in payload.get("categories", [])
    ]
    return {"count": len(categories), "categories": categories}


# ---------------------------------------------------------------------- eventos
@app.get(
    "/events",
    response_model=EventsResponse,
    tags=["events"],
    summary="Normalized EONET events",
)
def events(
    category: str | None = Query(
        None, description="One or more categories separated by commas (e.g. wildfires,floods)"
    ),
    status: Literal["open", "closed", "all"] = Query("open", description="Event status"),
    start: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2026-01-01"]),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$", examples=["2026-10-19"]),
    days: int | None = Query(None, ge=1, le=36500, description="Last N days"),
    bbox: str | None = Query(
        None,
        description="minLon,maxLat,maxLon,minLat (EONET format)",
        examples=["-76,-17,-66,-56"],
    ),
    limit: int = Query(100, ge=1, le=1000),
    mag_id: str | None = Query(None, description="E.g. mag_kts"),
    mag_min: float | None = Query(None, description="Minimum magnitude"),
    eonet: EonetClient = Depends(get_eonet_client),
) -> dict:
    items = service.list_events(
        eonet,
        _split_categories(category),
        status,
        start,
        end,
        days,
        service.parse_bbox(bbox),
        limit,
        mag_id,
        mag_min,
    )
    return {"count": len(items), "events": items}


@app.get(
    "/events/stats",
    response_model=EventStatsResponse,
    tags=["events"],
    summary="Statistics for the persisted EONET catalog",
)
def persisted_event_stats(
    category: str | None = Query(None, description="Comma-separated categories"),
    status: Literal["open", "closed", "all"] = Query("all"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    categories = [item.strip() for item in category.split(",") if item.strip()] if category else None
    return regions_service.event_stats(
        session,
        categories=categories,
        status=status,
        start=start_date,
        end=end_date,
    )


@app.get(
    "/events/map",
    tags=["events"],
    summary="Representative event points for the globe",
)
def events_map(
    category: str | None = Query(None, description="Comma-separated categories"),
    status: Literal["open", "closed", "all"] = Query("all"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(5000, ge=1, le=20000),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    categories = [item.strip() for item in category.split(",") if item.strip()] if category else None
    return regions_service.event_map(
        session,
        categories=categories,
        status=status,
        start=start_date,
        end=end_date,
        limit=limit,
    )


@app.get(
    "/events/persisted",
    response_model=EventsResponse,
    tags=["events"],
    summary="EONET catalog persisted in PostgreSQL",
)
def persisted_events(
    category: str | None = Query(None, description="Comma-separated categories"),
    status: Literal["open", "closed", "all"] = Query("all"),
    start: str = Query("2006-01-01", pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    limit: int = Query(500, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    session=Depends(get_db_session),
) -> dict:
    start_date = date.fromisoformat(start)
    end_date = date.fromisoformat(end or date.today().isoformat())
    categories = [item.strip() for item in category.split(",") if item.strip()] if category else None
    rows = regions_service.persisted_events(
        session,
        categories=categories,
        status=status,
        start=start_date,
        end=end_date,
        limit=limit,
        offset=offset,
    )
    total = regions_service.count_persisted_events(
        session,
        categories=categories,
        status=status,
        start=start_date,
        end=end_date,
    )
    return JSONResponse(
        content={"count": len(rows), "total": total, "events": rows}
    )


@app.get(
    "/events/{event_id}/context",
    tags=["events"],
    summary="Persisted environmental context for an EONET event",
)
def event_context(
    event_id: str,
    session=Depends(get_db_session),
) -> dict:
    result = regions_service.event_context(session, event_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return result


@app.get(
    "/events/{event_id}",
    response_model=EventOut,
    tags=["events"],
    summary="Details of an EONET event",
)
def event_detail(
    event_id: str,
    eonet: EonetClient = Depends(get_eonet_client),
) -> dict:
    return service.serialize_event(service.get_event(eonet, event_id))


# --------------------------------------------------------------- observaciones
@app.get(
    "/observations",
    response_model=ObservationsResponse,
    tags=["observations"],
    summary="Normalized POWER series (daily or monthly, single point)",
)
def observations(
    variables: str = Query(
        ...,
        description="Comma-separated POWER codes (the server splits them into ≤20 per request)",
        examples=["T2M,PRECTOTCORR,RH2M"],
    ),
    lat: float = Query(..., ge=-90, le=90, examples=[-33.45]),
    lon: float = Query(..., ge=-180, le=180, examples=[-70.66]),
    start: str = Query("20060101", pattern=r"^\d{8}$", examples=["20060101"]),
    end: str | None = Query(None, pattern=r"^\d{8}$", examples=["20261018"]),
    community: Literal["RE", "AG", "SB"] = Query("RE"),
    site_elevation: float | None = Query(
        None, description="Meters; required when querying PSC"
    ),
    granularity: Literal["daily", "monthly"] = Query(
        "daily",
        description=(
            "daily uses daily POWER; monthly uses monthly POWER (start/end are "
            "trimmed to the year)."
        ),
    ),
    power: PowerClient = Depends(get_power_client),
) -> dict:
    return service.observations(
        power,
        _split_codes(variables),
        lat,
        lon,
        start,
        end,
        community,
        site_elevation,
        granularity,
    )


@app.get(
    "/anomalies",
    response_model=AnomaliesResponse,
    tags=["analysis"],
    summary="Daily anomalies (empirical baseline by day of year)",
)
def anomalies(
    variables: str = Query(..., examples=["T2M,PRECTOTCORR"]),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: str = Query("20060101", pattern=r"^\d{8}$"),
    end: str | None = Query(None, pattern=r"^\d{8}$"),
    community: Literal["RE", "AG", "SB"] = Query("RE"),
    site_elevation: float | None = Query(None),
    baseline_window_days: int = Query(7, ge=1, le=30, description="±days window per day of the year"),
    power: PowerClient = Depends(get_power_client),
) -> dict:
    return service.anomalies(
        power,
        _split_codes(variables),
        lat,
        lon,
        start,
        end,
        community,
        site_elevation,
        baseline_window_days,
    )


@app.get(
    "/trends",
    response_model=TrendsResponse,
    tags=["analysis"],
    summary="Monthly trends (Mann–Kendall + Sen, seasonal adjustment)",
)
def trends(
    variables: str = Query(..., examples=["T2M,PRECTOTCORR,RH2M"]),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: str = Query("20060101", pattern=r"^\d{8}$"),
    end: str | None = Query(None, pattern=r"^\d{8}$"),
    community: Literal["RE", "AG", "SB"] = Query("RE"),
    site_elevation: float | None = Query(None),
    alpha: float = Query(0.05, gt=0, lt=0.5, description="Significance level"),
    power: PowerClient = Depends(get_power_client),
) -> dict:
    return service.trends(
        power,
        _split_codes(variables),
        lat,
        lon,
        start,
        end,
        community,
        site_elevation,
        alpha,
    )


@app.get(
    "/correlations",
    response_model=CorrelationsResponse,
    tags=["analysis"],
    summary="Correlation of events/month vs anomalies (lags −N…+N, FDR)",
)
def correlations(
    variables: str = Query(..., examples=["T2M,PRECTOTCORR,RH2M"]),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    category: str | None = Query(
        None, description="Comma-separated EONET categories; empty = all events"
    ),
    start: str = Query("20060101", pattern=r"^\d{8}$"),
    end: str | None = Query(None, pattern=r"^\d{8}$"),
    community: Literal["RE", "AG", "SB"] = Query("RE"),
    site_elevation: float | None = Query(None),
    bbox: str | None = Query(
        None, description="minLon,maxLat,maxLon,minLat (EONET format)"
    ),
    status: Literal["open", "closed", "all"] = Query("all"),
    limit: int = Query(200, ge=1, le=1000, description="Maximum number of EONET events to consider"),
    max_lag_months: int = Query(6, ge=0, le=24),
    method: Literal["spearman", "pearson"] = Query("spearman"),
    baseline_window_days: int = Query(7, ge=1, le=30),
    mag_id: str | None = Query(None),
    mag_min: float | None = Query(None),
    power: PowerClient = Depends(get_power_client),
    eonet: EonetClient = Depends(get_eonet_client),
) -> dict:
    return service.correlations(
        power,
        eonet,
        _split_codes(variables),
        lat,
        lon,
        start,
        end,
        community,
        site_elevation,
        _split_categories(category),
        service.parse_bbox(bbox),
        status,
        limit,
        max_lag_months,
        method,
        baseline_window_days,
        mag_id,
        mag_min,
    )


@app.get(
    "/events/{event_id}/analysis",
    response_model=EventAnalysisResponse,
    tags=["analysis"],
    summary="Anomalies of an event at a point (adaptive window)",
)
def event_analysis(
    event_id: str,
    variables: str = Query(..., examples=["T2M,PRECTOTCORR,RH2M"]),
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start: str = Query(
        "20060101",
        pattern=r"^\d{8}$",
        description="Start of the series used for the baseline (historical)",
    ),
    end: str | None = Query(None, pattern=r"^\d{8}$"),
    community: Literal["RE", "AG", "SB"] = Query("RE"),
    site_elevation: float | None = Query(None),
    baseline_window_days: int = Query(7, ge=1, le=30),
    max_context_days: int = Query(90, ge=7, le=180),
    power: PowerClient = Depends(get_power_client),
    eonet: EonetClient = Depends(get_eonet_client),
) -> dict:
    return service.event_analysis(
        power,
        eonet,
        event_id,
        _split_codes(variables),
        lat,
        lon,
        start,
        end,
        community,
        site_elevation,
        baseline_window_days,
        max_context_days,
    )


@app.post(
    "/analysis/point",
    response_model=PointAnalysisResponse,
    tags=["analysis"],
    summary="Full analysis at a point: trends + events + correlations",
    description=(
        "Runs the Phase 2 pipeline in a single call: daily series, trends, "
        "per-event summaries (adaptive windows), and correlations with lags/FDR. "
        "If `events` is omitted, only trends are computed."
    ),
)
def point_analysis(
    body: PointAnalysisRequest,
    power: PowerClient = Depends(get_power_client),
    eonet: EonetClient = Depends(get_eonet_client),
) -> dict:
    return service.point_analysis(power, eonet, body)


# ------------------------------------------------------------------- mundo base
@app.get(
    "/world/config",
    tags=["world"],
    response_model=None,
    summary="Configuration to render the planet in the Milanko globe",
    description=(
        "Returns all the URLs and metadata the 3D globe needs: base binaries "
        "(ETDW), fine level, decoded cells, hexbinning, and GIBS snapshots."
    ),
)
def world_config() -> dict:
    return world_service.config()


@app.get(
    "/world/meta.json",
    tags=["world"],
    summary="Base world metadata",
)
def world_meta_json():
    return FileResponse(
        world_service.WORLD_DIR / "meta.json", media_type="application/json"
    )


@app.get(
    "/world/base-56.bin",
    tags=["world"],
    summary="Base world f=56 (31.362 cells, ~158 km per cell)",
)
def world_base_56():
    return FileResponse(
        world_service.WORLD_DIR / "base-56.bin",
        media_type="application/octet-stream",
        filename="base-56.bin",
    )


@app.get(
    "/world/base-80.bin",
    tags=["world"],
    summary="Base world f=80 (64.002 cells, ~111 km per cell)",
)
def world_base_80():
    return FileResponse(
        world_service.WORLD_DIR / "base-80.bin",
        media_type="application/octet-stream",
        filename="base-80.bin",
    )


@app.get(
    "/world/fine-288/{filename}",
    tags=["world"],
    summary="Fine level f=288 per region (r000.bin … r161.bin)",
    description="ETDW format; 162 files, one per region.",
)
def world_fine(filename: str):
    if not re.fullmatch(r"r\d{3}\.bin", filename):
        raise HTTPException(status_code=404, detail="file not found")
    path = world_service.WORLD_DIR / "fine-288" / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type="application/octet-stream", filename=filename)


@app.get(
    "/world/cells",
    response_model=WorldCellsResponse,
    tags=["world"],
    summary="Decoded base world cells (biome, elevation, color, water)",
    description=(
        "JSON view of the base binary to explore/color the planet without parsing ETDW. "
        "Lets you filter by biome, water/land, and bbox (west,south,east,north)."
    ),
)
def world_cells(
    f: int = Query(80, description="Grid frequency (56 or 80)"),
    biome: str | None = Query(None, description="E.g. forest, desert, ice, sea, urban"),
    water: bool | None = Query(None, description="true=water, false=land"),
    bbox: str | None = Query(
        None, description="west,south,east,north (supports antimeridian crossing)"
    ),
    limit: int = Query(2000, ge=1, le=20000),
    offset: int = Query(0, ge=0),
) -> dict:
    return world_service.world_cells(
        f,
        biome=biome,
        water=water,
        bbox=world_service.parse_bbox(bbox),
        limit=limit,
        offset=offset,
    )


@app.get(
    "/world/snapshot",
    tags=["world"],
    summary="Satellite image of a point (GIBS proxy, MODIS TrueColor)",
    description=(
        "Returns a PNG of ~km×km centered on the point (MODIS/Terra TrueColor by "
        "default). Useful for the 'view from orbit' of a case file. Default date: today-3."
    ),
    response_class=Response,
    responses={200: {"content": {"image/png": {}}}},
)
def world_snapshot(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    date: str | None = Query(
        None, pattern=r"^\d{4}-\d{2}-\d{2}$", description="YYYY-MM-DD (default today-3)"
    ),
    km: float = Query(220, ge=20, le=2000, description="Width of the crop in km"),
    px: int = Query(480, ge=64, le=1024),
    gibs=Depends(get_gibs_client),
):
    png = world_service.snapshot(
        gibs, lat=lat, lon=lon, date_str=date, km=km, px=px
    )
    return Response(content=png, media_type="image/png")


# ---------------------------------------------------------------------- hexbin
@app.get(
    "/hexgrid/meta",
    tags=["hexbin"],
    response_model=None,
    summary="Metadata for the hexagonal geodesic grid (frequencies, sizes, biomes)",
)
def hexgrid_meta() -> dict:
    return world_service.grid_meta()


@app.get(
    "/hexbin/events",
    response_model=HexbinEventsResponse,
    tags=["hexbin"],
    summary="EONET events aggregated into hexagonal cells",
    description=(
        "Groups each event by its first geometry on the Milanko geodesic grid. "
        "Returns cell code, centroid, count, events, and magnitude totals. "
        "Use `format=geojson` for a FeatureCollection (point or polygon)."
    ),
)
def hexbin_events(
    f: int = Query(80, description="Grid frequency (56 or 80)"),
    category: str | None = Query(
        None, description="Comma-separated EONET categories; empty = all"
    ),
    status: Literal["open", "closed", "all"] = Query("all"),
    start: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    end: str | None = Query(None, pattern=r"^\d{4}-\d{2}-\d{2}$"),
    bbox: str | None = Query(
        None, description="EONET format: minLon,maxLat,maxLon,minLat"
    ),
    limit: int = Query(500, ge=1, le=1000),
    include_geometry: bool = Query(False, description="Include the cell polygon"),
    format: Literal["json", "geojson"] = Query("json"),
    eonet: EonetClient = Depends(get_eonet_client),
):
    payload = world_service.hexbin_events(
        eonet,
        f=f,
        categories=_split_categories(category),
        status=status,
        start=start,
        end=end,
        bbox=service.parse_bbox(bbox),
        limit=limit,
        include_geometry=include_geometry,
        geojson=format == "geojson",
    )
    if format == "geojson":
        return JSONResponse(content=payload)
    return payload


@app.post(
    "/hexbin/points",
    response_model=HexbinPointsResponse,
    tags=["hexbin"],
    summary="Aggregates arbitrary points (with optional value) into hexagonal cells",
    description=(
        "Works with any research data that has coordinates: events, "
        "POWER observations, field samples… `aggregate` = count/sum/mean/max. "
        "If `geojson=true`, returns a FeatureCollection instead of the typed JSON."
    ),
)
def hexbin_points(body: HexbinPointsRequest):
    payload = world_service.hexbin_points(
        body,
        f=body.f,
        include_geometry=body.include_geometry,
        geojson=body.geojson,
    )
    if body.geojson:
        return JSONResponse(content=payload)
    return payload


__all__ = ["app", "CATEGORY_PROFILES"]
