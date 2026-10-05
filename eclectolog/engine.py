from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field
from datetime import datetime

from .config import SOURCES, apply_directives
from .covers import apply_covers
from .history import ServedHistory
from .models import ArtistSeed, Candidate, Track
from .profile import Profile, build_profile, collect_history, compute_genres, enrich_genres
from .references import References, create_playlist, load_references
from .sources import Selector, Sources, allocate
from .spotify import Spotify, SpotifyError

log = logging.getLogger(__name__)

ATTEMPTS_PER_SLOT = 4


@dataclass
class RunResult:
    picks: list[Candidate]
    allocation: dict[str, int]
    profile: Profile
    playlist_name: str
    playlist_url: str | None = None
    dry_run: bool = False
    directive_notes: list[str] = field(default_factory=list)
    compass_seeds: list[str] = field(default_factory=list)
    liked_feedback: list[Track] = field(default_factory=list)
    created_playlists: list[str] = field(default_factory=list)
    api_calls: int = 0
    target_size: int = 0


def output_name(cfg: dict, now: datetime) -> str:
    p = cfg["playlist"]
    return p["name"] if p["mode"] == "replace" else f"{p['name']} · {now.strftime(p['date_format'])}"


def saved_subset(client: Spotify, tracks: list[Track]) -> list[Track]:
    """Which of these tracks the user has since saved to Liked Songs (positive feedback)."""
    liked: list[Track] = []
    try:
        for i in range(0, len(tracks), 40):
            chunk = tracks[i : i + 40]
            flags = client.get("/me/library/contains", {"uris": ",".join(t.uri for t in chunk)})
            liked += [t for t, saved in zip(chunk, flags if isinstance(flags, list) else []) if saved]
    except SpotifyError as exc:
        log.warning("Skipping liked-feedback check: %s", exc)
    return liked


def compass_seeds(client: Spotify, cfg: dict, refs: References, avoid_ids: set[str]) -> dict[str, ArtistSeed]:
    seeds: dict[str, ArtistSeed] = {}
    for t in refs.tracks_of("compass"):
        for i, (aid, name) in enumerate(t.artists[:2]):
            if aid not in avoid_ids:
                seeds.setdefault(aid, ArtistSeed(aid, name)).add(1.0 if i == 0 else 0.5, f"you added “{t.name}” to the Compass", t)
    for name in cfg["interests"]["artists"]:
        try:
            items = client.get("/search", {"q": name, "type": "artist", "limit": 1}).get("artists", {}).get("items") or []
        except SpotifyError as exc:
            log.warning("Couldn't look up interest artist %r: %s", name, exc)
            continue
        if items and items[0]["id"] not in avoid_ids:
            a = items[0]
            seed = seeds.setdefault(a["id"], ArtistSeed(a["id"], a.get("name", name)))
            seed.add(1.0, "listed in your interests")
            if a.get("genres") is not None:
                seed.genres = list(a["genres"])
    return seeds


def fill(sources: Sources, selector: Selector, allocation: dict[str, int], size: int, mix: dict[str, float]) -> None:
    def take(source: str) -> bool:
        c = sources.pick(source)
        if c and selector.offer(c):
            sources.profile.add_known(c.track)
            return True
        return False

    for source, quota in allocation.items():
        if quota == 0:
            continue
        if sources.exhausted(source):
            log.info("Source %s has nothing to work with; its %d slots go to the others", source, quota)
            continue
        got = attempts = 0
        while got < quota and attempts < quota * ATTEMPTS_PER_SLOT + 2:
            attempts += 1
            got += take(source)

    misses, i = 0, 0
    while len(selector.picks) < size and misses < size * ATTEMPTS_PER_SLOT:
        order = [s for s in SOURCES if mix.get(s, 0) > 0 and not sources.exhausted(s)] or ["wildcard"]
        source = order[i % len(order)]
        i += 1
        if not take(source):
            misses += 1


def arrange(picks: list[Candidate], rng: random.Random) -> list[Candidate]:
    """Shuffle, then avoid back-to-back tracks from the same source or genre where possible."""
    pool = picks[:]
    rng.shuffle(pool)
    out: list[Candidate] = []
    while pool:
        last = out[-1] if out else None
        idx = next(
            (i for i, c in enumerate(pool) if last is None or (c.source != last.source and (c.genre is None or c.genre != last.genre))),
            0,
        )
        out.append(pool.pop(idx))
    return out


def describe(cfg: dict, picks: list[Candidate], now: datetime) -> str:
    genres = {c.genre for c in picks if c.genre}
    compass = cfg["reference"]["compass_playlist"] if cfg["reference"]["enabled"] else ""
    text = f"Eclectolog · {now:%b %d %Y} · {len(picks)} tracks across {len(genres)} genres."
    if compass:
        text += f" Steer it: add songs to “{compass}” or edit its description."
    return text[:300]


def write_output(client: Spotify, cfg: dict, refs: References, name: str, picks: list[Candidate], now: datetime, created: list[str]) -> str | None:
    desc = describe(cfg, picks, now)
    pl = refs.get("output")
    if pl is None:
        pl = create_playlist(client, name, desc, cfg["playlist"]["public"])
        created.append(name)
        refs.playlists["output"] = pl
    else:
        client.put(f"/playlists/{pl['id']}", {"description": desc})

    uris = [c.track.uri for c in picks]
    client.put(f"/playlists/{pl['id']}/items", {"uris": uris[:100]})  # replaces contents
    for i in range(100, len(uris), 100):
        client.post(f"/playlists/{pl['id']}/items", {"uris": uris[i : i + 100]})

    if archive := refs.get("archive"):
        try:
            for i in range(0, len(uris), 100):
                client.post(f"/playlists/{archive['id']}/items", {"uris": uris[i : i + 100]})
        except SpotifyError as exc:
            log.warning("Couldn't append to archive: %s", exc)
    return (pl.get("external_urls") or {}).get("spotify")


def run(
    client: Spotify, cfg: dict, rng: random.Random, now: datetime, served: ServedHistory | None = None
) -> RunResult:
    """Builds one mix. `served` defaults to the history file named in the config."""
    name = output_name(cfg, now)
    refs = load_references(client, cfg, name)
    notes = apply_directives(cfg, refs.directives) if refs.directives else []
    size = cfg["playlist"]["size"]

    avoid_ids = {t.primary_artist_id for t in refs.tracks_of("avoid")}
    if served is None:
        served = ServedHistory.load(cfg["state"]["file"])
    previous = refs.tracks_of("output") or served.last_tracks()
    liked = saved_subset(client, previous) if cfg["reference"]["liked_feedback_boost"] > 0 else []

    history = collect_history(client, cfg)
    profile = build_profile(history, cfg, now, liked, avoid_ids, cfg["interests"]["avoid"]["artists"])
    seeds = compass_seeds(client, cfg, refs, avoid_ids)
    enrich_genres(client, list(profile.artists.values()), cfg["history"]["genre_lookups"])
    enrich_genres(client, list(seeds.values()), 15)
    compute_genres(profile, cfg)
    for role in ("compass", "avoid", "archive", "output"):
        for t in refs.tracks_of(role):
            profile.add_known(t)
    for t in served.all_tracks():
        profile.add_known(t)

    if not profile.artists and not seeds:
        log.warning("No listening history or Compass seeds found; this mix will be all wildcards")

    selector = Selector(cfg["diversity"]["max_per_artist"], cfg["diversity"]["max_per_genre"])
    sources = Sources(client, cfg, profile, selector, rng, compass_seeds=seeds, avoid_artist_ids=avoid_ids)
    allocation = allocate(size, cfg["mix"])
    fill(sources, selector, allocation, size, cfg["mix"])
    picks = arrange(selector.picks, rng)

    result = RunResult(
        picks=picks,
        allocation=allocation,
        profile=profile,
        playlist_name=name,
        dry_run=cfg["dry_run"],
        directive_notes=notes,
        compass_seeds=[s.name for s in seeds.values()],
        liked_feedback=liked,
        created_playlists=refs.created,
        target_size=size,
    )
    if picks and not cfg["dry_run"]:
        result.playlist_url = write_output(client, cfg, refs, name, picks, now, result.created_playlists)
        if cfg["playlist"]["covers"]:
            apply_covers(client, refs.playlists)  # best effort: only ever logs warnings
        served.add_run(now, name, picks, cfg["state"]["keep_days"], url=result.playlist_url)
        served.save()
    result.api_calls = getattr(client, "calls", 0)
    return result
