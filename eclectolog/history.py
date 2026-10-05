"""Served-track history kept as a JSON Lines file (one run per line) instead of a Spotify playlist.

In GitHub Actions the workflow keeps this file on a separate `eclectolog-state` branch, so it
survives between runs without costing Spotify API calls. Locally it's just a file (state/ is gitignored).
Roughly 5 KB per 40-track run, so a year of daily runs is ~2 MB; each run's commit appends one line.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

from .models import Candidate, Track

log = logging.getLogger(__name__)


class ServedHistory:
    def __init__(self, path: Path, runs: list[dict] | None = None):
        self.path = path
        self.runs = runs or []

    @classmethod
    def load(cls, path: str | Path) -> ServedHistory:
        path = Path(path)
        if not path.is_file():
            return cls(path)
        try:
            return cls(path, [json.loads(line) for line in path.read_text().splitlines() if line.strip()])
        except json.JSONDecodeError as exc:
            # Don't let a corrupt file block the playlist; start over but keep the old file around.
            backup = path.with_suffix(".corrupt")
            path.replace(backup)
            log.warning("History file was unreadable (%s); moved it to %s and starting fresh", exc, backup)
            return cls(path)

    def tracks(self, run: dict) -> list[Track]:
        out = []
        for t in run.get("tracks") or []:
            artists = tuple((a[0], a[1]) for a in t.get("artists") or [] if len(a) == 2)
            if t.get("id") and artists:
                out.append(Track(t["id"], f"spotify:track:{t['id']}", t.get("name", "?"), artists, t.get("album", "")))
        return out

    def all_tracks(self) -> list[Track]:
        return [t for run in self.runs for t in self.tracks(run)]

    def last_tracks(self) -> list[Track]:
        return self.tracks(self.runs[-1]) if self.runs else []

    def add_run(self, when: datetime, playlist: str, picks: list[Candidate], keep_days: int) -> None:
        self.runs.append({
            "at": when.isoformat(timespec="seconds"),
            "playlist": playlist,
            "tracks": [
                {"id": c.track.id, "name": c.track.name, "artists": [list(a) for a in c.track.artists],
                 "album": c.track.album, "source": c.source}
                for c in picks
            ],
        })
        if keep_days > 0:
            cutoff = when - timedelta(days=keep_days)
            self.runs = [r for r in self.runs if datetime.fromisoformat(r["at"]) >= cutoff]

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text("".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) + "\n" for r in self.runs))
        tmp.replace(self.path)
