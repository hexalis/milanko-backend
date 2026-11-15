"""HTTP client with retries and an on-disk response cache."""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from .config import CACHE_DIR

USER_AGENT = "nasa-events-research/0.1"


@dataclass(slots=True)
class Response:
    url: str
    status: int | None
    body: bytes
    elapsed_ms: int
    error: str | None = None
    from_cache: bool = False

    @property
    def ok(self) -> bool:
        return self.status == 200

    def json(self):
        return json.loads(self.body.decode("utf-8"))


def fetch(url: str, timeout: int = 90, retries: int = 2, backoff: float = 1.5) -> Response:
    """GET with retries on 429/5xx/network errors. Returns a Response (never raises)."""
    last: Response | None = None
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        started = time.monotonic()
        try:
            with urllib.request.urlopen(request, timeout=timeout) as resp:
                body = resp.read()
                return Response(url, resp.status, body, int((time.monotonic() - started) * 1000))
        except urllib.error.HTTPError as exc:
            body = exc.read()
            last = Response(
                url,
                exc.code,
                body,
                int((time.monotonic() - started) * 1000),
                f"HTTP {exc.code}: {exc.reason}",
            )
            if exc.code == 429 or 500 <= exc.code < 600:
                if attempt < retries:
                    time.sleep(backoff * (attempt + 1))
                    continue
            return last
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last = Response(
                url,
                None,
                b"",
                int((time.monotonic() - started) * 1000),
                f"{type(exc).__name__}: {exc}",
            )
            if attempt < retries:
                time.sleep(backoff * (attempt + 1))
    assert last is not None
    return last


def _cache_paths(url: str, cache_dir: Path) -> tuple[Path, Path]:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return cache_dir / f"{digest}.bin", cache_dir / f"{digest}.json"


def cached_fetch(
    url: str,
    *,
    cache_dir: Path = CACHE_DIR,
    max_age_s: int | None = 6 * 3600,
    timeout: int = 90,
    retries: int = 2,
) -> Response:
    """GET with disk cache. max_age_s=None means the cache never expires."""
    body_path, meta_path = _cache_paths(url, cache_dir)
    if body_path.exists():
        fresh = max_age_s is None or (time.time() - body_path.stat().st_mtime) <= max_age_s
        if fresh:
            return Response(url, 200, body_path.read_bytes(), 0, None, True)
    response = fetch(url, timeout=timeout, retries=retries)
    if response.status == 200 and response.body:
        cache_dir.mkdir(parents=True, exist_ok=True)
        body_path.write_bytes(response.body)
        meta_path.write_text(
            json.dumps({"url": url, "fetched_at": time.time()}), encoding="utf-8"
        )
    return response
