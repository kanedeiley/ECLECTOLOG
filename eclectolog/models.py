from __future__ import annotations

import re
from dataclasses import dataclass, field

# Strips "(Remastered 2011)", "[Live]", " - Radio Edit" so re-releases of the same song collide.
_TITLE_NOISE = re.compile(r"\s*[\(\[][^)\]]*[\)\]]|\s+-\s+.*$")


def normalize_title(name: str) -> str:
    return re.sub(r"\s+", " ", _TITLE_NOISE.sub("", name.lower())).strip()


@dataclass(frozen=True)
class Track:
    id: str
    uri: str
    name: str
    artists: tuple[tuple[str, str], ...]  # (artist_id, artist_name)
    album: str = ""
    album_id: str = ""

    @property
    def artist_ids(self) -> tuple[str, ...]:
        return tuple(a[0] for a in self.artists)

    @property
    def artist_names(self) -> tuple[str, ...]:
        return tuple(a[1] for a in self.artists)

    @property
    def primary_artist_id(self) -> str:
        return self.artists[0][0]

    @property
    def key(self) -> str:
        """Identity that survives remasters/re-releases: normalized title + primary artist."""
        return f"{normalize_title(self.name)}|{self.artists[0][1].lower()}"

    def label(self) -> str:
        return f"{self.name} — {', '.join(self.artist_names)}"


def parse_track(obj: dict | None, album: dict | None = None) -> Track | None:
    """Build a Track from a full or simplified Spotify track object; None for episodes/local files."""
    if not obj or obj.get("type", "track") != "track" or obj.get("is_local"):
        return None
    track_id = obj.get("id")
    artists = tuple((a["id"], a.get("name") or "?") for a in obj.get("artists") or [] if a.get("id"))
    if not track_id or not artists:
        return None
    album = album or obj.get("album") or {}  # album-tracks responses omit "album"; caller passes it
    return Track(
        id=track_id,
        uri=obj.get("uri") or f"spotify:track:{track_id}",
        name=obj.get("name") or "?",
        artists=artists,
        album=album.get("name") or "",
        album_id=album.get("id") or "",
    )


def parse_playlist_entry(entry: dict) -> Track | None:
    # Feb 2026 API renamed playlist entries' "track" to "item"; accept both.
    return parse_track(entry.get("item") or entry.get("track"))


@dataclass
class Candidate:
    track: Track
    source: str
    reason: str
    genre: str | None = None


@dataclass
class ArtistSeed:
    id: str
    name: str
    weight: float = 0.0
    genres: list[str] | None = None  # None = not looked up yet
    reasons: list[str] = field(default_factory=list)
    albums: dict[str, str] = field(default_factory=dict)  # album_id -> name, from tracks you know

    def add(self, weight: float, reason: str, track: Track | None = None) -> None:
        if track and track.album_id and track.primary_artist_id == self.id:
            self.albums[track.album_id] = track.album
        self.weight += weight
        if reason and reason not in self.reasons and len(self.reasons) < 3:
            self.reasons.append(reason)
