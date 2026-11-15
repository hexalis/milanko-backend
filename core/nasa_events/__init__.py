"""NASA events/climate data toolkit (Fase 1: normalization layer)."""
from __future__ import annotations

from .catalog import core_codes, load_core_selection, metadata, variable_metadata
from .models import Event, EventFeature, EventGeometry, Observation
from .normalize import clean_value, is_fill, lst_offset_hours, month_number, parse_date_key
from .sources.aeronet import AeronetClient, AeronetRecord
from .sources.donki import DonkiClient, DonkiError, DonkiUnavailable
from .sources.eonet import EonetApiError, EonetClient
from .sources.firms import FireDetection, FirmsApiError, FirmsClient
from .sources.gibs import GibsClient, GibsError
from .sources.power import PowerApiError, PowerClient

__all__ = [
    "AeronetClient",
    "AeronetRecord",
    "DonkiClient",
    "DonkiError",
    "DonkiUnavailable",
    "EonetApiError",
    "EonetClient",
    "Event",
    "EventFeature",
    "EventGeometry",
    "FireDetection",
    "FirmsApiError",
    "FirmsClient",
    "GibsClient",
    "GibsError",
    "Observation",
    "PowerApiError",
    "PowerClient",
    "clean_value",
    "core_codes",
    "is_fill",
    "load_core_selection",
    "lst_offset_hours",
    "metadata",
    "month_number",
    "parse_date_key",
    "variable_metadata",
]
