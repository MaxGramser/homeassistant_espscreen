# A full view's first link opens with an empty host

## The symptom
On the Guition 10.1, opening a camera full screen from a page with its live tile: "live link 300 ms after the camera
opened", "live link opened 87 ms later, after the page's streams ended", then "live failed for camera.tablet_video"
and "[W][live:794][live_view]: no connection to :80". The second attempt works: "live link 10044 ms after the camera
opened", first picture 11 s after the tap (2026-10-29 21:45, Debug mode log).

## What we know
read_stream was called with a URL whose host is empty. It happens on the first attempt right after the page's
streams ended; the retry 10 s later has a proper URL. So the link the app hands the screen, or the screen's own
building of the URL from it, is incomplete at that moment: perhaps the link arrives before the app's address is
known again after the page's streams closed, or the view takes the link of a stream that was just torn down.

## Next step
Reproduce on the bench with Debug mode: log the URL the view received (runtime_tiles.h, the live link) and where it
came from, at the moment of "no connection to :80". Fix the source; the 10 s retry then never runs.

## Pointers
components/smart_display/live_view.cpp (read_stream, the warning at line ~794), runtime_tiles.h (LIVE_LINK_WAIT_MS,
the full view's link while the page's streams end).

## Solved (2026-10-30)
The link was cleared under the view's feet. When the page's streams had not ended yet, `live_begin` kept the link in
`live_link_waiting`, and `live_tick` called `live_begin(live_link_waiting)` once they had: a reference to that very
string, which `live_begin` then cleared before `live_view::open(url, ...)`. So every tap on a live tile whose stream
had to end first opened ":80", failed, and waited 10 s for the next try. It came with the wait itself (03910c97,
0.4.91). `live_begin` now takes its own copy first; tests/test_live_view.py keeps the order.
