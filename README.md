<p align="center">
  <img src="assets/Eclectolog.svg" alt="Eclectolog" width="600">
</p>

An eclectic Spotify playlist builder for you and a few friends. Everyone joins through a small web
app, and a daily GitHub Actions job builds each person a new mix. It learns from what you listen
to, but on purpose it **doesn't converge on one "north star."** Recent listening counts a little
more, and everything else is flattened so the mix keeps branching out.

You steer it from the web app, where you set how much each source contributes, and from inside
Spotify. A **Compass** playlist sets what you want more of, an **Avoid** playlist bans artists, and
directives typed into the Compass description work like a settings panel.

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

Every mix is saved to Supabase (the `mix_runs` table, one row per mix). That's how it remembers
what it already served without spending Spotify API calls, and the web app's dashboard shows your
latest mix from there. Mixes older than two years are dropped.

Each mix lists every track with *why* it was picked, in the dashboard and in the job summary.

Playlists that still have Spotify's automatic cover get Eclectolog's record artwork from
[`eclectolog/covers/`](eclectolog/covers). A cover you set yourself is never replaced. This needs
the `ugc-image-upload` permission, so anyone who joined before it was added should sign in again.
If a cover can't be set, the run logs a warning and carries on. Set `playlist.covers: false` to
turn this off.

> **About the Spotify API (2026):** Spotify removed `/recommendations`, related artists, audio
> features (Nov 2024), artist top tracks, track and artist `popularity`, and capped search at 10
> results (Feb 2026). Eclectolog only uses endpoints that still work for Development Mode apps.
> It finds less mainstream music by digging to random search offsets instead of filtering on popularity.

---

## Setup (about 20 minutes)

You need a Spotify app, a Supabase project, somewhere to host the web app (Vercel works well) and
this repo on GitHub.

### 1. Create a Spotify app

1. Go to <https://developer.spotify.com/dashboard> and log in. As of Feb 2026, the app owner needs **Spotify Premium**.
2. Click **Create app**, tick **Web API**, and add these **Redirect URIs**:
   - `https://<project-ref>.supabase.co/auth/v1/callback` for sign-in through the web app
   - `http://127.0.0.1:8888/callback` for single-user local runs (optional)
3. Open **Settings** and copy the **Client ID** and **Client secret**.
4. Under **User Management**, add each friend's name and Spotify email. Development Mode apps
   allow 5 users, including you, and anyone not on the list gets a `403`.

### 2. Set up Supabase

1. Run the files in [`supabase/migrations/`](supabase/migrations) in order, in the **SQL Editor**
   or with `supabase db push`.
2. **Authentication → Sign In / Providers → Spotify:** turn it on and paste the Client ID and Secret.
3. **Authentication → Sign In / Providers → Email:** turn off **Confirm email**. Spotify reports
   emails as unverified, so with it on, sign-in stops to send a confirmation email.
4. **Authentication → URL Configuration:** set the Site URL to your web app's URL, and add
   `http://localhost:3000/**` and `https://<your-domain>/**` to Redirect URLs.

### 3. Deploy the web app

See [Web app](#web-app) below. Then sign in yourself so you have a profile and stored tokens.

### 4. Add GitHub secrets

On the repo, go to **Settings → Secrets and variables → Actions → Secrets** and add:

| Secret | Value |
|---|---|
| `SPOTIFY_CLIENT_ID` | from the Spotify dashboard. It must be the same app Supabase uses, or token refreshes fail |
| `SPOTIFY_CLIENT_SECRET` | from the Spotify dashboard |
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` |
| `SUPABASE_SERVICE_ROLE_KEY` | Supabase **Settings → API**. An `sb_secret_...` key works too |

### 5. Run it

Go to **Actions → Eclectolog → Run workflow** and tick **Dry run** first. The job summary shows
everyone's mix without changing anything. To try one person, put their Spotify user ID in **Only
this user**. Then run it for real.

Each person's first real run creates three private playlists in their library: **Eclectolog**,
plus **Eclectolog · Compass** and **Eclectolog · Avoid**.

After that it runs every day at 01:07 UTC (9 PM US Eastern in summer). It builds one person's mix
at a time with a 30-second pause in between (`api.user_pause_seconds`), because Spotify's rate
limits apply to the whole app, not to each user. If Spotify bans an endpoint for hours, the rest of
that day's mixes skip it. If one person's mix fails, the others still run, and the job is marked
failed so you notice.

To change the schedule, edit the `cron:` line in
[.github/workflows/eclectolog.yml](.github/workflows/eclectolog.yml). GitHub can't read the
schedule from a variable. GitHub also pauses scheduled workflows on public repos after 60 days
without commits. You'll get an email, and one click re-enables it.

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
7. Each person's mix from the web app
8. Each person's Compass directives

Layers 1 to 6 apply to everyone. Layers 7 and 8 are per person.

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
| `ECLECTOLOG_STATE_KEEP_DAYS` | `365` | Forget mixes older than this (default 730, 0 = forever) |
| `ECLECTOLOG_MARKET` | `US` | Default `from_token` (your account's country) |
| `ECLECTOLOG_SEED` | `42` | Reproducible mixes |
| `ECLECTOLOG_CONFIG_YAML` | *(multi-line YAML)* | Override any `config.yaml` key |
| `ECLECTOLOG_INTERESTS_YAML` | *(multi-line YAML)* | Same shape as `interests.yaml` |

---

## Running locally

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                         # tests (pip install pytest)
```

**Everyone, like the daily job:** put `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`,
`SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` in `.env`, then:

```bash
python -m eclectolog --all-users --dry-run        # preview everyone's mix
python -m eclectolog --all-users --user SPOTIFY_ID
```

**Just your own account, without Supabase:** history goes to `state/history.jsonl` instead.

```bash
python scripts/get_refresh_token.py --write-env   # once
python -m eclectolog --dry-run                    # preview
python -m eclectolog --size 25 --seed 7 -v        # for real
```

## Web app

[`web/`](web) is a Next.js + Tailwind + shadcn/ui app where friends join with their Spotify
account through Supabase Auth. On sign-in it saves their profile and Spotify refresh token. The
dashboard shows their latest mix, and the profile page lets them set their mix weights.

Everything is protected by row-level security. People can read only their own profile, mix
weights and mixes, and only the service role (the daily job and the sign-in callback) can read
Spotify tokens.

### Run it

```bash
cd web
cp .env.example .env.local   # fill in the Supabase URL and keys
npm install
npm run dev                  # http://localhost:3000
```

On Vercel, set **Root Directory** to `web` and add the same three variables from `.env.example`.
