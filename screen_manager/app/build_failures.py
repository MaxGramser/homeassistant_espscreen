"""Why a build failed, from what it wrote (docs/BUILDS.md, "Why a build failed"): the one place that reads a build's
log for its cause, for every kind of build. A plugin build names the kind with its failure (Plugins._built), an update
decides by it whether its screen goes once more (Updater.passing), and a plugin build tries a download once more
(Plugins._build).

- `build_reason`: the one line of the log a person reads first.
- `failed_components`: the components a compiler error lies in, and the plugins the core refused by their API.
- `failure_kind`: 'plugin', 'memory', 'offline', 'network' or 'build'.
- `PASSING`: the kinds that say nothing about the firmware: a build with one of them goes once more.
"""
import re


def build_reason(logs):
    """Why a build failed, in one line of its log. The app's own last line says it in words (memory that ran short, a
    screen that did not answer); only when that line points to the log, the last error the compiler or ESPHome named.
    The whole log is kept on disk (build_logs.py) and offered with the failure."""
    lines = [str(line).strip() for line in list(logs or [])[-60:] if str(line).strip()]
    if not lines:
        return 'build'
    if 'see the log' not in lines[-1]:
        return lines[-1][:200]
    errors = [line for line in lines if re.search(r'\berror\b|ERROR', line) and 'see the log' not in line]
    return (errors or lines)[-1][:200]


# A compiler error in a file of an external component: `../src/esphome/components/tap_sound/tap_sound.h:19:8: error: ...`.
COMPONENT_ERROR = re.compile(r'components/([a-z0-9_]+)/[^\s:]+:\d+(?::\d+)?:\s*(?:fatal\s+)?error:')
# A plugin the core refused while ESPHome read the configuration, before any compiler ran (smart_display.register_plugin):
# `Plugin tap_sound wants plugin API 0.11; this firmware offers 0.10.` or `Plugin tap_sound was written for plugin API ...`.
API_REFUSAL = re.compile(r'Plugin ([a-z0-9_]+) (?:wants|was written for) plugin API')


def failed_components(logs):
    """The components a build's compiler errors lie in, and the plugins the core refused by their API, Tessera's own
    components left out."""
    lines = [str(line) for line in logs or []]
    found = {match.group(1) for line in lines for match in [COMPONENT_ERROR.search(line)] if match}
    found |= {match.group(1) for line in lines for match in [API_REFUSAL.search(line)] if match}
    return found - {'smart_display', 'flash_layout'}


# A build that stopped on the network, not on its code: a download of a component, a library or a tool that did not come.
# Tried once more by itself (Plugins._build), and named as such when it stops again.
NETWORK = re.compile(r'Could not resolve host|Temporary failure in name resolution|Connection (?:reset|refused|timed out)|'
                     r'Failed to (?:download|clone|fetch)|unable to access .https?://|HTTP Error 5\d\d|'
                     r'RemoteDisconnected|Read timed out|Network is unreachable', re.I)
# An upload that found no screen: the build itself was good (Plugins.failure_kind 'offline').
NO_SCREEN = re.compile(r'Error resolving IP address|Connecting to .* failed|Connection to .* timed out|'
                       r'No route to host|Host is unreachable|OTA (?:failed|timed out)|Error binding|'
                       r'did not answer|could not reach', re.I)


def failure_kind(logs, memory=None, blamed=False):
    """What kind of failure a build's end was, which decides the sentence and the way out the editor offers (docs/BUILDS.md,
    "Why a build failed"): 'plugin' (a compiler error in a plugin's own code: its maker can fix it), 'memory' (the
    computer ran short), 'offline' (built, but the screen did not take it: installed by itself once it is back),
    'network' (a download did not come), or 'build' (anything else)."""
    lines = [str(line) for line in list(logs or [])[-200:]]
    if blamed:
        return 'plugin'
    if (memory or {}).get('reason') in ('out', 'limit'):
        return 'memory'
    tail = '\n'.join(lines[-40:])
    # Only an upload that found no screen: one the screen refused (a password, an image too large) is no absence.
    if NO_SCREEN.search(tail):
        return 'offline'
    if any(NETWORK.search(line) for line in lines):
        return 'network'
    return 'build'


# The kinds of failure that say nothing about the firmware itself: the build goes once more instead of counting as failed.
PASSING = ('network', 'offline')
