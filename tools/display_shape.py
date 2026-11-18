"""The circular frame for board metadata, matching components/smart_display/display_shape.h.

Only geometry lives here. Native widgets are drawn by the firmware and its WASM preview.
"""
import math


def home(width, height, edge, touch, line, mark, gap, row_gap):
    radius = max(0, min(width, height) // 2 - max(0, edge))

    def band(top, bottom):
        dy = max(abs(top - height // 2), abs(bottom - height // 2))
        half = math.floor(math.sqrt(radius * radius - dy * dy)) if dy < radius else 0
        return dict(x=width // 2 - half, y=top, w=2 * half, h=max(0, bottom - top))

    half = min(radius, touch * 3 // 2 + edge // 2)
    bottom = height // 2 + math.floor(math.sqrt(max(0, radius * radius - half * half)))
    footer = band(max(height // 2, bottom - touch), bottom)
    top = height // 2 - radius + touch * 2 // 5
    status = band(top, top + line)
    heading = band(top + line + row_gap, top + line + row_gap + max(line, mark))
    grid = band(heading['y'] + heading['h'] + gap, footer['y'] - gap)
    middle = height // 2
    half = max(0, min(middle - grid['y'], grid['y'] + grid['h'] - middle))
    grid = band(middle - half, middle + half)
    return dict(status=status, heading=heading, grid=grid, footer=footer)


def board_frame(values, line):
    dpi = round(float(values['DISPLAY_DPI']))
    reference = 143 if values['LOOK'].strip('"') == 'compact' else 170
    scale = (dpi * 100 + reference // 2) // reference
    px = lambda n: (n * scale + 50) // 100
    mm = lambda n: (dpi * n + 12) // 25
    mark = round(int(values['FONT_ICON_HOME_SIZE']) * 17 / 24)
    return home(int(values['PANEL_W']), int(values['PANEL_H']), mm(1), mm(7), line, mark,
                max(px(2), (dpi * 15 + 127) // 254), min(px(3), 4))
