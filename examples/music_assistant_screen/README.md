# Music Assistant Screen for Tessera

An expanded white main player with album art, Library, Favorites, Queue, Speakers and More directly on the page. Playback, shuffle, repeat, seeking and volume stay on this main screen. Library and search open their own pages; Back returns to the same player, with no automatic reopening of a duplicate detail screen. Starting playback from stopped or idle lowers an excessive volume to 30% by default. Paused playback resumes unchanged, and volume controls remain unrestricted afterward.

**Requires the accompanying Tessera media API extension (0.19). This example is not compatible with released Tessera versions that lack those hooks.**

## Set up

1. Use the matching Tessera core with the media extension. Keep existing screen credentials and board settings.
2. Place this folder beside ESPHome under `tessera-plugins/music_assistant_screen` and include `plugin.yaml` plus its external component in the screen profile. For a manual local build, pass `MUSIC_PLAYER`, `MUSIC_ENTRY` and `MUSIC_FAVORITE_BUTTON` as the include's `vars`; top-level substitutions do not override the package's local defaults.
3. Set the plugin inputs to your Music Assistant media player, integration config entry ID, and favorite-current-song button. No Wi-Fi passwords or API keys belong in this plugin.
4. Keep a media-player tile for that speaker on the home page. Install the complete screen build once.
5. Adjust Music starting volume, Music artwork timeout and Music screen enabled in Home Assistant or the screen settings without rebuilding.

Favorites use Music Assistant favorites rather than separate shortcuts. Queue shows current and next because that is what the Home Assistant queue action exposes. Favorites currently show up to 48 items per category. Search uses an on-screen keyboard. Playback commands with uncertain results are not automatically retried.

## Compatibility and testing

This example accompanies the proposed core API extension. It has been built and physically tested on the Waveshare ESP32-S3-Touch-LCD-7 (800x480). Other boards are not declared supported. Firmware images and individual screen profiles are intentionally excluded. Installers must use their own player and integration inputs.

Brought to you by [PixoraHQ.com](https://pixorahq.com/).
