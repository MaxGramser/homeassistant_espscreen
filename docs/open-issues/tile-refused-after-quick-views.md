# A live tile keeps its stills after a full view was opened and closed quickly

## The symptom
On a Guition 4848S040 (an S3, one live tile), a camera opened full screen and closed again six times within four
seconds over its live tile. After the last close the tile asked for its stream three times within two seconds, and
each time the app answered 503 ("not a picture (answer 503, 33 bytes)"). After its third failure the tile kept its
stills until the page turned (dev b50069e7, 2026-10-30, over the screen's API with `preview_camera`).

## What we know
The 503 is the app's `why_refused` (screen_manager/app/live_stream.py): "This screen plays one camera live", its count
of the screen's tile links that still stream (`tiles_streaming`) at or above the screen's `live_tiles` of 1. The
screen had already ended the tile's previous stream, so the app still counted a tile link the screen had left. With a
calmer close (one view, open for 30 s) the tile was live again 0.6 s after the view closed.

## Ruled out
The firmware's own count: every stream of the run opened in slot 0 and ended before the next opened, never two.

## Candidates
- A tile link "a picture an ask" counts as streaming until its idle timeout, not until the screen's last ask.
- The tile's question after a view is a new link while the old one of the same tile still counts.

## The deciding experiment
Repeat the six quick views with the app at debug: log `tiles_streaming(screen)` and each link's `streaming` and
`used` at every refusal. If an ended tile's link still counts, end a tile link when the same tile asks again.

## Pointers
screen_manager/app/live_stream.py (`why_refused`, `begin`, `end`), components/smart_display/live_spots.h (TRIES, the
spot giving up after three failures).
