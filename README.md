<p align="center">
  <img src="assets/Electolog.svg" alt="Eclectolog" width="600">
</p>

An eclectic Spotify playlist builder that runs on a GitHub Actions cron. It learns from what you
listen to, but on purpose it **doesn't converge on one "north star."** Recent listening counts a
little more, and everything else is flattened so the mix keeps branching out.

You steer it from inside Spotify. A **Compass** playlist sets what you want more of, an **Avoid**
playlist bans artists, and directives typed into the Compass description work like a settings
panel. You never have to touch the repo after setup.

---

## How it works

Each run builds a taste profile, then fills the playlist from four sources:

| Source | What it picks | Default share |
|---|---|---|
| **Deep cuts** | Unheard tracks from albums you've played, or sometimes from the artist's latest releases | 25% |
| **Neighbors** | *New* artists in genres you listen to, dug out of search results at random depth | 35% |
| **Wildcard** | Genres you *don't* listen to, from a built-in list of about 200 global and historical genres, sometimes pinned to an era | 20% |
| **Compass** | Artists and genres from your Compass playlist, `interests.yaml` and `more:` directives | 20% |

Three things stop it from converging on one taste:

- **Recency boost is small.** A play from a minute ago counts 1.35×, and that decays toward 1× with
  a 72-hour half-life. Your 1-year top tracks still carry full weight.
- **Temperature flattening.** Artist and genre weights are raised to the power 0.6. An artist you
  played 100× more often gets about 16× the chance of being picked, not 100×.
- **Hard caps.** One track per artist and four per genre. Wildcards skip your ten heaviest genres.

It never repeats itself. Anything in your listening history, your Liked Songs sample or any
previous mix is skipped. If you like a track from a previous mix, that artist gets boosted next time.

Every track served is logged to `history.jsonl` on a separate **`eclectolog-state`** branch, one
line per run. That costs no Spotify API calls, never expires, and comes to about 2 MB a year.
Browse the branch to see past mixes, or delete it to reset.

Every run writes a job summary listing each track with *why* it was picked.

> **About the Spotify API (2026):** Spotify removed `/recommendations`, related artists, audio
> features (Nov 2024), artist top tracks, track and artist `popularity`, and capped search at 10
> results (Feb 2026). Eclectolog only uses endpoints that still work for Development Mode apps.
> It finds less mainstream music by digging to random search offsets instead of filtering on popularity.

---

## Setup (about 10 minutes)

### 1. Fork this repo

Then open the **Actions** tab on your fork and click **"I understand my workflows, go ahead and enable them."**
Forks start with workflows disabled.

### 2. Create a Spotify app

1. Go to <https://developer.spotify.com/dashboard> and log in. As of Feb 2026, the app owner needs **Spotify Premium**.
2. Click **Create app** and fill in:
   - **App name:** `Eclectolog` (anything works)
   - **App description:** `Personal playlist builder`
   - **Redirect URIs:** `http://127.0.0.1:8888/callback`, then click **Add**.
     It must be exactly this. Spotify no longer accepts `localhost`, so you need the
     loopback IP `127.0.0.1`. Plain `http` is allowed only for loopback addresses.
   - **Which API/SDKs are you planning to use?** Tick **Web API**.
3. Accept the terms and click **Save**.
4. Open **Settings**. Copy the **Client ID**, then click **View client secret** and copy that too.
5. Optional: under **User Management**, add the name and email of the Spotify account the playlist
   is for. Do this if it isn't the account that owns the app. If you get `403` errors, do it anyway.
   Development Mode apps allow up to 5 users. Each person forking this repo makes their own app,
   so the limit doesn't matter here.

### 3. Get a refresh token

On your computer, from a clone of your fork (Python 3.10+, no packages needed for this step):

```bash
# Easiest: stores all three secrets on your fork with the GitHub CLI (https://cli.github.com)
python scripts/get_refresh_token.py --set-github-secrets

# Or print the token and add the secrets by hand
python scripts/get_refresh_token.py

# Also save a .env for local runs (gitignored)
python scripts/get_refresh_token.py --write-env
```

It asks for your Client ID and Secret, opens Spotify's consent page, catches the redirect on
`127.0.0.1:8888` and exchanges the code for a token. If port 8888 is busy, pass
`--redirect-uri http://127.0.0.1:9090/callback` and add that URI to your app's settings too.

### 4. Add GitHub secrets

Go to **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret | Value |
|---|---|
| `SPOTIFY_CLIENT_ID` | from the dashboard |
| `SPOTIFY_CLIENT_SECRET` | from the dashboard |
| `SPOTIFY_REFRESH_TOKEN` | from step 3 |
| `GH_PAT` *(optional)* | fine-grained token for this repo with **Secrets: Read and write**. If Spotify ever rotates your refresh token, the workflow uses this to save the new one automatically. |

### 5. Run it

Go to **Actions → Eclectolog → Run workflow** and tick **Dry run** first. The job summary shows
the mix without changing anything. Then run it for real.

The first real run creates three private playlists in your library: **Eclectolog**, plus
**Eclectolog · Compass** and **Eclectolog · Avoid**. It also creates the `eclectolog-state` branch.

After that it runs every day at 01:07 UTC (9 PM US Eastern in summer) on its own. To change the schedule, edit the `cron:` line in
[.github/workflows/eclectolog.yml](.github/workflows/eclectolog.yml). GitHub can't read the
schedule from a variable. Also note that GitHub pauses scheduled workflows on public repos after
60 days without commits. You'll get an email, and one click re-enables it.

---

## Steering from Spotify

| Playlist | Do this | Effect |
|---|---|---|
| **Eclectolog · Compass** | Add songs you want more of | Their artists become Compass seeds; their genres are explored with new artists |
| **Eclectolog · Avoid** | Add a song | That artist never appears in a mix |
| **Eclectolog** | Like tracks you love | Those artists get a boost next run |

### Compass directives

Edit the **Compass playlist's description** in the Spotify app. Entries look like `key: value`,
separated by `;`. Empty keys are ignored, and the template it starts with does nothing until you fill it in.

```
more: bossa nova, dub; less: country; era: 1970s; size: 30; wildcard: 0.4
```

| Directive | Example | Meaning |
|---|---|---|
| `more` | `more: krautrock, dub` | Explore these genres; also feeds the Compass source |
| `less` | `less: country` | Drop from exploration; deep cuts from artists in it are down-weighted (substring match) |
| `era` | `era: 1960s, 1985-1995` | Pin wildcards to these eras more often |
| `keywords` | `keywords: field recordings` | Free-text searches mixed into wildcards |
| `size` | `size: 25` | Track count |
| `familiar` / `explore` / `wildcard` / `compass` | `wildcard: 0.5` | Mix weights for deep cuts / neighbors / wildcard / compass |
| `recency` | `recency: 0.1` | Recency boost (0 = none) |
| `temperature` | `temperature: 0.4` | Lower = flatter, more eclectic |

Directives win over every other setting, and each run's summary lists the ones it applied.

---

## Configuration

Settings are layered. Each layer overrides the one before it:

1. Built-in defaults
2. [`config.yaml`](config.yaml), which documents every option
3. `ECLECTOLOG_CONFIG_YAML` repo variable: paste a YAML snippet to override anything without committing
4. [`interests.yaml`](interests.yaml) and the `ECLECTOLOG_INTERESTS_YAML` variable
5. `ECLECTOLOG_*` repo variables, listed below
6. Manual-run inputs (dry run, size, seed)
7. Compass directives

### Repository variables

Add these under **Settings → Secrets and variables → Actions → Variables**. Any variable whose
name starts with `ECLECTOLOG_` is picked up automatically, with no workflow edits needed.

| Variable | Example | Notes |
|---|---|---|
| `ECLECTOLOG_PLAYLIST_NAME` | `Weekly Wander` | Output playlist name |
| `ECLECTOLOG_PLAYLIST_MODE` | `new` | `replace` = one rolling playlist; `new` = a dated playlist each run |
| `ECLECTOLOG_PLAYLIST_SIZE` | `50` | 1–500 |
| `ECLECTOLOG_PLAYLIST_PUBLIC` | `true` | |
| `ECLECTOLOG_MIX` | `deep_cuts=0.2,wildcard=0.4` | Partial updates are fine |
| `ECLECTOLOG_RECENCY_BOOST` | `0.2` | |
| `ECLECTOLOG_RECENCY_HALF_LIFE_HOURS` | `48` | |
| `ECLECTOLOG_TEMPERATURE` | `0.5` | (0, 2] |
| `ECLECTOLOG_SAVED_TRACKS` | `0` | Liked Songs sample size |
| `ECLECTOLOG_MAX_PER_ARTIST` | `2` | |
| `ECLECTOLOG_MAX_PER_GENRE` | `3` | |
| `ECLECTOLOG_SEARCH_DEPTH` | `600` | Deeper = less mainstream (max 1000) |
| `ECLECTOLOG_NOVEL_ARTISTS_ONLY` | `false` | |
| `ECLECTOLOG_EXTRA_GENRES` | `dub, zouk` | Added to interests |
| `ECLECTOLOG_EXTRA_ARTISTS` | `Khruangbin` | Added to interests |
| `ECLECTOLOG_ERAS` | `1970s, 1990s` | |
| `ECLECTOLOG_KEYWORDS` | `field recordings` | |
| `ECLECTOLOG_AVOID_GENRES` | `christmas, kids` | |
| `ECLECTOLOG_AVOID_ARTISTS` | `Some Band` | |
| `ECLECTOLOG_WILDCARD_GENRES` | `gamelan, zydeco` | Added to the wildcard pool |
| `ECLECTOLOG_ERA_CHANCE` | `0.5` | |
| `ECLECTOLOG_REFERENCE_PLAYLISTS` | `false` | Turn off the Compass and Avoid playlists entirely |
| `ECLECTOLOG_CREATE_REFERENCE_PLAYLISTS` | `false` | Use them only if you create them yourself |
| `ECLECTOLOG_COMPASS_PLAYLIST` / `_AVOID_PLAYLIST` | `My Compass` | Rename them |
| `ECLECTOLOG_ARCHIVE_PLAYLIST` | `Eclectolog · Archive` | Optional: also log served tracks to a Spotify playlist (costs API calls, caps at 10k tracks) |
| `ECLECTOLOG_STATE_KEEP_DAYS` | `365` | Forget served tracks older than this (default 730, 0 = forever) |
| `ECLECTOLOG_MARKET` | `US` | Default `from_token` (your account's country) |
| `ECLECTOLOG_SEED` | `42` | Reproducible mixes |
| `ECLECTOLOG_CONFIG_YAML` | *(multi-line YAML)* | Override any `config.yaml` key |
| `ECLECTOLOG_INTERESTS_YAML` | *(multi-line YAML)* | Same shape as `interests.yaml` |

---

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/get_refresh_token.py --write-env   # once
python -m eclectolog --dry-run                    # preview
python -m eclectolog --size 25 --seed 7 -v        # for real
pytest -q                                         # tests (pip install pytest)
```
