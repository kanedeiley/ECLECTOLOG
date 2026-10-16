"""Deezer's public API: the related-artists graph, top tracks and fan counts that Spotify's Dev Mode took away.

No key or sign-in. Deezer allows about 50 requests per 5 seconds per IP, and reports errors (quota included)
as HTTP 200 with an {"error": {...}} body. Tracks are matched back to Spotify by ISRC.
"""
from __future__ import annotations

import logging
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

import requests

log = logging.getLogger(__name__)

API_URL = "https://api.deezer.com"
QUOTA_EXCEEDED = 4
NO_DATA = 800


class DeezerError(RuntimeError):
    pass


def name_key(name: str) -> str:
    """'Beyoncé' / 'BEYONCE' / 'The Beyonce' -> 'beyonce', so names from two catalogs can be compared."""
    text = "".join(c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c))
    text = re.sub(r"[\W_]+", " ", text.casefold()).strip()
    return text.removeprefix("the ")


@dataclass(frozen=True)
class DeezerArtist:
    id: int
    name: str
    fans: int


@dataclass(frozen=True)
class DeezerTrack:
    id: int
    title: str
    artist: str
    album: str = ""


class Deezer:
    def __init__(
        self,
        *,
        session: requests.Session | None = None,
        pace_seconds: float = 0.12,
        max_calls: int = 400,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.session = session or requests.Session()
        self.pace = pace_seconds
        self.max_calls = max_calls
        self.max_retries = max_retries
        self._sleep = sleep
        self._last_call = 0.0
        self._cache: dict[tuple, Any] = {}
        self.calls = 0

    def get(self, path: str, params: dict | None = None) -> dict:
        key = (path, tuple(sorted((params or {}).items())))
        if key in self._cache:
            return self._cache[key]
        for attempt in range(self.max_retries + 1):
            if self.calls >= self.max_calls:
                raise DeezerError(f"call budget of {self.max_calls} used up for this run")
            wait = self._last_call + self.pace - time.time()
            if wait > 0:
                self._sleep(wait)
            self._last_call = time.time()
            self.calls += 1
            try:
                resp = self.session.get(API_URL + path, params=params, timeout=20)
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise DeezerError(f"GET {path}: {exc}") from exc
                self._sleep(2 ** attempt)
                continue
            if resp.status_code == 429 or resp.status_code >= 500:
                self._sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise DeezerError(f"GET {path} -> {resp.status_code}: {resp.text[:200]}")
            data = resp.json()
            error = data.get("error") if isinstance(data, dict) else None
            if error:
                if error.get("code") == QUOTA_EXCEEDED:
                    self._sleep(5)  # the quota window is 5 seconds
                    continue
                if error.get("code") != NO_DATA:
                    raise DeezerError(f"GET {path}: {error.get('message') or error}")
                data = {"data": []}  # unknown id: cache the miss like any other answer
            self._cache[key] = data
            return data
        raise DeezerError(f"GET {path} failed after {self.max_retries} retries")

    def find_artist(self, name: str) -> DeezerArtist | None:
        """The exact-name match with the most fans. Search also returns collabs ("X & Y") and empty duplicates."""
        want = name_key(name)
        hits = [a for a in self.get("/search/artist", {"q": name, "limit": 10}).get("data") or [] if name_key(a.get("name", "")) == want]
        best = max(hits, key=lambda a: a.get("nb_fan") or 0, default=None)
        return _artist(best) if best else None

    def related(self, artist_id: int) -> list[DeezerArtist]:
        """Up to 20 artists Deezer's listeners pair with this one, most related first."""
        return [_artist(a) for a in self.get(f"/artist/{artist_id}/related", {"limit": 20}).get("data") or [] if a.get("id")]

    def top_tracks(self, artist_id: int, limit: int = 10) -> list[DeezerTrack]:
        out = []
        for t in self.get(f"/artist/{artist_id}/top", {"limit": limit}).get("data") or []:
            if t.get("id") and t.get("title"):
                out.append(DeezerTrack(t["id"], t["title"], (t.get("artist") or {}).get("name", ""), (t.get("album") or {}).get("title", "")))
        return out

    def isrc(self, track_id: int) -> str | None:
        """Track lists leave the ISRC out, so this is one call per track."""
        return self.get(f"/track/{track_id}").get("isrc") or None


def _artist(obj: dict) -> DeezerArtist:
    return DeezerArtist(int(obj["id"]), obj.get("name") or "?", int(obj.get("nb_fan") or 0))
