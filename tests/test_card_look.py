"""What LVGL draws later, in a draw callback, is drawn in its card's look (docs/THEME.md "A card's look"): a card in a
section whose tiles follow its contrast is painted in the other look, and a draw callback runs outside every paint of
ours, so each one that draws on a grid tile opens the card's scope on its own object (CardScope(obj), or
theme::LookScope where only theme.h is known). Without it a meter's value stood light on a light card (2026-11-15).

A new draw callback either opens the scope in its first lines or is named below with the reason it needs none."""
from pathlib import Path
import re
import unittest

COMPONENT = Path(__file__).resolve().parents[1] / 'components/smart_display'
CALL = 'lv_obj_add_event_cb('
SCOPE = re.compile(r'\b(CardScope|LookScope)\b')

# A registration whose callback is a parameter: the functions handed in there, each checked like any other.
HANDED_IN = {
    ('module_vacuum_tile.cpp', 'draw'): ['draw_under', 'draw_over'],
}
# Draw callbacks that need no scope, and why.
NEEDS_NONE = {
    ('weather_chart.h', 'draw_event'): 'the weather chart stands only on the open card (render_weather_detail)',
    ('calendar_view.cpp', 'draw_cb'): "the calendar's full view (open card), never a grid tile",
    ('module_todo.cpp', 'draw_cb'): "the to-do list's full view (open card), never a grid tile",
    ('module_clock_faces.cpp', 'paint_draw'): 'its colours are captured when render_slot paints the face',
    ('module_text_edit.cpp', 'area_draw'): 'the text editor, no card',
    ('keyboard_lvgl.h', 'draw'): 'the keyboard, no card',
    ('runtime_tiles.h', 'draw'): "the travel stripe's colour is a constant",
    ('runtime_tiles.h', 'history_fill'): 'the history graph of the open card',
    ('runtime_tiles.h', 'history_bar'): 'the history timeline of the open card',
    ('runtime_tiles.h', 'extra_draw'): 'its fill colour is captured in render_slot, inside the card scope',
}


def registrations(text):
    """Every lv_obj_add_event_cb(...) for a draw event in `text`: (callback name, None) or (None, a lambda's body)."""
    found, at = [], 0
    while (at := text.find(CALL, at)) >= 0:
        depth, end = 0, at + len(CALL) - 1
        for end in range(at + len(CALL) - 1, len(text)):
            depth += {'(': 1, ')': -1}.get(text[end], 0)
            if depth == 0:
                break
        call, at = text[at + len(CALL):end], end
        if 'LV_EVENT_DRAW_' not in call:
            continue
        callback = call.split(',', 1)[1].strip() if ',' in call else ''
        if callback.startswith('['):
            found.append((None, callback[callback.find('{') + 1:][:600]))
        else:
            name = re.match(r'([A-Za-z_][\w:]*)', callback)
            found.append((name.group(1) if name else callback[:40], None))
    return found


def sources():
    return {p.name: p.read_text() for p in sorted(COMPONENT.iterdir()) if p.suffix in ('.h', '.cpp')}


def body(files, name, first):
    """The first lines of the function `name` taking an lv_event_t, in `first` before any other file."""
    pattern = re.compile(r'(?:static\s+|inline\s+)?void\s+' + re.escape(name) + r'\s*\(\s*lv_event_t\s*\*\s*\w*\s*\)\s*\{')
    for file in [first] + [f for f in files if f != first]:
        found = pattern.search(files[file])
        if found:
            return file, files[file][found.end():found.end() + 600]
    return None, None


class CardLook(unittest.TestCase):
    def test_every_draw_callback_opens_the_card_scope_or_says_why_not(self):
        files = sources()
        missing, seen = [], set()
        for file, text in files.items():
            for name, lambda_body in registrations(text):
                if lambda_body is not None:
                    if not SCOPE.search(lambda_body[:400]):
                        missing.append(f'{file}: a lambda (open CardScope in it, or give it a name and a reason)')
                    continue
                bare = name.split('::')[-1]
                seen.add((file, bare))
                if (file, bare) in NEEDS_NONE:
                    continue
                for callee in HANDED_IN.get((file, bare), [bare]):
                    where, lines = body(files, callee, file)
                    if lines is None:
                        missing.append(f'{file}: {callee} (its definition was not found)')
                    elif not SCOPE.search(lines.split('\n\n')[0][:400]):
                        missing.append(f'{where}: {callee}')
        self.assertEqual(missing, [], 'a draw callback on a card opens CardScope(obj) in its first lines '
                                      '(docs/THEME.md "A card\'s look"), or is named in NEEDS_NONE with its reason')
        stale = sorted(set(NEEDS_NONE) - seen)
        self.assertEqual(stale, [], 'NEEDS_NONE names a draw callback that is no longer registered')

    def test_the_card_carries_its_look_for_what_lvgl_draws(self):
        sections = (COMPONENT / 'module_sections.h').read_text()
        self.assertIn('lv_obj_add_flag(card, theme::OTHER_LOOK_FLAG)', sections)
        self.assertIn('lv_obj_remove_flag(card, theme::OTHER_LOOK_FLAG)', sections)


if __name__ == '__main__':
    unittest.main()
