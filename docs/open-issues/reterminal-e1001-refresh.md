# The reTerminal E1001's panel and ESPHome's driver for it

## The symptom

Not seen here yet: the board is built (dev 2026-11-28) and no unit has run it. An ESPHome issue opened on 2026-11-27,
esphome/esphome#23367, reports that on ESPHome 2026.11.1 none of the refresh modes of the `epaper_spi` model
`Seeed-reTerminal-E1001` gave a right picture on that unit: a plain whole refresh showed grey noise, a fast whole
refresh had black and white the other way round, and a partial refresh was shifted sideways and wrapped at the edge.

## What we know

- The paper glass drives the panel with the driver's partial refresh and a fast whole refresh between
  (`full_update_every: 255`, `request_full_update`), the two modes the issue calls inverted and shifted.
- Another project (a weather display on the same board, public on GitHub) uses the same model with a partial refresh
  every minute and a fast whole one every hour, with a patch that only keeps the panel out of its own deep sleep, and
  reports a right picture.
- The issue's reporter saw the old `waveshare_epaper` models (`7.50inv2`, `7.50inv2p`) not drive the panel at all.

## Candidates

- The units differ (a panel revision), and one of the two reports holds for each.
- The issue's setup differs in something the paper glass does not share (its SPI speed, its own lambda).

## The deciding experiment

The first unit on this firmware, with the three checks of docs/RETERMINAL_E1001.md "What is still unknown": the first
page prints the right way round, a page turned with a key stands where it should, and the traces after a few turns.
A photo of each.

## Pointers

docs/RETERMINAL_E1001.md, `packages/hardware/seeed-reterminal-e1001.yaml`, `components/paper_glass/`, ESPHome's
`epaper_spi_uc8179.cpp`.
