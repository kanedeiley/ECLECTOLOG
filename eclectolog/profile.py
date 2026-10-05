"""Turn listening history into a deliberately flattened taste profile.

Two knobs keep the profile from collapsing onto one "north star":
  * recency_boost: a play from just now counts (1 + boost)x, decaying toward 1x with a half-life,
    so recent listening tilts things only slightly.
  * temperature: weights are raised to this power (< 1 flattens), so a heavily played artist
    or genre gets more picks, but not proportionally more.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from .models import ArtistSeed, Track, parse_track
from .spotify import Spotify, SpotifyError

log = logging.getLogger(__name__)

TERM_LABELS = {"short_term": "past-month", "medium_term": "past-6-months", "long_term": "all-time"}


@dataclass
class History:
    recent: list[tuple[Track, datetime]] = field(default_factory=list)
    top_tracks: dict[str, list[Track]] = field(default_factory=dict)
    top_artists: dict[str, list[dict]] = field(default_factory=dict)
    saved: list[Track] = field(default_factory=list)


@dataclass
class Profile:
    artists: dict[str, ArtistSeed]
    genres: dict[str, float] = field(default_factory=dict)
    known_tracks: set[str] = field(default_factory=set)
    known_keys: set[str] = field(default_factory=set)
    genre_examples: dict[str, str] = field(default_factory=dict)  # genre -> a representative artist name

    def add_known(self, track: Track) -> None:
        self.known_tracks.add(track.id)
        self.known_keys.add(track.key)

    def is_known(self, track: Track) -> bool:
        return track.id in self.known_tracks or track.key in self.known_keys


def recency_weight(age_hours: float, boost: float, half_life_hours: float) -> float:
    if half_life_hours <= 0:
        return 1.0
    return 1.0 + boost * 0.5 ** (max(age_hours, 0.0) / half_life_hours)


def temper(weights: dict[str, float], temperature: float) -> dict[str, float]:
    return {k: w ** temperature for k, w in weights.items() if w > 0}


def matches_any(text: str, patterns: list[str]) -> bool:
    text = text.lower()
    return any(p and p in text for p in patterns)


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def collect_history(client: Spotify, cfg: dict) -> History:
    """Fetch history. Each endpoint fails soft so one hiccup doesn't kill the run."""
    h = cfg["history"]
    hist = History()

    def attempt(what, fn):
        try:
            fn()
        except SpotifyError as exc:
            log.warning("Skipping %s: %s", what, exc)

    def recent():
        for item in client.get("/me/player/recently-played", {"limit": 50}).get("items", []):
            track = parse_track(item.get("track"))
            if track and item.get("played_at"):
                hist.recent.append((track, _parse_time(item["played_at"])))

    if h["recent_weight"] > 0:
        attempt("recently played", recent)

    for term, weight in h["top_terms"].items():
        if weight <= 0:
            continue
        params = {"time_range": term, "limit": 50}

        def top(term=term, params=params):
            hist.top_tracks[term] = [t for t in (parse_track(x) for x in client.paginate("/me/top/tracks", params, h["top_limit"])) if t]
            hist.top_artists[term] = list(client.paginate("/me/top/artists", params, h["top_limit"]))

        attempt(f"top items ({term})", top)

    if h["saved_tracks"] > 0:
        def saved():
            for item in client.paginate("/me/tracks", {"limit": 50}, h["saved_tracks"]):
                track = parse_track(item.get("track"))
                if track:
                    hist.saved.append(track)

        attempt("liked songs", saved)
    return hist


def build_profile(
    history: History,
    cfg: dict,
    now: datetime,
    liked_feedback: list[Track] = (),
    avoid_artist_ids: set[str] = frozenset(),
    avoid_artist_names: list[str] = (),
) -> Profile:
    h = cfg["history"]
    artists: dict[str, ArtistSeed] = {}
    profile = Profile(artists=artists)
    avoid_names = {n.lower() for n in avoid_artist_names}

    def credit(track: Track, weight: float, reason: str) -> None:
        profile.add_known(track)
        for i, (aid, name) in enumerate(track.artists):
            seed = artists.setdefault(aid, ArtistSeed(aid, name))
            seed.add(weight if i == 0 else weight * 0.5, reason, track)

    for track, played_at in history.recent:
        age_h = (now - played_at).total_seconds() / 3600
        w = h["recent_weight"] * recency_weight(age_h, h["recency_boost"], h["recency_half_life_hours"])
        credit(track, w, f"recently played “{track.name}”")

    for term, tracks in history.top_tracks.items():
        tw = h["top_terms"].get(term, 1.0)
        for rank, track in enumerate(tracks):
            credit(track, tw * (1 - 0.5 * rank / max(len(tracks), 1)), f"one of your {TERM_LABELS.get(term, term)} top tracks")

    for term, objs in history.top_artists.items():
        tw = h["top_terms"].get(term, 1.0)
        for rank, obj in enumerate(objs):
            if not obj.get("id"):
                continue
            seed = artists.setdefault(obj["id"], ArtistSeed(obj["id"], obj.get("name", "?")))
            seed.add(tw * (1 - 0.5 * rank / max(len(objs), 1)), f"one of your {TERM_LABELS.get(term, term)} top artists")
            if obj.get("genres") is not None:
                seed.genres = list(obj["genres"])

    for track in history.saved:
        credit(track, h["saved_weight"], "in your Liked Songs")

    boost = cfg["reference"]["liked_feedback_boost"]
    for track in liked_feedback:
        credit(track, boost, f"you saved “{track.name}” from a past mix")

    for aid in list(artists):
        if aid in avoid_artist_ids or artists[aid].name.lower() in avoid_names:
            del artists[aid]

    flattened = temper({k: s.weight for k, s in artists.items()}, h["temperature"])
    for k, s in artists.items():
        s.weight = flattened.get(k, 0.0)
    return profile


def enrich_genres(client: Spotify, seeds: list[ArtistSeed], limit: int) -> None:
    """Look up genres for the heaviest seeds that don't have them yet (batch endpoint is gone, so one call each)."""
    todo = [s for s in sorted(seeds, key=lambda s: -s.weight) if s.genres is None][:limit]
    for seed in todo:
        try:
            seed.genres = list(client.get(f"/artists/{seed.id}").get("genres") or [])
        except SpotifyError as exc:
            log.debug("Genre lookup failed for %s: %s", seed.name, exc)
            seed.genres = []


def compute_genres(profile: Profile, cfg: dict) -> None:
    """Spread each artist's weight across its genres, flatten, then fold in declared interests."""
    avoid = cfg["interests"]["avoid"]["genres"]
    raw: dict[str, float] = defaultdict(float)
    best: dict[str, tuple[float, str]] = {}
    for seed in profile.artists.values():
        if seed.genres and any(matches_any(g, avoid) for g in seed.genres):
            seed.weight *= 0.2  # `less:` also quiets deep cuts from artists in that genre
        for g in seed.genres or []:
            raw[g] += seed.weight / len(seed.genres)
            if seed.weight > best.get(g, (0, ""))[0]:
                best[g] = (seed.weight, seed.name)

    genres = temper(dict(raw), cfg["history"]["temperature"])
    baseline = sum(genres.values()) / len(genres) if genres else 1.0
    for g, w in cfg["interests"]["genres"].items():
        genres[g] = genres.get(g, 0.0) + w * baseline

    profile.genres = {g: w for g, w in genres.items() if not matches_any(g, avoid)}
    profile.genre_examples = {g: name for g, (_, name) in best.items()}
