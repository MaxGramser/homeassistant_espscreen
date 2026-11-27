# Without a picture store, a page of several pictured tiles loads them in turn without end

## The symptom

On the host render as a board without PSRAM (`tools/render/run.py guition --only media`, without `KEPT_PAGES_HOST=1`),
the favourites page of the media round has three favourites with a picture and one cover tile, all of one player. Each
tile asks for its picture once. After that the four pictures are downloaded again and again, each about once a second,
for as long as the page stands, and only the tile that loaded last shows a picture: the cover tile in most runs, the
favourites as plain tiles with their icon.

In one run of four on a JC8012P4A1 the favourite that was playing had its turn at the moment of the picture
(`media-favorites-playing.png`). It stood in the form of a favourite with its picture, its name and line in white and
its pause key, with no picture drawn under them: white words on a white card.

## What we know

- Measured 2026-11-27 on dev's tree (bac49021, ESPHome 2026.9.0): "asked for the picture of tile 0", 1, 2 and 4 once
  each, then "tile N: picture loaded" four times a second for the 35 seconds the page stood, 136 downloads. The paper
  branch's tree (c5aec308, ESPHome 2026.11.0) does the same.
- The host says so itself: `picture_store_lvgl.h` gives the host a store only with `KEPT_PAGES_HOST=1`, "without it
  the host keeps one download at a time, and a page of several pictured tiles shows only the last". That is the path of
  a board without PSRAM: a tile draws the download itself until the slot loads another picture
  (`picture_rounds_lvgl.h`, `picture_done`, `slot_letgo`, `tile_pictures_letgo`).
- The loader reads every round whether a picture is had (`picture_loader.h`, "what the store holds is there"), so a
  tile whose picture left the slot for the next tile's wants it again at once. With four tiles that never ends.
- This is why two runs of one tree differ in the media round's favourites pictures (docs/TESTING.md, the render):
  which tile had its turn decides the picture.

## Ruled out

- The paper branch: dev's own tree does it.
- The ESPHome version: 2026.9.0 and 2026.11.0 both.

## Not known

Whether a real board without PSRAM does this. On glass each turn is a download over Wi-Fi, and the white words would
show for as long as a turn takes. Nobody has looked at a board without PSRAM with two pictured tiles on one page.

## Candidates

- A rule is missing for a board without the store: a tile whose picture left the slot for another tile on the glass
  should not want it again while that other tile is drawn from the slot. One pictured tile per page would then show,
  as the comment in `picture_store_lvgl.h` describes, and nothing would be downloaded twice.
- The words of a favourite follow the picture object, not the picture: `render_favorite_card` reads `photo` from the
  object being shown, and the object is shown while its source is a download the slot is about to give to another tile.

## The deciding experiment

A board without PSRAM with two favourites that have a picture on one page, the log at DEBUG for a minute: count
"picture loaded", and watch the names. On a PC, tests/test_picture_loader.cpp with two tile owners on one slot and a
`kept` that holds only the last one loaded: the number of asks and loads in a minute says whether the loader itself
goes round. The render with `KEPT_PAGES_HOST=1` shows what the same page is with a store (not run on 2026-11-27).

## Pointers

`components/smart_display/picture_store_lvgl.h` (`pictures_kept`), `picture_rounds_lvgl.h` (`picture_done`,
`slot_letgo`, `tile_picture_want`), `tile_picture_lvgl.h` (`tile_picture_place`, `tile_pictures_letgo`),
`runtime_tiles.h` (`render_favorite_card`), `picture_loader.h`, tools/render/run.py (the media round's favourites),
[pictures-ahead-on-a-tight-store.md](pictures-ahead-on-a-tight-store.md) for the same family on a small store.
