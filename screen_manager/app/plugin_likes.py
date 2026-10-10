"""Likes of plugins (docs/PLUGINS.md, "Likes"): a heart a person gives a plugin that runs on one of their screens, so
others see which plugins people like.

The Tessera website counts them; the plugins repository copies the counts into likes.json every hour, and the app
reads that file from GitHub with the index (plugins.py), so looking at plugins never asks the website anything. A like
goes to the website only when someone taps the heart, and only this: the plugin's id, with this app's own random key
as the Bearer of the request. The key (secrets.token_hex(32)) is made at the first like and kept here; it is not a hash
of anything, says nothing about Home Assistant, a screen or a board, and stands for one installation of the app, so one
home is one like. The website keeps a hash of it. Taking the like back removes it there. Nothing is ever sent on a
schedule of its own, and a request that fails is not tried again: the heart says it did not go.

Storage: plugin_likes.json next to plugins.json (mode 0600), version 1: the key, whether the person agreed that a like
counts in a public number (asked once), and the plugins this app likes. A file with another version is left alone and
liking stays off until an app that knows it reads it.
"""
import asyncio
import json
import os
import re
import secrets
import tempfile
import threading
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

import feedback

LIKE_URL = f'{feedback.API}/plugins/{{plugin}}/like'
VERSION = 1
ID = re.compile(r'^[a-z][a-z0-9_]{0,31}$')


class Likes:
    def __init__(self, path):
        self.path = Path(path)
        self.lock = threading.RLock()
        self.data = {'version': VERSION, 'key': None, 'consented': False, 'liked': []}
        self.usable = True
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = None
        if isinstance(data, dict):
            if data.get('version') != VERSION:
                self.usable = False   # a newer app's file: left exactly as it is
            else:
                self.data.update({k: data[k] for k in ('key', 'consented', 'liked') if k in data})

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=self.path.parent, prefix=self.path.name + '.', suffix='.tmp')
        try:
            os.fchmod(fd, 0o600)
            with os.fdopen(fd, 'w') as handle:
                json.dump(self.data, handle, indent=1, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.path)
        except BaseException:
            try:
                os.unlink(temporary)
            except OSError:
                pass
            raise

    def liked(self, plugin):
        return plugin in (self.data.get('liked') or [])

    def consented(self):
        return bool(self.data.get('consented'))

    def _key(self):
        """This app's key, made and written down before the first request that carries it."""
        with self.lock:
            if not feedback.TOKEN_TEXT.fullmatch(str(self.data.get('key') or '')):
                self.data['key'] = feedback.new_token()
                self._save()
            return self.data['key']

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
        headers = {'Authorization': f'Bearer {self._key()}', 'Accept': 'application/json'}
        own = session is None
        session = session or ClientSession()
        try:
            async with session.request('PUT' if like else 'DELETE', LIKE_URL.format(plugin=plugin), headers=headers,
                                       timeout=ClientTimeout(total=10), allow_redirects=False) as response:
                if response.status != 200:
                    raise ValueError('like_failed')
                result = await response.json()
        except (ClientError, asyncio.TimeoutError, ValueError) as error:
            raise ValueError(str(error) if str(error) in ('like_failed',) else 'like_failed') from None
        finally:
            if own:
                await session.close()
        data = result.get('data') if isinstance(result, dict) else None
        if not isinstance(data, dict) or data.get('liked') is not like:
            raise ValueError('like_failed')
        with self.lock:
            liked = [p for p in (self.data.get('liked') or []) if p != plugin]
            self.data['liked'] = sorted(liked + ([plugin] if like else []))
            self._save()
        likes = data.get('likes')
        return {'liked': like, 'likes': likes if isinstance(likes, int) and likes >= 0 else None}
