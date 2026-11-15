"""SQLAlchemy models for the normalized NASA data store.

The migration is in core/migrations/versions. Models are deliberately
PostgreSQL-first: JSONB and BRIN indexes are part of the design.
"""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Location(Base):
    __tablename__ = "locations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    grid_version: Mapped[str | None] = mapped_column(String(64))
    region_code: Mapped[int | None] = mapped_column(Integer)
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    bbox: Mapped[dict | None] = mapped_column(JSONB)
    area_km2: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    observations: Mapped[list[Observation]] = relationship(back_populates="location")

    __table_args__ = (
        CheckConstraint(
            "kind IN ('hex_region', 'case_site', 'study_point')",
            name="locations_kind_check",
        ),
        Index("locations_grid_region_idx", "grid_version", "region_code"),
    )


class Variable(Base):
    __tablename__ = "variables"

    code: Mapped[str] = mapped_column(String(80), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    unit: Mapped[str] = mapped_column(String(40), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    native_resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    scale: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    offset: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    valid_min: Mapped[float | None] = mapped_column(Float)
    valid_max: Mapped[float | None] = mapped_column(Float)
    description: Mapped[str | None] = mapped_column(Text)

    observations: Mapped[list[Observation]] = relationship(back_populates="variable")


class SourceLayer(Base):
    __tablename__ = "source_layers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    layer: Mapped[str] = mapped_column(String(200), nullable=False)
    variable_code: Mapped[str] = mapped_column(
        String(80), ForeignKey("variables.code"), nullable=False
    )
    platform: Mapped[str | None] = mapped_column(String(80))
    native_resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    palette_id: Mapped[str | None] = mapped_column(String(120))
    extraction_method: Mapped[str] = mapped_column(String(80), nullable=False)

    __table_args__ = (UniqueConstraint("source", "layer", name="source_layers_source_layer_key"),)


class Palette(Base):
    __tablename__ = "palettes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    layer: Mapped[str] = mapped_column(String(200), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    mapping: Mapped[dict] = mapped_column(JSONB, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("layer", "version", name="palettes_layer_version_key"),)


class Observation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    location_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("locations.id"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    variable_code: Mapped[str] = mapped_column(
        String(80), ForeignKey("variables.code"), nullable=False
    )
    source_layer: Mapped[str | None] = mapped_column(String(200))
    platform: Mapped[str | None] = mapped_column(String(80))
    observed_on: Mapped[date] = mapped_column(Date, nullable=False)
    temporal_resolution: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str | None] = mapped_column(String(40))
    quality: Mapped[str] = mapped_column(String(20), default="ok", nullable=False)
    valid_fraction: Mapped[float | None] = mapped_column(Float)
    class_counts: Mapped[dict | None] = mapped_column(JSONB)
    dominant_class: Mapped[str | None] = mapped_column(String(120))
    metrics: Mapped[dict | None] = mapped_column(JSONB)
    unknown_color_fraction: Mapped[float | None] = mapped_column(Float)
    footprint: Mapped[dict | None] = mapped_column(JSONB)
    resolution_deg: Mapped[float | None] = mapped_column(Float)
    palette_version: Mapped[str | None] = mapped_column(String(80))
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    time_standard: Mapped[str | None] = mapped_column(String(20))
    source_url: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    location: Mapped[Location] = relationship(back_populates="observations")
    variable: Mapped[Variable] = relationship(back_populates="observations")

    __table_args__ = (
        UniqueConstraint(
            "location_id",
            "source",
            "variable_code",
            "observed_on",
            "temporal_resolution",
            name="observations_location_source_var_date_key",
        ),
        CheckConstraint(
            "quality IN ('ok', 'partial', 'fill', 'missing', 'no_data', 'estimated', 'error')",
            name="observations_quality_check",
        ),
        Index(
            "observations_loc_var_date_idx",
            "location_id",
            "variable_code",
            "observed_on",
        ),
        Index(
            "observations_source_var_date_idx",
            "source",
            "variable_code",
            "observed_on",
        ),
        Index("observations_date_brin_idx", "observed_on", postgresql_using="brin"),
    )


class Event(Base):
    __tablename__ = "events"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    source: Mapped[str] = mapped_column(String(40), default="EONET", nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    link: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str | None] = mapped_column(String(32))
    category: Mapped[str | None] = mapped_column(String(80))
    first_seen: Mapped[date | None] = mapped_column(Date)
    last_seen: Mapped[date | None] = mapped_column(Date)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    magnitude: Mapped[float | None] = mapped_column(Float)
    magnitude_unit: Mapped[str | None] = mapped_column(String(40))
    source_url: Mapped[str | None] = mapped_column(Text)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    geometry: Mapped[list[EventGeometry]] = relationship(
        back_populates="event", cascade="all, delete-orphan"
    )

    __table_args__ = (
        Index("events_category_status_idx", "category", "status"),
        Index("events_first_seen_idx", "first_seen"),
    )


class EventGeometry(Base):
    __tablename__ = "event_geometry"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    event_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    geometry_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    geometry_type: Mapped[str | None] = mapped_column(String(40))
    coordinates: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    magnitude: Mapped[float | None] = mapped_column(Float)
    magnitude_unit: Mapped[str | None] = mapped_column(String(40))

    event: Mapped[Event] = relationship(back_populates="geometry")

    __table_args__ = (Index("event_geometry_event_idx", "event_id"),)


class EventRegion(Base):
    __tablename__ = "event_regions"

    event_id: Mapped[str] = mapped_column(
        String(120), ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    region_code: Mapped[int] = mapped_column(Integer, primary_key=True)
    first_date: Mapped[date | None] = mapped_column(Date)
    last_date: Mapped[date | None] = mapped_column(Date)
    n_geometries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        Index("event_regions_region_idx", "region_code", "first_date"),
    )


class AnalysisCache(Base):
    __tablename__ = "analysis_cache"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    endpoint: Mapped[str] = mapped_column(String(120), nullable=False)
    request: Mapped[dict] = mapped_column(JSONB, nullable=False)
    method_version: Mapped[str] = mapped_column(String(80), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("analysis_cache_expiry_idx", "expires_at"),)


class IngestRun(Base):
    __tablename__ = "ingest_runs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    job: Mapped[str] = mapped_column(String(80), nullable=False)
    source: Mapped[str] = mapped_column(String(40), nullable=False)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    rows_read: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    rows_written: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONB)

    __table_args__ = (Index("ingest_runs_job_started_idx", "job", "started_at"),)


class IngestCheckpoint(Base):
    __tablename__ = "ingest_checkpoints"

    job: Mapped[str] = mapped_column(String(80), primary_key=True)
    scope_key: Mapped[str] = mapped_column(String(200), primary_key=True)
    cursor_date: Mapped[date | None] = mapped_column(Date)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class GibsAvailability(Base):
    __tablename__ = "gibs_availability"

    layer: Mapped[str] = mapped_column(String(200), primary_key=True)
    observed_on: Mapped[date] = mapped_column(Date, primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    http_status: Mapped[int | None] = mapped_column(Integer)
    valid_fraction: Mapped[float | None] = mapped_column(Float)
    unknown_fraction: Mapped[float | None] = mapped_column(Float)
    error: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
