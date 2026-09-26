"""Does this screen work as you expect? One answer per physical board, shared with the Tessera website (app 0.3.10).

The owner answers a short question on the screen's page in ESP Screens: yes, or not quite with what goes wrong. Only an
explicit answer leaves the app, and only this: the board's model (its key in boards.yaml, the same key the website uses),
the answer, the chosen problems, an optional note, and the firmware and app versions. Nothing about Home Assistant, the
screen's name, its entities or its logs.

Each board gets its own random key (secrets.token_hex(32)) the first time its owner shares an answer. The key is kept
here, in the app's private data, under the board's Home Assistant device id, and goes out only as the Bearer of a request
to the website: it is not a hash of anything, the device id itself never leaves, and two boards of one model get two
keys. The website keeps one latest answer per key; a changed answer is a higher revision of the same answer, and the
same revision with the same content is safe to send again, so a retry after a timeout never counts twice.

The answer, its revision and a new key are written to disk before the first request goes out. Requests for one board go
one at a time (a lock per board); a request that failed on the network is tried again after 1 minute, 5 minutes,
30 minutes and 6 hours (honouring Retry-After), and after 24 hours the app stops and offers to send it again by hand.
Deleting first stops those retries and waits for a request that is under way, so a late one cannot bring the deleted
answer back. Nothing is ever sent on a schedule of its own: no heartbeat, no daily report, nothing when the card shows.

Storage: feedback.json next to screens.json, version 1, readable only by the app. A file with another version is left
exactly as it is and the feature stays off until an app that knows it reads it.
"""
import asyncio
import contextlib
import json
import logging
import os
import random
import re
import secrets
import time
from pathlib import Path

from aiohttp import ClientError, ClientSession, ClientTimeout

LOG = logging.getLogger('screen_manager')

API = 'https://tessera-maxgramser.on-forge.com/api/v1/addon'
FEEDBACK_URL = f'{API}/feedback'
BOARDS_URL = f'{API}/boards'
PRIVACY_URL = 'https://tessera-maxgramser.on-forge.com/privacy'
STORAGE_VERSION = 1

OUTCOMES = ('working', 'not_working')
ISSUES = ('display', 'touch', 'connection', 'installation', 'other')
COMMENT_MAX = 1000
BODY_MAX = 8192
REVISION_MAX = 2147483647
# What the website takes as a version: letters, digits, dot, plus, underscore, space and hyphen, at most 80.
VERSION_TEXT = re.compile(r'[A-Za-z0-9.+_ -]{1,80}')
TOKEN_TEXT = re.compile(r'[0-9a-f]{64}')

# When the card asks by itself: a day after the board was first seen paired and online (a guess at "it has had a
# chance to work", never proof that it does), and 14 days after a Later. A second Later ends the asking.
ASK_AFTER = 24 * 3600
LATER = 14 * 86400
LATER_LIMIT = 2
# Tries after a network failure, 5xx or 429, then no more after a day.
RETRY_DELAYS = (60, 300, 1800, 21600)
GIVE_UP = 24 * 3600
# The website's list of models, kept for a day; asked only when an answer is about to go out.
CATALOGUE_TTL = 24 * 3600


def new_token():
    return secrets.token_hex(32)


def clean_version(value):
    """A version the website accepts, or None: never a build configuration or an address."""
    return value if isinstance(value, str) and VERSION_TEXT.fullmatch(value) else None


def clean_answer(outcome, issues, comment):
    """(outcome, issues, comment) as the website takes them, or ValueError with the field that is wrong."""
    if outcome not in OUTCOMES:
        raise ValueError('outcome')
    if issues is None:
        issues = []
    if not isinstance(issues, list) or any(issue not in ISSUES for issue in issues):
        raise ValueError('issues')
    issues = list(dict.fromkeys(issues))  # unique, in the order chosen
    if outcome == 'working':
        issues = []
    if comment is not None and not isinstance(comment, str):
        raise ValueError('comment')
    comment = (comment or '').strip() or None
    if comment and len(comment) > COMMENT_MAX:
        raise ValueError('comment')
    return outcome, issues, comment


async def send(session, token, payload=None, *, delete=False):
    """One request to the website, as its integration guide gives it. {'state': 'saved' | 'deleted' | 'retry' |
    'conflict' | 'invalid', ...}. Neither the key nor the body is ever logged."""
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    body = None
    if not delete:
        headers['Content-Type'] = 'application/json'
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        if len(body) > BODY_MAX:
            return {'state': 'invalid', 'status': 413}
    try:
        async with session.request('DELETE' if delete else 'POST', FEEDBACK_URL, data=body, headers=headers,
                                   timeout=ClientTimeout(total=10), allow_redirects=False) as response:
            if delete and response.status == 204:
                return {'state': 'deleted'}
            if not delete and response.status == 200:
                try:
                    result = await response.json()
                except (ValueError, ClientError):
                    return {'state': 'retry'}
                data = result.get('data') if isinstance(result, dict) else None
                if isinstance(data, dict) and data.get('status') == 'saved' and data.get('revision') == payload['revision']:
                    return {'state': 'saved', 'revision': data['revision']}
                return {'state': 'retry'}
            if response.status == 429:
                value = response.headers.get('Retry-After', '60')
                return {'state': 'retry', 'after': max(1, int(value)) if value.isdigit() else 60}
            if response.status >= 500:
                return {'state': 'retry'}
            if response.status == 409:
                return {'state': 'conflict'}
            return {'state': 'invalid', 'status': response.status}
    except (ClientError, asyncio.TimeoutError):
        return {'state': 'retry'}


async def fetch_boards(session):
    """The website's board ids, or None when it can't be asked right now."""
    try:
        async with session.get(BOARDS_URL, headers={'Accept': 'application/json'}, timeout=ClientTimeout(total=10),
                               allow_redirects=False) as response:
            if response.status != 200:
                return None
            result = await response.json()
    except (ClientError, asyncio.TimeoutError, ValueError):
        return None
    rows = result.get('data') if isinstance(result, dict) else None
    if not isinstance(rows, list):
        return None
    return {row['id'] for row in rows if isinstance(row, dict) and isinstance(row.get('id'), str)}


class Feedback:
    """Every board's answer, its key and when to ask, in feedback.json."""

    def __init__(self, path, clock=time.time, transport=send, catalogue=fetch_boards):
        self.path = Path(path)
        self.clock, self.transport, self.catalogue = clock, transport, catalogue
        self.boards, self.readonly = {}, False
        self.locks, self.timers = {}, {}
        self.session = None
        self.known_boards, self.known_at = None, 0.0
        # Said once after a deletion went through, so the page can confirm it; memory only.
        self.just_deleted = set()
        if self.path.exists():
            try:
                raw = json.loads(self.path.read_text(encoding='utf-8'))
            except (OSError, ValueError) as error:
                LOG.warning('Feedback stays off: %s cannot be read (%s)', self.path.name, type(error).__name__)
                self.readonly = True
                return
            if not isinstance(raw, dict) or raw.get('version') != STORAGE_VERSION:
                LOG.warning('Feedback stays off: %s has an unknown storage version; it stays unchanged', self.path.name)
                self.readonly = True
                return
            self.boards = {key: value for key, value in (raw.get('boards') or {}).items()
                           if isinstance(key, str) and isinstance(value, dict)}

    # ---- storage

    def save(self):
        if self.readonly:
            raise ValueError('feedback storage is read-only')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        with open(temp, 'w', encoding='utf8') as handle:
            os.chmod(temp, 0o600)
            json.dump({'version': STORAGE_VERSION, 'boards': self.boards}, handle, ensure_ascii=False)
            handle.flush()
            os.fsync(handle.fileno())
        temp.replace(self.path)

    def record(self, device):
        return self.boards.setdefault(device, {'next_revision': 1})

    def lock(self, device):
        return self.locks.setdefault(device, asyncio.Lock())

    # ---- asking

    def seen_usable(self, device):
        """The board is paired and online: the day before the card may ask starts now, once."""
        if self.readonly or not device:
            return
        record = self.boards.get(device)
        if record is None or 'first_usable_at' not in record:
            self.record(device)['first_usable_at'] = self.clock()
            self.save()

    def asks(self, device):
        record = self.boards.get(device) or {}
        now = self.clock()
        return (not self.readonly and not record.get('dismissed') and not record.get('answered')
                and record.get('later_count', 0) < LATER_LIMIT
                and isinstance(record.get('first_usable_at'), (int, float)) and now >= record['first_usable_at'] + ASK_AFTER
                and now >= record.get('ask_after', 0))

    def later(self, device):
        record = self.record(device)
        record['later_count'] = record.get('later_count', 0) + 1
        record['ask_after'] = self.clock() + LATER
        self.save()

    def never(self, device):
        self.record(device)['dismissed'] = True
        self.save()

    # ---- what the page sees: never the key, never a revision

    def view(self, device):
        record = self.boards.get(device) or {}
        pending = record.get('pending')
        if record.get('deletion_pending'):
            state = 'delete_failed' if record.get('stopped') else 'deleting'
        elif pending:
            state = 'failed' if record.get('stopped') else 'waiting'
        else:
            state = 'idle'
        answer = lambda payload: payload and {key: payload.get(key) for key in ('outcome', 'issues', 'comment')}
        return {
            'available': not self.readonly,
            'ask': self.asks(device),
            'answered': bool(record.get('answered')),
            'shared': answer(record.get('last_shared_answer')),
            'pending': answer(pending and pending.get('payload')),
            'state': state,
            'problem': record.get('problem'),
            'deleted': device in self.just_deleted,
            'retry_at': record.get('retry_at') if state in ('waiting', 'deleting') else None,
        }

    # ---- answering

    async def answer(self, device, board, outcome, issues=None, comment=None, versions=None):
        """A new answer from the owner: a new revision under the board's own key, stored first, then sent."""
        if self.readonly:
            raise ValueError('storage')
        outcome, issues, comment = clean_answer(outcome, issues, comment)
        known = await self.board_known(board)
        if known is False:
            raise ValueError('board')
        self.just_deleted.discard(device)
        self.cancel_timer(device)
        async with self.lock(device):
            record = self.record(device)
            if record.get('deletion_pending'):
                raise ValueError('deleting')
            if not TOKEN_TEXT.fullmatch(record.get('token') or ''):
                record['token'] = new_token()
            revision = int(record.get('next_revision') or 1)
            if revision > REVISION_MAX:
                raise ValueError('revision')
            payload = {'board_id': board, 'outcome': outcome, 'revision': revision, 'consent': True}
            if issues:
                payload['issues'] = issues
            for key in ('firmware_version', 'addon_version'):
                value = clean_version((versions or {}).get(key))
                if value:
                    payload[key] = value
            if comment:
                payload['comment'] = comment
            record.update({'next_revision': revision + 1, 'pending': {'payload': payload, 'since': self.clock()},
                           'attempts': 0, 'stopped': False, 'problem': None, 'answered': True, 'retry_at': None})
            self.save()
            await self._send_locked(device)

    async def retry(self, device):
        """Send again by hand what stopped after a day, or what is waiting for its next try."""
        self.cancel_timer(device)
        async with self.lock(device):
            record = self.boards.get(device)
            if not record or not (record.get('pending') or record.get('deletion_pending')):
                return
            if record.get('pending'):
                record['pending']['since'] = self.clock()
            record.update({'attempts': 0, 'stopped': False, 'retry_at': None, 'deletion_since': self.clock()})
            self.save()
            await self._send_locked(device)

    async def cancel(self, device):
        """Don't send the answer that is still waiting. What was shared before stays shared."""
        self.cancel_timer(device)
        async with self.lock(device):
            record = self.boards.get(device)
            if record and record.get('pending'):
                record.update({'pending': None, 'attempts': 0, 'stopped': False, 'retry_at': None})
                self.save()

    async def delete(self, device):
        """Delete the shared answer on the website: first stop the retries and wait for a request under way."""
        if self.readonly:
            raise ValueError('storage')
        self.cancel_timer(device)
        async with self.lock(device):
            record = self.boards.get(device)
            if not record:
                return
            if not TOKEN_TEXT.fullmatch(record.get('token') or ''):
                # Nothing ever left this app for this board.
                record.update({'pending': None, 'last_shared_answer': None})
                self.save()
                return
            record.update({'pending': None, 'deletion_pending': True, 'attempts': 0, 'stopped': False,
                           'problem': None, 'retry_at': None, 'deletion_since': self.clock()})
            self.save()
            await self._send_locked(device)

    # ---- sending

    async def board_known(self, board):
        """Whether the website knows this model: True, False, or None when its list can't be read (then the ids of
        boards.yaml, which are the website's own, decide, and the website refuses a model it doesn't have)."""
        now = self.clock()
        if self.known_boards is None or now - self.known_at > CATALOGUE_TTL:
            boards = await self.catalogue(self.client())
            if boards:
                self.known_boards, self.known_at = boards, now
        return None if self.known_boards is None else board in self.known_boards

    def client(self):
        # Its own session: no Home Assistant token or Supervisor header, certificate checks on.
        if self.session is None or self.session.closed:
            self.session = ClientSession()
        return self.session

    async def _send_locked(self, device):
        record = self.boards.get(device)
        if not record or not TOKEN_TEXT.fullmatch(record.get('token') or ''):
            return
        deleting = bool(record.get('deletion_pending'))
        pending = record.get('pending')
        if not deleting and not pending:
            return
        result = await self.transport(self.client(), record['token'], None if deleting else pending['payload'], delete=deleting)
        state = result.get('state')
        if deleting and state == 'deleted':
            record.update({'deletion_pending': False, 'last_shared_answer': None, 'last_ack_revision': None,
                           'attempts': 0, 'stopped': False, 'retry_at': None, 'problem': None})
            self.just_deleted.add(device)
            LOG.info('Feedback: the shared answer of a screen was deleted')
        elif not deleting and state == 'saved':
            record.update({'last_ack_revision': pending['payload']['revision'], 'last_shared_answer': pending['payload'],
                           'pending': None, 'attempts': 0, 'stopped': False, 'retry_at': None, 'problem': None})
            LOG.info('Feedback: a screen\'s answer was received')
        elif state == 'retry':
            since = (record.get('deletion_since') if deleting else pending.get('since')) or self.clock()
            attempts = int(record.get('attempts') or 0) + 1
            delay = max(result.get('after') or 0, RETRY_DELAYS[min(attempts - 1, len(RETRY_DELAYS) - 1)])
            delay *= random.uniform(1.0, 1.15)
            record['attempts'] = attempts
            if self.clock() + delay > since + GIVE_UP:
                record.update({'stopped': True, 'retry_at': None})
                LOG.info('Feedback: not sent after a day of tries; ESP Screens offers to send it again')
            else:
                record['retry_at'] = self.clock() + delay
                self.schedule(device, delay)
        else:
            # 409: an older or different answer under this key; 401, 413, 415, 422 and the rest: this request will not
            # get better by sending it again. Stop, say so, and leave a new choice to the owner.
            status = result.get('status')
            record.update({'pending': None, 'retry_at': None, 'stopped': False, 'attempts': 0,
                           'problem': 'conflict' if state == 'conflict' else 'rejected'})
            if deleting:
                record['deletion_pending'] = False
            LOG.warning('Feedback: the website did not take the %s (%s)', 'deletion' if deleting else 'answer',
                        'conflict' if state == 'conflict' else f'HTTP {status}')
        self.save()

    # ---- timers

    def schedule(self, device, delay):
        self.cancel_timer(device)
        self.timers[device] = asyncio.get_running_loop().create_task(self._later_try(device, delay))

    def cancel_timer(self, device):
        """Only a timer that is still waiting: one that started its request is out of this table and finishes under
        the board's lock, which the caller then waits for."""
        timer = self.timers.pop(device, None)
        if timer and not timer.done():
            timer.cancel()

    async def _later_try(self, device, delay):
        await asyncio.sleep(delay)
        if self.timers.get(device) is asyncio.current_task():
            del self.timers[device]
        async with self.lock(device):
            await self._send_locked(device)

    def start(self):
        """After a restart: what was waiting to go out tries again in about a minute, unless a day has passed."""
        if self.readonly:
            return
        now = self.clock()
        for device, record in self.boards.items():
            if record.get('stopped') or not (record.get('pending') or record.get('deletion_pending')):
                continue
            wanted = record.get('retry_at') or now
            self.schedule(device, max(60.0, wanted - now) * random.uniform(1.0, 1.15))

    async def close(self):
        for device in list(self.timers):
            self.cancel_timer(device)
        if self.session is not None and not self.session.closed:
            with contextlib.suppress(Exception):
                await self.session.close()
