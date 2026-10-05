"""Candidate generators. Each pick() returns one Candidate or None.

Built only on endpoints still open to Development Mode apps after Spotify's Nov 2024 and Feb 2026
changes (no /recommendations, related-artists, artist top-tracks or popularity):

  deep_cuts        a random album track from an artist you already play, which you haven't heard
  genre_neighbors  a track from one of your (flattened) genres, by an artist new to you
  wildcard         a genre you don't listen to, optionally pinned to an era or keyword
  compass          artists/genres from your Compass playlist, interests.yaml and `more:` directives
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from typing import Callable

from .config import SOURCES, parse_era
from .genres import BUILTIN_GENRES
from .models import ArtistSeed, Candidate, Track, parse_track
from .profile import Profile, matches_any
from .spotify import Spotify, SpotifyError

log = logging.getLogger(__name__)

SEARCH_LIMIT = 10  # Spotify's Dev Mode maximum since Feb 2026
ALBUM_LIMIT = 10  # /artists/{id}/albums rejects anything larger (undocumented, observed Oct 2026)
MAX_OFFSET = 1000 - SEARCH_LIMIT


class Selector:
    """Enforces per-artist and per-genre caps across the whole playlist."""

    def __init__(self, max_per_artist: int, max_per_genre: int):
        self.max_per_artist = max_per_artist
        self.max_per_genre = max_per_genre
        self.artist_counts: Counter[str] = Counter()
        self.genre_counts: Counter[str] = Counter()
        self.picks: list[Candidate] = []
        self._ids: set[str] = set()
        self._keys: set[str] = set()

    def artist_full(self, artist_id: str) -> bool:
        return self.artist_counts[artist_id] >= self.max_per_artist

    def any_artist_full(self, track: Track) -> bool:
        return any(self.artist_full(a) for a in track.artist_ids)

    def genre_full(self, genre: str | None) -> bool:
        return genre is not None and self.genre_counts[genre] >= self.max_per_genre

    def offer(self, c: Candidate) -> bool:
        t = c.track
        # Featured artists count too, so "X feat. Y" can't sneak Y in twice.
        if t.id in self._ids or t.key in self._keys or self.any_artist_full(t) or self.genre_full(c.genre):
            return False
        self._ids.add(t.id)
        self._keys.add(t.key)
        self.artist_counts.update(set(t.artist_ids))
        if c.genre:
            self.genre_counts[c.genre] += 1
        self.picks.append(c)
        return True


def weighted_choice(rng: random.Random, weights: dict[str, float], skip: Callable[[str], bool] = lambda _: False) -> str | None:
    pool = [(k, w) for k, w in weights.items() if w > 0 and not skip(k)]
    if not pool:
        return None
    return rng.choices([k for k, _ in pool], weights=[w for _, w in pool])[0]


class Sources:
    def __init__(
        self,
        client: Spotify,
        cfg: dict,
        profile: Profile,
        selector: Selector,
        rng: random.Random,
        *,
        compass_seeds: dict[str, ArtistSeed] | None = None,
        avoid_artist_ids: set[str] = frozenset(),
    ):
        self.client = client
        self.cfg = cfg
        self.profile = profile
        self.selector = selector
        self.rng = rng
        self.compass_seeds = compass_seeds or {}
        self.avoid_artist_ids = set(avoid_artist_ids)
        self.avoid_artist_names = {n.lower() for n in cfg["interests"]["avoid"]["artists"]}
        self.avoid_genres = cfg["interests"]["avoid"]["genres"]
        self.market = cfg.get("market") or None
        self.depth = min(int(cfg["diversity"]["search_depth"]), MAX_OFFSET)

        self._albums: dict[str, list[dict]] = {}
        self._album_tracks: dict[str, list[Track]] = {}
        self._search: dict[tuple[str, int], list[Track]] = {}
        self._totals: dict[str, int] = {}
        self.dead_genres: set[str] = set()  # genres Spotify's genre: filter doesn't recognise
        self.search_budget = int(cfg["diversity"]["search_budget"])
        self.discography_chance = float(cfg["diversity"]["discography_chance"])
        self.searches = 0
        self._warned: set[str] = set()

        self.compass_genres = self._compass_genres()
        self.wild_pool = self._wild_pool()
        interest_eras = cfg["interests"]["eras"]
        self.eras = [parse_era(e) for e in (interest_eras or cfg["wildcard"]["eras"])]
        self.era_chance = 0.6 if interest_eras else float(cfg["wildcard"]["era_chance"])

    # --- pools -----------------------------------------------------------------------------

    def _compass_genres(self) -> dict[str, float]:
        weights: Counter[str] = Counter()
        for seed in self.compass_seeds.values():
            for g in seed.genres or []:
                weights[g] += 1.0
        for g, w in self.cfg["interests"]["genres"].items():
            weights[g] += w
        return {g: w for g, w in weights.items() if not matches_any(g, self.avoid_genres)}

    def _wild_pool(self) -> list[str]:
        wc = self.cfg["wildcard"]
        pool = list(BUILTIN_GENRES) if wc["use_builtin_genres"] else []
        pool += [g.lower() for g in wc["genres"]]
        # "Wild" means away from where you already are: drop your ten heaviest genres.
        familiar = {g for g, _ in sorted(self.profile.genres.items(), key=lambda kv: -kv[1])[:10]}
        return sorted({g for g in pool if g not in familiar and not matches_any(g, self.avoid_genres)})

    # --- helpers -----------------------------------------------------------------------------

    def _fresh(self, t: Track, novel: bool = False) -> bool:
        if self.profile.is_known(t) or self.avoid_artist_ids.intersection(t.artist_ids):
            return False
        if any(n.lower() in self.avoid_artist_names for n in t.artist_names) or self.selector.any_artist_full(t):
            return False
        return not (novel and t.primary_artist_id in self.profile.artists)

    def _params(self, **extra) -> dict:
        if self.market:
            extra["market"] = self.market
        return extra

    def _warn_once(self, what: str, exc: SpotifyError) -> None:
        if what in self._warned:
            log.debug("%s: %s", what, exc)
        else:
            self._warned.add(what)
            log.warning("%s failed (further failures logged with -v): %s", what, exc)

    def search_available(self) -> bool:
        blocked = getattr(self.client, "is_blocked", lambda _: False)("/search")
        return not blocked and self.searches < self.search_budget

    def _artist_albums(self, artist_id: str) -> list[dict]:
        """The artist's newest releases (one page; the endpoint is rate-limited aggressively)."""
        if artist_id not in self._albums:
            albums: list[dict] = []
            try:
                data = self.client.get(f"/artists/{artist_id}/albums", self._params(include_groups="album,single", limit=ALBUM_LIMIT))
                albums = list(data.get("items") or [])
            except SpotifyError as exc:
                self._warn_once("Artist albums lookup", exc)
            self._albums[artist_id] = [a for a in albums if a.get("id")]
        return self._albums[artist_id]

    def _tracks_of_album(self, album: dict) -> list[Track]:
        if album["id"] not in self._album_tracks:
            try:
                data = self.client.get(f"/albums/{album['id']}/tracks", self._params(limit=50))
                self._album_tracks[album["id"]] = [t for t in (parse_track(x, album) for x in data.get("items", [])) if t]
            except SpotifyError as exc:
                self._warn_once("Album tracks lookup", exc)
                self._album_tracks[album["id"]] = []
        return self._album_tracks[album["id"]]

    def _search_tracks(self, query: str, offset: int) -> list[Track]:
        key = (query, offset)
        if key not in self._search:
            if not self.search_available():
                return []
            self.searches += 1
            try:
                data = self.client.get("/search", self._params(q=query, type="track", limit=SEARCH_LIMIT, offset=offset))
            except SpotifyError as exc:
                self._warn_once("Search", exc)
                self._search[key] = []
                return []
            block = data.get("tracks") or {}
            self._totals[query] = int(block.get("total") or 0)
            self._search[key] = [t for t in (parse_track(x) for x in block.get("items") or []) if t]
        return self._search[key]

    def _offset(self, query: str, attempt: int) -> int:
        """Random dig into results; deeper offsets skip the mainstream head of the list."""
        depth = self.depth if attempt == 0 else min(self.depth, 30)
        if query in self._totals:
            depth = min(depth, max(self._totals[query] - SEARCH_LIMIT, 0))
        return self.rng.randint(0, depth) if depth > 0 else 0

    # --- primitives --------------------------------------------------------------------------

    def deep_cut(self, seed: ArtistSeed, source: str, reason: str) -> Candidate | None:
        """An unheard track from an album of theirs you've played (one call), or sometimes from their releases."""
        known = [{"id": k, "name": v} for k, v in seed.albums.items()]
        browse = not known or self.rng.random() < self.discography_chance
        albums = (self._artist_albums(seed.id) if browse else []) or known
        for album in self.rng.sample(albums, min(3, len(albums))):
            pool = [t for t in self._tracks_of_album(album) if seed.id in t.artist_ids and self._fresh(t)]
            if pool:
                genre = (seed.genres or [None])[0]
                return Candidate(self.rng.choice(pool), source, reason.replace("{album}", album.get("name", "?")), genre)
        return None

    def search_pick(self, query: str, *, source: str, reason: str, genre: str | None, novel: bool) -> Candidate | None:
        # Search is the scarcest endpoint, so use up leftovers from pages already fetched first.
        cached = [t for (q, _), tracks in self._search.items() if q == query for t in tracks if self._fresh(t, novel)]
        if cached:
            return Candidate(self.rng.choice(cached), source, reason, genre)
        for attempt in range(3):
            if not self.search_available():
                return None
            tracks = self._search_tracks(query, self._offset(query, attempt))
            pool = [t for t in tracks if self._fresh(t, novel)]
            if pool:
                return Candidate(self.rng.choice(pool), source, reason, genre)
            if self._totals.get(query) == 0:
                break
        return None

    def genre_pick(self, genre: str, *, source: str, reason: str, novel: bool, era: str | None = None) -> Candidate | None:
        query = f'genre:"{genre}"' + (f" year:{era}" if era else "")
        c = self.search_pick(query, source=source, reason=reason, genre=genre, novel=novel)
        if c is None and not era and self._totals.get(query) == 0:
            self.dead_genres.add(genre)
        return c

    # --- sources -----------------------------------------------------------------------------

    def exhausted(self, source: str) -> bool:
        if source == "deep_cuts":
            return not self.profile.artists
        if source == "compass":
            return not self.compass_seeds and not (self.search_available() and self._live(self.compass_genres))
        if not self.search_available():
            return True
        if source == "genre_neighbors":
            return not self._live(self.profile.genres) and not self.wild_pool
        return not self.wild_pool and not self.cfg["interests"]["keywords"]

    def _live(self, genres: dict[str, float]) -> dict[str, float]:
        return {g: w for g, w in genres.items() if g not in self.dead_genres}

    def pick(self, source: str) -> Candidate | None:
        return getattr(self, f"_pick_{source}")()

    def _pick_deep_cuts(self) -> Candidate | None:
        aid = weighted_choice(self.rng, {k: s.weight for k, s in self.profile.artists.items()}, self.selector.artist_full)
        if not aid:
            return None
        seed = self.profile.artists[aid]
        why = seed.reasons[0] if seed.reasons else "in your rotation"
        return self.deep_cut(seed, "deep_cuts", f"deeper into {seed.name} ({why}) · from {{album}}")

    def _pick_genre_neighbors(self) -> Candidate | None:
        genre = weighted_choice(self.rng, self._live(self.profile.genres), self.selector.genre_full)
        if not genre:  # no genre data at all: Spotify returns empty genres for many artists
            return self._pick_wildcard(source="genre_neighbors")
        via = self.profile.genre_examples.get(genre)
        reason = f"new {genre} artist" + (f" (a thread from {via})" if via else " (from your interests)")
        return self.genre_pick(genre, source="genre_neighbors", reason=reason, novel=self.cfg["diversity"]["novel_artists_only"])

    def _pick_wildcard(self, source: str = "wildcard") -> Candidate | None:
        keywords = self.cfg["interests"]["keywords"]
        if keywords and (not self.wild_pool or self.rng.random() < self.cfg["wildcard"]["keyword_chance"]):
            kw = self.rng.choice(keywords)
            return self.search_pick(kw, source=source, reason=f"wildcard keyword “{kw}”", genre=None, novel=True)
        pool = [g for g in self.wild_pool if g not in self.dead_genres and not self.selector.genre_full(g)]
        if not pool:
            return None
        genre = self.rng.choice(pool)
        era = self.rng.choice(self.eras) if self.eras and self.rng.random() < self.era_chance else None
        label = f"wildcard: {genre}" + (f", {era}" if era else "")
        c = self.genre_pick(genre, source=source, reason=label, novel=True, era=era)
        if c is None and era:
            c = self.genre_pick(genre, source=source, reason=f"wildcard: {genre}", novel=True)
        return c

    def _pick_compass(self) -> Candidate | None:
        genres = self._live(self.compass_genres) if self.search_available() else {}
        use_artist = self.compass_seeds and (not genres or self.rng.random() < 0.5)
        if use_artist:
            aid = weighted_choice(self.rng, {k: s.weight for k, s in self.compass_seeds.items()}, self.selector.artist_full)
            if aid:
                seed = self.compass_seeds[aid]
                return self.deep_cut(seed, "compass", f"compass → {seed.name} ({seed.reasons[0] if seed.reasons else 'steering'}) · from {{album}}")
        genre = weighted_choice(self.rng, genres, self.selector.genre_full)
        if not genre:
            return None
        return self.genre_pick(genre, source="compass", reason=f"compass → {genre}", novel=True)


def allocate(size: int, mix: dict[str, float]) -> dict[str, int]:
    """Largest-remainder split of `size` across sources by mix weight."""
    total = sum(max(0.0, mix.get(s, 0.0)) for s in SOURCES)
    exact = {s: size * max(0.0, mix.get(s, 0.0)) / total for s in SOURCES}
    counts = {s: int(v) for s, v in exact.items()}
    for s in sorted(SOURCES, key=lambda s: -(exact[s] - counts[s]))[: size - sum(counts.values())]:
        counts[s] += 1
    return counts
