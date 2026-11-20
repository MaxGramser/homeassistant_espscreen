"""A script of tools/ as a module, by its path.

tools/i18n.py and the app's screen_manager/app/i18n.py share a name, and which one `import i18n` gives depends on what
another test put on sys.path first: alone a test got the tool, in the whole run the app's. A test that means the tool
asks for it here, by path, under a name of its own (`tools_i18n`), so the order of the run decides nothing."""
import importlib.util
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1] / 'tools'


def tool(name):
    """tools/<name>.py, loaded once."""
    key = f'tools_{name}'
    if key not in sys.modules:
        if str(TOOLS) not in sys.path:
            sys.path.append(str(TOOLS))  # for what the script imports beside itself; after everything else
        spec = importlib.util.spec_from_file_location(key, TOOLS / f'{name}.py')
        module = importlib.util.module_from_spec(spec)
        sys.modules[key] = module
        spec.loader.exec_module(module)
    return sys.modules[key]
