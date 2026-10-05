"""Custom cover art for Eclectolog's playlists. Best effort: problems are warnings, never failures.

A playlist gets its cover when it still has Spotify's auto-generated one (a mosaic of album art, or
nothing yet). Once a custom cover is set it's left alone, including one you pick yourself in Spotify.
The listing load_references already fetched carries each playlist's images, so checking costs no calls.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from .spotify import Spotify, SpotifyError

log = logging.getLogger(__name__)

COVERS_DIR = Path(__file__).parent / "covers"  # <role>.jpg: square JPEGs under 190 KB (256 KB as base64)
ROLES = ("output", "compass", "avoid")


def has_custom_cover(playlist: dict) -> bool:
    # Uploaded playlist covers have "ab67706c" image IDs. Auto-generated ones are a mosaic
    # (mosaic.scdn.co) or, for short playlists, a single album's art ("ab67616d").
    for img in playlist.get("images") or []:
        url = img.get("url") or ""
        if "ab67706c" in url or (url and "mosaic.scdn.co" not in url and "ab67616d" not in url):
            return True
    return False


def apply_covers(client: Spotify, playlists: dict[str, dict | None]) -> list[str]:
    """Uploads covers where they're missing. Returns warnings for the run report."""
    warnings: list[str] = []
    for role in ROLES:
        pl = playlists.get(role)
        path = COVERS_DIR / f"{role}.jpg"
        if not pl or not path.is_file() or has_custom_cover(pl):
            continue
        try:
            client.request("PUT", f"/playlists/{pl['id']}/images",
                           data=base64.b64encode(path.read_bytes()), content_type="image/jpeg")
            log.info("Set cover art on %r", pl.get("name"))
        except SpotifyError as exc:
            if exc.status in (401, 403):
                warnings.append("Couldn't set playlist covers: Spotify hasn't granted image upload for this "
                                "account. Sign in again from the web app to allow it.")
                break  # same answer for every playlist
            warnings.append(f"Couldn't set the cover on {pl.get('name')!r}: {exc}")
        except Exception as exc:  # covers are cosmetic: nothing here may fail a run
            warnings.append(f"Couldn't set the cover on {pl.get('name')!r}: {exc!r}")
    for w in warnings:
        log.warning("%s", w)
    return warnings
