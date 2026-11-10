# A call's picture over the whole glass, with its keys and the picture of oneself over it

A video call now shows the other screen's picture beside its keys, the doorbell's way. The design was the picture over the whole
glass with the keys and the picture of oneself lying over it. Tried and taken back on 2026-11-10.

## What was measured

A reTerminal D1001 and a Guition 10.1, a call through a Home Assistant Yellow, both directions at once:

| Route | Pictures a second | Laying out a picture | Sound waiting on its way |
|---|---|---|---|
| Keys beside the picture, as it is now | 8 to 10 | 22 to 55 ms | 20 to 30 ms |
| Whole glass, scaled twice through the PPA | 0.8 to 1.8 | 107 to 175 ms | 106 to 1230 ms |
| Whole glass, pictures sent at the glass's size and copied once | 1.9 to 4.2 | 175 to 210 ms | 123 to 366 ms |

## What is left to try

The time goes on the PPA, which the camera's own halving for the video encoder uses 15 times a second as well, and on the frame's
sprites. Candidates: a call's camera at a lower rate while its picture is being shown, the picture sent smaller and scaled on the way
to the glass while the sprites are laid afterwards on the glass itself, or the sprites only on the frames a key or the picture of
oneself changed.
