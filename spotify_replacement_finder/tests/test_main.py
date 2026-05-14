import pytest
from unittest.mock import MagicMock
from main import extract_playlist_id, find_playlist_by_name, needs_replacement, find_replacement, get_track

MARKET = 'NL'


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


# --- get_track ---

def test_get_track_uses_track_field():
    item = {'track': {'id': '1'}, 'item': {'id': '2'}}
    assert get_track(item)['id'] == '1'


def test_get_track_falls_back_to_item_field():
    item = {'track': None, 'item': {'id': '2'}}
    assert get_track(item)['id'] == '2'


def test_get_track_local_file_uses_item_field():
    item = {'is_local': True, 'track': None, 'item': {'id': None, 'name': 'Song', 'type': 'track'}}
    assert get_track(item)['name'] == 'Song'


# --- needs_replacement ---

def _make_item(is_local=False, track_type='track', track_id='abc123',
               available_markets=None, is_playable=None, restrictions=None, name='Test Track'):
    track = {
        'id': track_id,
        'type': track_type,
        'name': name,
        'uri': f'spotify:track:{track_id}',
        'artists': [{'name': 'Test Artist'}],
    }
    if available_markets is not None:
        track['available_markets'] = available_markets
    if is_playable is not None:
        track['is_playable'] = is_playable
    if restrictions is not None:
        track['restrictions'] = restrictions
    return {'is_local': is_local, 'track': track}


def test_needs_replacement_playable_track_in_market():
    item = _make_item(available_markets=['NL', 'DE', 'BE'])
    assert not needs_replacement(item, MARKET)


def test_needs_replacement_track_not_in_market():
    item = _make_item(available_markets=['US', 'GB'])
    assert needs_replacement(item, MARKET)


def test_needs_replacement_local_file_skipped_by_default():
    item = _make_item(is_local=True, track_id=None)
    item['track']['id'] = None
    assert not needs_replacement(item, MARKET)  # default: skip local files


def test_needs_replacement_local_file_with_replace_local():
    item = _make_item(is_local=True, track_id=None)
    item['track']['id'] = None
    assert needs_replacement(item, MARKET, replace_local=True)


def test_needs_replacement_local_file_without_name():
    item = _make_item(is_local=True, track_id=None, name=None)
    item['track']['id'] = None
    item['track']['name'] = None
    assert not needs_replacement(item, MARKET, replace_local=True)  # no name → can't search


def test_needs_replacement_null_track():
    assert not needs_replacement({'track': None, 'is_local': False}, MARKET)


def test_needs_replacement_episode():
    item = _make_item(track_type='episode')
    assert not needs_replacement(item, MARKET)


def test_needs_replacement_is_playable_false():
    item = _make_item(is_playable=False)
    assert needs_replacement(item, MARKET)


def test_needs_replacement_restrictions_market():
    item = _make_item(restrictions={'reason': 'market'})
    assert needs_replacement(item, MARKET)


def test_needs_replacement_no_available_markets_field():
    # available_markets absent → assume playable (e.g. for markets we can't check)
    item = _make_item()  # no available_markets key
    assert not needs_replacement(item, MARKET)


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
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id', MARKET)
    assert result['id'] == 'id2'


def test_find_replacement_filters_same_id():
    sp = _make_sp_search([
        _make_candidate('original_id', 'Artist X', popularity=95),
        _make_candidate('alt_id', 'Artist X', popularity=70),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id', MARKET)
    assert result['id'] == 'alt_id'


def test_find_replacement_filters_same_id_none():
    # Local files have id=None — all results are valid candidates
    sp = _make_sp_search([
        _make_candidate('id1', 'Artist X', popularity=80),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', None, MARKET)
    assert result['id'] == 'id1'


def test_find_replacement_filters_covers():
    sp = _make_sp_search([
        _make_candidate('cover_id', 'Cover Artist', popularity=90),
        _make_candidate('real_id', 'Artist X', popularity=65),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id', MARKET)
    assert result['id'] == 'real_id'


def test_find_replacement_filters_unplayable():
    sp = _make_sp_search([
        _make_candidate('id1', 'Artist X', popularity=80, is_playable=False),
        _make_candidate('id2', 'Artist X', popularity=60, is_playable=True),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id', MARKET)
    assert result['id'] == 'id2'


def test_find_replacement_no_candidates():
    sp = _make_sp_search([])
    result = find_replacement(sp, 'Rare Track', 'Obscure Artist', 'original_id', MARKET)
    assert result is None


def test_find_replacement_artist_case_insensitive():
    sp = _make_sp_search([
        _make_candidate('id1', 'artist x', popularity=80),
    ])
    result = find_replacement(sp, 'Same Song', 'Artist X', 'original_id', MARKET)
    assert result['id'] == 'id1'
