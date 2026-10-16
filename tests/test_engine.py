import json
import random
from collections import Counter
from datetime import datetime, timezone

from eclectolog.config import load_config
from eclectolog.engine import arrange, run
from eclectolog.models import Candidate, Track, normalize_title
from eclectolog.profile import History, build_profile, recency_weight, temper
from eclectolog.sources import allocate
from eclectolog.spotify import SpotifyError

from .fake_spotify import FakeDeezer, FakeSpotify

NOW = datetime(2026, 10, 4, 12, tzinfo=timezone.utc)


def cfg_for(tmp_path, **env):
    env.setdefault("STATE_FILE", str(tmp_path / "state" / "history.jsonl"))
    env.setdefault("DEEZER", "false")  # tests that want Deezer pass a FakeDeezer; never hit the network
    return load_config(environ={f"ECLECTOLOG_{k}": str(v) for k, v in env.items()}, base_dir=tmp_path)


def test_recency_boost_is_gentle():
    assert recency_weight(0, 0.35, 72) == 1.35
    assert recency_weight(72, 0.35, 72) == 1.175
    assert 1.0 < recency_weight(24 * 60, 0.35, 72) < 1.001


def test_temperature_flattens():
    flat = temper({"big": 100.0, "small": 1.0}, 0.5)
    assert flat["big"] / flat["small"] == 10.0  # 100:1 becomes 10:1


def test_profile_keeps_old_love_in_play(tmp_path):
    cfg = cfg_for(tmp_path)
    a = lambda i, aid: Track(f"t{i}{aid}", f"u{i}", f"Song {i}", ((aid, aid.upper()),))
    hist = History(recent=[(a(i, "hot"), NOW) for i in range(30)] + [(a(0, "old"), NOW.replace(year=2025))])
    profile = build_profile(hist, cfg, NOW)
    ratio = profile.artists["hot"].weight / profile.artists["old"].weight
    assert ratio < 30 * 1.35 / 4  # 40x raw advantage is squashed well below 10x


def test_allocate_sums_to_size():
    assert allocate(40, {"deep_cuts": 0.25, "genre_neighbors": 0.35, "wildcard": 0.2, "compass": 0.2}) == {
        "deep_cuts": 10, "genre_neighbors": 14, "wildcard": 8, "compass": 8}
    assert sum(allocate(7, {"deep_cuts": 1, "genre_neighbors": 1, "wildcard": 1, "compass": 0}).values()) == 7


def test_normalize_title_collapses_remasters():
    assert normalize_title("Song (Remastered 2011)") == normalize_title("Song - Radio Edit") == "song"


def test_arrange_avoids_back_to_back_sources():
    t = lambda i: Track(str(i), str(i), str(i), ((str(i), str(i)),))
    picks = [Candidate(t(i), "a" if i % 2 else "b", "") for i in range(10)]
    out = arrange(picks, random.Random(1))
    assert all(x.source != y.source for x, y in zip(out, out[1:]))


def test_end_to_end_creates_playlists_and_respects_caps(tmp_path):
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=30, EXTRA_ARTISTS="Neu!")
    fake = FakeSpotify(NOW)
    result = run(fake, cfg, random.Random(7), NOW)

    assert len(result.picks) == 30
    assert set(result.created_playlists) == {"Eclectolog · Compass", "Eclectolog · Avoid", "Eclectolog"}
    artists = Counter(c.track.primary_artist_id for c in result.picks)
    assert max(artists.values()) == 1
    genres = Counter(c.genre for c in result.picks if c.genre)
    assert max(genres.values()) <= cfg["diversity"]["max_per_genre"]
    known = {f"r{i}" for i in range(20)} | {"old", "saved1"}
    assert not known & {c.track.id for c in result.picks}
    assert {c.source for c in result.picks} >= {"deep_cuts", "genre_neighbors", "wildcard", "compass"}

    by_name = {p["name"]: p for p in fake.playlists.values()}
    assert len(by_name["Eclectolog"]["tracks"]) == 30
    history = (tmp_path / "state" / "history.jsonl").read_text().splitlines()
    assert len(history) == 1 and len(json.loads(history[0])["tracks"]) == 30


def test_second_run_uses_compass_directives_avoid_and_no_repeats(tmp_path):
    fake = FakeSpotify(NOW)
    run(fake, cfg_for(tmp_path, PLAYLIST_SIZE=20), random.Random(1), NOW)
    pls = {p["name"]: (pid, p) for pid, p in fake.playlists.items()}
    first = {t["id"] for t in pls["Eclectolog"][1]["tracks"]}

    pls["Eclectolog · Compass"][1]["description"] = "more: dub; size: 12; less: indie"
    pls["Eclectolog · Compass"][1]["tracks"] = [{"type": "track", "id": "c1", "uri": "spotify:track:c1", "name": "Steer",
                                                 "artists": [{"id": "a3", "name": "Jazz Person"}], "album": {"name": "x"}}]
    pls["Eclectolog · Avoid"][1]["tracks"] = [{"type": "track", "id": "v1", "uri": "spotify:track:v1", "name": "Nope",
                                               "artists": [{"id": "a2", "name": "Old Love"}], "album": {"name": "x"}}]
    fake.saved_ids = set(list(first)[:2])

    result = run(fake, cfg_for(tmp_path, PLAYLIST_SIZE=20), random.Random(2), NOW)
    assert len(result.picks) == 12
    assert result.directive_notes == ["more: dub", "size: 12", "less: indie"]
    assert len(result.liked_feedback) == 2
    ids = {c.track.id for c in result.picks}
    assert not ids & first
    assert all(c.track.primary_artist_id != "a2" for c in result.picks)
    assert "Jazz Person" in result.compass_seeds
    # less: removes the genre from exploration; deep cuts from artists in it are only down-weighted
    assert not any(c.genre and "indie" in c.genre for c in result.picks if c.source != "deep_cuts")


def test_dry_run_writes_nothing(tmp_path):
    fake = FakeSpotify(NOW)
    result = run(fake, cfg_for(tmp_path, DRY_RUN="true", PLAYLIST_SIZE=10), random.Random(3), NOW)
    assert len(result.picks) == 10
    assert fake.log == [] and fake.playlists == {}
    assert not (tmp_path / "state").exists()


def test_history_file_prevents_repeats_in_new_mode(tmp_path):
    # "new" mode makes a fresh playlist per day, so only the history file knows what was served.
    fake = FakeSpotify(NOW)
    first = run(fake, cfg_for(tmp_path, PLAYLIST_MODE="new", PLAYLIST_SIZE=15), random.Random(1), NOW)
    later = NOW.replace(day=5)
    second = run(fake, cfg_for(tmp_path, PLAYLIST_MODE="new", PLAYLIST_SIZE=15), random.Random(1), later)
    assert not {c.track.id for c in first.picks} & {c.track.id for c in second.picks}
    assert len((tmp_path / "state" / "history.jsonl").read_text().splitlines()) == 2


def test_history_prunes_old_runs_and_survives_corruption(tmp_path):
    from eclectolog.history import ServedHistory
    path = tmp_path / "h.jsonl"
    h = ServedHistory.load(path)
    t = Track("x", "spotify:track:x", "X", (("a", "A"),))
    h.add_run(NOW.replace(year=2024), "old", [Candidate(t, "wildcard", "")], keep_days=0)
    h.add_run(NOW, "new", [Candidate(t, "wildcard", "")], keep_days=30)
    h.save()
    assert [r["playlist"] for r in ServedHistory.load(path).runs] == ["new"]
    path.write_text("{not json\n")
    assert ServedHistory.load(path).runs == [] and (tmp_path / "h.corrupt").exists()


def test_search_budget_caps_calls_and_deep_cuts_fill_the_rest(tmp_path):
    fake = FakeSpotify(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=20, SEARCH_BUDGET=3, DRY_RUN="true", MAX_PER_ARTIST=6, MAX_PER_GENRE=10)
    result = run(fake, cfg, random.Random(5), NOW)
    assert len(result.picks) == 20
    assert fake.search_calls <= 3
    assert Counter(c.source for c in result.picks)["deep_cuts"] >= 10  # 3 searches yield up to ~10 picks via leftover reuse


def test_market_from_token_without_scope_falls_back_to_no_market(tmp_path, caplog):
    class NoPrivateScope(FakeSpotify):  # token lacks user-read-private, like every web-app sign-in so far
        markets: list = []

        def get(self, path, params=None):
            if params and "market" in params:
                self.markets.append(params["market"])
                if params["market"] == "from_token":
                    raise SpotifyError("GET /search -> 403: Insufficient client scope", 403)
            return super().get(path, params)

    fake = NoPrivateScope(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=20, DRY_RUN="true")
    result = run(fake, cfg, random.Random(5), NOW)
    assert fake.markets.count("from_token") == 1  # one 403, then no market for the rest of the run
    assert any(c.source == "wildcard" for c in result.picks)
    assert "user-read-private" in caplog.text


def test_featured_artist_counts_toward_artist_cap():
    from eclectolog.sources import Selector
    sel = Selector(max_per_artist=1, max_per_genre=9)
    solo = Track("1", "u1", "One", (("dope", "DOPE LEMON"),))
    feat = Track("2", "u2", "Two", (("stone", "STONE"), ("dope", "DOPE LEMON")))
    assert sel.offer(Candidate(solo, "deep_cuts", ""))
    assert not sel.offer(Candidate(feat, "deep_cuts", ""))


def test_deep_cuts_can_run_on_known_albums_alone(tmp_path):
    fake = FakeSpotify(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=6, DRY_RUN="true", DISCOGRAPHY_CHANCE=0, MIX="deep_cuts=1,genre_neighbors=0,wildcard=0,compass=0")
    result = run(fake, cfg, random.Random(2), NOW)
    assert result.picks and all(c.source == "deep_cuts" for c in result.picks)
    assert fake.album_list_calls == 0


def test_covers_are_set_once_and_failures_only_warn(tmp_path, caplog):
    from eclectolog.covers import apply_covers, has_custom_cover
    from eclectolog.spotify import SpotifyError

    fake = FakeSpotify(NOW)
    run(fake, cfg_for(tmp_path, PLAYLIST_SIZE=10), random.Random(1), NOW)
    covered = [p["name"] for p in fake.playlists.values() if p.get("cover")]
    assert sorted(covered) == ["Eclectolog", "Eclectolog · Avoid", "Eclectolog · Compass"]

    assert not has_custom_cover({"images": [{"url": "https://mosaic.scdn.co/640/ab67616d..."}]})
    assert not has_custom_cover({"images": [{"url": "https://i.scdn.co/image/ab67616d0000b273abc"}]})
    assert has_custom_cover({"images": [{"url": "https://i.scdn.co/image/ab67706c0000da84abc"}]})

    fake.cover_error = SpotifyError("PUT -> 401: missing scope", 401)
    warnings = apply_covers(fake, {"output": {"id": "pl1", "name": "Eclectolog", "images": []},
                                   "compass": {"id": "pl2", "name": "C", "images": []}})
    assert len(warnings) == 1 and "Sign in again" in warnings[0]  # one warning, then it stops trying

    fake.cover_error = RuntimeError("boom")
    assert apply_covers(fake, {"output": {"id": "pl1", "name": "Eclectolog", "images": []}})  # warned, not raised


def test_neighbors_never_borrow_wildcard_genres(tmp_path):
    class NoGenres(FakeSpotify):  # Spotify returns empty genres for many artists
        def get(self, path, params=None):
            data = super().get(path, params)
            if path.startswith("/artists/") and "genres" in data:
                data = data | {"genres": []}
            return data

    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=20, DRY_RUN="true", EXTRA_GENRES="dub")
    result = run(NoGenres(NOW), cfg, random.Random(3), NOW)
    neighbors = [c for c in result.picks if c.source == "genre_neighbors"]
    assert neighbors and not any(c.reason.startswith("wildcard") for c in neighbors)
    assert any(c.genre == "dub" for c in neighbors)  # interests/compass fill the gap instead


def test_wildcards_only_take_slots_familiar_sources_cant_fill(tmp_path):
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=12, DRY_RUN="true", MIX="deep_cuts=0.5,genre_neighbors=0.3,wildcard=0.2,compass=0")
    result = run(FakeSpotify(NOW), cfg, random.Random(4), NOW)
    assert len(result.picks) == 12
    assert Counter(c.source for c in result.picks)["wildcard"] <= result.allocation["wildcard"]


def test_wildcards_lean_toward_families_near_your_taste(tmp_path):
    from eclectolog.genres import GENRE_FAMILIES
    from eclectolog.profile import Profile
    from eclectolog.sources import Selector, Sources

    cfg = cfg_for(tmp_path)
    profile = Profile(artists={}, genres={"indie rock": 3.0, "chilean shoegaze": 2.0, "ambient": 1.0})
    sources = Sources(FakeSpotify(NOW), cfg, profile, Selector(1, 4), random.Random(0))
    w = sources.family_weights
    assert w["Rock & indie"] > w["Electronic"] > w["Asia & Middle East"] > 0  # far families are rare, not banned
    assert "indie rock" not in sources.wild_pool  # your own genres aren't wildcards

    cfg["wildcard"]["adjacency"] = 0
    flat = Sources(FakeSpotify(NOW), cfg, profile, Selector(1, 4), random.Random(0)).family_weights
    assert len(set(flat.values())) == 1 and len(flat) == len(GENRE_FAMILIES)


def test_neighbors_come_from_deezer_related_artists(tmp_path):
    fake = FakeSpotify(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=20, DRY_RUN="true", DEEZER="true", DEEZER_SECOND_HOP_CHANCE=0)
    result = run(fake, cfg, random.Random(3), NOW, deezer=FakeDeezer(fake))
    neighbors = [c for c in result.picks if c.source == "genre_neighbors"]
    assert len(neighbors) >= result.allocation["genre_neighbors"]  # overflow slots can land here too
    names = [c.track.artist_names[0] for c in neighbors]
    assert all(n.startswith("Near ") for n in names)  # Old Love is related too, but you already play them
    assert not any(n.endswith(" 0") or n.endswith(" 1") for n in names)  # 0 and 500 fans are under min_fans
    assert all(c.reason.startswith("new artist near ") for c in neighbors)
    assert result.deezer_calls > 0


def test_neighbor_artists_cool_down_between_runs(tmp_path):
    fake = FakeSpotify(NOW)
    cfg = lambda: cfg_for(tmp_path, PLAYLIST_SIZE=20, DEEZER="true", MIX="genre_neighbors=1,deep_cuts=0,wildcard=0,compass=0")
    first = run(fake, cfg(), random.Random(1), NOW, deezer=FakeDeezer(fake))
    second = run(fake, cfg(), random.Random(1), NOW.replace(day=5), deezer=FakeDeezer(fake))
    artists = lambda r: {c.track.artist_names[0] for c in r.picks if c.source == "genre_neighbors"}
    assert artists(first) and artists(second)
    assert not artists(first) & artists(second)


def test_deezer_outage_falls_back_to_genre_search(tmp_path, caplog):
    fake = FakeSpotify(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_SIZE=20, DRY_RUN="true", DEEZER="true")
    result = run(fake, cfg, random.Random(3), NOW, deezer=FakeDeezer(fake, fail=True))
    neighbors = [c for c in result.picks if c.source == "genre_neighbors"]
    assert neighbors and all(c.reason.startswith("new ") and "artist" in c.reason for c in neighbors)
    assert any(c.genre for c in neighbors)  # genre-search picks carry their genre
    assert caplog.text.count("Deezer failed") == 1
