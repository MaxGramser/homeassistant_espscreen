"""A plugin's own code for the editor's preview (docs/EMULATOR_ARCHITECTURE.md, "Plugins"): reading a module and deciding
whether the editor may load it.

The preview is the shared firmware in WebAssembly. A plugin's C++ is built into a module of its own
(web/wasm/build_plugin.py), which the browser loads into the preview's memory, so a plugin's tile is drawn in the
editor by the plugin itself. This file knows the module's shape and nothing of where one comes from (plugins.py).

What is checked before a module reaches a browser:

- It says what it is. Its last section (`tessera`) names the plugin, its version and the number of the preview it was
  built for (toolchain.plugin_abi); a module for another preview calls into another layout of the same memory, so it
  is refused, never tried.
- It can only call into the preview. A module has no way out but what it imports: here that is the preview's own
  functions and data (`env`, `GOT.func`, `GOT.mem`), never the browser's. A plugin's module that carries script for the
  page (Emscripten's EM_ASM and EM_JS), asks to run script, or asks for a file or a socket is refused.

Pure, as plugin_manifest.py is: the plugins repository's index build runs this file on every module it publishes.
"""
import json

MAGIC = b'\0asm\x01\0\0\0'
# Larger than any tile's code by far (the air quality tile is 116 KB), small enough to read whole and check.
MAX_BYTES = 2 * 1024 * 1024
SECTION = 'tessera'
# Where a module's imports may come from: the preview it is loaded into. Its memory, table and stack are the preview's.
IMPORT_FROM = ('env', 'GOT.func', 'GOT.mem')
# Functions of Emscripten's own that run script or reach past the preview: never a plugin's to call.
NEVER = ('emscripten_run_script', 'emscripten_asm_const', 'emscripten_async', 'emscripten_fetch', 'emscripten_websocket',
         'emscripten_wget', 'emscripten_idb', '__asyncjs__', '__syscall_', 'fd_', 'path_', 'sock_', '_dlopen_js',
         '_emscripten_dlopen', 'dlopen', 'system', 'popen', 'fork', 'exec')
# Exports that hand the loader script to evaluate for the page.
SCRIPT_EXPORTS = ('__em_js__', '__start_em_asm', '__stop_em_asm', '__start_em_js', '__stop_em_js', '__start_em_lib_deps')


class Unfit(ValueError):
    """Why a module is not loaded, in a few words for the log."""


def _leb(body, at):
    value = shift = 0
    while True:
        if at >= len(body) or shift > 28:
            raise Unfit('a number that does not end')
        byte = body[at]
        at += 1
        value |= (byte & 0x7F) << shift
        shift += 7
        if not byte & 0x80:
            return value, at


def _name(body, at):
    size, at = _leb(body, at)
    if at + size > len(body):
        raise Unfit('a name past the end')
    return body[at:at + size].decode('utf-8', 'replace'), at + size


def sections(body):
    """(id, payload) of every section, in order."""
    if not isinstance(body, (bytes, bytearray)) or not body.startswith(MAGIC):
        raise Unfit('not a WebAssembly module')
    at = len(MAGIC)
    while at < len(body):
        kind = body[at]
        size, at = _leb(body, at + 1)
        if at + size > len(body):
            raise Unfit('a section past the end')
        yield kind, bytes(body[at:at + size])
        at += size


def _limits(body, at, shared=False):
    flags, at = _leb(body, at)
    _, at = _leb(body, at)
    if flags & 1:
        _, at = _leb(body, at)
    return at


def imports(payload):
    """(module, name, kind) of every import; kind 0 a function, 1 a table, 2 a memory, 3 a global, 4 a tag."""
    count, at = _leb(payload, 0)
    found = []
    for _ in range(count):
        module, at = _name(payload, at)
        name, at = _name(payload, at)
        if at >= len(payload):
            raise Unfit('an import past the end')
        kind = payload[at]
        at += 1
        if kind == 0:
            _, at = _leb(payload, at)
        elif kind == 1:
            at = _limits(payload, at + 1)      # the element type, then its limits
        elif kind == 2:
            at = _limits(payload, at)
        elif kind == 3:
            at += 2                            # the value type and whether it changes
        elif kind == 4:
            _, at = _leb(payload, at + 1)      # the attribute, then its type
        else:
            raise Unfit('an import of a kind this app does not know')
        found.append((module, name, kind))
    return found


def exports(payload):
    count, at = _leb(payload, 0)
    names = []
    for _ in range(count):
        name, at = _name(payload, at)
        _, at = _leb(payload, at + 1)
        names.append(name)
    return names


def read(body):
    """What a module says about itself ({id, version, api, abi}), after the checks above; Unfit with the reason."""
    if not body or len(body) > MAX_BYTES:
        raise Unfit('empty, or larger than a plugin\'s module is')
    about = None
    for kind, payload in sections(body):
        if kind == 2:
            for module, name, _ in imports(payload):
                if module not in IMPORT_FROM:
                    raise Unfit(f'it imports from {module}')
                if any(name.startswith(prefix) for prefix in NEVER):
                    raise Unfit(f'it asks for {name}')
        elif kind == 7:
            for name in exports(payload):
                if any(name.startswith(prefix) for prefix in SCRIPT_EXPORTS):
                    raise Unfit('it carries script for the page')
        elif kind == 0:
            name, at = _name(payload, 0)
            if name == SECTION:
                try:
                    about = json.loads(payload[at:].decode('utf-8'))
                except ValueError:
                    raise Unfit('its own description does not read') from None
            elif name in ('em_asm', 'em_js'):
                raise Unfit('it carries script for the page')
    if not isinstance(about, dict) or not all(isinstance(about.get(key), str) and about[key]
                                              for key in ('id', 'version', 'abi')):
        raise Unfit('it does not say which plugin and which preview it is for')
    return {key: about[key] for key in ('id', 'version', 'abi')} | {'api': str(about.get('api') or '')}


def fits(body, plugin, version, abi):
    """Whether `body` is the module of this plugin at this version for the preview of this number; the reason when not."""
    try:
        about = read(body)
    except Unfit as reason:
        return str(reason)
    if about['id'] != plugin:
        return f'it is {about["id"]}\'s'
    if about['version'] != str(version):
        return f'it is version {about["version"]}'
    if about['abi'] != abi:
        return 'it was built for another preview'
    return None
