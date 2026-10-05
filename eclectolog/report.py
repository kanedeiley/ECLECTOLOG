"""Console output and the GitHub Actions job summary."""
from __future__ import annotations

from collections import Counter

from .engine import RunResult

SOURCE_LABELS = {
    "deep_cuts": "Deep cut",
    "genre_neighbors": "Neighbor",
    "wildcard": "Wildcard",
    "compass": "Compass",
}


def _shares(weights: dict[str, float], n: int) -> list[tuple[str, float]]:
    total = sum(weights.values()) or 1.0
    return [(k, 100 * w / total) for k, w in sorted(weights.items(), key=lambda kv: -kv[1])[:n]]


def _md(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def console(result: RunResult) -> str:
    lines = [
        f"{'[dry run] ' if result.dry_run else ''}{result.playlist_name}: {len(result.picks)}/{result.target_size} tracks"
        + (f" → {result.playlist_url}" if result.playlist_url else ""),
        "",
    ]
    for i, c in enumerate(result.picks, 1):
        lines.append(f"{i:>3}. [{SOURCE_LABELS.get(c.source, c.source):<8}] {c.track.label()}")
        lines.append(f"     {c.reason}")
    if result.directive_notes:
        lines += ["", "Compass directives: " + "; ".join(result.directive_notes)]
    lines += ["", f"{result.api_calls} API calls"]
    return "\n".join(lines)


def markdown(result: RunResult) -> str:
    counts = Counter(c.source for c in result.picks)
    mix = " · ".join(f"{SOURCE_LABELS.get(s, s)} {counts.get(s, 0)}/{n}" for s, n in result.allocation.items())
    head = f"## 🎛️ {_md(result.playlist_name)}\n\n"
    if result.dry_run:
        head += "**Dry run**: nothing was written to Spotify.\n\n"
    elif result.playlist_url:
        head += f"**[Open in Spotify]({result.playlist_url})**\n\n"
    head += f"{len(result.picks)} of {result.target_size} tracks · {mix} · {result.api_calls} API calls\n\n"

    out = [head]
    if result.created_playlists:
        out.append("Created: " + ", ".join(f"`{_md(n)}`" for n in result.created_playlists) + "\n\n")
    if result.directive_notes:
        out.append("**Compass directives applied:** " + "; ".join(_md(n) for n in result.directive_notes) + "\n\n")
    if result.liked_feedback:
        out.append("**You saved from last time:** " + ", ".join(_md(t.label()) for t in result.liked_feedback[:10]) + "\n\n")
    if result.compass_seeds:
        out.append("**Compass artists:** " + ", ".join(_md(n) for n in result.compass_seeds[:15]) + "\n\n")

    out.append("| # | Track | Album | Source | Why |\n|---|---|---|---|---|\n")
    for i, c in enumerate(result.picks, 1):
        link = f"[{_md(c.track.name)}](https://open.spotify.com/track/{c.track.id})"
        out.append(f"| {i} | {link} — {_md(', '.join(c.track.artist_names))} | {_md(c.track.album)} | {SOURCE_LABELS.get(c.source, c.source)} | {_md(c.reason)} |\n")

    artists = _shares({k: s.weight for k, s in result.profile.artists.items()}, 12)
    names = {k: s.name for k, s in result.profile.artists.items()}
    genres = _shares(result.profile.genres, 12)
    out.append("\n<details><summary>Taste profile after flattening</summary>\n\n")
    out.append("| Artist | Share | | Genre | Share |\n|---|---|---|---|---|\n")
    for i in range(max(len(artists), len(genres))):
        a = f"{_md(names[artists[i][0]])} | {artists[i][1]:.1f}%" if i < len(artists) else " | "
        g = f"{_md(genres[i][0])} | {genres[i][1]:.1f}%" if i < len(genres) else " | "
        out.append(f"| {a} | | {g} |\n")
    out.append("\n</details>\n")
    return "".join(out)
