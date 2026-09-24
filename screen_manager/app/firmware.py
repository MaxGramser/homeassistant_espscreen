"""Serialised ESPHome CLI jobs. YAML/secrets stay local; no shell or arbitrary commands."""
import asyncio
from collections import deque
import glob
import json
import logging
import os
from pathlib import Path
import re
import shutil
import signal
import time
import yaml
from core import BOARD_KEYS, ORIENTATIONS, REPO, SHAPES, installation_yaml
from i18n import t

LOG = logging.getLogger('screen_manager')

# libyaml parses a 300 KB profile roughly ten times faster than the pure-Python loader.
class LenientLoader(yaml.CSafeLoader if getattr(yaml, '__with_libyaml__', False) else yaml.SafeLoader):
    """Reads profile metadata without resolving !secret or !include."""
LenientLoader.add_multi_constructor('!', lambda loader, suffix, node: None)

def profile_meta(text):
    """{'node', 'friendly'} from profile YAML, or None when it has no esphome block."""
    data = yaml.load(text, Loader=LenientLoader)
    block = data.get('esphome') if isinstance(data, dict) else None
    if not isinstance(block, dict):
        return None
    substitutions = data.get('substitutions') if isinstance(data.get('substitutions'), dict) else {}
    def resolve(value):
        if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
            value = substitutions.get(value[2:-1])
        return value if isinstance(value, str) else None
    # 'screen': the profile pulls this project's board package, so it is one of ours (not any ESPHome device).
    packages = data.get('packages') if isinstance(data.get('packages'), dict) else {}
    ours = any(isinstance(entry, dict) and REPO in str(entry.get('url', '')) for entry in packages.values())
    # The board package the profile builds from ("packages/guition.yaml"): what the screen looks like follows
    # from it (core.SHAPES), so the editor draws the right screen before it has ever been flashed.
    package = None
    for entry in packages.values():
        if isinstance(entry, dict) and REPO in str(entry.get('url', '')):
            files = entry.get('files')
            first = files[0] if isinstance(files, list) and files else files
            if isinstance(first, str):
                package = first
                break
    api = data.get('api') if isinstance(data.get('api'), dict) else {}
    encryption = api.get('encryption') if isinstance(api.get('encryption'), dict) else {}
    key = encryption.get('key')
    # The angle the profile was built at (app 0.2.107), which says which way the screen hangs: only a screen
    # standing up carries the line, so nothing here means the board file's own default, lying down. A profile that
    # writes it as ${SOMETHING} is left to the board file as well, because only the build can resolve that.
    rotation = substitutions.get('LVGL_ROTATION')
    rotation = int(rotation) if isinstance(rotation, (int, str)) and str(rotation).strip().lstrip('-').isdigit() else None
    return {'node': resolve(block.get('name')), 'friendly': resolve(block.get('friendly_name')),
            'screen': ours, 'api_key': key if isinstance(key, str) else None, 'package': package,
            'rotation': rotation}

# What New screen offers, board by board in the catalog's order (boards.yaml, written into boards.json with what each
# board's files say): what it is called and printed on it, how far it has been tried, its glass (canvas, density,
# the size in inches) and the two ways it can hang with the cells of a page for each, what it can do, and the choices
# made when a screen of it is built. The editor draws the whole choice from this, so no board is written into the
# page's code or its translations. A board whose glass is square has the same entry twice and the editor leaves the
# orientation out; the shapes of a board a screen is already built from travel with that screen instead
# (core.shape_of).
def _board_choice(shape):
    return {'square': shape['width'] == shape['height'], 'orientations': shape.get('orientations', {}),
            'width': shape['width'], 'height': shape['height'], 'dpi': shape.get('dpi'), 'look': shape.get('look', 'standard'),
            'camera': bool(shape.get('camera')), 'dimmable': shape.get('dimmable', True),
            'can_standby': shape.get('can_standby', True), **shape.get('catalog', {})}

BOARD_CHOICES = {board: _board_choice(SHAPES[board]) for board in BOARD_KEYS}

class Firmware:
    OVERRIDE_SUFFIX = '.local.yaml'
    OVERRIDE_LIMIT = 12 * 1024  # bytes; checked here, far below the request body limit (128 KB since app 0.2.78)
    PROTECTED_OVERRIDE_KEYS = frozenset({'esphome', 'api', 'ota', 'wifi', 'packages',
                                         'external_components', 'captive_portal'})
    # LANGUAGE follows Settings -> Language & region (app 0.2.90), which writes it into the profile itself.
    # LVGL_ROTATION follows the orientation chosen when the screen is made (app 0.2.107), written into the profile
    # the same way. A profile's own substitutions beat a package's, so an override that set it would quietly lose
    # against a screen built standing up and quietly win on one built lying down. That is worse than being told, so
    # it is refused here with its own sentence rather than the general "these stay managed" one: people were told to
    # override display settings (GitHub #12 and #15), and the sentence has to say where the choice lives now.
    PROTECTED_SUBSTITUTIONS = frozenset({'DEVICE_NAME', 'DEVICE_FRIENDLY_NAME', 'SCREEN_FIRMWARE_VERSION', 'LANGUAGE',
                                         'LVGL_ROTATION'})
    # ESPHome's "Factory format" (bootloader, partition table and app from address 0), the file ESPHome Web
    # flashes on a board. A build writes it next to firmware.bin: under .pioenvs/<node>/ with PlatformIO,
    # under build/ with ESPHome's native ESP-IDF toolchain.
    FACTORY_IMAGES = ('*/.pioenvs/*/firmware.factory.bin', '*/build/firmware.factory.bin')
    # The compiler cache's limit (app 0.2.89+); past it ccache drops the oldest entries. Some seventeen full builds of
    # both boards took 0.6 GB on a Mac (docs/TEST_RESULTS_0289.md).
    CCACHE_SIZE = '1G'

    def __init__(self, root, data):
        self.root, self.data = Path(root).resolve(), Path(data)
        self.job = None
        self.task = None
        self.logs = deque(maxlen=300)
        self.process = None
        self.installed = set()  # profiles this process flashed successfully; the page nudges pairing for them
        # Factory image per profile from its last successful build in this process; only these are downloaded,
        # so a download is never older than the profile's latest build. Downloaded ones get their own pairing nudge.
        self.images = {}
        self.downloaded = set()
        self._names = {}  # file -> (stat signature, meta or None); parsed only when the file changes
        self.language = None  # the language builds speak: the manager's Settings -> Language & region (app 0.2.90)

    def profiles(self):
        if not self.root.exists(): return []
        return [{'file': p.name} for p in sorted(self.root.glob('*.yaml'))
                if p.name != 'secrets.yaml' and not p.name.endswith(self.OVERRIDE_SUFFIX)
                and p.is_file() and not p.is_symlink()]

    def profile_names(self):
        """{file: {'node': esphome name, 'friendly': friendly name}} for every readable profile.

        Parsing is cached per file on inode, mtime and size, so a request only pays for changed
        profiles. The dict is rebuilt from the current directory listing, so deleted files drop out.
        """
        found, cache = {}, {}
        for entry in self.profiles():
            path = self.root / entry['file']
            try:
                st = path.stat()
                key = (st.st_ino, st.st_mtime_ns, st.st_size)
                cached = self._names.get(entry['file'])
                if cached and cached[0] == key:
                    meta = cached[1]
                else:
                    meta = profile_meta(path.read_text())
            except (OSError, yaml.YAMLError, UnicodeError):
                continue
            cache[entry['file']] = (key, meta)
            if meta:
                found[entry['file']] = meta
        self._names = cache
        return found

    def ports(self):
        return sorted(set(glob.glob('/dev/serial/by-id/*') or glob.glob('/dev/ttyUSB*') + glob.glob('/dev/ttyACM*')))

    def profile(self, name):
        if not isinstance(name,str) or not re.fullmatch(r'[a-zA-Z0-9_-]+\.yaml', name):
            raise ValueError(t('addon.errors.firmware.choose_profile'))
        p = self.root / name
        if p.is_symlink() or p.resolve().parent != self.root or not p.is_file():
            raise ValueError(t('addon.errors.firmware.profile_missing'))
        return p

    def wifi_status(self):
        # Return availability only; never send secret values to the browser.
        path = self.root / 'secrets.yaml'
        if not path.exists():
            return {'state': 'new', 'missing': ['wifi_ssid', 'wifi_password']}
        try:
            values = yaml.safe_load(path.read_text())
            if not isinstance(values, dict):
                return {'state': 'invalid'}
            missing = [key for key in ('wifi_ssid', 'wifi_password')
                       if not isinstance(values.get(key), str)]
            if isinstance(values.get('wifi_ssid'), str) and not values['wifi_ssid'].strip():
                missing.append('wifi_ssid')
            return {'state': 'missing' if missing else 'ready', 'missing': missing}
        except (OSError, yaml.YAMLError, UnicodeError):
            return {'state': 'invalid'}

    def status(self):
        return {'available': bool(shutil.which('esphome')), 'profiles': self.profiles(),
                'ports': self.ports(), 'job': self.job, 'logs': list(self.logs), 'wifi': self.wifi_status(),
                'downloads': sorted(self.images), 'boards': BOARD_CHOICES}

    def store_wifi(self, data):
        """Put wifi_ssid/wifi_password in secrets.yaml when they are missing. Existing values and
        every other secret stay as they are; the browser never sees stored values."""
        wifi = self.wifi_status()
        if wifi['state'] == 'ready':
            return
        if wifi['state'] == 'invalid':
            raise ValueError(t('addon.errors.firmware.secrets_invalid'))
        values = {}
        for key in wifi['missing']:
            value = data.get(key)
            if not isinstance(value, str) or (key == 'wifi_ssid' and not value.strip()):
                raise ValueError(t('addon.errors.firmware.wifi_needed'))
            values[key] = value
        path = self.root / 'secrets.yaml'
        if wifi['state'] == 'new':
            with path.open('x') as f:
                os.chmod(path, 0o600)
                yaml.safe_dump(values, f, width=4096)
            return
        # An existing file with missing keys: replace only that key's own line, or append it.
        text = path.read_text()
        for key, value in values.items():
            line = yaml.safe_dump({key: value}, width=4096).strip()
            pattern = re.compile(rf'^{key}\s*:.*$', re.M)
            if pattern.search(text):
                text = pattern.sub(lambda match: line, text, count=1)
            else:
                text = text + ('' if not text or text.endswith('\n') else '\n') + line + '\n'
        check = yaml.safe_load(text)
        if not isinstance(check, dict) or any(check.get(key) != value for key, value in values.items()):
            raise ValueError(t('addon.errors.firmware.wifi_not_set'))
        path.write_text(text)

    def create(self, data):
        """Write the device profile, its empty local override, and any missing wifi secrets."""
        content = installation_yaml(data)
        self.root.mkdir(parents=True,exist_ok=True)
        profile = self.root / (data['name']+'.yaml')
        if profile.exists() or profile.is_symlink():
            raise ValueError(t('addon.errors.firmware.name_exists'))
        override = self.root / (data['name'] + self.OVERRIDE_SUFFIX)
        if override.exists() or override.is_symlink():
            raise ValueError(t('addon.errors.firmware.override_exists'))
        self.store_wifi(data)
        try:
            with profile.open('x') as f:
                os.chmod(profile,0o600);f.write(content)
        except FileExistsError:
            raise ValueError(t('addon.errors.firmware.name_exists'))
        try:
            with override.open('x') as f:
                os.chmod(override, 0o600); f.write('{}\n')
        except FileExistsError:
            raise ValueError(t('addon.errors.firmware.override_exists'))
        key = yaml.load(content, Loader=LenientLoader)['api']['encryption']['key']
        # The key is what Home Assistant asks for when pairing; the page shows it once.
        return {'file': profile.name, 'node': data['name'], 'api_key': key}

    def set_language(self, name, language):
        """Let the screen's next build speak `language` (app 0.2.90): the LANGUAGE line of the profile's substitutions,
        changed or added without reformatting the user's YAML. A profile that doesn't build from ESP Screens' packages is
        left alone, as is an English one without the line (English is the packages' own default). True when it changed."""
        return self._set_substitution(name, 'LANGUAGE', language, default='en', what='language')

    def set_orientation(self, name, orientation):
        """Let the screen's next build hang the way `orientation` says (app 0.2.107): the LVGL_ROTATION line of the
        profile's substitutions, written the way the language is, so a screen can be stood up or laid down by
        rebuilding it. The angle is the board's, from boards.json, so this app never invents one; lying down is the
        board file's own default and needs no line. False, and nothing written, when the profile builds from a board
        this app doesn't know or `orientation` is not one of the two words. True when it changed."""
        if orientation not in ORIENTATIONS:
            return False
        meta = self.profile_names().get(self.profile(name).name) or {}
        sides = (SHAPES.get(meta.get('package') or '', {}).get('orientations') or {})
        if not sides.get(orientation) or not sides.get('landscape'):
            return False
        return self._set_substitution(name, 'LVGL_ROTATION', str(sides[orientation]['rotation']),
                                      default=str(sides['landscape']['rotation']), what='orientation')

    def _set_substitution(self, name, key, value, default=None, what='setting'):
        """One substitution of an existing profile, changed or added without reformatting the user's YAML.

        A profile that doesn't build from ESP Screens' packages is left alone, as is one that already says this, one
        that says nothing while `default` is what it would say anyway (the packages' own default needs no line), and
        one whose substitutions this can't edit safely (an !include, a {...} mapping). The result is read back and
        written only when this one name is the one thing that changed. True when it changed."""
        profile = self.profile(name)
        raw = profile.read_bytes().decode('utf-8')
        if 'homeassistant_espscreen' not in raw and 'packages/core.yaml' not in raw:
            return False
        newline = '\r\n' if '\r\n' in raw else '\n'
        text = raw.replace('\r\n', '\n')
        if not text.endswith('\n'):
            text += '\n'
        before = yaml.load(text, Loader=LenientLoader)
        if not isinstance(before, dict):
            return False
        substitutions = before.get('substitutions')
        if 'substitutions' in before and not isinstance(substitutions, dict):
            LOG.warning('%s: its substitutions are not a plain block, so its %s stays as it is', profile.name, what)
            return False
        substitutions = substitutions or {}
        if substitutions.get(key) == value or (value == default and key not in substitutions):
            return False
        line = f'{key}: {json.dumps(value)}'
        block = re.search(r'(?m)^substitutions:[ \t]*(?:#.*)?\n', text)
        if block:
            # The block: indented lines, blank ones and comments, up to the next key at the start of a line.
            body = re.compile(r'(?:(?:[ \t]+.*|[ \t]*|#.*)\n)*').match(text, block.end())
            indent = re.search(r'(?m)^([ \t]+)\S', body.group(0))
            indent = indent.group(1) if indent else '  '
            current = re.search(rf'(?m)^[ \t]+["\']?{re.escape(key)}["\']?[ \t]*:.*$', body.group(0))
            if current:
                lines = body.group(0)[:current.start()] + indent + line + body.group(0)[current.end():]
            else:
                lines = indent + line + '\n' + body.group(0)
            updated = text[:body.start()] + lines + text[body.end():]
        elif 'substitutions' in before:
            LOG.warning('%s: its substitutions are not a plain block, so its %s stays as it is', profile.name, what)
            return False
        else:
            # After the comments (and a document start) at the top of the file.
            head = re.match(r'(?:(?:#.*|[ \t]*|---[ \t]*)\n)*', text)
            updated = text[:head.end()] + f'substitutions:\n  {line}\n\n' + text[head.end():]
        after = yaml.load(updated, Loader=LenientLoader)
        def rest(data):
            data = dict(data)
            rest_substitutions = {k: v for k, v in (data.get('substitutions') or {}).items() if k != key}
            data.pop('substitutions', None)
            return data, rest_substitutions
        if not isinstance(after, dict) or (after.get('substitutions') or {}).get(key) != value or rest(after) != rest(before):
            LOG.warning('%s: its %s could not be written without changing more, so it stays as it is', profile.name, what)
            return False
        self._atomic_write(profile, updated.replace('\n', newline))
        self._names.pop(profile.name, None)
        return True

    def _override_path(self, name):
        profile = self.profile(name)
        path = self.root / (profile.stem + self.OVERRIDE_SUFFIX)
        if path.is_symlink():
            raise ValueError(t('addon.errors.firmware.override_symlink'))
        return profile, path

    def _atomic_write(self, path, text):
        temporary = path.with_name(path.name + '.tmp')
        with temporary.open('w', encoding='utf8') as handle:
            os.chmod(temporary, 0o600)
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

    def _ensure_override_include(self, profile):
        """Attach an existing profile to its sidecar without reformatting user YAML."""
        filename = profile.stem + self.OVERRIDE_SUFFIX
        text = profile.read_text()
        if re.search(rf'(?m)^\s*local_overrides:\s*!include\s+{re.escape(filename)}\s*$', text):
            return False
        if re.search(r'(?m)^\s*local_overrides\s*:', text):
            raise ValueError(t('addon.errors.firmware.other_include'))
        try:
            parsed = yaml.load(text, Loader=LenientLoader)
        except yaml.YAMLError as error:
            raise ValueError(t('addon.errors.firmware.profile_invalid')) from error
        packages = parsed.get('packages') if isinstance(parsed, dict) else None
        if not isinstance(packages, dict):
            raise ValueError(t('addon.errors.firmware.no_packages'))
        match = re.search(r'(?m)^packages:\s*\n', text)
        if not match:
            raise ValueError(t('addon.errors.firmware.no_packages'))
        next_top = re.search(r'(?m)^[^\s#][^\n]*\n', text[match.end():])
        if not next_top and not text.endswith('\n'):
            text += '\n'
        end = match.end() + next_top.start() if next_top else len(text)
        addition = f'  local_overrides: !include {filename}\n'
        self._atomic_write(profile, text[:end] + addition + text[end:])
        self._names.pop(profile.name, None)
        return True

    def _validate_override(self, content):
        if not isinstance(content, str):
            raise ValueError(t('addon.errors.firmware.yaml_needed'))
        if len(content.encode('utf8')) > self.OVERRIDE_LIMIT:
            raise ValueError(t('addon.errors.firmware.override_too_large'))
        if not content.strip():
            content = '{}\n'
        try:
            parsed = yaml.load(content, Loader=LenientLoader)
        except yaml.YAMLError as error:
            # PyYAML's own description of the problem stays in English.
            problem = getattr(error, 'problem', None) or t('addon.errors.firmware.invalid_yaml')
            mark = getattr(error, 'problem_mark', None)
            if mark:
                raise ValueError(t('addon.errors.firmware.yaml_error_line', line=mark.line + 1, problem=problem)) from error
            raise ValueError(t('addon.errors.firmware.yaml_error', problem=problem)) from error
        if not isinstance(parsed, dict):
            raise ValueError(t('addon.errors.firmware.override_object'))
        protected = sorted(set(parsed) & self.PROTECTED_OVERRIDE_KEYS)
        if protected:
            raise ValueError(t('addon.errors.firmware.sections_managed', names=', '.join(protected)))
        substitutions = parsed.get('substitutions')
        if isinstance(substitutions, dict):
            # The one people are most likely to have written themselves gets the sentence that says where it went.
            if 'LVGL_ROTATION' in substitutions:
                raise ValueError(t('addon.errors.firmware.orientation_managed'))
            protected = sorted(set(substitutions) & self.PROTECTED_SUBSTITUTIONS)
            if protected:
                raise ValueError(t('addon.errors.firmware.substitutions_managed', names=', '.join(protected)))
        return content if content.endswith('\n') else content + '\n'

    def override(self, name):
        profile, path = self._override_path(name)
        attached = bool(re.search(rf'(?m)^\s*local_overrides:\s*!include\s+{re.escape(path.name)}\s*$',
                                  profile.read_text()))
        content = path.read_text() if path.exists() else '{}\n'
        return {'file': profile.name, 'override_file': path.name, 'attached': attached,
                'exists': path.exists(), 'content': content}

    def save_override(self, name, content):
        profile, path = self._override_path(name)
        content = self._validate_override(content)
        # A substitution the screen's own YAML sets wins over the override's, which is a package: a choice made under
        # New screen (a CYD's display controller, app 0.2.129) would quietly beat the same line here. Said instead.
        mine = (yaml.load(content, Loader=LenientLoader) or {}).get('substitutions')
        own = (yaml.load(profile.read_text(), Loader=LenientLoader) or {}).get('substitutions')
        clash = sorted(set(mine) & set(own)) if isinstance(mine, dict) and isinstance(own, dict) else []
        if clash:
            raise ValueError(t('addon.errors.firmware.substitutions_in_profile', names=', '.join(clash)))
        # The sidecar first: a profile must never include a file that isn't there.
        self._atomic_write(path, content)
        self._ensure_override_include(profile)
        return self.override(profile.name)

    def install(self, data):
        """Profile plus, when a USB port is chosen, the build and flash in one go. With the target
        'download' it builds only, and the owner flashes the image from their own computer.

        The target and the job slot are checked before anything is written, so a refused
        install leaves no half-made profile behind."""
        target = data.get('target') or ''
        if target:
            if target != 'download' and (not isinstance(target, str) or target not in self.ports()):
                raise ValueError(t('addon.errors.firmware.usb_port'))
            if self.task and not self.task.done():
                raise ValueError(t('addon.errors.firmware.busy_wait'))
            if not shutil.which('esphome'):
                raise ValueError(t('addon.errors.firmware.no_esphome'))
        result = self.create(data)
        if target == 'download':
            result['job'] = self.start({'file': result['file'], 'action': 'download'})
        elif target:
            result['job'] = self.start({'file': result['file'], 'action': 'install', 'target': target})
        return result

    async def delete_profile(self, name):
        """Everything New screen wrote for one screen: its YAML, its local override and its build folder.

        The mirror of `create` (app 0.2.112). `profile` refuses a name that is a symbolic link or points
        outside the ESPHome folder, so only this app's own files go. A running job keeps its profile:
        it would otherwise compile a file that is no longer there."""
        if self.task and not self.task.done():
            raise ValueError(t('addon.errors.firmware.busy_wait'))
        profile = self.profile(name)
        override = self.root / (profile.stem + self.OVERRIDE_SUFFIX)
        removed = [profile.name]
        profile.unlink()
        if override.is_file() and not override.is_symlink():
            override.unlink()
            removed.append(override.name)
        # The build folder is this app's own (/data/build/<profile>, build_env), so nothing in the ESPHome
        # folder depends on it; a big one is removed off the loop, which keeps the screens going.
        build = self.data / 'build' / profile.stem
        if build.is_dir() and not build.is_symlink():
            await asyncio.to_thread(shutil.rmtree, build, True)
            removed.append(f'build/{profile.stem}')
        self._names.pop(profile.name, None)
        self.images.pop(profile.name, None)
        self.installed.discard(profile.name)
        self.downloaded.discard(profile.name)
        LOG.info('Removed the profile %s and what it built', profile.name)
        return removed

    def factory_image(self, profile):
        """The factory image in this profile's own build folder, or None. The newest wins: a renamed node
        leaves its old folder behind."""
        build = self.data / 'build' / profile.stem
        found = [path for pattern in self.FACTORY_IMAGES for path in build.glob(pattern)
                 if path.is_file() and not path.is_symlink()]
        return max(found, key=lambda path: path.stat().st_mtime_ns) if found else None

    def image(self, name):
        """(path, file name) of the image a profile's last build made, for the page's download.

        Only an image built by this process counts, and a new job for the profile withdraws it first, so the
        owner never gets firmware from before a change or a failed build."""
        profile = self.profile(name)
        if self.job and self.job.get('file') == profile.name and self.job.get('state') == 'running':
            raise ValueError(t('addon.errors.firmware.still_building'))
        path = self.images.get(profile.name)
        if not path or not path.is_file():
            raise ValueError(t('addon.errors.firmware.build_first'))
        self.downloaded.add(profile.name)
        return path, profile.stem + '.factory.bin'

    def redact(self, text):
        text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', text)
        for value in self._secret_values:
            if len(value) >= 3: text=text.replace(value,'[redacted]')
        return re.sub(r'(?i)((?:password|encryption.key|token|ssid)\s*[:=]\s*).+',r'\1[redacted]',text)[:1500]

    def start(self, data):
        if self.task and not self.task.done(): raise ValueError(t('addon.errors.firmware.busy'))
        profile = self.profile(data.get('file'))
        action = data.get('action')
        if action not in ('validate','build','install','download'): raise ValueError(t('addon.errors.firmware.unknown_action'))
        # Every build speaks the language of Settings -> Language & region, also for a profile made or changed since
        # that language was set (app 0.2.90).
        if action != 'validate' and callable(self.language):
            try:
                self.set_language(profile.name, self.language())
            except (OSError, ValueError, yaml.YAMLError) as error:
                LOG.warning('Could not write the language into %s (%s)', profile.name, error)
        if not shutil.which('esphome'): raise ValueError(t('addon.errors.firmware.no_esphome'))
        target = data.get('target','')
        if action == 'install':
            if target.startswith('/dev/'):
                if target not in self.ports(): raise ValueError(t('addon.errors.firmware.usb_port'))
            elif not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}',target):
                raise ValueError(t('addon.errors.firmware.host'))
        self._secret_values=set()
        # Collect scalar literals, including !secret values, without executing YAML tags.
        def collect(node):
            if isinstance(node,yaml.ScalarNode):
                if node.value: self._secret_values.add(node.value)
            elif isinstance(node,yaml.SequenceNode):
                for child in node.value: collect(child)
            elif isinstance(node,yaml.MappingNode):
                for key,value in node.value:
                    if key.value in ('password','key','ssid','token') or profile.name=='secrets.yaml':collect(value)
                    elif isinstance(value,(yaml.MappingNode,yaml.SequenceNode)):collect(value)
        collect(yaml.compose(profile.read_text()))
        secret_file=self.root/'secrets.yaml'
        if secret_file.exists():
            node=yaml.compose(secret_file.read_text())
            if isinstance(node,yaml.MappingNode):
                for _,v in node.value:collect(v)
        override_file = self.root / (profile.stem + self.OVERRIDE_SUFFIX)
        if override_file.exists() and not override_file.is_symlink():
            collect(yaml.compose(override_file.read_text()))
        self.images.pop(profile.name, None)  # until this job succeeds, the old image may no longer match the profile
        self.logs.clear()
        self.job={'file':profile.name,'action':action,'target':target,'state':'running','started':time.time()}
        self.task=asyncio.create_task(self.run(profile,action,target))
        return dict(self.job)

    def build_env(self, profile):
        """The ESPHome CLI's environment: everything it downloads or builds goes in the app's own /data, which an app
        update or restart keeps and a backup leaves out (config.yaml backup_exclude), none of it in the ESPHome folder.

        - build/<profile>: the screen's build folder.
        - esphome: ESPHome's memory of each build (storage/) and what it fetched from GitHub (app 0.2.89+). It used to
          be the ESPHome folder's .esphome, which the ESPHome Device Builder app deletes whenever it starts, so every
          screen's next update was built from scratch.
        - idf: ESP-IDF, its tools and the compiler cache, with which ESPHome 2026.7+ builds an ESP32 instead of
          PlatformIO (app 0.2.89+); by default they would go in the container's own cache, gone at every restart.
        - platformio: PlatformIO, for anything ESPHome still builds with it.

        As many compilers at once as the machine has cores, as PlatformIO ran them: ESP-IDF's ninja would start two
        more, and each takes a few hundred MB next to Home Assistant on a small Raspberry Pi (ESPHome's own limit, which
        the official ESPHome app sets too)."""
        return {**os.environ, 'ESPHOME_BUILD_PATH': str(self.data / 'build' / profile.stem),
                'ESPHOME_DATA_DIR': str(self.data / 'esphome'), 'ESPHOME_ESP_IDF_PREFIX': str(self.data / 'idf'),
                'CCACHE_MAXSIZE': os.environ.get('CCACHE_MAXSIZE', self.CCACHE_SIZE),
                'ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT': os.environ.get('ESPHOME_DEFAULT_COMPILE_PROCESS_LIMIT',
                                                                        str(os.cpu_count() or 1)),
                'PLATFORMIO_CORE_DIR': str(self.data / 'platformio'), 'NO_COLOR': '1'}

    async def retire_platformio(self):
        """PlatformIO's ESP32 toolchains and ESP-IDF, with which ESPHome built the screens before 2026.7 (app 0.2.88 and
        older), take gigabytes that no screen uses any more. They go once: before the first build with ESPHome's own
        ESP-IDF, which creates /data/idf. Anything that still needs PlatformIO downloads its own part again."""
        old = self.data / 'platformio'
        if old.is_dir() and not (self.data / 'idf').exists():
            self.logs.append('Removing PlatformIO from before ESPHome 2026.7: the screens build with ESP-IDF now.')
            await asyncio.to_thread(shutil.rmtree, old, True)

    async def run(self, profile, action, target):
        env = self.build_env(profile)
        try:
            if action != 'validate':
                await self.retire_platformio()
            stages = ['config'] if action=='validate' else ['compile'] + (['upload'] if action=='install' else [])
            for stage in stages:
                cmd=['esphome']+(['--quiet'] if stage=='config' else [])+[stage,str(profile)]
                if stage=='upload': cmd += ['--device',target]
                self.job['stage']=stage
                self.logs.append('ESPHome: '+stage)
                self.process=await asyncio.create_subprocess_exec(*cmd,cwd=self.root,env=env,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.STDOUT,limit=1024*1024,start_new_session=True)
                async with asyncio.timeout(7200):
                    async for line in self.process.stdout:
                        self.logs.append(self.redact(line.decode(errors='replace').rstrip()))
                    code=await self.process.wait()
                if code: raise RuntimeError('ESPHome '+stage+' failed; see the log.')
            image = self.factory_image(profile) if action != 'validate' else None
            if action == 'download' and not image:
                raise RuntimeError('ESPHome built no factory image (firmware.factory.bin) to download; see the log.')
            self.job['state']='success'; self.logs.append('Succeeded: '+action)
            if action=='install': self.installed.add(profile.name)
            if image: self.images[profile.name] = image
        except asyncio.CancelledError:
            self.job['state']='interrupted'
            raise
        except Exception as error:
            self.job['state']='failed';self.logs.append(self.redact(str(error)))
        finally:
            if self.process and self.process.returncode is None:
                os.killpg(self.process.pid,signal.SIGTERM)
                try: await asyncio.wait_for(self.process.wait(),10)
                except TimeoutError: os.killpg(self.process.pid,signal.SIGKILL);await self.process.wait()
            self.process=None
            self.job['finished']=time.time()
