import random
from datetime import timedelta

import eclectolog.__main__ as cli
from eclectolog.db import Supabase, SupabaseHistory, load_members
from eclectolog.engine import run
from eclectolog.spotify import AuthError

from .fake_spotify import FakeSpotify
from .test_engine import NOW, cfg_for


class FakeDB(Supabase):
    """In-memory stand-in for the PostgREST calls Supabase makes (eq/lt filters and order only)."""

    def __init__(self, **tables):
        self.tables = {name: [dict(r) for r in rows] for name, rows in tables.items()}

    @staticmethod
    def _match(row, filters):
        for col, cond in filters.items():
            if col in ("select", "order"):
                continue
            op, _, value = cond.partition(".")
            if op == "eq" and str(row.get(col)) != value:
                return False
            if op == "lt" and not str(row.get(col)) < value:
                return False
        return True

    def select(self, table, params):
        rows = [dict(r) for r in self.tables.get(table, []) if self._match(r, params)]
        if order := params.get("order"):
            col, _, direction = order.partition(".")
            rows.sort(key=lambda r: r[col], reverse=direction == "desc")
        return rows

    def insert(self, table, rows):
        self.tables.setdefault(table, []).extend(rows if isinstance(rows, list) else [rows])

    def update(self, table, filters, values):
        for row in self.tables.get(table, []):
            if self._match(row, filters):
                row.update(values)

    def delete(self, table, filters):
        self.tables[table] = [r for r in self.tables.get(table, []) if not self._match(r, filters)]


def test_supabase_history_records_runs_and_prevents_repeats(tmp_path):
    db = FakeDB(mix_runs=[])
    fake = FakeSpotify(NOW)
    cfg = cfg_for(tmp_path, PLAYLIST_MODE="new", PLAYLIST_SIZE=15)
    first = run(fake, cfg, random.Random(1), NOW, served=SupabaseHistory.load_for(db, "u1"))

    [row] = db.tables["mix_runs"]
    assert row["user_id"] == "u1" and len(row["tracks"]) == len(first.picks)
    assert all(t["reason"] for t in row["tracks"])
    assert not (tmp_path / "state").exists()  # nothing written to the history file

    later = NOW + timedelta(days=1)
    second = run(fake, cfg_for(tmp_path, PLAYLIST_MODE="new", PLAYLIST_SIZE=15), random.Random(1), later,
                 served=SupabaseHistory.load_for(db, "u1"))
    assert not {c.track.id for c in first.picks} & {c.track.id for c in second.picks}
    assert len(db.tables["mix_runs"]) == 2


def test_supabase_history_prunes_only_that_users_old_runs():
    old = (NOW - timedelta(days=40)).isoformat()
    db = FakeDB(mix_runs=[
        {"user_id": "u1", "ran_at": old, "playlist_name": "old", "tracks": []},
        {"user_id": "u2", "ran_at": old, "playlist_name": "theirs", "tracks": []},
    ])
    h = SupabaseHistory.load_for(db, "u1")
    h.add_run(NOW, "new", [], keep_days=30)
    h.save()
    assert sorted(r["playlist_name"] for r in db.tables["mix_runs"]) == ["new", "theirs"]


def test_load_members_joins_tables_and_converts_mix():
    db = FakeDB(
        spotify_tokens=[
            {"user_id": "b", "refresh_token": "rb"},
            {"user_id": "a", "refresh_token": "ra"},
            {"user_id": "ghost", "refresh_token": "rg"},
        ],
        profiles=[
            {"id": "a", "spotify_id": "alice", "display_name": "Alice", "joined_at": "2026-01-01"},
            {"id": "b", "spotify_id": "bob", "display_name": None, "joined_at": "2026-02-01"},
        ],
        preferences=[{"user_id": "a", "deep_cuts": 40, "genre_neighbors": 30, "wildcard": 20, "compass": 10}],
    )
    members = load_members(db)
    assert [m.spotify_id for m in members] == ["alice", "bob"]  # oldest first, no profile = skipped
    assert members[0].mix == {"deep_cuts": 0.4, "genre_neighbors": 0.3, "wildcard": 0.2, "compass": 0.1}
    assert members[1].mix is None and members[1].name == "bob"


def test_all_users_keeps_going_after_one_fails(tmp_path, monkeypatch):
    db = FakeDB(
        spotify_tokens=[{"user_id": "a", "refresh_token": "revoked"}, {"user_id": "b", "refresh_token": "ok"}],
        profiles=[
            {"id": "a", "spotify_id": "alice", "display_name": "Alice", "joined_at": "1"},
            {"id": "b", "spotify_id": "bob", "display_name": "Bob", "joined_at": "2"},
        ],
        preferences=[],
        mix_runs=[],
    )

    def fake_client(client_id, secret, refresh_token, **_):
        if refresh_token == "revoked":
            raise AuthError("invalid_grant", 400)
        return FakeSpotify(NOW)

    for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.setenv(key, "x")
    monkeypatch.setattr(cli, "Supabase", lambda url, key: db)
    monkeypatch.setattr(cli, "Spotify", fake_client)
    monkeypatch.setattr(cli, "configure", lambda client, cfg: client)
    pauses = []

    code = cli.run_all_users(lambda: cfg_for(tmp_path, PLAYLIST_SIZE=10), sleep=pauses.append)

    assert code == 1  # Alice failed, so the job reports failure
    assert [r["user_id"] for r in db.tables["mix_runs"]] == ["b"]  # but Bob still got his mix
    assert pauses == [30]


def test_all_users_can_target_one_user(tmp_path, monkeypatch):
    db = FakeDB(
        spotify_tokens=[{"user_id": "a", "refresh_token": "ra"}, {"user_id": "b", "refresh_token": "rb"}],
        profiles=[
            {"id": "a", "spotify_id": "alice", "display_name": "Alice", "joined_at": "1"},
            {"id": "b", "spotify_id": "bob", "display_name": "Bob", "joined_at": "2"},
        ],
        preferences=[],
        mix_runs=[],
    )
    for key in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY"):
        monkeypatch.setenv(key, "x")
    monkeypatch.setattr(cli, "Supabase", lambda url, key: db)
    monkeypatch.setattr(cli, "Spotify", lambda *a, **k: FakeSpotify(NOW))
    monkeypatch.setattr(cli, "configure", lambda client, cfg: client)

    assert cli.run_all_users(lambda: cfg_for(tmp_path, PLAYLIST_SIZE=10), only="bob", sleep=lambda s: None) == 0
    assert [r["user_id"] for r in db.tables["mix_runs"]] == ["b"]
