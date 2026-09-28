"""Optional Spotify catalogue for voice. Playback always goes through HA.

Client credentials grant catalogue access only. Never reuse HA's private OAuth
storage, send these credentials to an AI provider or accept model-written URIs.
"""
import asyncio
from base64 import b64encode
import json
import re
import secrets
import time

from aiohttp import ClientError, ClientTimeout

TOKEN_URL = 'https://accounts.spotify.com/api/token'
SEARCH_URL = 'https://api.spotify.com/v1/search'
RESULT_SECONDS = 300


def credentials(data):
    if not isinstance(data, dict) or set(data) != {'client_id', 'client_secret', 'market'}:
        raise ValueError('Enter the Spotify Client ID, Client Secret and country code.')
    result = {}
    for field in ('client_id', 'client_secret'):
        value = data[field]
        if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{16,128}', value.strip()):
            raise ValueError('Enter the complete Spotify Client ID and Client Secret.')
        result[field] = value.strip()
    market = data['market']
    if not isinstance(market, str) or not re.fullmatch(r'[A-Za-z]{2}', market.strip()):
        raise ValueError('Enter a two-letter country code, such as NL or GB.')
    result['market'] = market.strip().upper()
    return result


def player_platform(ha, eid):
    return next((e.get('platform') for e in ha.registry if e.get('entity_id') == eid), None)


def supports_player(ha, eid):
    return player_platform(ha, eid) in ('sonos', 'spotify')


async def payload(response):
    if response.status == 429:
        raise ValueError('Spotify search is rate limited. Try again later.')
    if response.status in (400, 401, 403):
        raise ValueError('Spotify search was refused. Check the Spotify app credentials, access and country in Voice assistant settings.')
    if response.status != 200:
        raise ConnectionError('Spotify search is unavailable.')
    raw = bytearray()
    async for chunk in response.content.iter_chunked(16384):
        raw.extend(chunk)
        if len(raw) > 512 * 1024:
            raise ValueError('Spotify returned an oversized response.')
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError('Spotify returned an invalid response.')
    return data


class SpotifyCatalogue:
    def __init__(self, settings=None):
        self.settings = credentials(settings) if settings else None
        self.token, self.expires = '', 0
        self.lock = asyncio.Lock()

    @property
    def configured(self):
        return self.settings is not None

    def status(self):
        return {'configured': self.configured, 'market': self.settings['market'] if self.settings else ''}

    async def access_token(self, http):
        async with self.lock:
            if self.token and time.monotonic() < self.expires:
                return self.token
            encoded = b64encode((self.settings['client_id'] + ':' + self.settings['client_secret']).encode()).decode()
            async with http.post(TOKEN_URL, headers={'Authorization': 'Basic ' + encoded},
                    data={'grant_type': 'client_credentials'}, allow_redirects=False,
                    timeout=ClientTimeout(total=10)) as response:
                data = await payload(response)
            token, expires = data.get('access_token'), data.get('expires_in')
            if not isinstance(token, str) or not token or len(token) > 4096 or not token.isascii() or any(c.isspace() or ord(c) < 33 for c in token):
                raise ValueError('Spotify returned an invalid access token.')
            if type(expires) is not int or not 0 < expires <= 86400:
                raise ValueError('Spotify returned an invalid token lifetime.')
            self.token, self.expires = token, time.monotonic() + max(0, expires - 30)
            return token

    async def search(self, http, title, artist):
        if not self.configured:
            return {'status': 'not_configured', 'message': 'Set up Spotify search in Settings > Voice assistant. Playback controls remain available.'}
        # Quotes in a spoken name are data, never extra Spotify query operators.
        query = 'track:"' + title.replace('"', ' ') + '"'
        if artist:
            query += ' artist:"' + artist.replace('"', ' ') + '"'
        try:
            token = await self.access_token(http)
            async with http.get(SEARCH_URL, headers={'Authorization': 'Bearer ' + token},
                    params={'q': query, 'type': 'track', 'limit': 5, 'market': self.settings['market']},
                    allow_redirects=False, timeout=ClientTimeout(total=15)) as response:
                if response.status == 401:
                    self.token, self.expires = '', 0
                data = await payload(response)
        except (ClientError, TimeoutError):
            raise ConnectionError('Spotify search is unavailable.') from None
        tracks = data.get('tracks')
        if not isinstance(tracks, dict) or not isinstance(tracks.get('items'), list):
            raise ValueError('Spotify returned invalid search results.')
        results, seen = [], set()
        for item in tracks['items'][:5]:
            if not isinstance(item, dict) or item.get('is_playable') is False or item.get('restrictions'):
                continue
            track_id, title = item.get('id'), item.get('name')
            if not isinstance(track_id, str) or not re.fullmatch(r'[a-zA-Z0-9]{22}', track_id) or track_id in seen:
                continue
            if item.get('type') != 'track' or item.get('uri') != f'spotify:track:{track_id}' or not isinstance(title, str) or not title.strip():
                continue
            artists = item.get('artists')
            names = [a['name'][:240] for a in artists[:10] if isinstance(a, dict) and isinstance(a.get('name'), str) and a['name'].strip()] if isinstance(artists, list) else []
            album = item.get('album')
            if not names or not isinstance(album, dict) or not isinstance(album.get('name'), str):
                continue
            seen.add(track_id)
            results.append({'uri': item['uri'], 'title': title[:240], 'artists': names, 'album': album['name'][:240]})
        return {'status': 'ok' if results else 'not_found', 'tracks': results}


def remember(results, entity_id, tracks):
    now = time.monotonic()
    for key in list(results):
        if results[key]['expires'] <= now:
            del results[key]
    while len(results) + len(tracks) > 32:
        del results[next(iter(results))]
    public = []
    for track in tracks:
        key = secrets.token_urlsafe(12)
        results[key] = {'entity_id': entity_id, 'expires': now + RESULT_SECONDS, **track}
        public.append({'result_id': key, **{k: v for k, v in track.items() if k != 'uri'}})
    return public


def selection(results, entity_id, result_id):
    if not isinstance(result_id, str) or len(result_id) > 64:
        raise ValueError('Choose a result from the current music search.')
    track = results.get(result_id)
    if not track or track['expires'] <= time.monotonic() or track['entity_id'] != entity_id:
        raise ValueError('That music result expired or belongs to another player. Search again.')
    return track
