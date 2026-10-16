# The vacuum card

A tap on a robot vacuum's tile opens its card. On a board with 8 MB of flash or more the card shows the robot's map,
cleaning per room and the robot's own routines, next to its state, battery, keys and suction and water. The CYD and
the other 4 MB boards keep the card they had: the robot, its keys and its suction and water.

## What it shows

Everything comes from Home Assistant, and the card shows only what your robot offers. A robot without a map, rooms or
routines gets a card without them; nothing is greyed out that it can never do.

- **The robot.** Its state as Home Assistant names it, with its battery (from the battery sensor on its device; a robot
  without one shows none). While it cleans: the room it is in, how far it is and the floor it did, with a thin bar.
  On an error: why, in Home Assistant's words, when the robot's integration reports it.
- **The map.** When the robot's device has a map (an image or camera entity, as Roborock, Ecovacs, Neato and Tuya give
  one), the card shows it. Tessera Screen Manager cleans the map up and draws it in the screen's own colours, light or
  dark: soft colours per room, walls as lines, without the hatching and specks the integration draws. A map that is
  more like a photo is only cut and fitted. Most robots draw a new map only while they clean, so the map of a robot in
  its dock is the one of its last run.
- **Start and Dock.** The keys follow what the robot can do, as Home Assistant's own dialog does: Pause while it
  cleans, or Stop for a robot that cannot pause, or Dock for one that can do neither; Resume while it is paused; Stop
  instead of Dock for a robot that cannot go home. Locate sits beside them as a round key where there is room, else
  in the top bar.
- **Per room.** For a robot that can clean by area (Home Assistant 2026.3 and later, `vacuum.clean_area`): tap the
  rooms in the order you want them cleaned and press Start, which counts them. The rooms are the areas you linked to
  the robot's segments in Home Assistant, in Home Assistant's order, on the card itself on a larger screen or behind
  the **By area** key. With rooms on more than one floor, the view shows one floor at a time; with more rooms than fit,
  it shows them in pages. A robot with more than one map only offers the rooms of the map it is on now, because it
  skips the others. Home Assistant itself notes that not every robot keeps the order.
- **Suction and water.** The cleaning mode, the suction and the water or mop intensity, the rows the chosen mode uses.
  On a larger screen they are on the card; on a smaller one the fan key in the top bar opens them.
- **Routines.** The buttons the robot's integration puts on its device that run something (Roborock's routines from
  its app, an Ecovacs station's actions), as a list on a larger screen or behind the **Routines** key. Buttons that
  reset a consumable or change a setting are left out.

## Linking the rooms

Cleaning per room needs the robot's segments linked to your areas, once, in Home Assistant: open the vacuum's entity
settings and choose **Map vacuum segments to areas**. Until then the **By area** view says so. When the robot's map
changes (a new map, a firmware update), Home Assistant raises a repair to link them again.

## How it fits the glass

The card grows with the screen. Square and standing glass stack it in one column: the robot with its map, the keys,
and then the rooms, suction and water and routines as long as the map keeps its room; what does not fit becomes a key
to its own view. Landscape glass puts the map at the left and the rest at the right. Low glass (a 3.5-inch landscape
board) puts the state beside the map and one row of keys under it.

## For developers

- `screen_manager/app/vacuum_card.py`: the `vc` block of a vacuum's state message, sent to a screen whose hello says
  `vacuum_card`: the map entity and its mark, the rooms (`[area id, name, icon, floor]`) with the floors, `unmapped`,
  the routines, the error (`err`), the progress (`pg`) and the floor cleaned (`ar`). `related()` lists the entities
  whose change sends it again.
- `screen_manager/app/vacuum_map.py`: the map read once per mark and drawn per size and look; served through the
  picture port (`camera_feed.CameraFeed.vacuum_map`, the camera request with `vmap`, answered with `t` `vmap`).
- `components/smart_display/vacuum_model.h`: the block on the screen and the decisions without LVGL: the keys a robot
  gets, the rooms picked in order and the template for `cleaning_area_id`, floors and pages
  (`tests/test_vacuum_model.cpp`).
- `components/smart_display/module_vacuum_card.cpp`: the card of the module `vacuum_card` (docs/MODULES.md), a
  compilation unit of its own (as media_library.cpp: the S3's literal range): its plan per glass, its views (rooms,
  routines, suction and water) and the map's picture. `module_vacuum_card.h` is what runtime_tiles.h reaches of it.
- `tests/test_vacuum_module.py` checks the block and the map; `tools/render/run.py --only vacuum` renders the card in
  every state, with a drawn map or your own (`VACUUM_MAP=<a PNG>`).
