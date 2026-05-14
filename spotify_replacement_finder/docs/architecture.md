# Architecture

**Type:** Standalone Python CLI tool (lives inside the tools repo but is not an HTML tool)

**Tech stack:**
- Python 3.13
- `uv` for dependency management (`pyproject.toml` + `uv.lock`)
- `spotipy` — Spotify Web API client (Authorization Code OAuth)
- `python-dotenv` — loads credentials from `.env`
- `justlog` — logging

## Project Layout

```
spotify_replacement_finder/
  main.py          # Single-file CLI: all logic lives here
  pyproject.toml   # uv dependencies
  .env             # gitignored; holds SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI
  .env.example     # template to copy
  .gitignore
  tests/
    test_main.py   # unit tests for extract_playlist_id, is_unavailable, find_replacement
  docs/
    doel.md
    architecture.md
    brainstorms/
    plans/
    solutions/
```

## Key Functions (`main.py`)

| Function | Purpose |
|---|---|
| `extract_playlist_id(raw)` | Parses URL / URI / raw ID → playlist ID |
| `build_client()` | Creates authenticated `spotipy.Spotify` via SpotifyOAuth |
| `fetch_all_tracks(sp, id)` | Paginates `playlist_items` with `market='from_token'` |
| `is_unavailable(item)` | Returns True if track has `is_playable=False`; skips local files, episodes, null IDs |
| `find_replacement(sp, title, artist, id)` | Searches for same song by same artist, excludes original ID, picks highest popularity |
| `with_retry(fn, ...)` | Wraps API calls with 429 backoff using Retry-After header |
| `run(playlist_input, dry_run)` | Main orchestration: auth → fetch → detect → replace → report |

## Data Flow

```
CLI args
  → extract_playlist_id()
  → build_client() [SpotifyOAuth, .env creds, .cache token]
  → ownership check (skip in --dry-run)
  → fetch_all_tracks() [paginated, market='from_token']
  → filter is_unavailable()
  → sort by position DESCENDING (prevents index shift)
  → for each: find_replacement() [search + filter + popularity rank]
  → [if not dry-run] remove + insert at same position via Spotify API
  → summary report
```

## Auth

Uses `SpotifyOAuth` (Authorization Code flow). On first run, opens browser for consent and caches token to `.cache`. Subsequent runs refresh silently. Requires a Spotify Developer App with `http://127.0.0.1:8888/callback` as redirect URI.

## Usage

```bash
cd spotify_replacement_finder
cp .env.example .env  # fill in your Spotify app credentials
uv sync
uv run python main.py <playlist_url_or_id>
uv run python main.py <playlist_url_or_id> --dry-run
```
