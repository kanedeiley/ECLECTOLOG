"""python -m eclectolog [--dry-run] [--size N] [--seed N] [--config PATH] [-v]"""
from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import report
from .config import ConfigError, load_config
from .engine import run
from .spotify import AuthError, Spotify, SpotifyError

log = logging.getLogger("eclectolog")
ROTATED_TOKEN_FILE = "eclectolog_refresh_token"


def load_dotenv(path: Path) -> None:
    """Tiny .env reader for local runs; real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m.group(1), m.group(2).strip("'\""))


def handle_rotated_token(token: str) -> None:
    """Spotify occasionally issues a new refresh token. Save it so the workflow can update the secret."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::add-mask::{token}", flush=True)
        out = Path(os.environ.get("RUNNER_TEMP", ".")) / ROTATED_TOKEN_FILE
        out.write_text(token)
        log.warning("Spotify rotated the refresh token; the workflow will try to update the secret")
        return
    env = Path(".env")
    if env.is_file() and "SPOTIFY_REFRESH_TOKEN" in env.read_text():
        env.write_text(re.sub(r"(?m)^(\s*(?:export\s+)?SPOTIFY_REFRESH_TOKEN\s*=).*$", lambda m: m.group(1) + token, env.read_text()))
        log.warning("Spotify rotated the refresh token; updated .env")
    else:
        log.warning("Spotify rotated the refresh token; re-run scripts/get_refresh_token.py to save the new one")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eclectolog", description="Build an eclectic Spotify playlist from your listening.")
    parser.add_argument("--dry-run", action="store_true", default=None, help="print the playlist without touching Spotify")
    parser.add_argument("--size", type=int, help="number of tracks")
    parser.add_argument("--seed", type=int, help="random seed for a reproducible mix")
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    load_dotenv(Path(".env"))

    try:
        cfg = load_config(args.config, cli_overrides={"dry_run": args.dry_run, "playlist.size": args.size, "seed": args.seed})
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        return 2

    creds = {k: os.environ.get(k, "").strip() for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        log.error("Missing %s. See README → Setup (locally, put them in .env).", ", ".join(missing))
        return 2

    client = Spotify(*creds.values(), on_token_rotated=handle_rotated_token)
    client.max_reads = cfg["api"]["max_reads"]
    client.default_pace = cfg["api"]["pace_seconds"]
    client.pace["/search"] = cfg["api"]["search_pace_seconds"]
    rng = random.Random(cfg["seed"])
    try:
        result = run(client, cfg, rng, datetime.now(timezone.utc))
    except AuthError as exc:
        log.error("%s", exc)
        return 1
    except SpotifyError as exc:
        hint = ""
        if exc.status == 403:
            hint = (" (403: in Development Mode the account must be added under User Management in the Spotify "
                    "dashboard, and the app owner needs Premium.)")
        log.error("Spotify API error: %s%s", exc, hint)
        return 1

    print(report.console(result))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(report.markdown(result))
    if not result.picks:
        log.error("No tracks found; try a larger search_depth, more mix sources, or add songs to the Compass")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
