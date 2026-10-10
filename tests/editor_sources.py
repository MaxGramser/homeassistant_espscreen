"""The editor's source, for the tests that read it.

The page is a Vue app in web/ (app 0.2.73); `npm run build` writes it to screen_manager/app/static. Tests look at
the source, not the build: every .ts and .vue file under web/src as one text (SCRIPT, which is also the markup:
a .vue file carries its template), and the stylesheets as another (CSS). Its English words are in the `editor` section
of screen_manager/translations/en.json since app 0.2.90: text() reads one of them.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'web/src'
STATIC = ROOT / 'screen_manager/app/static'

FILES = sorted(p for p in WEB.rglob('*') if p.suffix in ('.ts', '.vue'))
SCRIPT = '\n'.join(p.read_text() for p in FILES)
PAGE = SCRIPT
CSS = '\n'.join(p.read_text() for p in sorted(WEB.glob('styles/*.css')))


def source(name):
    """One file by name, e.g. 'stores/document.ts' or 'components/Sidebar.vue'."""
    return (WEB / name).read_text()


def component(name):
    return source(f'components/{name}.vue')


TEXTS = json.loads((ROOT / 'screen_manager/translations/en.json').read_text(encoding='utf-8'))['editor']


def text(key):
    """One English text of the editor by its key under `editor`, e.g. 'empty.choose.title'."""
    node = TEXTS
    for part in key.split('.'):
        node = node[int(part)] if isinstance(node, list) else node[part]
    return node
