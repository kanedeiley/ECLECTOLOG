"""Reference playlists: your steering wheel lives in Spotify itself, no repo edits needed.

  Compass  add songs you want more of; type directives into its description (more: dub; size: 30)
  Avoid    add songs whose artists should never appear
  Archive  optional (off by default): a browsable log of served tracks. Repeat prevention uses
           the history file instead (see history.py), which costs no API calls.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .config import parse_directives
from .models import Track, parse_playlist_entry
from .spotify import Spotify, SpotifyError

log = logging.getLogger(__name__)

DESCRIPTIONS = {
    # Directive keys are left empty on purpose: empty values are ignored until you fill them in.
    "compass": (
        "Steer Eclectolog: add songs you want more of. Tune it by editing this text → "
        "more: ; less: ; era: ; size: ; familiar: ; explore: ; wildcard: ; compass: ; keywords: "
    ),
    "avoid": "Eclectolog skips every artist on this playlist. Add a song to ban its artist.",
    "archive": "Every track Eclectolog has served you, so it never repeats. Delete this playlist to reset.",
}


@dataclass
class References:
    me_id: str
    playlists: dict[str, dict | None] = field(default_factory=dict)  # role -> playlist object
    tracks: dict[str, list[Track]] = field(default_factory=dict)  # role -> tracks
    directives: dict[str, str] = field(default_factory=dict)
    created: list[str] = field(default_factory=list)

    def get(self, role: str) -> dict | None:
        return self.playlists.get(role)

    def tracks_of(self, role: str) -> list[Track]:
        return self.tracks.get(role, [])


def playlist_total(pl: dict) -> int:
    # Feb 2026 renamed the playlist's "tracks" block to "items"; read either.
    block = pl.get("items") if isinstance(pl.get("items"), dict) else pl.get("tracks")
    return int((block or {}).get("total") or 0)


def owned_playlists(client: Spotify, me_id: str) -> list[dict]:
    return [p for p in client.paginate("/me/playlists", {"limit": 50}) if p and (p.get("owner") or {}).get("id") == me_id]


def read_tracks(client: Spotify, playlist_id: str, offset: int = 0, max_items: int | None = None) -> list[Track]:
    params = {"limit": 50, "offset": offset, "additional_types": "track"}
    return [t for t in (parse_playlist_entry(e) for e in client.paginate(f"/playlists/{playlist_id}/items", params, max_items)) if t]


def create_playlist(client: Spotify, name: str, description: str, public: bool) -> dict:
    log.info("Creating playlist %r", name)
    return client.post("/me/playlists", {"name": name, "description": description, "public": public})


def load_references(client: Spotify, cfg: dict, output_name: str) -> References:
    me = client.get("/me")
    refs = References(me_id=me["id"])
    by_name: dict[str, dict] = {}
    for pl in owned_playlists(client, refs.me_id):
        by_name.setdefault((pl.get("name") or "").casefold(), pl)

    refs.playlists["output"] = by_name.get(output_name.casefold())
    if refs.playlists["output"]:
        refs.tracks["output"] = read_tracks(client, refs.playlists["output"]["id"], max_items=500)

    rc = cfg["reference"]
    if not rc["enabled"]:
        return refs

    for role in ("compass", "avoid", "archive"):
        name = (rc.get(f"{role}_playlist") or "").strip()
        if not name:
            continue
        if name.casefold() == output_name.casefold():
            log.warning("%s playlist has the same name as the output playlist; ignoring it", role)
            continue
        pl = by_name.get(name.casefold())
        if pl is None and rc["create_if_missing"] and not cfg["dry_run"]:
            try:
                pl = create_playlist(client, name, DESCRIPTIONS[role], public=False)
                refs.created.append(name)
            except SpotifyError as exc:
                log.warning("Couldn't create %s playlist: %s", role, exc)
        refs.playlists[role] = pl

    if pl := refs.get("compass"):
        refs.tracks["compass"] = read_tracks(client, pl["id"], max_items=300)
        refs.directives = parse_directives(pl.get("description"))
    if pl := refs.get("avoid"):
        refs.tracks["avoid"] = read_tracks(client, pl["id"], max_items=500)
    if pl := refs.get("archive"):
        total = playlist_total(pl)
        if total > 9000:
            log.warning("Archive has %d tracks (Spotify caps playlists at 10,000); consider deleting it to reset", total)
        refs.tracks["archive"] = read_tracks(client, pl["id"], offset=max(0, total - rc["archive_lookback"]))
    return refs
