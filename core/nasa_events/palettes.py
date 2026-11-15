"""Curated discrete palettes for GIBS layers (validated in Fase 0).

Only class-based layers can be decoded automatically with exact colors.
Continuous layers require their full palette curve (curate per layer in Fase 2).
"""
from __future__ import annotations

# VIIRS/MODIS thermal anomalies: rgb(240, 40, 40) = "Fire"
FIRE_RGBA: dict[tuple[int, int, int, int], str] = {
    (240, 40, 40, 255): "fire",
}

# MODIS Combined Flood 2-Day: water / reference classes observed in the PoC
FLOOD_RGBA: dict[tuple[int, int, int, int], str] = {
    (50, 210, 245, 255): "flood_water",
    (175, 175, 175, 255): "reference",
}
