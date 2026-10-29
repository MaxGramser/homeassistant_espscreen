"""The screen's camera as video: its RTSP stream, on the screen's own device."""
from __future__ import annotations

import hashlib
import logging

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.components.ffmpeg import async_get_image
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import PASSWORD_LENGTH, PASSWORD_SALT, PORT, USER

LOG = logging.getLogger(__name__)


def password(key: str | None) -> str:
    """The stream's password for a screen's API key: the firmware works out the same one when it is built (Screen
    camera, components/screen_video/__init__.py)."""
    return hashlib.sha256((PASSWORD_SALT + (key or "")).encode()).hexdigest()[:PASSWORD_LENGTH]


def _screen(hass: HomeAssistant, device_id: str):
    """The device, its MAC and the ESPHome entry behind it (its host and API key)."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None, None, None
    mac = next((value for kind, value in device.connections if kind == dr.CONNECTION_NETWORK_MAC), None)
    esphome = next((e for e in hass.config_entries.async_entries("esphome") if e.entry_id in device.config_entries), None)
    return device, mac, esphome


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddEntitiesCallback) -> None:
    device, mac, esphome = _screen(hass, entry.data["device"])
    if device is None or mac is None or esphome is None:
        # The screen's ESPHome integration is not there (yet): Home Assistant tries again.
        raise ConfigEntryNotReady("The screen's ESPHome device is not in Home Assistant")
    # The camera belongs on the device the ESPHome integration keeps for the screen. A device this entry held before
    # without it (the screen was added to ESPHome again, and Home Assistant made it a new device) lets go of this entry,
    # and Home Assistant removes it once nothing holds it, so the camera finds the screen's device by its MAC.
    registry = dr.async_get(hass)
    for other in dr.async_entries_for_config_entry(registry, entry.entry_id):
        if esphome.entry_id not in other.config_entries:
            registry.async_update_device(other.id, remove_config_entry_id=entry.entry_id)
    add([ScreenVideo(mac, esphome)])


class ScreenVideo(Camera):
    _attr_has_entity_name = True
    _attr_translation_key = "video"
    _attr_supported_features = CameraEntityFeature.STREAM

    def __init__(self, mac: str, esphome: ConfigEntry) -> None:
        super().__init__()
        self._esphome = esphome
        self._attr_unique_id = f"{mac}-video"
        # Its MAC puts the camera on the screen's ESPHome device, beside its other entities.
        self._attr_device_info = DeviceInfo(connections={(dr.CONNECTION_NETWORK_MAC, mac)})

    def _url(self) -> str:
        # Read each time: Home Assistant keeps the host and key in the ESPHome entry and changes them there.
        host = self._esphome.data.get("host")
        return f"rtsp://{USER}:{password(self._esphome.data.get('noise_psk'))}@{host}:{PORT}/"

    async def stream_source(self) -> str | None:
        return self._url()

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        # A still from the stream go2rtc already has open, so the screen serves one connection for everything; ffmpeg,
        # which opens one of its own, only without go2rtc.
        provider = getattr(self, "_webrtc_provider", None)
        if provider is not None and hasattr(provider, "async_get_image"):
            try:
                return await provider.async_get_image(self, width=width, height=height)
            except Exception as error:  # noqa: BLE001 - go2rtc not ready yet: the stream answers below
                LOG.debug("No still from go2rtc: %s", error)
        return await async_get_image(self.hass, self._url(), width=width, height=height)
