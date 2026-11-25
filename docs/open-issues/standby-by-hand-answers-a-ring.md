# A standby by hand answers a ring for every screen

Someone sends one screen to standby by hand while a doorbell rings: **Sleep** in Home Assistant, the board's key, or
the home button held. That screen closes the ring and reports it as `closed`. The app counts `closed` as an answer, so
the ring also closes on every other screen, and Home Assistant gets `esp_screens_doorbell_answered` for it. Nobody
dealt with the door, yet no screen still rings and no `esp_screens_doorbell_missed` comes.

## What we know

Seen 2026-11-24 on a Guition 10.1 running dev 0b9a3955, over the screen's API without a finger. A ring from
`esp_screens_doorbell` woke the screen out of a standby by hand. Sleep pressed during the ring logged the ring
`closed`, the camera closed, the speaker was given back, and `esphome.screen_doorbell` arrived with `action: closed`.
A second ring right after woke the screen and showed its picture in 279 ms. Firmware before the standby moved to C++
did the same: Sleep ran `alert_dismiss` and `dim_display`, which closed every card, the ring's view included.

The road, step by step:
- `screen_standby::standby_by_hand` closes the cards before the standby shows (`glass.close_cards`).
- The ring's view closes, and `module_doorbell.cpp` `closing()` reports `closed` when the ring had not ended yet.
- `screen_manager/app/doorbell.py` has `ANSWERS = ('answered', 'closed')`. Its `ENDINGS` describe `closed` as "its
  close key, or something else that closed it, such as a new alert".
- `Manager.doorbell_report` in `server.py` treats an answer from the first screen as the ring's answer. It fires
  `esp_screens_doorbell_answered` and closes the ring's view and alerts on the other screens.

The standby time running out never ends a ring: a ring holds the screen lit (`tests/test_screen_standby.cpp`,
`a_standby_by_hand_closes_a_ring`).

## The question

Two readings of the same moment:
1. "I am done with this screen" closes everything on it, a ring included. Whoever pressed Sleep saw the ring and
   chose to end it. Then today's behaviour is right, as the close key's is.
2. "I put this screen to sleep" is not "someone dealt with the door". A person who darkens the bedroom screen, or a
   nightly automation that presses Sleep on every screen, would silence the hall and tell Home Assistant the ring was
   answered.

docs/DOORBELL.md describes today's behaviour (point 5 of "What happens").

## Candidates

- Keep it. Write in docs/DOORBELL.md that a standby by hand answers the ring everywhere.
- A standby by hand ends the ring on its own screen with an action of its own, for example `put_away`. The app does
  not count it as an answer, so the ring stays on the other screens, the automation still gets `missed` when nobody
  answers before the timeout, and that screen still shows the missed ring in its top bar. That touches
  `module_doorbell.cpp` (the reason closing() reports), `doorbell.py` (`ENDINGS`, `ANSWERS`), `doorbell_report`, the
  host test and DOORBELL.md, and the add-on must accept the new action from new firmware only.
- Sleep refuses while a ring is up, as the home button's hold already does (`hold_home` returns false under a ring).
  That changes a documented Home Assistant button, and an automation that presses Sleep would no longer close a ring.

## What decides it

Max's call on the meaning: does Sleep or the key on one screen mean "the door is dealt with"? If not, the second
candidate is the one that keeps every other path unchanged. Its proof: a ring on two screens, Sleep on one. The other
keeps ringing, `esp_screens_doorbell_answered` does not come, and `missed` comes at the timeout. The host test names
the new action.

## Pointers

`components/smart_display/screen_standby.h` (`standby_by_hand`), `components/smart_display/module_doorbell.cpp`
(`closing`, `say`), `screen_manager/app/doorbell.py` (`ENDINGS`, `ANSWERS`), `screen_manager/app/server.py`
(`doorbell_report`), `tests/test_screen_standby.cpp` (`a_standby_by_hand_closes_a_ring`), docs/DOORBELL.md.
