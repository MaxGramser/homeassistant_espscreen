"""Tessera video: the live video of a Tessera screen's own camera, on the screen's ESPHome device.

A screen with Screen camera's part Video serves its camera as an RTSP stream: H.264 from the ESP32-P4's encoder and the
microphone as Opus. This integration adds one camera, "Video", to the screen's device in Home Assistant, found by its
MAC address, so it sits beside the screen's ESPHome entities. Its stream is that RTSP address; Home Assistant's go2rtc
turns it into WebRTC for the browser and the app without transcoding. The password is worked out from the API key Home
Assistant's ESPHome integration keeps for the screen, so nobody types one.

ESP Screen Manager (Tessera) installs this folder when asked (Settings, Video in Home Assistant) and adds one entry for
each screen that has the video. It can also be added by hand: Add integration, Tessera video, choose the screen.
"""
from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

PLATFORMS = [Platform.CAMERA]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
