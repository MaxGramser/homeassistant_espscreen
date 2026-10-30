# The add-on counts a screen's reboot as missing frames

## The symptom
After the Guition 10.1 rebooted at 21:40 (2026-10-29) its stream's line said "695780 missing" and "20.18 s at most":
the RTP sequence numbers and timestamps start again at boot and the frame watch counts the gap as missing frames
and a huge lag.

## Next step
In the frame watch, treat a sequence number that jumps backwards (or a timestamp that jumps back) as a new stream:
reset the expected sequence and the lag baseline, count nothing. A small test with a sequence that restarts.

## Pointers
screen_manager/app/camera_source.py (FrameWatch, Lag), tests/test_camera_source.py (FrameWatch, Lag).
