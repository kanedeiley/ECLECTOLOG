"""Layered configuration.

Precedence (lowest -> highest):
  1. DEFAULTS below
  2. config.yaml                      (repo file, or ECLECTOLOG_CONFIG_FILE)
  3. ECLECTOLOG_CONFIG_YAML           (a whole YAML blob in one GitHub variable)
  4. interests.yaml                   (or ECLECTOLOG_INTERESTS_FILE) + ECLECTOLOG_INTERESTS_YAML
  5. ECLECTOLOG_* env vars / GitHub repo variables (see ENV_OPTIONS)
  6. CLI flags
  7. Directives typed into the Compass playlist description on Spotify (applied at run time)
"""
from __future__ import annotations

import copy
import html
import json
import os
import re
from pathlib import Path
from typing import Any, Callable

import yaml

SOURCES = ("deep_cuts", "genre_neighbors", "wildcard", "compass")

DEFAULTS: dict[str, Any] = {
    "playlist": {
        "name": "Eclectolog",
        "mode": "replace",  # replace = one rolling playlist; new = a fresh dated playlist each run
        "size": 40,
        "public": False,
        "date_format": "%Y-%m-%d",
        "covers": True,  # put the cover art from eclectolog/covers/ on playlists that still have Spotify's default
    },
    "history": {
        "recent_weight": 1.0,  # base weight of each of your last 50 plays
        "recency_boost": 0.35,  # a play from just now counts (1 + boost)x; decays toward 1x
        "recency_half_life_hours": 72,
        "top_terms": {"short_term": 1.0, "medium_term": 1.0, "long_term": 1.0},
        "top_limit": 50,
        "saved_tracks": 100,  # how many Liked Songs to sample (0 disables)
        "saved_weight": 0.5,
        "temperature": 0.6,  # <1 flattens artist/genre weights so no single taste dominates
        "genre_lookups": 10,  # max artist lookups to discover genres (one call each)
    },
    "mix": {"deep_cuts": 0.25, "genre_neighbors": 0.35, "wildcard": 0.2, "compass": 0.2},
    "diversity": {
        "max_per_artist": 1,
        "max_per_genre": 4,
        "search_depth": 300,  # how far down search results to dig (max 1000); deeper = less mainstream
        "min_offset": 50,  # always skip this many top results (the most popular) when a search has that many
        "novel_artists_only": True,  # genre_neighbors/wildcard only pick artists absent from your history
        "search_budget": 40,  # max search calls per run; Spotify bans apps that search too much
        "discography_chance": 0.3,  # deep cuts: chance to browse the artist's releases vs. albums you've played
        "collaborator_chance": 0.35,  # neighbors/compass: chance to hop to an artist who's worked with a seed
        "skip_compilations": True,  # "Greatest Hits" and other compilations are mainstream by construction
    },
    "wildcard": {
        "use_builtin_genres": True,
        "genres": [],
        "era_chance": 0.35,
        "eras": ["1950-1959", "1960-1969", "1970-1979", "1980-1989", "1990-1999", "2000-2009", "2010-2019", "2020-2029"],
        "keyword_chance": 0.25,
    },
    "reference": {
        "enabled": True,
        "create_if_missing": True,
        "compass_playlist": "Eclectolog · Compass",
        "avoid_playlist": "Eclectolog · Avoid",
        "archive_playlist": "",  # optional: also log served tracks to a Spotify playlist (costs API calls)
        "archive_lookback": 1000,
        "liked_feedback_boost": 1.5,
        "directive_genre_weight": 2.0,
    },
    "interests": {
        "genres": {},  # name -> weight
        "artists": [],
        "eras": [],
        "keywords": [],
        "avoid": {"genres": [], "artists": []},
    },
    "api": {
        "max_reads": 300,  # hard cap on GET requests per run (playlist writes are exempt)
        "pace_seconds": 0.15,  # min gap between requests; bursts get apps banned for ~24h
        "search_pace_seconds": 0.5,
        "user_pause_seconds": 30,  # multi-user job: rest between users so bursts don't stack up
    },
    "interests_file": "interests.yaml",
    "state": {
        "file": "state/history.jsonl",  # served-track history for single-user runs (--all-users uses Supabase)
        "keep_days": 730,  # forget runs older than this (0 = keep forever)
    },
    "market": "from_token",
    "seed": None,
    "dry_run": False,
}


class ConfigError(ValueError):
    pass


def _bool(v: str) -> bool:
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "on", "y"):
        return True
    if s in ("0", "false", "no", "off", "n", ""):
        return False
    raise ConfigError(f"Expected a boolean, got {v!r}")


def _list(v: str | list) -> list[str]:
    if isinstance(v, list):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[,\n]", str(v)) if x.strip()]


def _mix(v: str) -> dict[str, float]:
    """"deep_cuts=0.3, wildcard=0.2" -> partial mix dict."""
    out: dict[str, float] = {}
    for part in _list(v):
        if "=" not in part:
            raise ConfigError(f"ECLECTOLOG_MIX entries look like source=weight, got {part!r}")
        k, val = (x.strip() for x in part.split("=", 1))
        if k not in SOURCES:
            raise ConfigError(f"Unknown mix source {k!r}; choose from {', '.join(SOURCES)}")
        out[k] = float(val)
    return out


def _optional_int(v: str) -> int | None:
    return None if str(v).strip().lower() in ("", "none", "random") else int(v)


# ECLECTOLOG_<NAME> -> (dotted config path, parser, append?)
ENV_OPTIONS: dict[str, tuple[str, Callable[[Any], Any], bool]] = {
    "PLAYLIST_NAME": ("playlist.name", str, False),
    "PLAYLIST_MODE": ("playlist.mode", str, False),
    "PLAYLIST_SIZE": ("playlist.size", int, False),
    "PLAYLIST_PUBLIC": ("playlist.public", _bool, False),
    "PLAYLIST_COVERS": ("playlist.covers", _bool, False),
    "RECENCY_BOOST": ("history.recency_boost", float, False),
    "RECENCY_HALF_LIFE_HOURS": ("history.recency_half_life_hours", float, False),
    "TEMPERATURE": ("history.temperature", float, False),
    "SAVED_TRACKS": ("history.saved_tracks", int, False),
    "MIX": ("mix", _mix, False),
    "MAX_PER_ARTIST": ("diversity.max_per_artist", int, False),
    "MAX_PER_GENRE": ("diversity.max_per_genre", int, False),
    "SEARCH_DEPTH": ("diversity.search_depth", int, False),
    "NOVEL_ARTISTS_ONLY": ("diversity.novel_artists_only", _bool, False),
    "SEARCH_BUDGET": ("diversity.search_budget", int, False),
    "MIN_OFFSET": ("diversity.min_offset", int, False),
    "DISCOGRAPHY_CHANCE": ("diversity.discography_chance", float, False),
    "COLLABORATOR_CHANCE": ("diversity.collaborator_chance", float, False),
    "SKIP_COMPILATIONS": ("diversity.skip_compilations", _bool, False),
    "MAX_API_READS": ("api.max_reads", int, False),
    "WILDCARD_GENRES": ("wildcard.genres", _list, True),
    "ERA_CHANCE": ("wildcard.era_chance", float, False),
    "EXTRA_GENRES": ("interests.genres", _list, True),
    "EXTRA_ARTISTS": ("interests.artists", _list, True),
    "ERAS": ("interests.eras", _list, False),
    "KEYWORDS": ("interests.keywords", _list, True),
    "AVOID_GENRES": ("interests.avoid.genres", _list, True),
    "AVOID_ARTISTS": ("interests.avoid.artists", _list, True),
    "REFERENCE_PLAYLISTS": ("reference.enabled", _bool, False),
    "CREATE_REFERENCE_PLAYLISTS": ("reference.create_if_missing", _bool, False),
    "COMPASS_PLAYLIST": ("reference.compass_playlist", str, False),
    "AVOID_PLAYLIST": ("reference.avoid_playlist", str, False),
    "ARCHIVE_PLAYLIST": ("reference.archive_playlist", str, False),
    "MARKET": ("market", str, False),
    "STATE_FILE": ("state.file", str, False),
    "STATE_KEEP_DAYS": ("state.keep_days", int, False),
    "SEED": ("seed", _optional_int, False),
    "DRY_RUN": ("dry_run", _bool, False),
}


def deep_merge(base: dict, override: dict) -> dict:
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            deep_merge(base[k], v)
        else:
            base[k] = copy.deepcopy(v)
    return base


def _set_path(cfg: dict, dotted: str, value: Any, append: bool) -> None:
    *parents, leaf = dotted.split(".")
    node = cfg
    for p in parents:
        node = node.setdefault(p, {})
    if isinstance(value, dict) and isinstance(node.get(leaf), dict):
        node[leaf].update(value)
    elif append and isinstance(node.get(leaf), dict):  # e.g. interests.genres is name -> weight
        for item in value:
            node[leaf].setdefault(item, 1.0)
    elif append and isinstance(node.get(leaf), list):
        node[leaf] = node[leaf] + [x for x in value if x not in node[leaf]]
    else:
        node[leaf] = value


class EnvSource:
    """Reads ECLECTOLOG_* from real env vars, falling back to a JSON dump of GitHub repo variables.

    The workflow passes `toJSON(vars)` so any repo variable you add flows through without
    editing the workflow file. Empty strings count as unset.
    """

    def __init__(self, environ: dict[str, str] | None = None):
        self.environ = os.environ if environ is None else environ
        try:
            self.vars = json.loads(self.environ.get("ECLECTOLOG_VARS_JSON") or "{}") or {}
        except json.JSONDecodeError:
            self.vars = {}

    def get(self, name: str) -> str | None:
        for source in (self.environ, self.vars):
            v = source.get(name)
            if v is not None and str(v).strip() != "":
                return str(v)
        return None


def _load_yaml_file(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text()) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"{path} must contain a YAML mapping")
    return data


def _load_yaml_text(text: str | None, what: str) -> dict:
    if not text:
        return {}
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"{what} is not valid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ConfigError(f"{what} must be a YAML mapping")
    return data


def normalize_interests(raw: dict) -> dict:
    """Accept friendly shapes (lists or name->weight maps) and return the canonical structure."""
    raw = raw or {}
    genres = raw.get("genres") or {}
    if isinstance(genres, list):
        genres = {str(g): 1.0 for g in genres}
    avoid = raw.get("avoid") or {}
    return {
        "genres": {str(k).strip().lower(): float(v if v is not None else 1.0) for k, v in genres.items() if str(k).strip()},
        "artists": _list(raw.get("artists") or []),
        "eras": _list(raw.get("eras") or []),
        "keywords": _list(raw.get("keywords") or []),
        "avoid": {
            "genres": [g.lower() for g in _list(avoid.get("genres") or [])],
            "artists": _list(avoid.get("artists") or []),
        },
    }


def load_config(
    config_file: str | Path | None = None,
    environ: dict[str, str] | None = None,
    cli_overrides: dict[str, Any] | None = None,
    base_dir: Path | None = None,
) -> dict:
    env = EnvSource(environ)
    base_dir = base_dir or Path.cwd()
    cfg = copy.deepcopy(DEFAULTS)

    path = Path(config_file or env.get("ECLECTOLOG_CONFIG_FILE") or base_dir / "config.yaml")
    deep_merge(cfg, _load_yaml_file(path))
    deep_merge(cfg, _load_yaml_text(env.get("ECLECTOLOG_CONFIG_YAML"), "ECLECTOLOG_CONFIG_YAML"))

    interests_path = Path(env.get("ECLECTOLOG_INTERESTS_FILE") or cfg.get("interests_file") or "interests.yaml")
    if not interests_path.is_absolute():
        interests_path = base_dir / interests_path
    merged = normalize_interests(cfg.get("interests"))
    for layer in (_load_yaml_file(interests_path), _load_yaml_text(env.get("ECLECTOLOG_INTERESTS_YAML"), "ECLECTOLOG_INTERESTS_YAML")):
        layer = normalize_interests(layer)
        merged["genres"].update(layer["genres"])
        for key in ("artists", "keywords"):
            merged[key] += [x for x in layer[key] if x not in merged[key]]
        merged["eras"] = layer["eras"] or merged["eras"]
        for key in ("genres", "artists"):
            merged["avoid"][key] += [x for x in layer["avoid"][key] if x not in merged["avoid"][key]]
    cfg["interests"] = merged

    for name, (dotted, parse, append) in ENV_OPTIONS.items():
        raw = env.get(f"ECLECTOLOG_{name}")
        if raw is None:
            continue
        try:
            value = parse(raw)
        except (ValueError, TypeError) as exc:
            raise ConfigError(f"ECLECTOLOG_{name}={raw!r}: {exc}") from exc
        if dotted.startswith("interests.genres"):
            value = [v.lower() for v in value]
        _set_path(cfg, dotted, value, append)

    for dotted, value in (cli_overrides or {}).items():
        if value is not None:
            _set_path(cfg, dotted, value, False)

    validate(cfg)
    return cfg


def validate(cfg: dict) -> None:
    p, h, d, m = cfg["playlist"], cfg["history"], cfg["diversity"], cfg["mix"]
    if p["mode"] not in ("replace", "new"):
        raise ConfigError("playlist.mode must be 'replace' or 'new'")
    if not 1 <= int(p["size"]) <= 500:
        raise ConfigError("playlist.size must be between 1 and 500")
    if not 0 < float(h["temperature"]) <= 2:
        raise ConfigError("history.temperature must be in (0, 2]; 1 = raw weights, lower = flatter")
    if float(h["recency_boost"]) < 0:
        raise ConfigError("history.recency_boost must be >= 0")
    unknown = set(m) - set(SOURCES)
    if unknown:
        raise ConfigError(f"Unknown mix sources: {', '.join(sorted(unknown))}")
    if any(float(v) < 0 for v in m.values()) or sum(float(v) for v in m.values()) <= 0:
        raise ConfigError("mix weights must be >= 0 with at least one > 0")
    if int(d["max_per_artist"]) < 1 or int(d["max_per_genre"]) < 1:
        raise ConfigError("diversity.max_per_artist / max_per_genre must be >= 1")
    if int(d["search_budget"]) < 0:
        raise ConfigError("diversity.search_budget must be >= 0")
    if not 0 <= int(d["search_depth"]) <= 1000:
        raise ConfigError("diversity.search_depth must be between 0 and 1000")
    if not 0 <= int(d["min_offset"]) <= 1000:
        raise ConfigError("diversity.min_offset must be between 0 and 1000")
    if not 0 <= float(d["collaborator_chance"]) <= 1:
        raise ConfigError("diversity.collaborator_chance must be between 0 and 1")
    for era in cfg["interests"]["eras"] + list(cfg["wildcard"]["eras"]):
        parse_era(era)


_ERA = re.compile(r"^(\d{4})s?(?:\s*-\s*(\d{4}))?$")


def parse_era(text: str) -> str:
    """'1970s' -> '1970-1979', '1994' -> '1994', '1965-1979' stays. Spotify's year: filter format."""
    m = _ERA.match(str(text).strip())
    if not m:
        raise ConfigError(f"Can't read era {text!r}; use 1970s, 1994, or 1965-1979")
    lo, hi = m.group(1), m.group(2)
    if hi:
        return f"{lo}-{hi}"
    if str(text).strip().endswith("s"):
        return f"{lo}-{int(lo) + 9}"
    return lo


# --- Compass playlist directives -------------------------------------------------------------

DIRECTIVE_ALIASES = {
    "more": "more", "less": "less", "avoid": "less",
    "era": "era", "eras": "era",
    "size": "size", "keywords": "keywords", "keyword": "keywords",
    "familiar": "deep_cuts", "explore": "genre_neighbors", "wildcard": "wildcard", "compass": "compass",
    "recency": "recency", "temperature": "temperature",
}


def parse_directives(description: str | None) -> dict[str, str]:
    """Parse 'more: bossa nova, dub; less: country; size: 30' out of free text.

    The key is the last word before each ':' so leading prose ("Steer me → more: jazz") is fine.
    Unknown keys and empty values are ignored.
    """
    text = html.unescape(description or "")
    out: dict[str, str] = {}
    for part in re.split(r"[;\n]", text):
        if ":" not in part:
            continue
        left, value = part.split(":", 1)
        m = re.search(r"([a-z_]+)\s*$", left.strip().lower())
        key = DIRECTIVE_ALIASES.get(m.group(1)) if m else None
        if key and value.strip():
            out[key] = value.strip()
    return out


def apply_directives(cfg: dict, directives: dict[str, str]) -> list[str]:
    """Mutate cfg from Compass directives. Returns human-readable notes; bad values are skipped, not fatal."""
    snapshot = copy.deepcopy(cfg)
    notes: list[str] = []
    interests = cfg["interests"]
    for key, value in directives.items():
        try:
            if key == "more":
                for g in _list(value):
                    interests["genres"][g.lower()] = cfg["reference"]["directive_genre_weight"]
            elif key == "less":
                interests["avoid"]["genres"] += [g.lower() for g in _list(value)]
            elif key == "era":
                interests["eras"] = [parse_era(e) for e in _list(value)]
            elif key == "keywords":
                interests["keywords"] += _list(value)
            elif key == "size":
                cfg["playlist"]["size"] = max(1, min(500, int(value)))
            elif key in SOURCES:
                cfg["mix"][key] = max(0.0, float(value))
            elif key == "recency":
                cfg["history"]["recency_boost"] = max(0.0, float(value))
            elif key == "temperature":
                cfg["history"]["temperature"] = max(0.05, min(2.0, float(value)))
            notes.append(f"{key}: {value}")
        except (ValueError, ConfigError) as exc:
            notes.append(f"ignored {key}: {value!r} ({exc})")
    try:
        validate(cfg)
    except ConfigError as exc:
        cfg.clear()
        cfg.update(snapshot)
        return [f"ignored all directives ({exc})"]
    return notes
