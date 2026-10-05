"""Minimal Spotify Web API client: refresh-token auth, retries, pagination."""
from __future__ import annotations

import logging
import re
import time
import urllib.parse
from typing import Any, Callable, Iterator

import requests

log = logging.getLogger(__name__)

TOKEN_URL = "https://accounts.spotify.com/api/token"
AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
API_URL = "https://api.spotify.com/v1"

SCOPES = (
    "user-read-recently-played",
    "user-top-read",
    "user-library-read",
    "playlist-read-private",
    "playlist-read-collaborative",
    "playlist-modify-private",
    "playlist-modify-public",
)


class SpotifyError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class AuthError(SpotifyError):
    pass


class RateLimited(SpotifyError):
    pass


_ID_SEGMENT = re.compile(r"^[A-Za-z0-9]{22}$")


def endpoint_key(url: str) -> str:
    """'/artists/<id>/albums?x=1' -> '/artists/*/albums'. Spotify rate-limits per endpoint."""
    path = urllib.parse.urlsplit(url).path.removeprefix("/v1")
    return "/".join("*" if _ID_SEGMENT.match(seg) else seg for seg in path.split("/"))


def _human(seconds: float) -> str:
    return f"{seconds / 3600:.1f}h" if seconds >= 3600 else f"{seconds / 60:.0f}m" if seconds >= 60 else f"{seconds:.0f}s"


class Spotify:
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        refresh_token: str,
        *,
        session: requests.Session | None = None,
        on_token_rotated: Callable[[str], None] | None = None,
        max_retries: int = 5,
        max_wait: float = 60,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.session = session or requests.Session()
        self.on_token_rotated = on_token_rotated
        self.max_retries = max_retries
        self.max_wait = max_wait
        self._sleep = sleep
        self._blocked_until: dict[str, float] = {}  # endpoint -> epoch seconds
        self.pace = {"/search": 0.5}  # per-endpoint min seconds between calls
        self.default_pace = 0.0  # min seconds between any two calls
        self.max_reads: int | None = None  # GET budget per run; writes are never blocked
        self.reads = 0
        self._last_call: dict[str, float] = {}
        self._access_token: str | None = None
        self._expires_at = 0.0
        self.calls = 0

    def _refresh(self) -> None:
        resp = self.session.post(
            TOKEN_URL,
            data={"grant_type": "refresh_token", "refresh_token": self.refresh_token},
            auth=(self.client_id, self.client_secret),
            timeout=30,
        )
        if resp.status_code != 200:
            hint = ""
            if "invalid_grant" in resp.text:
                hint = " The refresh token was revoked or expired: run scripts/get_refresh_token.py again."
            elif "invalid_client" in resp.text:
                hint = " Check SPOTIFY_CLIENT_ID / SPOTIFY_CLIENT_SECRET."
            raise AuthError(f"Token refresh failed ({resp.status_code}): {resp.text[:200]}.{hint}", resp.status_code)
        data = resp.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600)) - 60
        rotated = data.get("refresh_token")
        if rotated and rotated != self.refresh_token:
            self.refresh_token = rotated
            if self.on_token_rotated:
                self.on_token_rotated(rotated)

    def request(self, method: str, path: str, *, params: dict | None = None, json: Any = None) -> Any:
        url = path if path.startswith("http") else API_URL + path
        key = endpoint_key(url)
        if self.is_blocked(key):
            raise RateLimited(f"{key} is rate limited for another {self._blocked_until[key] - time.time():.0f}s", 429)
        if method == "GET":
            if self.max_reads is not None and self.reads >= self.max_reads:
                raise RateLimited(f"read budget of {self.max_reads} calls used up for this run")
            self.reads += 1
        reauthed = False
        for attempt in range(self.max_retries + 1):
            if not self._access_token or time.time() >= self._expires_at:
                self._refresh()
            for pace_key, gap in ((key, self.pace.get(key, 0)), ("*", self.default_pace)):
                wait = self._last_call.get(pace_key, 0) + gap - time.time()
                if gap and wait > 0:
                    self._sleep(wait)
                self._last_call[pace_key] = time.time()
            self.calls += 1
            try:
                resp = self.session.request(
                    method, url, params=params, json=json,
                    headers={"Authorization": f"Bearer {self._access_token}"}, timeout=30,
                )
            except requests.RequestException as exc:
                if attempt == self.max_retries:
                    raise SpotifyError(f"{method} {path}: {exc}") from exc
                self._sleep(2 ** attempt)
                continue

            if resp.status_code == 401 and not reauthed:
                self._access_token, reauthed = None, True
                continue
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", 2))
                if wait > self.max_wait:
                    # Long bans (Spotify hands out ~24h ones for search) aren't worth waiting out:
                    # trip a breaker so the rest of the run stops hammering this endpoint.
                    self._blocked_until[key] = time.time() + wait
                    log.warning("Spotify rate-limited %s for %s; skipping it for this run", key, _human(wait))
                    raise RateLimited(f"{key} rate limited for {wait:.0f}s", 429)
                log.info("Rate limited, sleeping %.0fs", wait)
                self._sleep(wait + 0.5)
                continue
            if resp.status_code >= 500:
                self._sleep(2 ** attempt)
                continue
            if resp.status_code >= 400:
                raise SpotifyError(f"{method} {path} -> {resp.status_code}: {resp.text[:300]}", resp.status_code)
            if resp.status_code == 204 or not resp.content:
                return {}
            return resp.json()
        raise SpotifyError(f"{method} {path} failed after {self.max_retries} retries")

    def is_blocked(self, key: str) -> bool:
        return self._blocked_until.get(key, 0) > time.time()

    def get(self, path: str, params: dict | None = None) -> Any:
        return self.request("GET", path, params=params)

    def post(self, path: str, json: Any = None) -> Any:
        return self.request("POST", path, json=json)

    def put(self, path: str, json: Any = None) -> Any:
        return self.request("PUT", path, json=json)

    def paginate(self, path: str, params: dict | None = None, max_items: int | None = None) -> Iterator[dict]:
        url: str | None = path
        count = 0
        while url:
            page = self.get(url, params)
            params = None  # "next" URLs already carry the query string
            for item in page.get("items") or []:
                yield item
                count += 1
                if max_items is not None and count >= max_items:
                    return
            url = page.get("next")
