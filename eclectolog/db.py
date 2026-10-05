"""Supabase access for the multi-user job: who has joined, their tokens and mix, and served history.

Talks to Supabase's REST API (PostgREST) directly with the service-role key, which bypasses
row-level security. Tables are defined in supabase/migrations/.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import requests

from .history import ServedHistory

log = logging.getLogger(__name__)

MIX_KEYS = ("deep_cuts", "genre_neighbors", "wildcard", "compass")


class DatabaseError(RuntimeError):
    pass


class Supabase:
    def __init__(self, url: str, key: str, session: requests.Session | None = None):
        self.base = url.rstrip("/") + "/rest/v1"
        self.session = session or requests.Session()
        self.session.headers["apikey"] = key
        # Legacy service_role keys are JWTs and go in Authorization too; new sb_secret_ keys only use apikey.
        if key.startswith("eyJ"):
            self.session.headers["Authorization"] = f"Bearer {key}"

    def _call(self, method: str, table: str, params: dict | None = None, json: Any = None, prefer: str | None = None) -> Any:
        headers = {"Prefer": prefer} if prefer else {}
        resp = self.session.request(method, f"{self.base}/{table}", params=params, json=json, headers=headers, timeout=30)
        if resp.status_code >= 400:
            raise DatabaseError(f"{method} {table} -> {resp.status_code}: {resp.text[:300]}")
        return resp.json() if resp.content else None

    def select(self, table: str, params: dict) -> list[dict]:
        return self._call("GET", table, params=params) or []

    def insert(self, table: str, rows: list[dict] | dict) -> None:
        self._call("POST", table, json=rows, prefer="return=minimal")

    def update(self, table: str, filters: dict, values: dict) -> None:
        self._call("PATCH", table, params=filters, json=values, prefer="return=minimal")

    def delete(self, table: str, filters: dict) -> None:
        self._call("DELETE", table, params=filters, prefer="return=minimal")


@dataclass
class Member:
    user_id: str
    spotify_id: str
    name: str
    refresh_token: str
    mix: dict[str, float] | None  # fractions summing to 1, or None to use the config's mix


def load_members(db: Supabase) -> list[Member]:
    """Everyone with a stored Spotify token, oldest member first."""
    tokens = db.select("spotify_tokens", {"select": "user_id,refresh_token"})
    profiles = {p["id"]: p for p in db.select("profiles", {"select": "id,spotify_id,display_name,joined_at"})}
    prefs = {p["user_id"]: p for p in db.select("preferences", {"select": "user_id," + ",".join(MIX_KEYS)})}

    members = []
    for row in tokens:
        uid = row["user_id"]
        profile = profiles.get(uid)
        if not profile:
            log.warning("Skipping user %s: has a token but no profile", uid)
            continue
        pref = prefs.get(uid)
        members.append(Member(
            user_id=uid,
            spotify_id=profile["spotify_id"],
            name=profile.get("display_name") or profile["spotify_id"],
            refresh_token=row["refresh_token"],
            mix={k: pref[k] / 100 for k in MIX_KEYS} if pref else None,
        ))
    members.sort(key=lambda m: profiles[m.user_id].get("joined_at") or "")
    return members


def save_refresh_token(db: Supabase, user_id: str, token: str) -> None:
    db.update("spotify_tokens", {"user_id": f"eq.{user_id}"}, {"refresh_token": token})


class SupabaseHistory(ServedHistory):
    """Served history for one user, stored as one public.mix_runs row per run."""

    def __init__(self, db: Supabase, user_id: str, runs: list[dict]):
        super().__init__(None, runs)
        self.db = db
        self.user_id = user_id
        self._saved = len(runs)
        self._keep_days = 0
        self._now: datetime | None = None

    @classmethod
    def load_for(cls, db: Supabase, user_id: str) -> SupabaseHistory:
        rows = db.select("mix_runs", {
            "select": "ran_at,playlist_name,playlist_url,tracks",
            "user_id": f"eq.{user_id}",
            "order": "ran_at.asc",
        })
        runs = [{"at": r["ran_at"], "playlist": r["playlist_name"], "url": r.get("playlist_url"),
                 "tracks": r.get("tracks") or []} for r in rows]
        return cls(db, user_id, runs)

    def add_run(self, when: datetime, playlist: str, picks, keep_days: int, url: str | None = None) -> None:
        # Pruning happens in save() with a DELETE, so skip the base class's in-memory trim.
        super().add_run(when, playlist, picks, keep_days=0, url=url)
        self._keep_days, self._now = keep_days, when

    def save(self) -> None:
        new = self.runs[self._saved:]
        if new:
            self.db.insert("mix_runs", [
                {"user_id": self.user_id, "ran_at": r["at"], "playlist_name": r["playlist"],
                 "playlist_url": r.get("url"), "tracks": r["tracks"]}
                for r in new
            ])
            self._saved = len(self.runs)
        if self._keep_days > 0 and self._now is not None:
            cutoff = (self._now - timedelta(days=self._keep_days)).isoformat(timespec="seconds")
            self.db.delete("mix_runs", {"user_id": f"eq.{self.user_id}", "ran_at": f"lt.{cutoff}"})
