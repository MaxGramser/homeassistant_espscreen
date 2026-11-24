# Save in the phone editor's dock does nothing for some phones

## The symptom

In the phone editor, inside Home Assistant's app, a tap on Save in the dock at the foot (beside Layoutbot's key and Add
tile) does nothing (GitHub #438: a Google Pixel with the Android app, 0.4.98; confirmed by another user on an iPhone,
2026-11-21). The issue's video shows the phone editor, a page changed, and a tap on Save that has no effect.

## What we know

- The dock is `.phone-dock` (web/src/styles/app.css), fixed at the foot, its padding `--safe-bottom`
  (web/src/styles/tokens.css, `env(safe-area-inset-bottom)`). Layoutbot's key stands in it (`docked`), beside Save.
- Home Assistant's Android app (home-assistant/android, frontend/WebViewAction.kt `ApplySafeAreaInsets`, since
  2026-07-09) sets `--app-safe-area-inset-*` on the frontend's document; it draws the WebView edge to edge for a server
  at 2026.2 or later (FrontendViewModel.kt `serverHandlesInsets`). The frontend (home-assistant/frontend,
  src/resources/theme/main.globals.ts) reads those as `--safe-area-inset-*`, and its app panel
  (src/panels/app/ha-panel-app.ts, since #53127, 2026-07-15, so Home Assistant 2026.8+) pads an app's iframe by them,
  unless the app opts out with `home-assistant/subscribe-properties` and `handleSafeArea`. So on 2026.8+ the editor's
  iframe ends above the gesture bar, and env() reading 0 inside it is right.

## Ruled out

- Locally (Chrome at 412 x 915, the phone editor against a local Home Assistant, 2026-11-24): `elementsFromPoint` at
  Save's centre is the Save button itself, before Layoutbot's chat opened and after it closed; nothing covers it.
- "The dock is dimmed in the video": that was most likely the video player's own control gradient on paused frames,
  not the page. Not evidence.
- A floor of 24 px at the foot on every touch screen (d087c5fe) was taken out again the same day: it rested on the
  theory above and cost every phone 24 px.

## Candidates

- Home Assistant 2026.2 to 2026.7 with the current Android app: edge to edge, but the app panel does not pad the iframe
  yet, so the dock lies under the gesture bar there.
- Something over the dock on their phones only (Layoutbot's sheet, a veil, a toast) that the desktop preview does not
  show.
- Save disabled (a save on its way) without it showing.

## The deciding experiment

Ask the reporters: their Home Assistant version and Android or iOS app version; whether it also happens in the phone's
browser (not the app); a screenshot (not a video) with Save visible. A tester with the Android app on Home Assistant
2026.8 or later: open a screen in the phone editor, change a tile, tap Save, and say what happens.

## Pointers

web/src/components/ScreenView.vue (the dock), web/src/components/LayoutBot.vue and LayoutBotKey.vue, web/src/styles/app.css
(`.phone-dock`), web/src/styles/tokens.css (`--safe-bottom`).
