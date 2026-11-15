"""Project configuration and paths (Fase 1)."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_DIR = ROOT / "data" / "catalog"
MASTER_CSV = CATALOG_DIR / "endpoints-variables.csv"
CORE_CSV = CATALOG_DIR / "core-selection.csv"
SAMPLES_DIR = ROOT / "tests" / "fixtures"
CACHE_DIR = ROOT / "data" / "cache"


@lru_cache(maxsize=1)
def load_env() -> dict[str, str]:
    """Read .env values without overriding real environment variables."""
    env = dict(os.environ)
    env_path = ROOT / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            env.setdefault(key.strip(), value.strip())
    return env


def get(name: str, default: str = "") -> str:
    return load_env().get(name, default)
