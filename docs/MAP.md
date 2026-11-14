# A map card

Tessera can show a map of where people are: the streets around them, your zones, and a marker for everyone on the
card. Tessera draws the whole card in the screen's own colours and sends the screen a picture, the way a live camera
arrives. The screen never gets a location.

There are two kinds of map:

- **A person's map** (app 0.4.33, firmware 0.20.0): set a `person.*` tile's **Display** to **Map**. It follows that
  person, and whoever you add under **Also on the map**.
- **The map tile** (app 0.4.36, firmware 0.21.0): **Map** under the screen's own cards in the library. It belongs to
  no one: it follows **everyone** Home Assistant knows the place of, or only the people and trackers you choose. Just
  the two of you, or only your devices.

Both work on every tile size, from one cell to the whole page, on every board that draws pictures (the boards with
`camera` in `screen_manager/app/boards.json`). The CYD and the other boards without memory for pictures do not offer them,
and a layout with one is refused on them.

**A tap opens the map over the whole screen**, as a camera tile does: drawn as large as the board takes a camera picture,
with the round back key and the tile's name at the top. A small 1 x 1 map you glance at becomes a full map with a tap.

**On the full map, tap a person or a tracker** to focus on them, as Home Assistant's own map does: they stay exactly on
their place in the middle, closer in, their name goes into the top bar, and a card over the bottom has rows as the
light's effects page has them: their state with Home Assistant's icon and since when, the battery where they report one,
and the changes of the last day, newest first, each with its time. A tap beside the markers, or the back key, goes back
to everyone. The screen gets where each marker is on the picture (pixels) and the card's words, never a place.

**A person's own tile** (any display, firmware 0.21.0) opens the same focused map with a tap, on a board that draws
pictures: where they are, with their card. Holding the tile opens its card with the history, as before; on a board
without pictures a tap opens the card too.

Markers stand exactly on their coordinates. Only markers that would cover each other on the glass fan out round their
middle, so each stays to be seen; the one a finger picked never moves.

## The choices

| Choice | What it does |
| --- | --- |
| **Follow** (map tile) | **Everyone**: every person, and every device tracker that is not already someone's, as Home Assistant's own map card does with `show_all`. **Chosen**: the list under it. |
| **On the map** / **Also on the map** | People and device trackers, up to eight. A device tracker is anything Home Assistant reports a place for: a phone through the Companion app, a car through its integration, a tag. One that only knows home or away has no place and is not offered. |
| **Show** | **Everyone**: the smallest view that holds everyone, with the zone each is in. **Around home**: your home zone in the middle. **Around this person** (a person's map): that person in the middle. |
| **Distance** | How far Around home and Around this person reach: street, neighborhood, town or region. Someone outside the view is a small marker at the edge, pointing the way. |
| **Markers** | **Photo**: a person's picture in their marker, as Home Assistant shows it, and their initials when they have none. **Initials**: always the letters. |
| **Names** | First names beside the markers: where the card has room (from about 200 pixels high, and always over the whole screen), always, or never. |
| **Zones** | Your zones as soft circles, or none. |
| **Streets** | The streets from Home Assistant's map, or a plain ground with only the zones and people: nothing is fetched. |
| **Look** | As the screen (light or dark with it), or always light, or always dark. |
| **On the picture** | The tile's name on a small label at the bottom left, or nothing. |

## As Home Assistant does it

The map follows Home Assistant's own map card (`hui-map-card.ts`, `ha-map.ts` and `get_entity_location.ts` in its
frontend), so a household looks the same on a screen as in Home Assistant:

- **Where someone is**: their own latitude and longitude. A person without one who is in a zone (`in_zones`) stands in
  the middle of that zone.
- **Everyone** leaves out a tracker a person already follows (the person's `source`) and anything hidden in the entity
  registry.
- **Colours**: every person, tracker and zone gets a colour in the order Home Assistant made them (the home zone
  apart), so someone has the same colour on every map. The colours are the screen's own tile palette.
- **Markers**: a ring in that colour, around the person's picture (`entity_picture`) or the first letter of each word of
  their name, at most three. Where Home Assistant reports a GPS accuracy wider than the marker, a faint circle in the
  same colour shows it.
- **Zones**: passive zones are left out.

## Where the streets come from

Home Assistant Core has a `map_tiles` integration, which its own map card uses. It fetches OpenStreetMap's vector tiles
with Home Assistant's own identification, as the OpenStreetMap tile policy asks, and keeps them for a week. Tessera
asks Home Assistant for those tiles and never contacts a tile server itself. A request names a zoom and two whole numbers:
no entity, no name.

A vector tile says what is there (a street of some kind, water, a park) and nothing about how it looks, so Tessera
draws it in the screen's colours: a quiet ground of greys with white streets, water and green in soft tints, in light and
dark. The only strong colours on the card are the people and their zones. The card carries "© OpenStreetMap".

When Home Assistant has no tiles to give (an older Home Assistant, or no internet), the card is drawn from the zones and
the people alone, and Tessera asks again after ten minutes. A person's picture comes through Home Assistant too, or
from a public address on the internet; never from another address in the house.

## When it is drawn again

Never on a clock. With the layout, each map tile gets a short movement mark: a hash of who is on it and where (rounded to
about 25 meters, so a phone's drift is no change), their states, names, pictures and colours, the zones, and the tile's
own choices and name. The screen asks for a new picture when the mark changes. A household that stays put costs nothing.

When a picture does not come (firmware 0.30.0): a card keeps the map it shows until the next one has loaded, so
someone moving never empties it. If Tessera cannot draw one at that moment, the screen asks again after ten seconds
and then a little later each time, up to five minutes, and keeps the last map meanwhile. Older firmware asked once: a
page with only maps then showed its plain tiles until the page was turned.

A map can take a while to draw, longer on a slow host and on a large screen, whose full view has many more streets. It
is drawn once for the screen's question, however long that takes: the screen goes on waiting and asks again after ten
seconds, and that second question shares the drawing under way. The picture of that drawing is what the screen's first
download gets, at once, because a download stops when its first bytes take more than four seconds. A map some streets
were missing from is kept for a minute, so an open full view, which looks again every four seconds, does not draw it
over and over.

## Light and dark

The screen says which look it is in when it asks for its pictures, and gets the map drawn for that look, unless the tile
keeps a look of its own. A screen in dark mode and one in light mode showing the same card each get their own picture.
Tessera keeps the last maps it drew by their mark, their size and their look, so a page that loads again for a camera
next to it does not draw its map again. The screen keeps its pictures under a name that includes the look as well, so
switching the look asks for the other map.

## Privacy

- **No location reaches a screen.** Who is on a card and how it frames them stay in Tessera; the screen gets the
  movement mark and pixels.
- **The picture travels unencrypted over your network**, on port 8098, like every other picture. A map shows roughly
  where someone is to anyone who can read that traffic. Keep that in mind for a screen on a guest network.
- A screen only gets a map for a map tile on its own saved layout, drawn from that saved tile.

## For developers

| Piece | Where |
| --- | --- |
| Reading Home Assistant's vector tiles | `screen_manager/app/vector_tiles.py` |
| The tiles through Home Assistant, cached | `screen_manager/app/map_tiles.py`, `HomeAssistant.map_tile` in `server.py` |
| Who is on it, framing, the movement mark, the drawing | `screen_manager/app/map_card.py` |
| A screen's request, the full view, focus and its card, pictures, kept maps | `Manager.answer_live`, `answer_map_full`, `map_sheet`, `map_render`, `map_photos` in `server.py` |
| The choices | `catalogue/person.yaml` (`map`), `core.validate_layout`, the map tile `screen.map` in `core.BUILTIN` |
| The firmware | `Tile::is_map()`, `card_art`, `live_wanted` (the mark and `dark`), the tap into `camera_open`, `MapSheet` and `map_sheet_draw` in `components/smart_display` |
| The editor | `TileInspector.vue`, `model/tile-options.ts`, `model/page-validation.ts` |
| Tests and renders | `tests/test_map_card.py`, `tools/render/map_tiles.py` |

The picture pipeline the map shares is described in [CAMERA.md](CAMERA.md).
