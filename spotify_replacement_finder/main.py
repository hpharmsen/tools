import argparse
import os
import re
import sys
import time

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPE = 'playlist-read-private playlist-modify-private playlist-modify-public'


def extract_playlist_id(raw: str) -> str:
    if m := re.search(r'playlist[/:]([A-Za-z0-9]+)', raw):
        return m.group(1)
    if re.match(r'^[A-Za-z0-9]{22}$', raw):
        return raw
    raise ValueError(f'Cannot parse playlist ID from: {raw}')


def build_client() -> spotipy.Spotify:
    client_id = os.getenv('SPOTIFY_CLIENT_ID')
    client_secret = os.getenv('SPOTIFY_CLIENT_SECRET')
    redirect_uri = os.getenv('SPOTIFY_REDIRECT_URI', 'http://127.0.0.1:8888/callback')

    missing = [k for k, v in [
        ('SPOTIFY_CLIENT_ID', client_id),
        ('SPOTIFY_CLIENT_SECRET', client_secret),
    ] if not v]
    if missing:
        print(f'Error: missing env vars: {", ".join(missing)}', file=sys.stderr)
        print('Copy .env.example to .env and fill in your Spotify app credentials.', file=sys.stderr)
        sys.exit(1)

    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
    ))


def fetch_all_tracks(sp: spotipy.Spotify, playlist_id: str) -> list[dict]:
    items = []
    result = sp.playlist_items(playlist_id, market='from_token', additional_types=['track'])
    while result:
        items.extend(result['items'])
        result = sp.next(result) if result['next'] else None
    return items


def is_unavailable(item: dict) -> bool:
    track = item.get('track')
    if not track:
        return False
    if item.get('is_local') or track.get('id') is None:
        return False
    if track.get('type') != 'track':
        return False
    return not track.get('is_playable', True)


def find_replacement(sp: spotipy.Spotify, title: str, artist: str, original_id: str) -> dict | None:
    q = f'track:"{title}" artist:"{artist}"'
    results = sp.search(q=q, type='track', market='from_token', limit=10)
    candidates = [
        t for t in results['tracks']['items']
        if t.get('id') != original_id
        and t.get('is_playable', True)
        and t['artists'][0]['name'].lower() == artist.lower()
    ]
    return max(candidates, key=lambda t: t['popularity'], default=None) if candidates else None


def with_retry(fn, *args, max_retries: int = 3, **kwargs):
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


def run(playlist_input: str, dry_run: bool) -> None:
    sp = build_client()

    try:
        playlist_id = extract_playlist_id(playlist_input)
    except ValueError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)

    playlist = sp.playlist(playlist_id, fields='owner,name,snapshot_id,tracks.total')
    playlist_name = playlist['name']
    snapshot_id = playlist['snapshot_id']

    if not dry_run:
        user_id = sp.current_user()['id']
        if playlist['owner']['id'] != user_id:
            print(
                f'Error: playlist "{playlist_name}" is owned by '
                f'{playlist["owner"]["id"]}, not {user_id}.',
                file=sys.stderr,
            )
            print('Use --dry-run to scan playlists you do not own.', file=sys.stderr)
            sys.exit(1)

    tracks = fetch_all_tracks(sp, playlist_id)
    total = len(tracks)

    unavailable = [
        (idx, item) for idx, item in enumerate(tracks) if is_unavailable(item)
    ]

    print(f'\nSpotify Replacement Finder')
    print(f'Playlist: "{playlist_name}" ({total} tracks, {len(unavailable)} unavailable)')

    if not unavailable:
        print('\nAll tracks are playable. Nothing to do.')
        return

    if dry_run:
        print('[DRY RUN] No changes will be made.\n')

    # Process in reverse order to avoid position shifting
    unavailable_sorted = sorted(unavailable, key=lambda x: x[0], reverse=True)

    replaced = []
    no_replacement = []

    for idx, item in unavailable_sorted:
        track = item['track']
        title = track['name']
        artist = track['artists'][0]['name']
        original_id = track['id']
        original_uri = track['uri']

        replacement = find_replacement(sp, title, artist, original_id)

        if replacement is None:
            no_replacement.append((title, artist))
            continue

        if dry_run:
            replaced.append((title, artist, replacement))
            continue

        with_retry(
            sp.playlist_remove_specific_occurrences_of_items,
            playlist_id,
            [{'uri': original_uri, 'positions': [idx]}],
            snapshot_id=snapshot_id,
        )
        result = sp.playlist_add_items(playlist_id, [replacement['uri']], position=idx)
        snapshot_id = result.get('snapshot_id', snapshot_id)
        replaced.append((title, artist, replacement))

    verb = 'Would replace' if dry_run else 'Replaced'
    print(f'\n{verb} ({len(replaced)}):')
    for title, artist, r in replaced:
        album = r['album']['name']
        year = r['album'].get('release_date', '')[:4]
        pop = r['popularity']
        year_str = f', {year}' if year else ''
        print(f'  ✓ "{title}" by {artist}  →  "{r["name"]}" by {r["artists"][0]["name"]} '
              f'(album: {album}{year_str}) [popularity: {pop}]')

    if no_replacement:
        print(f'\nNo replacement found ({len(no_replacement)}):')
        for title, artist in no_replacement:
            print(f'  ✗ "{title}" by {artist}')

    action = 'would be replaced' if dry_run else 'replaced'
    print(f'\nDone. {len(replaced)} tracks {action}, {len(no_replacement)} could not be fixed.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Replace unavailable Spotify tracks in a playlist'
    )
    parser.add_argument('playlist', help='Spotify playlist URL or ID')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Find replacements without modifying the playlist',
    )
    args = parser.parse_args()
    run(args.playlist, args.dry_run)
