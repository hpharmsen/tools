---
title: Spotify Replacement Finder CLI
type: feat
status: active
date: 2026-05-14
origin: docs/brainstorms/2026-05-14-spotify-replacement-finder-requirements.md
---

# feat: Spotify Replacement Finder CLI

## Overview

A Python CLI tool that authenticates with Spotify, scans a playlist for tracks that are unavailable in the user's market, finds the same song in a still-available version, and auto-replaces dead tracks in place — with a `--dry-run` mode to preview changes first.

## Problem Statement

Spotify silently leaves unavailable tracks in playlists (licensing changes, market blocks). They appear in the playlist but skip during playback. Manually finding and replacing them is tedious; this tool automates it.
(see origin: docs/brainstorms/2026-05-14-spotify-replacement-finder-requirements.md)

## Proposed Solution

Single-file Python CLI (`main.py`) using `spotipy` (PKCE OAuth, no client secret required). Fetches all playlist tracks with `market='from_token'`, processes unavailable ones in **reverse position order** (prevents index shifting during removal), searches for the highest-popularity alternative by same artist, and patches the playlist via two sequential API calls (remove + insert at position).

## Technical Considerations

### Libraries & Setup

- **`spotipy`** — canonical Spotify Python client. Handles Authorization Code OAuth, token caching (`.cache`), and auto-refresh.
- **`python-dotenv`** — load `.env` for `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and `SPOTIFY_REDIRECT_URI`.
- **`justlog`** — required logging library per project conventions.
- **`uv`** — dependency manager; `pyproject.toml` + `uv.lock`.
- **`argparse`** — CLI arg parsing (project convention; no Click/Typer).

### Spotify API Surface

| Task | Method |
|---|---|
| Auth | `SpotifyOAuth(client_id, client_secret, redirect_uri, scope)` |
| Current user | `sp.current_user()` |
| Fetch playlist metadata | `sp.playlist(playlist_id, fields='owner,name,snapshot_id')` |
| Fetch tracks (paginated) | `sp.playlist_items(playlist_id, market='from_token', additional_types=['track'])` |
| Search alternatives | `sp.search(q='track:"X" artist:"Y"', type='track', market='from_token', limit=10)` |
| Remove at position | `sp.playlist_remove_specific_occurrences_of_items(playlist_id, [{"uri": uri, "positions": [idx]}], snapshot_id=snap)` |
| Insert at position | `sp.playlist_add_items(playlist_id, [uri], position=idx)` |

### Auth Setup

Read credentials from `.env` via `python-dotenv`, then build the spotipy client using `SpotifyOAuth` (Authorization Code flow — supports user-owned playlist read/write):

```python
from spotipy.oauth2 import SpotifyOAuth

def build_client() -> spotipy.Spotify:
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=os.getenv('SPOTIFY_CLIENT_ID'),
        client_secret=os.getenv('SPOTIFY_CLIENT_SECRET'),
        redirect_uri=os.getenv('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback'),
        scope=SCOPE,
    ))
```

On first run, spotipy opens the browser for user consent and caches the token to `.cache`. Subsequent runs use the cached token, refreshing silently when expired.

### Detecting Unavailable Tracks

Pass `market='from_token'` to `playlist_items` — this activates the `is_playable` and `restrictions` fields per track.

```python
def is_unavailable(item: dict) -> bool:
    track = item.get('track')
    if not track:
        return False
    if item.get('is_local') or track.get('id') is None:
        return False  # local file
    if track.get('type') != 'track':
        return False  # podcast episode
    return not track.get('is_playable', True)
```

**Track Relinking:** when `is_playable=True` but `linked_from` exists, Spotify already relinked automatically — treat as playable, skip.

### Position Shifting — Critical

Removing a track at position N shifts all tracks after it down by one. Processing multiple unavailable tracks left-to-right would corrupt positions for subsequent removals.

**Solution:** collect all `(position, track)` pairs, sort by position **descending**, process highest index first. Insertions at high positions don't affect lower indices.

### Pagination

`playlist_items` returns max 100 items per page. Pre-fetch all pages into a flat list before any mutations:

```python
def fetch_all_tracks(sp, playlist_id: str) -> list[dict]:
    items = []
    result = sp.playlist_items(playlist_id, market='from_token', additional_types=['track'])
    while result:
        items.extend(result['items'])
        result = sp.next(result) if result['next'] else None
    return items
```

### snapshot_id Chaining

Each mutation returns a new `snapshot_id`. Chain it through every remove+insert pair and across all replacements:

```python
snapshot_id = playlist['snapshot_id']
# For each unavailable track (reverse order):
result = sp.playlist_remove_specific_occurrences_of_items(..., snapshot_id=snapshot_id)
snapshot_id = result['snapshot_id']
sp.playlist_add_items(playlist_id, [new_uri], position=idx)
# No snapshot_id needed for add — it's positional, not snapshot-locked
```

### Searching for Replacements

```python
def find_replacement(sp, title: str, artist: str, original_id: str) -> dict | None:
    q = f'track:"{title}" artist:"{artist}"'
    results = sp.search(q=q, type='track', market='from_token', limit=10)
    candidates = [
        t for t in results['tracks']['items']
        if t.get('id') != original_id                           # not the same broken track
        and t.get('is_playable', True)                          # playable in market
        and t['artists'][0]['name'].lower() == artist.lower()   # same primary artist (no covers)
    ]
    return max(candidates, key=lambda t: t['popularity'], default=None) if candidates else None
```

### Rate Limiting

Spotify returns `HTTP 429` with `Retry-After` header when rate-limited. spotipy does not auto-retry. Wrap mutations with backoff:

```python
def with_retry(fn, *args, max_retries=3, **kwargs):
    for attempt in range(max_retries):
        try:
            return fn(*args, **kwargs)
        except spotipy.SpotifyException as e:
            if e.http_status == 429:
                wait = int(getattr(e, 'headers', {}).get('Retry-After', 2 ** attempt))
                time.sleep(wait + 1)
            else:
                raise
    raise RuntimeError(f'Rate limit exceeded after {max_retries} retries')
```

### Ownership Check

Before any track fetching, verify the user owns the playlist (write permission):

```python
user_id = sp.current_user()['id']
playlist = sp.playlist(playlist_id, fields='owner,name,snapshot_id')
if not dry_run and playlist['owner']['id'] != user_id:
    print(f'Error: playlist is owned by {playlist["owner"]["id"]}, not {user_id}', file=sys.stderr)
    sys.exit(1)
```

### URL/ID Parsing

Handle three input formats:
- `https://open.spotify.com/playlist/{id}?...`
- `spotify:playlist:{id}`
- Raw ID (22-char alphanumeric)

```python
import re

def extract_playlist_id(raw: str) -> str:
    if m := re.search(r'playlist[/:]([A-Za-z0-9]+)', raw):
        return m.group(1)
    if re.match(r'^[A-Za-z0-9]{22}$', raw):
        return raw
    raise ValueError(f'Cannot parse playlist ID from: {raw}')
```

## Implementation Phases

### Phase 1 — Project Setup

**Files to create:**

`pyproject.toml`:
```toml
[project]
name = 'spotify-replacement-finder'
version = '0.1.0'
description = 'Replace unavailable Spotify playlist tracks automatically'
requires-python = '>=3.13'
dependencies = [
    'spotipy>=2.24',
    'python-dotenv>=1.0',
    'justlog @ git+https://github.com/hpharmsen/justlog.git',
]

[tool.ruff]
line-length = 100

[dependency-groups]
dev = ['ruff>=0.14', 'pytest>=8']
```

`.gitignore`:
```
.env
.venv
__pycache__/
*.pyc
.cache
.cache-*
```

`.env.example`:
```
SPOTIFY_CLIENT_ID=your_client_id_here
SPOTIFY_CLIENT_SECRET=your_client_secret_here
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

### Phase 2 — Core Implementation (`main.py`)

Structure:

```python
# main.py
import argparse, os, re, sys, time
import spotipy
from spotipy.oauth2 import SpotifyPKCE
from dotenv import load_dotenv
from justlog import log

SCOPE = 'playlist-read-private playlist-modify-private playlist-modify-public'

def extract_playlist_id(raw: str) -> str: ...
def build_client() -> spotipy.Spotify: ...
def fetch_all_tracks(sp, playlist_id: str) -> list[dict]: ...
def is_unavailable(item: dict) -> bool: ...
def find_replacement(sp, title: str, artist: str, original_id: str) -> dict | None: ...
def with_retry(fn, *args, max_retries=3, **kwargs): ...
def run(playlist_input: str, dry_run: bool) -> None: ...

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Replace unavailable Spotify tracks in a playlist')
    parser.add_argument('playlist', help='Spotify playlist URL or ID')
    parser.add_argument('--dry-run', action='store_true', help='Find replacements without modifying the playlist')
    args = parser.parse_args()
    run(args.playlist, args.dry_run)
```

**`run()` logic:**
1. `load_dotenv()`, validate env vars
2. Build SpotifyPKCE client (opens browser on first run)
3. Parse playlist ID
4. Fetch playlist metadata; check ownership (skip check for `--dry-run`)
5. `fetch_all_tracks()` — all pages, flat list
6. Collect `unavailable = [(idx, item) for idx, item in enumerate(tracks) if is_unavailable(item)]`
7. If empty → print "All tracks are playable." and exit
8. Sort `unavailable` by index **descending**
9. For each `(idx, item)`:
   - Extract `title = item['track']['name']`, `artist = item['track']['artists'][0]['name']`, `original_id = item['track']['id']`
   - `replacement = find_replacement(sp, title, artist, original_id)`
   - If None → add to `no_replacement` list, continue
   - If `--dry-run` → add to `would_replace` list, continue
   - `with_retry(sp.playlist_remove_specific_occurrences_of_items, ...)` → update `snapshot_id`
   - `with_retry(sp.playlist_add_items, ..., position=idx)`
   - Add to `replaced` list
10. Print summary report

**Summary report format:**
```
Spotify Replacement Finder
Playlist: "My Playlist" (42 tracks, 3 unavailable)

Replaced (2):
  ✓ "Song A" by Artist X  →  "Song A" by Artist X (album: Single, 2023) [popularity: 74]
  ✓ "Song B" by Artist Y  →  "Song B" by Artist Y (album: Greatest Hits) [popularity: 81]

No replacement found (1):
  ✗ "Rare Track" by Obscure Artist

Done. 2 tracks replaced, 1 could not be fixed.
```

For `--dry-run`, prefix output with `[DRY RUN] ` and change verbs to "Would replace".

### Phase 3 — Tests (`tests/test_main.py`)

Test cases:
- `test_extract_playlist_id` — URL, URI, raw ID, malformed input
- `test_is_unavailable` — `is_playable=False`, local file, episode, absent `is_playable`, relinked track
- `test_find_replacement_filters_same_id` — search returns original track → should return None
- `test_find_replacement_filters_covers` — candidate with different artist → excluded
- `test_find_replacement_picks_highest_popularity` — multiple valid candidates → highest wins
- `test_position_order` — unavailable tracks processed high-to-low index

Use `unittest.mock.patch` to mock `sp.search`, `sp.playlist_items`, etc.

## Acceptance Criteria

- [ ] R1: `python main.py <url>` and `python main.py <id>` both work; malformed input exits with error
- [ ] R2: First run opens browser for PKCE auth; subsequent runs use cached token (`.cache`)
- [ ] R3: All playlist tracks fetched including pages beyond 100; unavailable tracks detected via `is_playable=False`
- [ ] R4/R5: Replacement found by title+artist search; same primary artist required; highest popularity selected
- [ ] R6: Unavailable track removed and replacement inserted at same position; playlist order preserved for all other tracks
- [ ] R7: Tracks with no replacement logged in report, left untouched
- [ ] R8: `--dry-run` produces report without modifying playlist
- [ ] R9: Summary report shows replaced tracks (with album/popularity), tracks with no replacement, and totals
- [ ] Edge: Local files and podcast episodes skipped silently
- [ ] Edge: "All tracks playable" outputs a clear message rather than silently exiting
- [ ] Edge: Non-owned playlist (write mode) exits before any modification with clear error
- [ ] Edge: HTTP 429 triggers backoff with `Retry-After`, max 3 retries per call

## Dependencies & Risks

**Dependencies:**
- Spotify Developer App (create at developer.spotify.com; add `http://127.0.0.1:8888/callback` as a Redirect URI in the app settings)
- `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET`, and `SPOTIFY_REDIRECT_URI` in `.env`
- Python 3.13, `uv`

**Risks:**
- Spotify search may not find an available alternative for niche/rare tracks (R7 handles this)
- Port 8888 conflicts block OAuth redirect — user must pick a free port and update both the app settings and `SPOTIFY_REDIRECT_URI`
- Authorization Code flow requires a local HTTP server to capture the redirect; first-run UX depends on the browser opening successfully

## Sources & References

### Origin

- **Origin document:** [docs/brainstorms/2026-05-14-spotify-replacement-finder-requirements.md](../brainstorms/2026-05-14-spotify-replacement-finder-requirements.md)
  Key decisions carried forward: CLI over HTML, PKCE OAuth, most-popular-wins replacement strategy, --dry-run flag

### External References

- [Spotify Track Relinking](https://developer.spotify.com/documentation/web-api/concepts/track-relinking)
- [Get Playlist Items API](https://developer.spotify.com/documentation/web-api/reference/get-playlists-tracks)
- [Add Items to Playlist API](https://developer.spotify.com/documentation/web-api/reference/add-tracks-to-playlist)
- [Remove Playlist Items API](https://developer.spotify.com/documentation/web-api/reference/remove-tracks-playlist)
- [Spotify Search API](https://developer.spotify.com/documentation/web-api/reference/search)
- [spotipy docs](https://spotipy.readthedocs.io/en/latest/)
