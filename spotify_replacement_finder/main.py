import argparse
import os
import re
import sys
import time

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

load_dotenv()

SCOPE = 'user-read-private playlist-read-private playlist-modify-private playlist-modify-public'


def extract_playlist_id(raw: str) -> str:
    if m := re.search(r'playlist[/:]([A-Za-z0-9]+)', raw):
        return m.group(1)
    if re.match(r'^[A-Za-z0-9]{22}$', raw):
        return raw
    raise ValueError(f'Cannot parse playlist ID from: {raw}')


def find_playlist_by_name(sp: spotipy.Spotify, name: str) -> str:
    result = sp.current_user_playlists()
    matches = []
    while result:
        matches.extend(p for p in result['items'] if p['name'].lower() == name.lower())
        result = sp.next(result) if result['next'] else None
    if not matches:
        raise ValueError(f'No playlist named "{name}" found in your library.')
    if len(matches) > 1:
        lines = '\n'.join(f'  {p["id"]}  ({p["tracks"]["total"]} tracks)' for p in matches)
        raise ValueError(f'Multiple playlists named "{name}":\n{lines}\nUse the ID instead.')
    return matches[0]['id']


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

    print(f'Authenticating... (redirect URI: {redirect_uri})')
    print('Make sure this URI is added in your Spotify app at developer.spotify.com → your app → Edit settings → Redirect URIs\n')
    return spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=SCOPE,
    ))


def get_track(item: dict) -> dict | None:
    # Spotify API uses 'track' for streams and 'item' for local files / newer API format
    return item.get('track') or item.get('item')


def fetch_all_tracks(sp: spotipy.Spotify, playlist_id: str) -> list[dict]:
    # No market param: ensures local file track objects are populated (market=X makes them null)
    items = []
    result = sp.playlist_items(playlist_id, additional_types=['track'])
    while result:
        items.extend(result['items'])
        result = sp.next(result) if result['next'] else None
    return items


def needs_replacement(item: dict, user_country: str, replace_local: bool = True) -> bool:
    track = get_track(item)
    if not track:
        return False
    if track.get('type') == 'episode':
        return False
    # Local file: only replace when explicitly requested — the API cannot tell
    # whether the local file still exists on the user's machine.
    if item.get('is_local') or track.get('id') is None:
        return replace_local and bool(track.get('name'))
    # Unavailable Spotify track: user's country not in available_markets
    available = track.get('available_markets')
    if available is not None and user_country not in available:
        return True
    # is_playable / restrictions as additional signal (when present)
    if not track.get('is_playable', True):
        return True
    if track.get('restrictions', {}).get('reason') == 'market':
        return True
    return False


def _normalize(name: str) -> str:
    return re.sub(r'[^\w\s]', '', name).lower().strip()


def find_replacement(sp: spotipy.Spotify, title: str, artist: str, original_id: str | None, market: str) -> dict | None:
    # For filename-style local files: "Bing Crosby - White Christmas.mp3" with empty artist
    clean_title = re.sub(r'\.\w{2,4}$', '', title)  # strip extension
    if not artist and ' - ' in clean_title:
        artist, clean_title = [p.strip() for p in clean_title.split(' - ', 1)]

    q = f'track:"{clean_title}" artist:"{artist}"' if artist else f'track:"{clean_title}"'
    results = sp.search(q=q, type='track', market=market, limit=10)

    def artist_matches(t: dict) -> bool:
        candidate = _normalize(t['artists'][0]['name'])
        return not artist or candidate == _normalize(artist) or _normalize(artist) in candidate

    candidates = [
        t for t in results['tracks']['items']
        if t.get('id') != original_id
        and t.get('is_playable', True)
        and artist_matches(t)
    ]
    return max(candidates, key=lambda t: t.get('popularity', 0), default=None) if candidates else None


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


def run(playlist_input: str, dry_run: bool, replace_local: bool = False, debug: bool = False) -> None:
    sp = build_client()

    try:
        playlist_id = extract_playlist_id(playlist_input)
    except ValueError:
        try:
            playlist_id = find_playlist_by_name(sp, playlist_input)
        except ValueError as e:
            print(f'Error: {e}', file=sys.stderr)
            sys.exit(1)

    user = sp.current_user()
    user_id = user['id']
    market = user.get('country', 'NL')

    playlist = sp.playlist(playlist_id, fields='owner,name,snapshot_id,tracks.total')
    playlist_name = playlist['name']
    snapshot_id = playlist['snapshot_id']

    if not dry_run:
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

    if debug:
        print('\n[DEBUG] Track fields from API:')
        for idx, item in enumerate(tracks):
            t = get_track(item) or {}
            markets = t.get('available_markets', [])
            in_market = market in markets if markets else 'n/a'
            print(f'  [{idx+1}] is_local={item.get("is_local")} '
                  f'id={t.get("id")} type={t.get("type")} '
                  f'is_playable={t.get("is_playable")} '
                  f'in_market={in_market} '
                  f'name="{t.get("name")}" artist="{(t.get("artists") or [{}])[0].get("name")}"')

    to_replace = [
        (idx, item) for idx, item in enumerate(tracks) if needs_replacement(item, market, replace_local)
    ]

    local_count = sum(1 for _, item in to_replace if item.get('is_local') or (item.get('track') or {}).get('id') is None)
    unavail_count = len(to_replace) - local_count

    print(f'\nSpotify Replacement Finder')
    print(f'Playlist: "{playlist_name}" ({total} tracks)')
    if local_count:
        print(f'  Local files to replace: {local_count}')
    if unavail_count:
        print(f'  Unavailable Spotify tracks: {unavail_count}')

    if not to_replace:
        print('\nAll tracks are playable Spotify streams. Nothing to do.')
        return

    if dry_run:
        print('[DRY RUN] No changes will be made.\n')

    # Process in reverse order to avoid position shifting
    to_replace_sorted = sorted(to_replace, key=lambda x: x[0], reverse=True)

    replaced = []
    no_replacement = []

    for idx, item in to_replace_sorted:
        track = get_track(item)
        title = track['name']
        artist = track['artists'][0]['name']
        original_id = track.get('id')
        original_uri = track['uri']

        replacement = find_replacement(sp, title, artist, original_id, market)

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
        pop = r.get('popularity', '?')
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
        description='Replace unavailable or local-file Spotify tracks in a playlist'
    )
    parser.add_argument('playlist', help='Spotify playlist name, URL, or ID')
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Find replacements without modifying the playlist',
    )
    parser.add_argument(
        '--keep-local',
        action='store_true',
        help='Skip local files, only fix unavailable Spotify tracks',
    )
    parser.add_argument('--debug', action='store_true', help='Print raw API fields per track')
    args = parser.parse_args()
    run(args.playlist, args.dry_run, not args.keep_local, args.debug)
