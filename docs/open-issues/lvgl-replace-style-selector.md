# LVGL's lv_obj_replace_style overwrites the selector of every style it replaces

Not sent anywhere. This is the report LVGL could get, written down so the maintainer can decide whether to send it.
Until LVGL changes, `components/smart_display/look_trade.h` trades a style in place itself (docs/THEME.md "A card's
look"), and its head says why.

## The symptom

A card that changes look trades each shared style on its objects for a copy. With `lv_obj_replace_style(obj, old, new,
LV_PART_ANY | LV_STATE_ANY)` the traded styles stopped applying to anything: the card showed LVGL's default theme
(small corners, a square circle with a border), and trading back did not restore it (found 2026-11-15 with the host
render, tools/render/sections.py).

## The report

**Title:** `lv_obj_replace_style` with `LV_PART_ANY | LV_STATE_ANY` gives every replaced style that selector, so the new
style applies to no part and no state.

**Version:** LVGL 9.5.0 (`src/core/lv_obj_style.c`, the function from line 167; `src/core/lv_obj_style.h`, its
comment from line 108).

**What the documentation says.** `lv_obj_style.h` gives this as an example of replacing a style regardless of its
selector:

```c
lv_obj_replace_style(obj, &yellow_style, &blue_style, LV_PART_ANY | LV_STATE_ANY); //Replace a specific style
```

**What the code does.** The selector argument is used to choose which styles match (the `LV_STATE_ANY` and `LV_PART_ANY`
tests), and then written into every style it replaced:

```c
        lv_memzero(&obj->styles[i], sizeof(lv_obj_style_t));
        obj->styles[i].style = new_style;
        obj->styles[i].selector = selector;
```

So a style that was added with `LV_PART_MAIN | LV_STATE_DEFAULT` comes out with `LV_PART_ANY | LV_STATE_ANY`. No object
is ever in every state at once, so the new style never applies, and the object falls back to its theme. The
`lv_memzero` also clears `is_theme` and `is_disabled`, so a replaced theme style is no longer one.

**Reproduction** (any LVGL 9.5 port):

```c
static lv_style_t red, blue;
lv_style_init(&red);  lv_style_set_bg_color(&red, lv_color_hex(0xff0000));
lv_style_init(&blue); lv_style_set_bg_color(&blue, lv_color_hex(0x0000ff));
lv_obj_t *box = lv_obj_create(lv_screen_active());
lv_obj_add_style(box, &red, LV_PART_MAIN | LV_STATE_DEFAULT);
lv_obj_replace_style(box, &red, &blue, LV_PART_ANY | LV_STATE_ANY);
lv_color_t c = lv_obj_get_style_bg_color(box, LV_PART_MAIN);
/* Expected: blue (0x0000ff). Actual: the default theme's background, not blue. */
LV_LOG_USER("bg %06x", (unsigned) (lv_color_to_u32(c) & 0xffffff));
```

**Expected:** each replaced style keeps the selector it was added with (and its `is_theme` / `is_disabled` flags); the
argument only chooses which styles are replaced. A one-line change would do it: keep the old entry's selector,
`lv_style_selector_t was = obj->styles[i].selector;` before the `lv_memzero`, and write `was` back instead of
`selector`. With a fully specified selector the result is the same as today.

## Pointers

`components/smart_display/look_trade.h` (the trade that works around it), `theme.h` (`restyle_card`, `style_in`),
`tests/test_card_look.py` (only look_trade.h reads an object's styles).
