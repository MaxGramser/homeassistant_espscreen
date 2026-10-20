"""Likes, ratings and counting of plugins (docs/PLUGINS.md, "Likes, ratings and counting"): what a person shares about
the plugins of the index, so others find the good ones and their makers see that their work is used.

- A like is a heart for any plugin of the index, also one that runs on none of this app's screens: a thank-you.
- A rating is one to five stars for a plugin that runs on one of this app's screens, with its version and the model of
  the screen. The card that asks for one (ask_for) comes ASK_AFTER after a screen first ran the plugin.
- Counting, off until the person turns it on, tells the website once a day (and soon after a change) which plugins of
  the index this app's screens run, as Home Assistant's own analytics does for integrations.

The Tessera website counts them; the plugins repository copies the numbers into likes.json and stats.json every hour,
and the app reads those from GitHub with the index (plugins.py), so looking at plugins never asks the website anything.
A request goes to the website only when someone taps a heart or a star, or while counting is on, and carries only the
plugin's id (with a rating its stars, version and screen model; with counting the ids, versions and screen models), with
this app's own random key as the Bearer. The key (secrets.token_hex(32)) is made at the first request and kept here;
it is not a hash of anything, says nothing about Home Assistant, a screen or a board, and stands for one installation of
the app, so one home is one like. The website keeps a hash of it. Taking a like or a rating back removes it there, and
turning counting off deletes what was counted. A like or a rating that fails is not tried again: the control says it
did not go.

Storage: plugin_likes.json next to plugins.json (mode 0600), version 1: the key, whether the person agreed that a like
counts in a public number (asked once), the plugins this app likes, and, kept beside them by apps since ratings came,
its ratings (`rated`), when each screen first ran each plugin (`seen`), whether the cards may ask (`asking`, `later`),
and counting (`counting`, `counting_asked`, `counted`, `sent`). An app from before ratings reads the same file and keeps
its likes. A file with another version is left alone and all of this stays off until an app that knows it reads it.
"""
import asyncio
import hashlib
import json
import re
import threading
import time
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

import feedback
import atomic

LIKE_URL = f'{feedback.API}/plugins/{{plugin}}/like'
RATE_URL = f'{feedback.API}/plugins/{{plugin}}/rating'
USAGE_URL = f'{feedback.API}/plugins/usage'
VERSION = 1
ID = re.compile(r'^[a-z][a-z0-9_]{0,31}$')
# The card asks for stars once a screen has run the plugin this long: time to have seen it work, as the board's card
# waits a day. A Later asks again after LATER, a second Later ends the asking for that plugin, as on the board's card.
ASK_AFTER = 5 * 86400
LATER = 14 * 86400
LATER_LIMIT = 2
# Counting: once a day, as Home Assistant's analytics; one that did not go tries again after RETRY.
DAILY = 86400
RETRY = 3600
STATE_KEYS = ('key', 'consented', 'liked', 'rated', 'seen', 'asking', 'later', 'counting', 'counting_asked', 'counted',
              'sent')


class Likes:
    def __init__(self, path, clock=time.time):
        self.path = Path(path)
        self.clock = clock
        self.lock = threading.RLock()
        self.data = {'version': VERSION, 'key': None, 'consented': False, 'liked': [], 'rated': {}, 'seen': {},
                     'asking': True, 'later': {}, 'counting': False, 'counting_asked': False, 'counted': None,
                     'sent': None}
        data = atomic.read_json(self.path, VERSION)
        self.usable = not atomic.frozen(self.path)   # a newer app's file: left exactly as it is
        if data:
            self.data.update({k: data[k] for k in STATE_KEYS if k in data})
        self.retry_at = 0.0   # counting that did not go waits until then (kept only while the app runs)

    def _save(self):
        atomic.write_json(self.path, self.data, indent=1, sort_keys=True)

    def liked(self, plugin):
        return plugin in (self.data.get('liked') or [])

    def consented(self):
        return bool(self.data.get('consented'))

    def stars(self, plugin):
        """This app's stars for a plugin, or None."""
        rated = (self.data.get('rated') or {}).get(plugin)
        return rated.get('stars') if isinstance(rated, dict) else None

    def counting(self):
        return bool(self.data.get('counting'))

    def view(self):
        """What the editor shows about this app's sharing: never the key."""
        return {'consented': self.consented(), 'counting': self.counting(),
                'counting_asked': bool(self.data.get('counting_asked')), 'asking': bool(self.data.get('asking', True)),
                'counted': self.data.get('counted'), 'usable': self.usable}

    def _key(self):
        """This app's key, made and written down before the first request that carries it."""
        with self.lock:
            if not feedback.TOKEN_TEXT.fullmatch(str(self.data.get('key') or '')):
                self.data['key'] = feedback.new_token()
                self._save()
            return self.data['key']

    async def _request(self, method, url, body=None, session=None):
        """The website's `data` for one request, else ValueError('failed')."""
        headers = {'Authorization': f'Bearer {self._key()}', 'Accept': 'application/json'}
        own = session is None
        session = session or ClientSession()
        try:
            async with session.request(method, url, headers=headers, json=body, timeout=ClientTimeout(total=10),
                                       allow_redirects=False) as response:
                if response.status != 200:
                    raise ValueError('failed')
                result = await response.json()
        except (ClientError, asyncio.TimeoutError, ValueError):
            raise ValueError('failed') from None
        finally:
            if own:
                await session.close()
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, dict):
            raise ValueError('failed')
        return data

    # ---- Likes ----

    async def send(self, plugin, like, consent=False, session=None):
        """Like (or take back the like of) one plugin at the website. {'liked': bool, 'likes': count or None} when it
        went, else ValueError with the reason as a key of addon.errors.plugins: like_consent, like_off, like_failed."""
        if not ID.match(str(plugin or '')):
            raise ValueError('request')
        if not self.usable:
            raise ValueError('like_off')
        if like and not self.consented() and not consent:
            raise ValueError('like_consent')
        if consent and not self.consented():
            with self.lock:
                self.data['consented'] = True
                self._save()
        try:
            data = await self._request('PUT' if like else 'DELETE', LIKE_URL.format(plugin=plugin), session=session)
        except ValueError:
            raise ValueError('like_failed') from None
        if data.get('liked') is not like:
            raise ValueError('like_failed')
        with self.lock:
            liked = [p for p in (self.data.get('liked') or []) if p != plugin]
            self.data['liked'] = sorted(liked + ([plugin] if like else []))
            self._save()
        likes = data.get('likes')
        return {'liked': like, 'likes': likes if isinstance(likes, int) and likes >= 0 else None}

    # ---- Ratings ----

    async def rate(self, plugin, stars, version=None, board=None, session=None):
        """Rate one plugin with one to five stars, or take the rating back (stars None). {'stars', 'rating', 'ratings'}
        from the website's answer when it went, else ValueError: rate_off, rate_failed, request."""
        if not ID.match(str(plugin or '')) or not (stars is None or (isinstance(stars, int) and not isinstance(stars, bool)
                                                                     and 1 <= stars <= 5)):
            raise ValueError('request')
        if not self.usable:
            raise ValueError('rate_off')
        version = feedback.clean_version(version)
        version = version if version and re.fullmatch(r'[A-Za-z0-9.+_-]{1,40}', version) else None
        board = board if isinstance(board, str) and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}', board) else None
        body = {'stars': stars, **({'version': version} if version else {}), **({'board_id': board} if board else {})}
        try:
            data = await self._request('PUT' if stars else 'DELETE', RATE_URL.format(plugin=plugin),
                                       body if stars else None, session=session)
        except ValueError:
            raise ValueError('rate_failed') from None
        if data.get('stars') != stars:
            raise ValueError('rate_failed')
        with self.lock:
            rated = dict(self.data.get('rated') or {})
            if stars:
                rated[plugin] = {'stars': stars, 'version': version, 'board': board}
            else:
                rated.pop(plugin, None)
            self.data['rated'] = rated
            (self.data.get('later') or {}).pop(plugin, None)
            self._save()
        rating, ratings = data.get('rating'), data.get('ratings')
        return {'stars': stars, 'rating': rating if isinstance(rating, (int, float)) and not isinstance(rating, bool) else None,
                'ratings': ratings if isinstance(ratings, int) and ratings >= 0 else None}

    # ---- When the card asks ----

    def saw(self, inbox, plugins, now=None):
        """The plugins a screen runs now (its hello): the first time each ran there is kept, for ask_for."""
        if not self.usable or not plugins:
            return
        now = int(self.clock() if now is None else now)
        with self.lock:
            seen = self.data.setdefault('seen', {})
            changed = False
            for plugin in plugins:
                if ID.match(str(plugin)) and inbox not in (seen.get(plugin) or {}):
                    seen.setdefault(plugin, {})[inbox] = now
                    changed = True
            if changed:
                self._save()

    def ask_for(self, inbox, plugins, now=None):
        """The plugin of `plugins` (those of the index this screen runs) the card asks stars for on this screen, with
        the days since the screen first ran it: (id, days), or None. The one that has run longest goes first."""
        if not self.usable or not self.data.get('asking', True):
            return None
        now = self.clock() if now is None else now
        rated = self.data.get('rated') or {}
        later = self.data.get('later') or {}
        waiting = []
        for plugin in plugins:
            since = (self.data.get('seen') or {}).get(plugin, {}).get(inbox)
            put_off = later.get(plugin) or {}
            if since is None or plugin in rated or now - since < ASK_AFTER:
                continue
            if put_off.get('count', 0) >= LATER_LIMIT or now < put_off.get('next', 0):
                continue
            waiting.append((since, plugin))
        if not waiting:
            return None
        since, plugin = min(waiting)
        return plugin, int((now - since) // 86400)

    def later(self, plugin, now=None):
        """Ask about this plugin again after LATER; a second Later ends the asking for it."""
        now = self.clock() if now is None else now
        with self.lock:
            later = self.data.setdefault('later', {})
            count = (later.get(plugin) or {}).get('count', 0) + 1
            later[plugin] = {'count': count, 'next': int(now + LATER)}
            self._save()

    def never(self, asking=False):
        """The cards ask for no plugin's stars again (the Plugins page still takes them), or, from Settings, again."""
        with self.lock:
            self.data['asking'] = bool(asking)
            if asking:
                self.data['later'] = {}
            self._save()

    # ---- Counting ----

    async def set_counting(self, on, session=None):
        """Turn counting on (the next tick sends) or off (what was counted is deleted at the website first)."""
        if not self.usable:
            raise ValueError('rate_off')
        if not on and (self.data.get('counted') or self.data.get('sent')):
            try:
                await self._request('DELETE', USAGE_URL, session=session)
            except ValueError:
                raise ValueError('count_failed') from None
        with self.lock:
            self.data.update(counting=bool(on), counting_asked=True, sent=None, **({} if on else {'counted': None}))
            self._save()

    def asked_counting(self):
        """The first card asked whether to count, and the answer was no: it does not ask again."""
        with self.lock:
            if not self.data.get('counting_asked'):
                self.data['counting_asked'] = True
                self._save()

    def usage_due(self, plugins, now=None):
        """Whether counting sends `plugins` now: on, and a day since the last time, or the list changed since."""
        if not self.usable or not self.counting():
            return False
        now = self.clock() if now is None else now
        if now < self.retry_at:
            return False
        counted = self.data.get('counted') or 0
        return now - counted >= DAILY or (self.data.get('sent') != fingerprint(plugins) and now - counted >= 60)

    async def send_usage(self, plugins, now=None, session=None):
        """Tell the website which plugins this app's screens run: [{'id', 'version', 'boards'}]. True when it went; one
        that did not tries again after RETRY."""
        now = self.clock() if now is None else now
        try:
            await self._request('PUT', USAGE_URL, {'plugins': plugins}, session=session)
        except ValueError:
            self.retry_at = now + RETRY
            return False
        self.retry_at = 0.0
        with self.lock:
            if self.data.get('counting'):
                self.data.update(counted=int(now), sent=fingerprint(plugins))
                self._save()
        return True


def fingerprint(plugins):
    """A short mark of what was sent, so a change shows without keeping the list."""
    return hashlib.sha256(json.dumps(plugins, sort_keys=True).encode()).hexdigest()[:16]
