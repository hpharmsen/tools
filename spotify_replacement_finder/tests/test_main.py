import pytest
from unittest.mock import MagicMock, patch
from main import extract_playlist_id, find_playlist_by_name, is_unavailable, find_replacement, fetch_all_tracks


# --- extract_playlist_id ---

def test_extract_playlist_id_from_url():
    url = 'https://open.spotify.com/playlist/37i9dQZEVXbMDoHDwVN2tF?si=abc'
    assert extract_playlist_id(url) == '37i9dQZEVXbMDoHDwVN2tF'


def test_extract_playlist_id_from_uri():
    uri = 'spotify:playlist:37i9dQZEVXbMDoHDwVN2tF'
    assert extract_playlist_id(uri) == '37i9dQZEVXbMDoHDwVN2tF'


def test_extract_playlist_id_from_raw_id():
    raw = '37i9dQZEVXbMDoHDwVN2tF'
    assert extract_playlist_id(raw) == '37i9dQZEVXbMDoHDwVN2tF'


def test_extract_playlist_id_malformed():
    with pytest.raises(ValueError):
        extract_playlist_id('not-a-playlist')


# --- find_playlist_by_name ---

def _make_playlists_page(names_and_ids, next_page=None):
    return {
        'items': [{'name': n, 'id': i, 'tracks': {'total': 10}} for n, i in names_and_ids],
        'next': next_page,
    }


def test_find_playlist_by_name_exact_match():
    sp = MagicMock()
    sp.current_user_playlists.return_value = _make_playlists_page([('My Mix', 'id_abc'), ('Other', 'id_xyz')])
    sp.next.return_value = None
    assert find_playlist_by_name(sp, 'My Mix') == 'id_abc'


def test_find_playlist_by_name_case_insensitive():
    sp = MagicMock()
    sp.current_user_playlists.return_value = _make_playlists_page([('my mix', 'id_abc')])
    sp.next.return_value = None
    assert find_playlist_by_name(sp, 'MY MIX') == 'id_abc'


def test_find_playlist_by_name_not_found():
    sp = MagicMock()
    sp.current_user_playlists.return_value = _make_playlists_page([('Other Playlist', 'id_xyz')])
    sp.next.return_value = None
    with pytest.raises(ValueError, match='No playlist named'):
        find_playlist_by_name(sp, 'Missing Playlist')


def test_find_playlist_by_name_multiple_matches():
    sp = MagicMock()
    sp.current_user_playlists.return_value = _make_playlists_page([('Chill', 'id1'), ('Chill', 'id2')])
    sp.next.return_value = None
    with pytest.raises(ValueError, match='Multiple playlists'):
        find_playlist_by_name(sp, 'Chill')


def test_find_playlist_by_name_paginated():
    sp = MagicMock()
    page1 = _make_playlists_page([('Page One', 'p1')], next_page='url2')
    page2 = _make_playlists_page([('Target', 'target_id')])
    sp.current_user_playlists.return_value = page1
    sp.next.side_effect = [page2, None]
    assert find_playlist_by_name(sp, 'Target') == 'target_id'


# --- is_unavailable ---

def _make_item(is_playable=True, is_local=False, track_type='track', track_id='abc123', track=True):
    if not track:
        return {'track': None, 'is_local': False}
    return {
        'is_local': is_local,
        'track': {
            'id': track_id,
            'type': track_type,
            'is_playable': is_playable,
            'name': 'Test Track',
            'artists': [{'name': 'Test Artist', 'id': 'artist1'}],
        },
    }


def test_is_unavailable_playable_track():
    assert not is_unavailable(_make_item(is_playable=True))


def test_is_unavailable_unavailable_track():
    assert is_unavailable(_make_item(is_playable=False))


def test_is_unavailable_local_file():
    assert not is_unavailable(_make_item(is_local=True, is_playable=False))


def test_is_unavailable_episode():
    assert not is_unavailable(_make_item(track_type='episode', is_playable=False))


def test_is_unavailable_null_track():
    assert not is_unavailable({'track': None, 'is_local': False})


def test_is_unavailable_null_id():
    assert not is_unavailable(_make_item(track_id=None, is_playable=False))


def test_is_unavailable_absent_is_playable():
    item = _make_item(is_playable=True)
    del item['track']['is_playable']
    assert not is_unavailable(item)  # absent = assume playable


def test_is_unavailable_restrictions_market():
    # is_playable may be absent; restrictions.reason='market' is the fallback signal
    item = _make_item(is_playable=True)
    del item['track']['is_playable']
    item['track']['restrictions'] = {'reason': 'market'}
    assert is_unavailable(item)


def test_is_unavailable_relinked_track():
    # Relinked tracks have is_playable=True (Spotify already substituted) — skip
    item = _make_item(is_playable=True)
    item['track']['linked_from'] = {'id': 'original_id', 'uri': 'spotify:track:original_id'}
    assert not is_unavailable(item)


# --- find_replacement ---

def _make_sp_search(candidates):
    sp = MagicMock()
    sp.search.return_value = {'tracks': {'items': candidates}}
    return sp


def _make_candidate(track_id, artist_name, popularity, is_playable=True):
    return {
        'id': track_id,
        'name': 'Same Song',
        'popularity': popularity,
        'is_playable': is_playable,
        'uri': f'spotify:track:{track_id}',
        'artists': [{'name': artist_name, 'id': 'a1'}],
        'album': {'name': 'Album', 'release_date': '2023-01-01'},
    }


def test_find_replacement_picks_highest_popularity():
    sp = _make_sp_search([
        _make_candidate('id1', 'Artist X', popularity=60),
        _make_candidate('id2', 'Artist X', popularity=85),
        _make_candidate('id3', 'Artist X', popularity=70),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result['id'] == 'id2'


def test_find_replacement_filters_same_id():
    # Original track ID returned in search results — must be excluded
    sp = _make_sp_search([
        _make_candidate('original_id', 'Artist X', popularity=95),
        _make_candidate('alt_id', 'Artist X', popularity=70),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result['id'] == 'alt_id'


def test_find_replacement_filters_covers():
    # Candidate with different artist should be excluded
    sp = _make_sp_search([
        _make_candidate('cover_id', 'Cover Artist', popularity=90),
        _make_candidate('real_id', 'Artist X', popularity=65),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result['id'] == 'real_id'


def test_find_replacement_filters_unplayable():
    sp = _make_sp_search([
        _make_candidate('id1', 'Artist X', popularity=80, is_playable=False),
        _make_candidate('id2', 'Artist X', popularity=60, is_playable=True),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result['id'] == 'id2'


def test_find_replacement_no_candidates():
    sp = _make_sp_search([])
    result = find_replacement(sp, 'Rare Track', 'Obscure Artist', 'original_id')
    assert result is None


def test_find_replacement_all_same_id():
    sp = _make_sp_search([
        _make_candidate('original_id', 'Artist X', popularity=95),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result is None


def test_find_replacement_artist_case_insensitive():
    sp = _make_sp_search([
        _make_candidate('id1', 'artist x', popularity=80),  # lowercase
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id')
    assert result['id'] == 'id1'
