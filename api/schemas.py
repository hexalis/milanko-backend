"""Pydantic schemas for the API (request/response contracts)."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------- system
class HealthResponse(BaseModel):
    status: str = Field(..., examples=["ok"])
    version: str
    core_variables: int
    timestamp: str
    database: str = Field(default="not_configured", examples=["ok", "not_configured", "error"])


# --------------------------------------------------------------------- catalog
class VariableInfo(BaseModel):
    code: str
    name: str
    source: str
    section: str
    unit: str
    temporal: str
    coverage: str
    definition: str
    disposition: str = Field(..., description="nucleo | descartado | (empty if not applicable)")
    usage: str = Field(..., description="Original suggested use from the master CSV")


class CatalogResponse(BaseModel):
    count: int
    variables: list[VariableInfo]


class CategoryInfo(BaseModel):
    id: str
    title: str


class CategoriesResponse(BaseModel):
    count: int
    categories: list[CategoryInfo]


# ---------------------------------------------------------------------- events
class GeometryOut(BaseModel):
    date: str | None
    type: str
    coordinates: list
    magnitude_value: float | None = None
    magnitude_unit: str | None = None


class EventOut(BaseModel):
    id: str
    title: str
    description: str | None
    link: str
    closed: str | None
    categories: list[str]
    sources: list[dict]
    geometry: list[GeometryOut]
    first_date: str | None
    last_date: str | None
    duration_days: float | None
    n_geometries: int


class EventsResponse(BaseModel):
    count: int
    total: int | None = None
    events: list[EventOut]


# ---------------------------------------------------------------- observations
class SeriesPoint(BaseModel):
    time: str
    value: float | None
    quality: str = Field(..., description="ok | fill | missing | invalid")


class VariableSeries(BaseModel):
    unit: str | None
    time_standard: str = Field(..., description="POWER provides LST (local solar time)")
    granularity: str
    values: list[SeriesPoint]


class ObservationsResponse(BaseModel):
    request: dict
    variables: dict[str, VariableSeries]


# ------------------------------------------------------------------- anomalies
class AnomalyPoint(BaseModel):
    time: str
    value: float
    anomaly: float | None = Field(..., description="value - median of the DOY window")
    z: float | None
    percentile: float | None
    extreme: str | None = Field(..., description="high | low | null")


class AnomalyVariable(BaseModel):
    unit: str | None
    time_standard: str
    values: list[AnomalyPoint]


class AnomaliesResponse(BaseModel):
    request: dict
    baseline_window_days: int
    variables: dict[str, AnomalyVariable]


# ---------------------------------------------------------------------- trends
class MannKendallOut(BaseModel):
    n: int
    s: int
    z: float | None
    p_value: float | None
    trend: str
    alpha: float


class TrendOut(BaseModel):
    code: str
    n_months: int
    seasonally_adjusted: bool
    mann_kendall: MannKendallOut | None
    sen_slope_per_month: float | None
    sen_slope_per_year: float | None


class TrendsResponse(BaseModel):
    request: dict
    trends: dict[str, TrendOut]


# ---------------------------------------------------------------- correlations
class LagCorrelationOut(BaseModel):
    lag: int = Field(..., description="Positive = the anomaly precedes the event")
    r: float | None
    p: float | None
    q: float | None = Field(None, description="FDR q-value (Benjamini-Hochberg)")
    n: int


class CorrelationOut(BaseModel):
    code: str
    best: LagCorrelationOut | None
    lags: list[LagCorrelationOut]


class CorrelationsResponse(BaseModel):
    request: dict
    events_count: int
    correlations: dict[str, CorrelationOut]


# -------------------------------------------------------------------- analysis
class EventWindowOut(BaseModel):
    start: str
    end: str
    lead_days: int
    lag_days: int
    event_start: str
    event_end: str
    duration_days: int
    profile: str
    rationale: str


class EventVariableSummary(BaseModel):
    n_days: int
    mean_anomaly: float | None
    mean_z: float | None
    extreme_fraction: float


class EventSummaryOut(BaseModel):
    event_id: str
    title: str
    categories: list[str]
    window: EventWindowOut
    variables: dict[str, EventVariableSummary]


class EventAnalysisResponse(BaseModel):
    request: dict
    event: EventOut
    window: EventWindowOut
    variables: dict[str, EventVariableSummary]


class EventFilter(BaseModel):
    category: list[str] | None = Field(None, examples=[["wildfires", "drought"]])
    bbox: list[float] | None = Field(
        None,
        min_length=4,
        max_length=4,
        description="EONET format: [minLon, maxLat, maxLon, minLat]",
        examples=[[-76.0, -17.0, -66.0, -56.0]],
    )
    status: Literal["open", "closed", "all"] = "all"
    limit: int = Field(default=200, ge=1, le=1000)
    mag_id: str | None = None
    mag_min: float | None = None


class PointAnalysisRequest(BaseModel):
    lat: float = Field(..., ge=-90, le=90, examples=[-33.45])
    lon: float = Field(..., ge=-180, le=180, examples=[-70.66])
    variables: list[str] = Field(
        ...,
        min_length=1,
        max_length=40,
        examples=[["T2M", "T2M_MAX", "PRECTOTCORR", "RH2M"]],
    )
    start: str = Field(default="20060101", pattern=r"^\d{8}$")
    end: str | None = Field(default=None, pattern=r"^\d{8}$")
    community: Literal["RE", "AG", "SB"] = "RE"
    site_elevation: float | None = Field(
        None, description="Meters; required if PSC is included"
    )
    baseline_window_days: int = Field(default=7, ge=1, le=30)
    max_context_days: int = Field(default=90, ge=7, le=180)
    max_lag_months: int = Field(default=6, ge=0, le=24)
    alpha: float = Field(default=0.05, gt=0, lt=0.5)
    correlation_method: Literal["spearman", "pearson"] = "spearman"
    events: EventFilter | None = Field(
        None, description="If omitted, only trends are computed"
    )


class PointAnalysisResponse(BaseModel):
    request: dict
    trends: dict[str, TrendOut]
    events_count: int
    event_summaries: list[EventSummaryOut]
    correlations: dict[str, CorrelationOut]


# -------------------------------------------------------------- world / hexbin
class LatLonOut(BaseModel):
    lat: float
    lon: float


class WorldCellOut(BaseModel):
    code: int
    face: int
    i: int
    j: int
    region: int
    lat: float
    lon: float
    biome: str
    biome_index: int
    flags: list[str]
    elevation_m: int | None
    rgb: str
    lake_fraction: float
    water: bool
    area_km2: float


class WorldCellsResponse(BaseModel):
    f: int
    total_cells: int
    matched: int
    returned: int
    offset: int
    cells: list[WorldCellOut]


class HexbinEventOut(BaseModel):
    id: str
    title: str
    date: str | None = None
    categories: list[str] = Field(default_factory=list)
    magnitude_value: float | None = None
    magnitude_unit: str | None = None


class HexbinCellOut(BaseModel):
    code: int
    face: int
    i: int
    j: int
    region: int
    centroid: LatLonOut
    count: int
    value: float | None = None
    n_values: int = 0
    events: list[HexbinEventOut] | None = None
    magnitude_totals: dict[str, float] | None = None
    labels: list[str] | None = None
    geometry: dict | None = None


class HexbinEventsResponse(BaseModel):
    f: int
    events_total: int
    cells_returned: int
    cells: list[HexbinCellOut]


class HexbinPointIn(BaseModel):
    lat: float = Field(..., ge=-90, le=90)
    lon: float = Field(..., ge=-180, le=180)
    value: float | None = None
    label: str | None = None


class HexbinPointsRequest(BaseModel):
    f: Literal[56, 80] = 80
    points: list[HexbinPointIn] = Field(..., min_length=1, max_length=20000)
    aggregate: Literal["count", "sum", "mean", "max"] = "count"
    include_geometry: bool = False
    geojson: bool = False


class HexbinPointsResponse(BaseModel):
    f: int
    aggregation: str
    points_total: int
    cells_returned: int
    cells: list[HexbinCellOut]


# --------------------------------------------------------------------- regions
class RegionOut(BaseModel):
    code: int
    slug: str
    name: str
    lat: float | None = None
    lon: float | None = None
    area_km2: float | None = None
    grid_version: str | None = None


class RegionsResponse(BaseModel):
    count: int
    regions: list[RegionOut]


class RegionObservationOut(BaseModel):
    variable: str
    name: str
    date: str
    value: float | None = None
    unit: str | None = None
    quality: str
    valid_fraction: float | None = None
    temporal_resolution: str
    metrics: dict | None = None
    resolution_deg: float | None = None
    method_version: str | None = None
    palette_version: str | None = None


class RegionObservationsResponse(BaseModel):
    region: RegionOut
    count: int
    observations: list[RegionObservationOut]


class VariableCoverageOut(BaseModel):
    variable: str
    source: str
    name: str
    unit: str | None = None
    count: int
    start: str | None = None
    end: str | None = None


class CoverageResponse(BaseModel):
    count: int
    variables: list[VariableCoverageOut]


class RegionLatestItem(BaseModel):
    variable: str
    source: str
    name: str
    unit: str | None = None
    date: str
    value: float | None = None
    quality: str
    valid_fraction: float | None = None
    temporal_resolution: str


class RegionLatestResponse(BaseModel):
    region: RegionOut
    count: int
    variables: list[RegionLatestItem]


class EventCategoryCount(BaseModel):
    category: str | None = None
    count: int


class EventYearCount(BaseModel):
    year: int
    count: int


class EventStatsResponse(BaseModel):
    total: int
    statuses: dict[str, int]
    categories: list[EventCategoryCount]
    years: list[EventYearCount]


class RegionSnapshotItem(BaseModel):
    code: int
    value: float | None = None
    date: str | None = None
    anomaly: float | None = None
    z: float | None = None
    baseline: float | None = None


class RegionSnapshotResponse(BaseModel):
    variable: str
    source: str
    unit: str | None = None
    date: str
    metric: str
    count: int
    min: float | None = None
    max: float | None = None
    regions: list[RegionSnapshotItem]


class RegionRankingItem(BaseModel):
    code: int
    name: str
    value: float | None = None
    date: str | None = None
    anomaly: float | None = None
    z: float | None = None
    slope_per_year: float | None = None
    r2: float | None = None
    n_months: int | None = None


class RegionRankingsResponse(BaseModel):
    variable: str
    source: str
    unit: str | None = None
    metric: str
    order: str
    date: str | None = None
    count: int
    total: int
    regions: list[RegionRankingItem]


class RegionEventOut(BaseModel):
    id: str
    title: str
    category: str | None = None
    status: str | None = None
    first_date: str | None = None
    last_date: str | None = None
    link: str | None = None
    magnitude: float | None = None
    magnitude_unit: str | None = None
    n_geometries: int
    is_primary: bool


class RegionEventsResponse(BaseModel):
    region: RegionOut
    count: int
    events: list[RegionEventOut]
