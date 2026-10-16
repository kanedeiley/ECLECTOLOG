"""Candidate generators. Each pick() returns one Candidate or None.

Built only on endpoints still open to Development Mode apps after Spotify's Nov 2024 and Feb 2026
changes (no /recommendations, related-artists, artist top-tracks or popularity):

  deep_cuts        a random album track from an artist you already play, which you haven't heard
  genre_neighbors  a new artist Deezer relates to one you play (genre search when Deezer is off or down)
  wildcard         a genre you don't listen to, optionally pinned to an era or keyword
  compass          artists/genres from your Compass playlist, interests.yaml and `more:` directives
"""
from __future__ import annotations

import logging
import random
from collections import Counter
from typing import Callable

from .config import SOURCES, parse_era
from .deezer import Deezer, DeezerArtist, DeezerError, DeezerTrack, name_key
from .genres import FAMILY_HINTS, GENRE_FAMILIES
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
        deezer: Deezer | None = None,
        recent_artists: list[tuple[str, str]] = (),
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
        # Wildcards are genres you don't know, so stay near the top of the results instead of the long tail.
        self.wild_depth = min(int(cfg["wildcard"]["search_depth"]), MAX_OFFSET)

        self._albums: dict[str, list[dict]] = {}
        self._album_tracks: dict[str, list[Track]] = {}
        self._search: dict[tuple[str, int], list[Track]] = {}
        self._totals: dict[str, int] = {}
        self.dead_genres: set[str] = set()  # genres Spotify's genre: filter doesn't recognise
        self.search_budget = int(cfg["diversity"]["search_budget"])
        self.discography_chance = float(cfg["diversity"]["discography_chance"])
        self.searches = 0
        self._warned: set[str] = set()

        self.deezer = deezer if cfg["deezer"]["enabled"] else None
        self.dz = cfg["deezer"]
        # Neighbors skip anyone you play, have steered toward or avoided, or were served within the cooldown.
        self.cooled_ids = {aid for aid, _ in recent_artists}
        self.skip_names = {name_key(n) for _, n in recent_artists}
        self.skip_names |= {name_key(s.name) for s in [*self.profile.artists.values(), *self.compass_seeds.values()]}
        self.skip_names |= {name_key(n) for n in self.avoid_artist_names}
        self._dead_seeds: set[str] = set()

        self.compass_genres = self._compass_genres()
        self.wild_families = self._wild_families()
        self.wild_pool = sorted({g for genres in self.wild_families.values() for g in genres})
        self.family_weights = self._family_weights()
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

    def _wild_families(self) -> dict[str, list[str]]:
        wc = self.cfg["wildcard"]
        families = dict(GENRE_FAMILIES) if wc["use_builtin_genres"] else {}
        if wc["genres"]:
            families["yours"] = [g.lower() for g in wc["genres"]]
        # "Wild" means away from where you already are: drop your ten heaviest genres.
        familiar = {g for g, _ in sorted(self.profile.genres.items(), key=lambda kv: -kv[1])[:10]}
        keep = lambda g: g not in familiar and not matches_any(g, self.avoid_genres)
        return {f: sorted({g for g in genres if keep(g)}) for f, genres in families.items() if any(map(keep, genres))}

    def _family_weights(self) -> dict[str, float]:
        """Lean wildcards toward families near your taste: a stretch from where you are, not a random region.

        Each of your genres (history, Compass, interests) votes for the families it belongs to; `adjacency`
        blends those votes with an even split, so distant families still turn up now and then."""
        votes: Counter[str] = Counter()
        for genre, weight in list(self.profile.genres.items()) + list(self.compass_genres.items()):
            hits = [f for f, gs in GENRE_FAMILIES.items() if genre in gs or any(h in genre for h in FAMILY_HINTS[f])]
            for f in hits:
                votes[f] += weight / len(hits)
        builtin = [f for f in self.wild_families if f in GENRE_FAMILIES]
        total = sum(votes[f] for f in builtin)
        adjacency = float(self.cfg["wildcard"]["adjacency"]) if total else 0.0
        weights = {f: (1 - adjacency) / len(builtin) + adjacency * votes[f] / (total or 1) for f in builtin}
        if "yours" in self.wild_families:  # genres you listed yourself are always fair game
            weights["yours"] = max(weights.values(), default=1.0)
        log.debug("Wildcard family weights: %s", {f: round(w, 3) for f, w in weights.items()})
        return weights

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

    def _get(self, path: str, **params) -> dict:
        """GET with the configured market. market=from_token needs the user-read-private scope, which older
        sign-ins never granted: Spotify answers 403, so retry without a market for the rest of the run."""
        try:
            return self.client.get(path, self._params(**params))
        except SpotifyError as exc:
            if exc.status != 403 or self.market != "from_token":
                raise
            log.warning("market=from_token needs the user-read-private scope this account hasn't granted; "
                        "searching without a market (some picks may not be playable in their country)")
            self.market = None
            return self.client.get(path, self._params(**params))

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
                data = self._get(f"/artists/{artist_id}/albums", include_groups="album,single", limit=ALBUM_LIMIT)
                albums = list(data.get("items") or [])
            except SpotifyError as exc:
                self._warn_once("Artist albums lookup", exc)
            self._albums[artist_id] = [a for a in albums if a.get("id")]
        return self._albums[artist_id]

    def _tracks_of_album(self, album: dict) -> list[Track]:
        if album["id"] not in self._album_tracks:
            try:
                data = self._get(f"/albums/{album['id']}/tracks", limit=50)
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
                data = self._get("/search", q=query, type="track", limit=SEARCH_LIMIT, offset=offset)
            except SpotifyError as exc:
                self._warn_once("Search", exc)
                self._search[key] = []
                return []
            block = data.get("tracks") or {}
            self._totals[query] = int(block.get("total") or 0)
            self._search[key] = [t for t in (parse_track(x) for x in block.get("items") or []) if t]
        return self._search[key]

    def _offset(self, query: str, attempt: int, depth: int) -> int:
        """Random dig into results; deeper offsets skip the mainstream head of the list."""
        depth = depth if attempt == 0 else min(depth, 30)
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

    def search_pick(
        self, query: str, *, source: str, reason: str, genre: str | None, novel: bool, depth: int | None = None
    ) -> Candidate | None:
        # Search is the scarcest endpoint, so use up leftovers from pages already fetched first.
        cached = [t for (q, _), tracks in self._search.items() if q == query for t in tracks if self._fresh(t, novel)]
        if cached:
            return Candidate(self.rng.choice(cached), source, reason, genre)
        for attempt in range(3):
            if not self.search_available():
                return None
            tracks = self._search_tracks(query, self._offset(query, attempt, self.depth if depth is None else depth))
            pool = [t for t in tracks if self._fresh(t, novel)]
            if pool:
                return Candidate(self.rng.choice(pool), source, reason, genre)
            if self._totals.get(query) == 0:
                break
        return None

    def genre_pick(
        self, genre: str, *, source: str, reason: str, novel: bool, era: str | None = None, depth: int | None = None
    ) -> Candidate | None:
        query = f'genre:"{genre}"' + (f" year:{era}" if era else "")
        c = self.search_pick(query, source=source, reason=reason, genre=genre, novel=novel, depth=depth)
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
            return not self._similar_seeds() and not self._live(self.profile.genres) and not self._live(self.compass_genres)
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
        if self._similar_seeds():
            return self._pick_similar()
        genre = weighted_choice(self.rng, self._live(self.profile.genres), self.selector.genre_full)
        if not genre:
            # Spotify returns empty genres for many artists, and the per-genre cap fills up fast. Lean on genres
            # you've steered toward rather than wildcards, so "neighbors" never lands somewhere you didn't pick.
            genre = weighted_choice(self.rng, self._live(self.compass_genres), self.selector.genre_full)
            if not genre:
                return None
            reason = f"new {genre} artist (from your compass)"
        else:
            via = self.profile.genre_examples.get(genre)
            reason = f"new {genre} artist" + (f" (a thread from {via})" if via else " (from your interests)")
        return self.genre_pick(genre, source="genre_neighbors", reason=reason, novel=self.cfg["diversity"]["novel_artists_only"])

    # --- Deezer neighbors --------------------------------------------------------------------

    def _similar_seeds(self) -> dict[str, ArtistSeed]:
        if not self.deezer:
            return {}
        pool = self.profile.artists or self.compass_seeds
        return {k: s for k, s in pool.items() if k not in self._dead_seeds}

    def _pick_similar(self) -> Candidate | None:
        """A new artist Deezer pairs with one you play (sometimes two steps out), via one of their best-known tracks."""
        try:
            for _ in range(3):
                seeds = self._similar_seeds()
                aid = weighted_choice(self.rng, {k: s.weight for k, s in seeds.items()})
                if not aid:
                    return None
                seed = seeds[aid]
                home = self.deezer.find_artist(seed.name)
                near = self._neighbors(home) if home else []
                if not near:
                    self._dead_seeds.add(aid)
                    continue
                pick, via = self.rng.choice(near), None
                if self.rng.random() < float(self.dz["second_hop_chance"]):
                    far = [a for a in self._neighbors(pick) if a.id != home.id]
                    if far:
                        pick, via = self.rng.choice(far), pick
                self.skip_names.add(name_key(pick.name))  # one try per artist per run, hit or miss
                if c := self._neighbor_track(pick, seed, via):
                    return c
                if not self.search_available():
                    return None
        except DeezerError as exc:
            log.warning("Deezer failed, so neighbors use genre search for the rest of this run: %s", exc)
            self.deezer = None
        return None

    def _neighbors(self, artist: DeezerArtist) -> list[DeezerArtist]:
        lo, hi = int(self.dz["min_fans"]), int(self.dz["max_fans"])
        return [a for a in self.deezer.related(artist.id)
                if a.fans >= lo and (not hi or a.fans <= hi) and name_key(a.name) not in self.skip_names]

    def _neighbor_track(self, artist: DeezerArtist, seed: ArtistSeed, via: DeezerArtist | None) -> Candidate | None:
        want = name_key(artist.name)
        tracks = [t for t in self.deezer.top_tracks(artist.id, int(self.dz["top_tracks"])) if name_key(t.artist) == want]
        for dt in self.rng.sample(tracks, min(2, len(tracks))):
            t = self._on_spotify(dt)
            if t and self._fresh(t, novel=True) and not self.cooled_ids.intersection(t.artist_ids):
                reason = f"new artist near {seed.name}" + (f" (via {via.name})" if via else "")
                return Candidate(t, "genre_neighbors", reason, None)
        return None

    def _on_spotify(self, dt: DeezerTrack) -> Track | None:
        """Find a Deezer track on Spotify: by ISRC (exact recording), else by title and artist."""
        isrc = self.deezer.isrc(dt.id)
        clean = lambda s: s.replace('"', "")
        queries = ([f"isrc:{isrc}"] if isrc else []) + [f'track:"{clean(dt.title)}" artist:"{clean(dt.artist)}"']
        want = name_key(dt.artist)
        for q in queries:
            if match := next((t for t in self._search_tracks(q, 0) if want in map(name_key, t.artist_names)), None):
                return match
        return None

    def _pick_wildcard(self) -> Candidate | None:
        keywords = self.cfg["interests"]["keywords"]
        if keywords and (not self.wild_pool or self.rng.random() < self.cfg["wildcard"]["keyword_chance"]):
            kw = self.rng.choice(keywords)
            return self.search_pick(kw, source="wildcard", reason=f"wildcard keyword “{kw}”", genre=None, novel=True, depth=self.wild_depth)
        open_genres = {
            f: [g for g in genres if g not in self.dead_genres and not self.selector.genre_full(g)]
            for f, genres in self.wild_families.items()
        }
        family = weighted_choice(self.rng, self.family_weights, lambda f: not open_genres[f])
        if not family:
            return None
        genre = self.rng.choice(open_genres[family])
        era = self.rng.choice(self.eras) if self.eras and self.rng.random() < self.era_chance else None
        label = f"wildcard: {genre}" + (f", {era}" if era else "")
        c = self.genre_pick(genre, source="wildcard", reason=label, novel=True, era=era, depth=self.wild_depth)
        if c is None and era:
            c = self.genre_pick(genre, source="wildcard", reason=f"wildcard: {genre}", novel=True, depth=self.wild_depth)
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
