"""python -m eclectolog [--all-users [--user SPOTIFY_ID]] [--dry-run] [--size N] [--seed N] [--config PATH] [-v]

Without --all-users: one mix for the account in SPOTIFY_REFRESH_TOKEN, history in a local file.
With --all-users: one mix for everyone who joined through the web app, read from Supabase.
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from . import report
from .config import ConfigError, load_config
from .db import DatabaseError, Member, Supabase, SupabaseHistory, load_members, save_refresh_token
from .engine import RunResult, run
from .spotify import AuthError, Spotify, SpotifyError

log = logging.getLogger("eclectolog")


def load_dotenv(path: Path) -> None:
    """Tiny .env reader for local runs; real env vars win."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        m = re.match(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$", line)
        if m and not line.lstrip().startswith("#"):
            os.environ.setdefault(m.group(1), m.group(2).strip("'\""))


def handle_rotated_token(token: str) -> None:
    """Single-user mode: Spotify occasionally issues a new refresh token, so keep .env current."""
    env = Path(".env")
    if env.is_file() and "SPOTIFY_REFRESH_TOKEN" in env.read_text():
        env.write_text(re.sub(r"(?m)^(\s*(?:export\s+)?SPOTIFY_REFRESH_TOKEN\s*=).*$", lambda m: m.group(1) + token, env.read_text()))
        log.warning("Spotify rotated the refresh token; updated .env")
    else:
        log.warning("Spotify rotated the refresh token; re-run scripts/get_refresh_token.py to save the new one")


def configure(client: Spotify, cfg: dict) -> Spotify:
    client.max_reads = cfg["api"]["max_reads"]
    client.default_pace = cfg["api"]["pace_seconds"]
    client.pace["/search"] = cfg["api"]["search_pace_seconds"]
    return client


def explain(exc: SpotifyError) -> str:
    hint = ""
    if exc.status == 403:
        hint = (" (403: in Development Mode the account must be added under User Management in the Spotify "
                "dashboard, and the app owner needs Premium.)")
    return f"Spotify API error: {exc}{hint}"


def write_summary(markdown: str) -> None:
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a", encoding="utf-8") as fh:
            fh.write(markdown)


def run_single(cfg: dict) -> int:
    creds = {k: os.environ.get(k, "").strip() for k in ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SPOTIFY_REFRESH_TOKEN")}
    missing = [k for k, v in creds.items() if not v]
    if missing:
        log.error("Missing %s. See README → Running locally (put them in .env).", ", ".join(missing))
        return 2

    client = configure(Spotify(*creds.values(), on_token_rotated=handle_rotated_token), cfg)
    try:
        result = run(client, cfg, random.Random(cfg["seed"]), datetime.now(timezone.utc))
    except AuthError as exc:
        log.error("%s", exc)
        return 1
    except SpotifyError as exc:
        log.error("%s", explain(exc))
        return 1

    print(report.console(result))
    write_summary(report.markdown(result))
    if not result.picks:
        log.error("No tracks found; try a larger search_depth, more mix sources, or add songs to the Compass")
        return 1
    return 0


def run_member(member: Member, cfg: dict, db: Supabase, client_id: str, client_secret: str,
               blocked_until: dict[str, float]) -> RunResult:
    if member.mix:
        cfg["mix"] = member.mix  # web-app preferences; Compass directives can still override them
    client = configure(Spotify(
        client_id, client_secret, member.refresh_token,
        on_token_rotated=lambda token: save_refresh_token(db, member.user_id, token),
        blocked_until=blocked_until,
    ), cfg)
    served = SupabaseHistory.load_for(db, member.user_id)
    return run(client, cfg, random.Random(cfg["seed"]), datetime.now(timezone.utc), served=served)


def run_all_users(load_cfg, only: str | None = None, sleep=time.sleep) -> int:
    env = {k: os.environ.get(k, "").strip() for k in
           ("SPOTIFY_CLIENT_ID", "SPOTIFY_CLIENT_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY")}
    missing = [k for k, v in env.items() if not v]
    if missing:
        log.error("Missing %s for --all-users.", ", ".join(missing))
        return 2

    db = Supabase(env["SUPABASE_URL"], env["SUPABASE_SERVICE_ROLE_KEY"])
    try:
        members = load_members(db)
    except DatabaseError as exc:
        log.error("Couldn't load users from Supabase: %s", exc)
        return 1
    if only:
        members = [m for m in members if m.spotify_id == only]
    if not members:
        log.error("No users to build mixes for%s.", f" (no one with Spotify ID {only!r})" if only else "")
        return 1

    blocked_until: dict[str, float] = {}  # shared: Spotify rate limits apply to the whole app
    failed = 0
    for i, member in enumerate(members):
        cfg = load_cfg()
        if i:
            sleep(cfg["api"]["user_pause_seconds"])
        log.info("Building a mix for %s (%d/%d)", member.name, i + 1, len(members))
        try:
            result = run_member(member, cfg, db, env["SPOTIFY_CLIENT_ID"], env["SPOTIFY_CLIENT_SECRET"], blocked_until)
        except AuthError as exc:
            failed += 1
            log.error("%s: Spotify sign-in failed; they may need to join again from the web app. %s", member.name, exc)
            continue
        except SpotifyError as exc:
            failed += 1
            log.error("%s: %s", member.name, explain(exc))
            continue
        except DatabaseError as exc:
            failed += 1
            log.error("%s: Supabase error: %s", member.name, exc)
            continue

        print(f"\n=== {member.name} ===\n{report.console(result)}")
        write_summary(f"\n# {member.name}\n\n{report.markdown(result)}")
        if not result.picks:
            failed += 1
            log.error("%s: no tracks found", member.name)

    log.info("Done: %d of %d mixes built", len(members) - failed, len(members))
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="eclectolog", description="Build an eclectic Spotify playlist from your listening.")
    parser.add_argument("--all-users", action="store_true", help="build a mix for every user stored in Supabase")
    parser.add_argument("--user", metavar="SPOTIFY_ID", help="with --all-users, only build this user's mix")
    parser.add_argument("--dry-run", action="store_true", default=None, help="print the playlist without touching Spotify")
    parser.add_argument("--size", type=int, help="number of tracks")
    parser.add_argument("--seed", type=int, help="random seed for a reproducible mix")
    parser.add_argument("--config", help="path to config.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    load_dotenv(Path(".env"))

    def load_cfg() -> dict:
        return load_config(args.config, cli_overrides={"dry_run": args.dry_run, "playlist.size": args.size, "seed": args.seed})

    try:
        cfg = load_cfg()
    except ConfigError as exc:
        log.error("Config error: %s", exc)
        return 2

    if args.all_users:
        return run_all_users(load_cfg, only=args.user)
    if args.user:
        log.error("--user only works with --all-users")
        return 2
    return run_single(cfg)


if __name__ == "__main__":
    sys.exit(main())
