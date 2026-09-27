"""What's new for the Update badge (app 0.2.73): the CHANGELOG sections since a screen's firmware.

The Dockerfile copies CHANGELOG.md next to this file; a development checkout has it one folder up.
Each `## <app> (firmware <fw>)` section gives its bullet lines as plain text, newest first. A firmware for some boards
alone (app 0.3.20) says which: `## <app> (firmware <fw> for <board>, <board>)`, with the board keys of boards.yaml.
"""
import logging
import re
from pathlib import Path

LOG = logging.getLogger('screen_manager')

HEADER = re.compile(r'^## (\d+\.\d+\.\d+) \(firmware (\d+\.\d+\.\d+)(?: for ([a-z0-9]+(?:, [a-z0-9]+)*))?\)')
# A heading of level one or two ends a section; a `### ` inside one doesn't.
SECTION_END = re.compile(r'^#{1,2}(\s|$)')
BULLET = re.compile(r'^[-*+]\s+(.*)$')
BOLD = re.compile(r'\*\*(.+?)\*\*')
# *Full page*: single asterisks around text. A lone asterisk (5 * 3) or one inside a word stays (app 0.2.78).
ITALIC = re.compile(r'(?<![\w*])\*(?=\S)([^*\n]*?\S)\*(?![\w*])')
CODE = re.compile(r'`([^`]*)`')
LINK = re.compile(r'\[([^\]]+)\]\([^)]+\)')


def load(path=None, limit=20):
    """[{app, firmware, lines}] for the latest sections; [] without a changelog, or with one that can't be read (a
    folder, no permission, not UTF-8): the Update badge then has no notes, and the app still starts (app 0.2.78)."""
    candidates = [Path(path)] if path else [Path(__file__).with_name('CHANGELOG.md'), Path(__file__).parent.parent / 'CHANGELOG.md']
    for candidate in candidates:
        if candidate.exists():
            try:
                return parse(candidate.read_text(encoding='utf-8'), limit)
            except (OSError, UnicodeDecodeError) as error:
                LOG.warning("What's new stays empty: %s can't be read (%s)", candidate, type(error).__name__)
                return []
    return []


def parse(text, limit=20):
    """The sections of a changelog. A bullet (`- ` or `* `) takes the lines that continue it, indented or wrapped
    right under it; bullets under any other heading of level one or two belong to no section (app 0.2.78)."""
    sections, current, item, blank = [], None, None, False

    def close():
        if item is not None and current is not None:
            current['lines'].append(plain(' '.join(item)))

    for line in text.splitlines():
        stripped = line.strip()
        if SECTION_END.match(line):
            close()
            item, match = None, HEADER.match(line)
            if match and len(sections) >= limit:
                return sections
            # `boards`: the boards this firmware is for; empty for the shared firmware every board builds.
            current = ({'app': match.group(1), 'firmware': match.group(2),
                        'boards': match.group(3).split(', ') if match.group(3) else [], 'lines': []} if match else None)
            if current:
                sections.append(current)
        elif (bullet := BULLET.match(line)) and current is not None:
            close()
            item = [bullet.group(1).strip()]
        elif stripped and item is not None and (line[:1].isspace() or not blank) and not line.startswith('#'):
            # Markdown continues a bullet with an indented line, or with any line right under it.
            item.append(stripped)
        elif stripped:
            close()
            item = None
        blank = not stripped
    close()
    return sections


def plain(markdown):
    """The text of one bullet without Markdown: bold, italics and links outside code, and the code's backticks."""
    parts = CODE.split(markdown)
    for index in range(0, len(parts), 2):
        parts[index] = LINK.sub(r'\1', ITALIC.sub(r'\1', BOLD.sub(r'\1', parts[index])))
    return ''.join(parts).strip()
