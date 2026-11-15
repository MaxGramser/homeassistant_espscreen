# The tile icon font follows whichever cards are bound

## The symptom
On a Guition 10.1 inch (2026-11-15) a meter's ring showed an empty circle after its page came back onto the glass
(page 3, then 4, twice), until the sensor's next value drew it again: up to a minute.

## What we know
`runtime_tiles::tile_icon_font()` returns the icon font of the first card in `widgets` that has one, so its answer
depends on which page's card set is bound when it is asked. A card drawn while another set is bound measures that set's
icon font. The meter took it as its middle icon face, fell to a face without the glyph and drew nothing. The meter
now uses its own card's icon font and a face that has the glyph (`meter_view.cpp`, `meter_card.h` `ring_at`).

## Still open
The same scan feeds `energy_view.cpp`, `calendar_view.cpp`, `module_todo.cpp`, `module_text_edit.cpp`,
`module_text_card.cpp`, `module_vacuum_tile.cpp`, `plugin_host.cpp` (`Font::ICON`), `module_dock.h` and several card
builders in `runtime_tiles.h` (the detail keys, the remote, the media keys). Each can measure differently by the page
that is bound. The fix: one tile icon font fixed at boot from the look, as every other font is (AGENTS.md, "A fixed set
of fonts"), and `tile_icon_font()` returns it.

## The deciding experiment
With the fixed font in, each of those cards on a page that is not the first, opened after a page with other card sizes:
their icons keep one size and none is empty.
