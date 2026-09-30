"""The alert card's layout, the same rule as the firmware's (components/smart_display/alert_overlay.h), for ESP Screens.

The firmware lays its alert out on the glass it draws on (screen_alert::layout, firmware 0.2.103+), and once the picture
of an alert with a camera is there, again for that picture's own proportions. ESP Screen Manager sends the picture at the
size that layout gives it, so it measures the camera's snapshot and works the frame out here (camera_feed.alert_box),
from the screen's canvas and what boards.json says of its board (tools/generate_board_shapes.py writes the box for a
16:9 picture there too). tests/test_alert_layout.py compiles the C++ rule and checks that the two give the same numbers.
Change one, change the other.
"""
from dataclasses import dataclass


def configure(display_dpi, look):
    """ui::configure: the look, and the scale every size of it is drawn at on this board (a whole percentage)."""
    reference = 143 if look == 'compact' else 170
    dpi = display_dpi if display_dpi > 0 else reference
    return look == 'compact', (dpi * 100 + reference // 2) // reference


# The card's two fonts: `headline` for its title and `sublabel_big` for its words (packages/core.yaml), both Roboto, whose
# line is 2400 font units of 2048 to the em ('hhea' ascender - descender + line gap, tools/font_metrics.py). Their sizes
# are the look's FONT_HEADLINE_SIZE and FONT_SUBLABEL_BIG_SIZE (packages/looks/), drawn at the look's own density.
FONT_LINE_UNITS, FONT_UNITS_PER_EM = 2400, 2048
LOOK_FONTS = {'standard': (170, 27, 21), 'compact': (143, 18, 14)}


def font_line(size):
    """The line height LVGL gets for an ESPHome font of this pixel size: FreeType's, as tools/font_metrics.py reads it."""
    scale = ((size * 64) << 16) // FONT_UNITS_PER_EM
    return ((FONT_LINE_UNITS * scale + 0x8000) >> 16) + 32 >> 6


def lines(display_dpi, look):
    """(title line, subtitle line) of a screen of this density and look: the look's font sizes scaled the way the look
    scales them (at least 8 px, rounded half up like Jinja's round), and the line height of each."""
    reference, title, words = LOOK_FONTS.get(look, LOOK_FONTS['standard'])
    size = lambda base: max(8, int(base * display_dpi / reference + 0.5))  # noqa: E731
    return font_line(size(title)), font_line(size(words))


def px(n, scale):
    """ui::px: a size of the look's own, in this board's pixels."""
    if scale == 100:
        return n
    return (n * scale + 50) // 100 if n >= 0 else -((-n * scale + 50) // 100)


def shrink(parts, over):
    """ui::shrink: take `over` pixels from the parts in order, never below what each needs. `parts` is a list of
    [value, least]; the values are changed in place. Returns what could not be taken."""
    for part in parts:
        if over <= 0:
            break
        room = part[0] - part[1]
        if room <= 0:
            continue
        take = min(room, over)
        part[0] -= take
        over -= take
    return max(over, 0)


def whole_lines(room, line):
    """screen_alert::whole_lines: the subtitle's label is as tall as the whole lines that fit."""
    return room // line * line if line > 0 else room


@dataclass
class Layout:
    card_w: int = 0
    card_h: int = 0
    icon_x: int = 0
    icon_y: int = 0
    text_x: int = 0
    text_w: int = 0
    title_y: int = 0
    title_h: int = 0
    subtitle_y: int = 0
    subtitle_h: int = 0
    button_x: int = 0
    button_y: int = 0
    button_w: int = 0
    button_h: int = 0
    button_inset: int = 0
    image_x: int = 0
    image_y: int = 0
    image_w: int = 0
    image_h: int = 0


PICTURE_W, PICTURE_H = 392, 220  # screen_alert::PICTURE_W/H: a picture's proportions before one is known
PICTURE_MAX_W, PICTURE_MAX_H = 392, 300  # screen_alert::PICTURE_MAX_W/H: the largest picture, in the look's pixels


def picture_area(w, h, aw, ah):
    """screen_alert::picture_area: how much of a picture of aw x ah proportions a frame of w x h shows."""
    if w <= 0 or h <= 0 or aw <= 0 or ah <= 0:
        return 0
    return min(w, h * aw // ah) * min(h, w * ah // aw)


def plain(canvas_w, canvas_h, title_line, line, scale, big):
    p = lambda n: px(n, scale)  # noqa: E731
    l = Layout()
    inset = p(22 if big else 14)
    l.card_w = max(0, min(p(420 if big else 292), canvas_w - 2 * inset))
    l.card_h = max(0, min(p(320 if big else 196), canvas_h - 2 * inset))
    l.icon_x = p(26 if big else 18)
    l.icon_y = p(22 if big else 16)
    l.text_x = p(90 if big else 62)
    l.text_w = max(0, l.card_w - l.text_x - l.icon_x)
    l.title_y = p(26 if big else 16)
    l.title_h = title_line
    l.subtitle_y = l.title_y + l.title_h + p(10 if big else 7)
    l.button_w = p(150 if big else 100)
    l.button_h = p(60 if big else 40)
    l.button_inset = inset
    l.button_x = l.card_w - inset - l.button_w
    l.button_y = l.card_h - inset - l.button_h
    l.subtitle_h = whole_lines(max(0, l.button_y - l.subtitle_y - p(20 if big else 10)), line)
    # Keep this fallback identical to screen_alert::plain in alert_overlay.h.
    if l.subtitle_h < 2 * line:
        gap = p(4)
        l.card_h = max(0, canvas_h - 16)
        l.title_y = l.icon_y = gap
        l.subtitle_y = l.title_y + title_line + gap
        l.button_inset = gap
        l.button_h = min(l.button_h, max(line + gap, l.card_h - l.subtitle_y - 2 * line - 2 * gap))
        l.button_y = l.card_h - gap - l.button_h
        l.subtitle_h = whole_lines(max(0, l.button_y - l.subtitle_y - gap), line)
    if l.text_w < p(80):
        gap = p(4)
        l.text_x = l.icon_x
        l.text_w = max(0, l.card_w - 2 * l.text_x)
        l.title_y = l.icon_y + p(54 if big else 36) + gap
        l.subtitle_y = l.title_y + title_line + gap
        l.subtitle_h = whole_lines(max(0, l.button_y - l.subtitle_y - gap), line)
    l.button_w = max(0, min(l.button_w, l.card_w - 2 * l.button_inset))
    l.button_x = l.card_w - l.button_inset - l.button_w
    return l


def above(canvas_w, canvas_h, title_line, line, scale, big, aw, ah):
    p = lambda n: px(n, scale)  # noqa: E731
    l = plain(canvas_w, canvas_h, title_line, line, scale, big)
    image_inset = p(14 if big else 10)
    widest = max(0, min(l.card_w - 2 * image_inset, p(PICTURE_MAX_W)))
    image_h = [min(widest * ah // aw, p(PICTURE_MAX_H)), 0]
    subtitle = [p(62 if big else 40), 0]
    image_gap, button_gap = p(16), p(4)

    def height():
        return (image_h[0] + image_gap + p(26 if big else 16) + title_line + p(10 if big else 7) + subtitle[0] + button_gap
                + l.button_h + l.button_inset)
    room = canvas_h - 2 * image_inset
    over = height() - room
    if over > 0:
        subtitle[1] = min(subtitle[0], line)
        image_h[1] = min(image_h[0], p(96))
        if shrink([subtitle, image_h], over) > 0:
            return plain(canvas_w, canvas_h, title_line, line, scale, big)
    l.image_h = image_h[0]
    l.image_w = min(widest, l.image_h * aw // ah)
    l.image_x = (l.card_w - l.image_w) // 2
    l.image_y = image_inset
    shift = l.image_h + image_gap
    l.card_h = max(0, min(height(), room))
    l.icon_y += shift
    l.title_y += shift
    l.subtitle_y += shift
    l.subtitle_h = whole_lines(subtitle[0], line)
    l.button_y = l.card_h - l.button_inset - l.button_h
    if l.subtitle_y + l.subtitle_h > l.button_y - button_gap:
        return plain(canvas_w, canvas_h, title_line, line, scale, big)
    return l


def beside(canvas_w, canvas_h, title_line, line, scale, big, aw, ah):
    p = lambda n: px(n, scale)  # noqa: E731
    l = plain(canvas_w, canvas_h, title_line, line, scale, big)
    image_inset = p(14 if big else 10)
    room = canvas_w - 2 * l.button_inset
    tallest = max(0, min(canvas_h - 4 * image_inset, p(PICTURE_MAX_H)))
    narrowest = min(l.card_w, p(300 if big else 210))
    column = max(narrowest, min(l.card_w, room - image_inset - tallest * aw // ah))
    l.image_h = max(0, min(tallest, min(room - column - image_inset, p(PICTURE_MAX_W)) * ah // aw))
    l.image_w = l.image_h * aw // ah
    if l.image_h < min(tallest, p(96)):
        return plain(canvas_w, canvas_h, title_line, line, scale, big)
    l.card_h = max(l.card_h, l.image_h + 2 * image_inset)
    l.button_y = l.card_h - l.button_inset - l.button_h
    shift = image_inset + l.image_w
    icon_x, text_x = l.icon_x, l.text_x
    l.card_w = shift + column
    l.image_x = image_inset
    l.image_y = (l.card_h - l.image_h) // 2
    l.icon_x = icon_x + shift
    l.text_x = text_x + shift
    l.text_w = max(0, column - text_x - icon_x)
    l.button_x = l.card_w - l.button_inset - l.button_w
    return l


def layout(canvas_w, canvas_h, title_line, line, image, display_dpi, look, aw=PICTURE_W, ah=PICTURE_H):
    """screen_alert::layout, number for number."""
    compact, scale = configure(display_dpi, look)
    big = not compact
    if not image:
        return plain(canvas_w, canvas_h, title_line, line, scale, big)
    if aw <= 0 or ah <= 0:
        aw, ah = PICTURE_W, PICTURE_H
    top = above(canvas_w, canvas_h, title_line, line, scale, big, aw, ah)
    side = beside(canvas_w, canvas_h, title_line, line, scale, big, aw, ah)
    return side if picture_area(side.image_w, side.image_h, aw, ah) > picture_area(top.image_w, top.image_h, aw, ah) else top
