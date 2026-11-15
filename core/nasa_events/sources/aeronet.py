"""AERONET client and parser (HTML-wrapped CSV, fill -999)."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as date_cls, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from ..client import Response, cached_fetch, fetch
from ..config import CACHE_DIR

BASE = "https://aeronet.gsfc.nasa.gov/cgi-bin/print_web_data_v3"


class AeronetError(RuntimeError):
    pass


@dataclass(slots=True)
class AeronetRecord:
    site: str
    datetime: datetime
    values: dict[str, float | None] = field(default_factory=dict)


def _num(text: str) -> float | None:
    text = (text or "").strip()
    if text in ("", "-999", "-999.0", "-999.000000"):
        return None
    try:
        return float(text)
    except ValueError:
        return None


class AeronetClient:
    def __init__(
        self,
        *,
        cache_dir: Path = CACHE_DIR,
        use_cache: bool = True,
        timeout: int = 120,
    ):
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.timeout = timeout

    def download(
        self,
        site: str = "GSFC",
        start: date_cls | None = None,
        end: date_cls | None = None,
        *,
        aod15: bool = True,
        avg: int = 10,
    ) -> str:
        end = end or date_cls.today()
        start = start or (end - timedelta(days=30))
        params = {
            "site": site,
            "year": start.year,
            "month": start.month,
            "day": start.day,
            "year2": end.year,
            "month2": end.month,
            "day2": end.day,
            "AOD15": "1" if aod15 else "0",
            "AVG": str(avg),
        }
        url = f"{BASE}?{urlencode(params)}"
        response: Response = (
            cached_fetch(url, cache_dir=self.cache_dir, max_age_s=24 * 3600, timeout=self.timeout)
            if self.use_cache
            else fetch(url, timeout=self.timeout)
        )
        if response.status != 200:
            raise AeronetError(f"HTTP {response.status}")
        return response.body.decode("utf-8", "replace")

    @staticmethod
    def parse(text: str) -> list[AeronetRecord]:
        lines = text.splitlines()
        try:
            header_index = next(
                index for index, line in enumerate(lines) if line.startswith("AERONET_Site,")
            )
        except StopIteration:
            raise AeronetError("AERONET CSV header not found") from None
        header = [column.strip() for column in lines[header_index].strip().split(",")]
        records: list[AeronetRecord] = []
        for line in lines[header_index + 1 :]:
            stripped = line.strip()
            if not stripped or stripped.startswith("<"):
                continue
            cells = [cell.strip() for cell in line.split(",")]
            if len(cells) < 4:
                continue
            row = {header[i]: cells[i] if i < len(cells) else "" for i in range(len(header))}
            try:
                stamp = datetime.strptime(
                    f"{row['Date(dd:mm:yyyy)']} {row['Time(hh:mm:ss)']}", "%d:%m:%Y %H:%M:%S"
                )
            except (KeyError, ValueError):
                continue
            values = {
                name: _num(value)
                for name, value in row.items()
                if name
                not in ("AERONET_Site", "Date(dd:mm:yyyy)", "Time(hh:mm:ss)")
            }
            records.append(
                AeronetRecord(site=row.get("AERONET_Site", ""), datetime=stamp, values=values)
            )
        return records
