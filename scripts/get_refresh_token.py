#!/usr/bin/env python3
"""One-time Spotify authorization: prints a refresh token (and can store it as a GitHub secret).

Usage:
    python scripts/get_refresh_token.py                 # prompts for client id/secret
    python scripts/get_refresh_token.py --write-env     # also writes .env for local runs
    python scripts/get_refresh_token.py --set-github-secrets   # uses the gh CLI

Your Spotify app must list the exact redirect URI below under "Redirect URIs"
(default http://127.0.0.1:8888/callback). Spotify no longer accepts "localhost";
use the loopback IP literally.

Standard library only, so it runs before `pip install`.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import http.server
import json
import os
import secrets
import shutil
import ssl
import subprocess
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from pathlib import Path

AUTHORIZE_URL = "https://accounts.spotify.com/authorize"
TOKEN_URL = "https://accounts.spotify.com/api/token"
# Keep in sync with eclectolog/spotify.py
SCOPES = (
    "user-read-recently-played user-top-read user-library-read playlist-read-private "
    "playlist-read-collaborative playlist-modify-private playlist-modify-public ugc-image-upload"
)


def wait_for_code(redirect_uri: str, expected_state: str, timeout: int = 300) -> str:
    parsed = urllib.parse.urlparse(redirect_uri)
    if parsed.hostname not in ("127.0.0.1", "[::1]", "::1"):
        sys.exit(f"Redirect URI host must be 127.0.0.1 for this helper (got {parsed.hostname}).")
    result: dict[str, str] = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            url = urllib.parse.urlparse(self.path)
            if url.path != parsed.path:
                self.send_response(404)
                self.end_headers()
                return
            query = dict(urllib.parse.parse_qsl(url.query))
            if query.get("state") != expected_state:
                result["error"] = "state mismatch (possible CSRF); try again"
            elif "error" in query:
                result["error"] = query["error"]
            else:
                result["code"] = query.get("code", "")
            ok = "code" in result
            body = ("<h2>Eclectolog is authorized ✅</h2><p>You can close this tab and return to the terminal.</p>" if ok
                    else f"<h2>Authorization failed</h2><p>{result.get('error')}</p>")
            self.send_response(200 if ok else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(body.encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer((parsed.hostname.strip("[]"), parsed.port or 80), Handler)
    timer = threading.Timer(timeout, server.shutdown)
    timer.start()
    try:
        server.serve_forever()
    finally:
        timer.cancel()
        server.server_close()
    if "code" not in result:
        sys.exit(f"No authorization code received: {result.get('error', 'timed out')}")
    return result["code"]


def _ssl_context() -> ssl.SSLContext:
    # python.org builds on macOS ship without trusted CAs until "Install Certificates.command" is run;
    # certifi (installed with requirements.txt) sidesteps that.
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def _open(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=30, context=_ssl_context()) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            sys.exit(
                "SSL certificate verification failed. Run this script with the project venv "
                "(.venv/bin/python scripts/get_refresh_token.py) after `pip install -r requirements.txt`, "
                "or run \"Install Certificates.command\" in your /Applications/Python 3.x folder."
            )
        sys.exit(f"Network error talking to Spotify: {exc.reason}")


def exchange(code: str, client_id: str, client_secret: str, redirect_uri: str) -> dict:
    data = urllib.parse.urlencode({"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}).encode()
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    req = urllib.request.Request(TOKEN_URL, data=data, headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"})
    try:
        return _open(req)
    except urllib.error.HTTPError as exc:
        sys.exit(f"Token exchange failed ({exc.code}): {exc.read().decode()[:300]}")


def whoami(access_token: str) -> str:
    req = urllib.request.Request("https://api.spotify.com/v1/me", headers={"Authorization": f"Bearer {access_token}"})
    try:
        me = _open(req)
        return me.get("display_name") or me.get("id", "?")
    except urllib.error.HTTPError as exc:
        return f"(couldn't read profile: HTTP {exc.code}; check User Management in the dashboard)"


def write_env(values: dict[str, str]) -> None:
    path = Path(".env")
    lines = path.read_text().splitlines() if path.exists() else []
    lines = [l for l in lines if l.split("=", 1)[0].strip() not in values]
    lines += [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n")
    path.chmod(0o600)
    print("Wrote .env (gitignored).")


def set_github_secrets(values: dict[str, str], repo: str | None) -> None:
    if not shutil.which("gh"):
        sys.exit("gh CLI not found. Install it (https://cli.github.com) or add the secrets in the GitHub UI.")
    for name, value in values.items():
        cmd = ["gh", "secret", "set", name] + (["--repo", repo] if repo else [])
        subprocess.run(cmd, input=value.encode(), check=True)
        print(f"Set GitHub secret {name}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--redirect-uri", default=os.environ.get("SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"))
    ap.add_argument("--write-env", action="store_true", help="save credentials to .env for local runs")
    ap.add_argument("--set-github-secrets", action="store_true", help="store all three secrets with the gh CLI")
    ap.add_argument("--repo", help="owner/repo for --set-github-secrets (default: current repo)")
    ap.add_argument("--no-browser", action="store_true", help="print the URL instead of opening a browser")
    args = ap.parse_args()

    client_id = os.environ.get("SPOTIFY_CLIENT_ID") or input("Spotify Client ID: ").strip()
    client_secret = os.environ.get("SPOTIFY_CLIENT_SECRET") or getpass.getpass("Spotify Client Secret (hidden): ").strip()
    if not client_id or not client_secret:
        sys.exit("Client ID and secret are required (Spotify dashboard → your app → Settings).")

    state = secrets.token_urlsafe(16)
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": args.redirect_uri,
        "scope": SCOPES,
        "state": state,
        "show_dialog": "true",
    })
    print(f"\nRedirect URI in use: {args.redirect_uri}\n(It must match your app settings exactly.)\n")
    print("Open this URL to authorize:\n\n" + url + "\n")
    if not args.no_browser:
        webbrowser.open(url)

    code = wait_for_code(args.redirect_uri, state)
    tokens = exchange(code, client_id, client_secret, args.redirect_uri)
    refresh = tokens.get("refresh_token")
    if not refresh:
        sys.exit(f"No refresh token in response: {tokens}")
    print(f"\nAuthorized as: {whoami(tokens['access_token'])}")

    values = {"SPOTIFY_CLIENT_ID": client_id, "SPOTIFY_CLIENT_SECRET": client_secret, "SPOTIFY_REFRESH_TOKEN": refresh}
    if args.write_env:
        write_env(values)
    if args.set_github_secrets:
        set_github_secrets(values, args.repo)
    if not args.write_env and not args.set_github_secrets:
        print("\nSPOTIFY_REFRESH_TOKEN (keep this secret):\n")
        print(refresh)
        print("\nAdd it as a repository secret, or re-run with --set-github-secrets / --write-env.")


if __name__ == "__main__":
    main()
