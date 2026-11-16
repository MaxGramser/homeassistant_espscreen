"""The firmware's YAML packages read as ESPHome reads them, for tests that state a rule over their structure instead of
quoting lines (docs/TESTING.md, "A test reads behaviour, not lines").

ESPHome's own tags (!lambda, !include, !secret, !extend, !remove) read as plain values: a lambda is its C++ text, an
`- id: !remove x` item is marked so a rule can leave it out. Only the structure is read; nothing is merged or resolved."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / 'packages'
CORE = PACKAGES / 'core.yaml'


class Removed(str):
    """The id of an `- id: !remove <id>` item: it takes that item out instead of being one."""


class _Loader(yaml.SafeLoader):
    pass


def _tag(loader, suffix, node):
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
        return Removed(value) if suffix == 'remove' else value
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node, deep=True)
    return loader.construct_mapping(node, deep=True)


_Loader.add_multi_constructor('!', _tag)


def load(path):
    return yaml.load(Path(path).read_text(), Loader=_Loader) or {}


def files():
    """Every YAML file of the packages a screen is built from: the core, the boards, their hardware, looks and features."""
    return sorted(path for path in PACKAGES.rglob('*.yaml'))


def scripts(path):
    """{id: script} of one file's `script:` block, without the items that take a script out."""
    return {item['id']: item for item in load(path).get('script') or [] if not isinstance(item.get('id'), Removed)}


def every_script():
    """[(file, id, script)] of every script in every package file."""
    return [(path, name, item) for path in files() for name, item in scripts(path).items()]


def script(name):
    """The one script `name` of the shared packages (the core and its features), where a screen gets it from."""
    found = [item for path, key, item in every_script() if key == name and 'boards' not in path.parts]
    if not found:
        raise KeyError(f'no script {name} in packages/')
    return found[0]


def actions():
    """{name: action} of the API actions the core gives Home Assistant."""
    return {item['action']: item for item in load(CORE)['api']['actions']}


def steps(item):
    """Every step of an automation, depth first: each `then:`, `else:` and `repeat:` opened, with the step itself."""
    out = []

    def walk(node):
        if isinstance(node, list):
            for step in node:
                walk(step)
        elif isinstance(node, dict):
            out.append(node)
            for value in node.values():
                if isinstance(value, (list, dict)):
                    walk(value)
    walk(item.get('then') if isinstance(item, dict) and 'then' in item else item)
    return out


def executed(item):
    """[(script id, its arguments)] that an automation runs with `script.execute`, in order."""
    out = []
    for step in steps(item):
        if 'script.execute' in step:
            target = step['script.execute']
            out.append((target, {}) if isinstance(target, str) else (target['id'], {k: v for k, v in target.items() if k != 'id'}))
    return out


def widgets(node):
    """{id: (kind, widget)} of every widget under an LVGL node, at any depth."""
    out = {}

    def walk(items):
        for entry in items or []:
            for kind, widget in entry.items():
                if isinstance(widget, dict):
                    if 'id' in widget:
                        out[widget['id']] = (kind, widget)
                    walk(widget.get('widgets'))
    walk(node.get('widgets') if isinstance(node, dict) else node)
    return out
