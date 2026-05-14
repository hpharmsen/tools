---
date: 2026-05-14
topic: spotify-replacement-finder
---

# Spotify Replacement Finder

## Problem Frame

Spotify tracks sometimes become unavailable in a user's market (licensing changes, label pulls, regional blocks). When this happens, a playlist silently contains dead tracks that skip on playback. This tool detects those dead tracks, finds the same song still available on Spotify (different album/single/compilation), and auto-replaces them in place — restoring the playlist without manual searching.

Target user: the developer themselves.

## Requirements

- R1. Accept a Spotify playlist URL or ID as CLI input.
- R2. Authenticate with Spotify via OAuth (scope: read + modify playlist).
- R3. Fetch all tracks in the playlist and identify those marked unavailable in the user's market.
- R4. For each unavailable track, search Spotify by title + primary artist for alternative versions.
- R5. Select the candidate with the highest Spotify popularity score.
- R6. Remove the unavailable track and insert the replacement at the same position in the playlist.
- R7. If no replacement is found for a track, skip it (leave the dead track in place).
- R8. Support a `--dry-run` flag: find and report replacements without modifying the playlist.
- R9. Print a summary report: tracks replaced (or would-be replaced in dry-run), tracks with no replacement found.

## Success Criteria

- Running the tool on a playlist with known unavailable tracks replaces them with playable versions.
- The report clearly shows what changed and what couldn't be fixed.
- Tracks without a replacement are not silently dropped.

## Scope Boundaries

- Stays within Spotify only — no YouTube or other platform fallback.
- Fully automatic replacement selection (no per-track interactive prompt).
- Does not handle playlists the user does not own (no write permission).
- No deduplication or general playlist cleanup beyond replacing unavailable tracks.

## Key Decisions

- **CLI, not HTML**: More natural for personal automation; avoids browser OAuth complexity in a single-file constraint.
- **Spotify API (not export file)**: Live data means availability is checked in real time against the user's market.
- **Most popular wins**: When multiple versions exist, highest Spotify popularity score is chosen — typically the canonical release.

## Dependencies / Assumptions

- Requires a Spotify Developer app (Client ID + Secret) — user must create one at developer.spotify.com.
- Credentials stored in `.env` (never committed).
- Tool uses the `spotipy` library (or direct Spotify Web API calls) — resolved during planning.
- User's market is inferred from their Spotify account profile.

## Outstanding Questions

### Resolve Before Planning
_(none)_

### Deferred to Planning

- [Affects R2][Technical] Use `spotipy` library vs. raw `requests` + token management?
- [Affects R3][Technical] How does Spotify's API surface unavailable tracks — `is_playable` flag, `restrictions` object, or null `id`?
- [Affects R6][Technical] Insertion at same position: does Spotify API support positional insertion, or only append + reorder?

## Next Steps

→ `/hp:plan` for structured implementation planning
