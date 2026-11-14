"""The icons a screen takes on top of the fixed set (docs/ICONS.md).

Icons are compiled into a screen's firmware, so an icon of its own means a build. Per screen this keeps three lists of
names: `chosen` (what the person wants), `written` (what the screen's plugins file says, so what its next build brings)
and `built` (what went onto the screen). What a screen is sent follows `built` (tile_icons.carrying); until a build is
done a chosen icon shows as `auto`, and a build that fails puts the file back to `built`.

The icons travel in the screen's plugins file (Plugins.sidecar) as an `!extend` of the three fonts of packages/core.yaml
whose list they join. An icon the fixed set has must never be in that list, ESPHome stops at a glyph it finds twice, so
the file is written again before every build (`before_build`): a release can move an icon into the set.
"""
import json
import logging
import threading
from pathlib import Path

import atomic
import core
import tile_icons
from build_queue import Round
from i18n import t

LOG = logging.getLogger('screen_manager')
VERSION = 1
# The fonts a screen's icons join: the ones that carry the whole fixed set (a card's icon, the small one of a small card
# and of the top bar, the watch's). The big font keeps its own short list and a card falls back from it.
FONTS = ('materialdesign_icons', 'materialdesign_icons_mini', 'watch_icon')
SUGGESTED = 40


class ScreenIcons:
    def __init__(self, manager, data_dir):
        self.manager = manager
        self.path = Path(data_dir) / 'screen_icons.json'
        self.lock = threading.RLock()
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            data = {}
        self.screens = data.get('screens') if isinstance(data, dict) and isinstance(data.get('screens'), dict) else {}

    def save(self):
        with self.lock:
            atomic.write_text(self.path, json.dumps({'version': VERSION, 'screens': self.screens}, separators=(',', ':')), 0o644)

    # ---- what a screen has ----
    def record(self, inbox):
        entry = self.screens.get(inbox) or {}
        return {key: [name for name in entry.get(key) or [] if isinstance(name, str)] for key in ('chosen', 'written', 'built')}

    def _put(self, inbox, record):
        with self.lock:
            if any(record.values()):
                self.screens[inbox] = record
            else:
                self.screens.pop(inbox, None)
            self.save()

    @staticmethod
    def beyond_set(names):
        """These names in order, without the fixed set's and the names no icon has: what a build has to add."""
        table = tile_icons.mdi()
        return list(dict.fromkeys(name for name in names if name not in tile_icons.GLYPHS and name in table))

    def on_screen(self, inbox):
        """{name: codepoint} of the icons of its own this screen's firmware has."""
        entry = self.screens.get(inbox)
        if not entry:
            return {}
        table = tile_icons.mdi()
        return {name: table[name][0] for name in self.beyond_set(entry.get('built') or [])}

    def room(self, screen):
        """How many icons of its own this screen may have: none on a board with 4 MB of flash, or one this app has no shape of."""
        board = core.SHAPES.get(core.board_of(screen)) if isinstance(screen, dict) else None
        return tile_icons.room() if board and board.get('own_icons') else 0

    def font_lines(self, inbox):
        """The `font:` part of this screen's plugins file; nothing for a screen without icons of its own, whose build stays
        as it was."""
        names = self.beyond_set(self.record(inbox)['written'])
        if not names:
            return []
        table = tile_icons.mdi()
        lines = ['font:']
        for index, font in enumerate(FONTS):
            lines.append(f'  - id: !extend {font}')
            if index == 0:
                lines.append('    glyphs: &own_icons')
                lines += [f'      - "\\U000{table[name][0]}" # {name}' for name in names]
            else:
                lines.append('    glyphs: *own_icons')
        return lines

    # ---- the editor ----
    def view(self, inbox):
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        inbox = screen['id']
        record, table = self.record(inbox), tile_icons.mdi()
        chosen, built = self.beyond_set(record['chosen']), self.beyond_set(record['built'])
        builds = self.manager.build_queue.on_the_way(screen=inbox)
        own_yaml = not self.manager.updates.resolve(screen)[0]
        return {'room': self.room(screen), 'most': tile_icons.MOST_ICONS, 'fixed': len(tile_icons.GLYPHS), 'chosen': chosen, 'built': built,
                'waiting': [name for name in chosen if name not in built], 'leaving': [name for name in built if name not in chosen],
                'building': any(build.icons for build in builds), 'own_yaml': own_yaml,
                'icons': {name: table[name] for name in dict.fromkeys(chosen + built)}, 'suggested': self.suggested(chosen)}

    def suggested(self, chosen):
        """The icons Home Assistant gives the entities of this house that this screen cannot draw: those on most entities first."""
        table, taken = tile_icons.mdi(), set(chosen) | set(tile_icons.GLYPHS)
        counts = {}
        for state in (getattr(self.manager.ha, 'states', None) or {}).values():
            icon = (state.get('attributes') or {}).get('icon') if isinstance(state, dict) else None
            if isinstance(icon, str) and icon.startswith('mdi:') and icon[4:] in table and icon[4:] not in taken:
                counts[icon[4:]] = counts.get(icon[4:], 0) + 1
        return sorted(counts, key=lambda name: (-counts[name], name))[:SUGGESTED]

    def choose(self, inbox, names):
        """The icons this screen should have; nothing is built yet."""
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        if not isinstance(names, list) or not all(isinstance(name, str) for name in names):
            raise ValueError(t('addon.errors.icons.request'))
        wanted = self.beyond_set(names)
        room = self.room(screen)
        if len(wanted) > room:
            raise ValueError(t('addon.errors.icons.too_many', most=room))
        inbox = screen['id']
        self._put(inbox, {**self.record(inbox), 'chosen': wanted})
        return self.view(inbox)

    # ---- building ----
    def _write(self, inbox, record):
        self._put(inbox, record)
        self.manager.plugins.rewrite_sidecar(inbox)

    def apply(self, inbox, round=None):
        """Build this screen with the icons chosen for it, in the build line. {'queued': turn}, or for a screen built from
        its own YAML the file and the line to add ({'own_yaml': True, ...}), which counts as on the screen."""
        screen = self.manager.screen(inbox)
        if screen is None:
            raise ValueError(t('addon.errors.not_paired'))
        inbox = screen['id']
        profile, host = self.manager.updates.resolve(screen)
        record = self.record(inbox)
        wanted = self.beyond_set(record['chosen'])
        if not profile:
            self._put(inbox, {**record, 'written': wanted, 'built': wanted})
            return {'own_yaml': True, **self.manager.plugins.file_for(inbox)}
        if not host:
            raise ValueError(t('addon.errors.plugins.offline', screen=screen.get('name') or screen.get('node') or inbox))
        self._write(inbox, {**record, 'written': wanted})
        line = self.manager.build_queue
        build = line.add('icons', profile, self._build, screen=inbox, target=host, round=round)
        if self._ended not in build.ends:
            build.ends.append(self._ended)
        self.manager.notify()
        return {'queued': line.place(build)}

    def apply_everywhere(self, inbox):
        """This screen's icons on every screen with room for them, each one a build, as one round: a build that fails ends
        the ones that still wait. A screen that is off is told apart and keeps its icons chosen."""
        source = self.manager.screen(inbox)
        if source is None:
            raise ValueError(t('addon.errors.not_paired'))
        wanted = self.beyond_set(self.record(source['id'])['chosen'])
        queued, off, own_yaml = [], [], []
        round = Round()
        for screen in self.manager.screens():
            if screen.get('virtual') or not self.room(screen):
                continue
            target = screen['id']
            self._put(target, {**self.record(target), 'chosen': wanted})
            if wanted == self.beyond_set(self.record(target)['built']):
                continue
            try:
                outcome = self.apply(target, round)
            except ValueError:
                off.append(screen.get('name') or target)
                continue
            (own_yaml if outcome.get('own_yaml') else queued).append(screen.get('name') or target)
        return {'queued': queued, 'off': off, 'own_yaml': own_yaml}

    async def _build(self, build):
        ok = await self.manager.build_queue.step({'file': build.file, 'action': 'install', 'target': build.target})
        return 'success' if ok else 'failed'

    def before_build(self, build):
        """Right before a build of a screen: what it brings is what the file says, and the file fits this app's fixed set.
        A build that was not asked for icons brings what the screen has, also when a restart left another list in the file."""
        if not build.screen or build.screen not in self.screens:
            return
        record = self.record(build.screen)
        if not build.icons:
            record['written'] = record['built']
        self._write(build.screen, record)

    def _ended(self, build):
        """The firmware went on: the screen has what the file said. It did not: the file goes back to what the screen has."""
        record = self.record(build.screen)
        if build.installed:
            self._put(build.screen, {**record, 'built': self.beyond_set(record['written'])})
        else:
            self._write(build.screen, {**record, 'written': record['built']})
        self.manager.notify()

    def forget_screen(self, inbox):
        with self.lock:
            if self.screens.pop(inbox, None) is not None:
                self.save()

    def renamed(self, old, new):
        with self.lock:
            if old in self.screens:
                self.screens[new] = self.screens.pop(old)
                self.save()
