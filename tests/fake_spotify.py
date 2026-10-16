"""In-memory stand-in for the Spotify client, shaped like the post-Feb-2026 API."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone


def track(tid, name, artists, album="Album"):
    return {
        "type": "track", "id": tid, "uri": f"spotify:track:{tid}", "name": name,
        "artists": [{"id": a, "name": n} for a, n in artists], "album": {"id": f"{artists[0][0]}-known", "name": album},
    }


HOME_ARTISTS = {
    "a1": ("Heavy Rotation", ["indie rock"]),
    "a2": ("Old Love", ["bossa nova"]),
    "a3": ("Jazz Person", ["spiritual jazz", "free jazz"]),
    "a4": ("No Genres", []),
}


class FakeSpotify:
    def __init__(self, now: datetime, playlists=None, saved_ids=()):
        self.now = now
        self.calls = 0
        self.search_calls = 0
        self.album_list_calls = 0
        self.log: list[tuple[str, str, object]] = []
        self.playlists = playlists or {}  # id -> {"name","description","tracks":[track objs]}
        self.saved_ids = set(saved_ids)
        self._next_id = 0
        self.catalog: dict[str, dict] = {}  # exact-match queries (isrc:/track:) -> track object; see FakeDeezer

    # --- routing -----------------------------------------------------------------------
    def get(self, path, params=None):
        self.calls += 1
        params = params or {}
        if path == "/me":
            return {"id": "me"}
        if path == "/me/player/recently-played":
            items = []
            for i in range(20):  # 20 plays of a1 in the last day, one old play of a2
                items.append({"track": track(f"r{i}", f"Recent {i}", [("a1", "Heavy Rotation")]),
                              "played_at": (self.now - timedelta(hours=i)).isoformat().replace("+00:00", "Z")})
            items.append({"track": track("old", "Old Song", [("a2", "Old Love")]),
                          "played_at": (self.now - timedelta(days=40)).isoformat().replace("+00:00", "Z")})
            return {"items": items}
        if path == "/me/library/contains":
            return [u.split(":")[-1] in self.saved_ids for u in params["uris"].split(",")]
        if path.startswith("/artists/") and path.endswith("/albums"):
            self.album_list_calls += 1
            aid = path.split("/")[2]
            return {"items": [{"id": f"{aid}-alb{i}", "name": f"{aid} album {i}"} for i in range(3)]}
        if path.startswith("/albums/"):
            alb = path.split("/")[2]
            aid = alb.split("-")[0]
            name = HOME_ARTISTS.get(aid, (aid, []))[0]
            return {"items": [track(f"{alb}-t{i}", f"{alb} song {i}", [(aid, name)]) | {"album": None} for i in range(8)]}
        if path.startswith("/artists/"):
            aid = path.split("/")[2]
            name, genres = HOME_ARTISTS.get(aid, (aid, ["unknown"]))
            return {"id": aid, "name": name, "genres": genres}
        if path == "/search":
            self.search_calls += 1
            return self._search(params)
        raise AssertionError(f"unexpected GET {path}")

    def post(self, path, json=None):
        self.calls += 1
        self.log.append(("POST", path, json))
        if path == "/me/playlists":
            self._next_id += 1
            pid = f"pl{self._next_id}"
            self.playlists[pid] = {"name": json["name"], "description": json.get("description", ""), "tracks": []}
            return {"id": pid, "name": json["name"], "external_urls": {"spotify": f"https://open.spotify.com/playlist/{pid}"}}
        if path.endswith("/items"):
            pid = path.split("/")[2]
            self.playlists[pid]["tracks"] += [{"id": u.split(":")[-1]} for u in json["uris"]]
            return {"snapshot_id": "x"}
        raise AssertionError(f"unexpected POST {path}")

    def put(self, path, json=None):
        self.calls += 1
        self.log.append(("PUT", path, json))
        pid = path.split("/")[2]
        if path.endswith("/items"):
            self.playlists[pid]["tracks"] = [{"id": u.split(":")[-1]} for u in json["uris"]]
        return {}

    def request(self, method, path, *, params=None, json=None, data=None, content_type=None):
        """Only cover uploads come through here; set `cover_error` to simulate a failure."""
        self.calls += 1
        self.log.append((method, path, content_type))
        if getattr(self, "cover_error", None):
            raise self.cover_error
        self.playlists[path.split("/")[2]]["cover"] = data
        return {}

    def paginate(self, path, params=None, max_items=None):
        items = self._collection(path, params or {})
        return iter(items[:max_items] if max_items else items)

    # --- data ----------------------------------------------------------------------------
    def _collection(self, path, params):
        if path == "/me/top/tracks":
            return [track(f"top-{params['time_range']}-{i}", f"Top {i}", [("a3", "Jazz Person")]) for i in range(5)] + \
                   [track(f"top4-{params['time_range']}", "Genre-less", [("a4", "No Genres")])]
        if path == "/me/top/artists":
            return [{"id": "a2", "name": "Old Love", "genres": ["bossa nova"]}]
        if path == "/me/tracks":
            return [{"track": track("saved1", "Saved", [("a2", "Old Love")])}]
        if path == "/me/playlists":
            return [{"id": pid, "name": p["name"], "description": p["description"], "owner": {"id": "me"},
                     "items": {"total": len(p["tracks"])}} for pid, p in self.playlists.items()]
        if path.startswith("/playlists/") and path.endswith("/items"):
            pid = path.split("/")[2]
            tracks = self.playlists[pid]["tracks"][params.get("offset", 0):]
            return [{"item": t if "type" in t else track(t["id"], t["id"], [("x" + t["id"], "X")])} for t in tracks]
        raise AssertionError(f"unexpected paginate {path}")

    def _search(self, params):
        q, offset = params["q"], int(params.get("offset", 0))
        if params["type"] == "artist":
            return {"artists": {"items": [{"id": "int1", "name": params["q"], "genres": ["krautrock"]}]}}
        if q.startswith("isrc:") or q.startswith("track:"):
            hit = self.catalog.get(q)
            return {"tracks": {"total": int(bool(hit)), "items": [hit] if hit else []}}
        if "nonexistent" in q:
            return {"tracks": {"total": 0, "items": []}}
        total = 200
        if offset >= total:
            return {"tracks": {"total": total, "items": []}}
        items = []
        for i in range(10):
            h = hashlib.md5(f"{q}|{offset + i}".encode()).hexdigest()[:8]
            items.append(track(f"s{h}", f"Song {h}", [(f"new{h}", f"Artist {h}")]))
        return {"tracks": {"total": total, "items": items}}


class FakeDeezer:
    """Each artist relates to six "Near <name> <i>" artists with i*500 fans; Old Love is also near Heavy Rotation.

    Registers every track it hands out in the FakeSpotify catalog so ISRC searches resolve.
    """

    def __init__(self, spotify: FakeSpotify, fail: bool = False):
        self.spotify = spotify
        self.fail = fail
        self.calls = 0
        self.ids: dict[int, str] = {}

    def _artist(self, name):
        from eclectolog.deezer import DeezerArtist
        aid = int(hashlib.md5(name.encode()).hexdigest()[:8], 16)
        self.ids[aid] = name
        fans = int(name.rsplit(" ", 1)[-1]) * 500 if name.startswith("Near") else 50_000
        return DeezerArtist(aid, name, fans)

    def _call(self):
        from eclectolog.deezer import DeezerError
        self.calls += 1
        if self.fail:
            raise DeezerError("GET /search/artist: connection refused")

    def find_artist(self, name):
        self._call()
        return self._artist(name)

    def related(self, artist_id):
        self._call()
        name = self.ids[artist_id]
        out = [self._artist(f"Near {name} {i}") for i in range(6)]
        return out + ([self._artist("Old Love")] if name == "Heavy Rotation" else [])

    def top_tracks(self, artist_id, limit=10):
        from eclectolog.deezer import DeezerTrack
        self._call()
        name = self.ids[artist_id]
        return [DeezerTrack(artist_id * 10 + k, f"{name} hit {k}", name) for k in range(min(limit, 3))]

    def isrc(self, track_id):
        self._call()
        artist = self.ids[track_id // 10]
        slug = hashlib.md5(artist.encode()).hexdigest()[:8]
        self.spotify.catalog[f"isrc:DZ{track_id}"] = track(f"dz{track_id}", f"{artist} hit {track_id % 10}", [(f"sp{slug}", artist)])
        return f"DZ{track_id}"
