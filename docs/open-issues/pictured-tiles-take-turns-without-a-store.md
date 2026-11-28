# Without a place in the picture store, a page of several pictured tiles loaded them in turn without end

## The symptom

On the host render as a board without PSRAM (`tools/render/run.py guition --only media`, without `KEPT_PAGES_HOST=1`),
the favourites page of the media round has three favourites with a picture and one cover tile, all of one player. Each
tile asks for its picture once. After that the four pictures were downloaded again and again, each about once a second,
for as long as the page stood, and only the tile that loaded last showed a picture: the cover tile in most runs, the
favourites as plain tiles with their icon.

In one run of four on a JC8012P4A1 the favourite that was playing had its turn at the moment of the picture
(`media-favorites-playing.png`). It stood in the form of a favourite with its picture, its name and line in white and
its pause key, with no picture drawn under them: white words on a white card.

## What we know

- Measured 2026-11-27 on dev's tree (bac49021, ESPHome 2026.9.0): "asked for the picture of tile 0", 1, 2 and 4 once
  each, then "tile N: picture loaded" four times a second for the 35 seconds the page stood, 136 downloads. Measured
  again 2026-11-28 on ef5681da: 60 downloads in the 15 seconds the page stood, fifteen of each tile.
- The loader itself goes round (tests/test_picture_loader.cpp, 2026-11-28, a `kept` that holds only the last download
  of a slot): two tiles give 2 asks and 120 downloads in a minute, four tiles 4 asks and 240 downloads, each download
  taking the last picture off the glass. A picture no store took over is its slot's own download
  (`picture_rounds_lvgl.h`: `picture_done`, `slot_key`) and goes when the next one loads into that slot (`slot_letgo`).
  The loader reads every round whether a picture is had, so the tile whose picture left the slot wanted it again at
  once, through the link it had: no new question, a new download every 800 ms for each tile (`camera_view::GAP_MS`).
- The same happened in the slot of the cards: with the library open over the media card, the card's cover and the
  library's page took the slot from each other (three downloads of each in the three seconds the library stood in the
  render of ef5681da).
- The white words: `tile_pictures_letgo` hides a card's picture at once and has the card drawn again, which happens a
  tenth of a second later (`ui_refresh` in packages/core.yaml waits 100 ms). `style_tall` gives a favourite its white
  name while its picture object is shown, and only runs when the card is drawn. So for a tenth of a second after every
  download of another tile, the card stood in white on its own colour. With four downloads a second a snapshot met that
  moment now and then.

## Which screens this is

- **No board without a store draws pictures.** A board has pictures when its file includes
  `packages/features/camera.yaml`, which binds the three download slots; without it `camera_supported()` and
  `tile_pictures_supported()` are false and no picture is ever asked for. The three boards without PSRAM (the two CYDs
  and the Hosyond 4-inch) do not include it, nor do the Freenove FNK0104S and the Waveshare 3.5. Every board that does
  has PSRAM, so `picture_store::budget_for` gives it a store. The path without any store is the host program's alone,
  where a build without `KEPT_PAGES_HOST=1` has a budget of 0. The editor's preview has a store of its own
  (`web/wasm/image_transport.h`).
- **A board with a store can reach the same path.** `picture_store::adopt` returns nothing when every one of its 48
  places (`ENTRIES`) holds a picture that a card still draws, on the glass or on a kept page
  (tests/test_picture_store.cpp, "one more"); `picture_done` then leaves the picture in its slot ("no room to keep" in
  the log), which is the path above. The budget in bytes does not stop it: over the budget a kept page's picture makes
  way, but nothing makes way for a place. A board with 8 MB of PSRAM keeps about 1.2 MB, which pictures the size of
  a card fill long before 48 places are taken (a tile of the 4-inch Guition's page of two by three is about 58 KB:
  twenty of them). A P4 board keeps 6 MB: a tile of a 10.1-inch page of five by five is about 65 KB, so 48 of them are
  about 3 MB, and two pages of 25 favourites, covers, cameras or maps are 50 pictures. The last two of the second page
  would then have taken turns as the host's tiles did, two downloads a second over Wi-Fi for as long as that page
  stood. Nobody has reported it, and it was not looked for on glass.

## Ruled out

- The paper branch: dev's own tree does it.
- The ESPHome version: 2026.9.0 and 2026.11.0 both.
- A board without PSRAM: none draws pictures (above).

## Solved

2026-11-28, on the branch `pictured-tiles-take-turns` (the commit "Pictures: a picture without a place in the store has
one turn in its slot").

- **The loader** (`picture_loader.h`, `in_slot`, `stands_aside`): the binding tells the loader which picture is its
  slot's own download. A picture that left its slot for another owner's stands aside while that one is drawn from the
  slot and still wanted: it does not load, is not asked for, and counts as not waiting, so no spinner turns and nothing
  is held up behind it. When the picture in the slot is no longer wanted (its tile went, its card closed), one of those
  that stood aside has its turn again. Another picture of the same owner (another track) is a new picture with a turn
  of its own. A picture for a page out of sight never takes a slot from the glass, and the glass never stands aside
  for one. A picture the store let go, which was never its slot's own, is fetched again at once as before.
- **The words** (`tile_picture_lvgl.h`, `tile_pictures_letgo`): the card whose picture is taken has `style_tall` run in
  the same moment, so a favourite's name, line and key and a camera card's name take the card's own colours at once
  and not a tenth of a second later.

Measured after it:

- tests/test_picture_loader.cpp: two tiles 2 asks and 2 downloads in a minute, four tiles 4 and 4; the last one loaded
  stays; two cameras, the one in the slot refreshes at its pace and the other loads once; a download that takes the slot
  and breaks off gives it back; a store with one place left keeps its picture untouched.
- The host render, `guition --only media` on ESPHome 2026.9.0, without `KEPT_PAGES_HOST=1`: the favourites page asks
  for four pictures and downloads four, where the tree before it downloaded 60 in the same 15 seconds. The cover tile,
  the last one loaded, has its picture in every picture of the page, and the three favourites stand as plain tiles.
  The card's cover and the library's page come to five downloads where they were seven. The round passes.
- Two pictures of that round were a matter of timing before and are steady now: the library's albums
  (`media-albums.png`) stood without their covers when the card's cover had the slot at that moment, and
  `media-favorites-starting.png` showed whichever tile had its turn (Low Sun with its picture in the run before the
  change, the cover tile after it).
- Two runs of the tree with the rule differ only in what moves by itself (the spinners of the starting screens and of
  the favourites that wait, the rolling line of the card's full view): the favourites and the albums are the same to
  the pixel.
- The same with `KEPT_PAGES_HOST=1` (the store of a 4-inch Guition): four asked, four downloaded, all four kept
  ("store: 4 pictures, 275 of 1200 KB"), and every favourite that has a picture shows it. No "no room to keep".

## Left open

- Not seen on glass: no home test screen has 49 pictured tiles on its glass and kept pages. A P4 board with two full
  pages of favourites and its log at DEBUG would show it: "no room to keep" once for each picture past the 48th, and
  each of those loaded once.
- On such a board the pictures past the 48th still do not all show: of those on the glass the last one loaded has its
  picture, the others stand as plain tiles. What would give the glass all of its pictures is a rule in the store, not
  in the loader: when every place is taken by a picture on a card, the one that only a page out of sight draws makes
  way for the glass, as it does over the budget in bytes (`picture_store::collect`, `picture_away`,
  `picture_let_go`), with a picture fetched ahead never using it (the lesson of
  [pictures-ahead-on-a-tight-store.md](pictures-ahead-on-a-tight-store.md)). Not built.
- A cover tile of one row takes its light words from `style_tall` only while its picture is shown, and its own colours
  from the pass before it, so it still waits the tenth of a second for its redraw when its picture is taken.
- The slot is held by a picture, not by its owner. When the owner of the slot's picture moves on to another picture
  (the library turns a page, a tile's track changes), nobody wants the slot's picture for the moment the new one takes
  to come, and one of those that stood aside loads in between: one download more, and on glass a picture that shows
  for that moment. In the render it is the card's cover loading again under the library at each page turn.

## Pointers

`components/smart_display/picture_loader.h` and `picture_loader.cpp` (`in_slot`, `stands_aside`, `settle`),
`picture_rounds_lvgl.h` (`loader_bind`, `picture_done`, `slot_letgo`), `picture_store_lvgl.h` (`pictures_kept`),
`picture_store.h` (`adopt`, `make_room`, `ENTRIES`), `tile_picture_lvgl.h` (`tile_pictures_letgo`),
`runtime_tiles.h` (`style_tall`, `render_favorite_card`), tests/test_picture_loader.cpp, tools/render/run.py (the media
round's favourites), docs/PICTURES.md ("Memory"),
[pictures-ahead-on-a-tight-store.md](pictures-ahead-on-a-tight-store.md) for the same family on a small store.
