# The page behind an alert that arrives in standby is dimmed twice

## The symptom

An alert that arrives while the screen is in standby wakes it and shows its card, and the page behind the card is
darker than behind the same alert on a screen that was lit. In the light look the difference is plain; in the dark
look the page is black either way and nothing shows. The card itself is the same in both cases.

## What we know

Measured on a Guition 10.1 (ESP32-P4, a screen with motion and the dim on the glass), reading the frame buffer back
over the API (`glass_snapshot`) 2.5 s after `show_alert`, light look, 2026-11-24:

| The screen when the alert arrived | A pixel of the page behind the card |
|---|---|
| lit | (98, 105, 106) |
| in standby (Home Assistant's Sleep, 3 s before) | (49, 56, 57) |

The page's own colour under a 60 % scrim gives the first value, so the lit case is right. The second is that value
dimmed once more.

It is not new. The firmware from before the standby and the alert moved to C++ gave the same picture as the firmware
after it, pixel for pixel but for the clock's digits (32 of 28,676 sampled pixels), when the alert arrived in standby
on both.

## Ruled out

- The move of the standby and of an alert's life to C++ (`screen_standby.h`, `alert_life.h`): same picture before and
  after, and the order is unchanged (the screen wakes, then the card is revealed).
- The card: its place, size, words and key are the same lit and from standby.

## Candidates

1. `screen_motion::show` draws the card with `lv_refr_now` before it lays the dim on the glass. A wake from standby
   leaves LVGL with the whole screen to draw again (the wake overlay goes, a screensaver goes, the cards close). That
   refresh then draws the overlay's own scrim over the whole glass, since the overlay is no longer hidden, and the dim
   on the glass comes on top of it.
2. LVGL resumes from a pause on a dark screen (`screen_power`) and draws the whole screen once, at the same moment.

Both say the same thing: the dim on the glass assumes LVGL has not drawn the overlay's scrim, and after a wake it has.

## The deciding experiment

On a board with the dim on the glass, in the light look: invalidate the whole screen and call `screen_motion::show`
in the same pass, without any standby. If the page comes out dimmed twice, candidate 1 holds, and `show` should finish
what LVGL still has to draw before it reveals the overlay, or skip the dim on the glass when the screen was not clean.
The host render cannot see it: the host has no dim on the glass.

## Pointers

- `components/smart_display/screen_motion.h`: `show`, `dim`, `room_of` (a rim dimmed twice was fixed there before).
- `components/smart_display/alert_life.h`: `show` wakes the screen (`glass.wake`), then reveals the card (`glass.reveal`).
- `components/smart_display/screen_standby.h`: `wake` (the light, the wake overlay, the cards).

## Solved (to be seen on glass)

2026-11-24, the same day, in 1c38b1d2. Candidate 1 was it, and what leaves LVGL the whole screen at a wake is the sheet over a
screen in standby that takes the waking tap: it covers the glass, and hiding it invalidates all of it. `show` revealed
the overlay and then called `lv_refr_now` for the card, which drew that pending whole screen with the overlay's scrim
in it; the dim on the glass came on top. `screen_motion::show` now lets LVGL finish what it still has to draw before
it reveals the overlay, so the page under the dim is always the page as LVGL draws it without one. A lit screen has
nothing pending and pays nothing. `hide` needed no change: it ends by having LVGL draw the whole screen again.

The proof is glass, since the host has no dim on it: `alert_glass.py <node> <prefix> standby` on a board with the dim
on the glass, light look, and the pixel of the page behind the card reads as on a lit screen, (98, 105, 106) on the
Guition 10.1, where it read (49, 56, 57).
