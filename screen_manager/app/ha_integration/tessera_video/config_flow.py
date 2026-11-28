"""Choose the screen: one of the ESPHome devices. Its address, MAC and API key come from Home Assistant itself."""
from __future__ import annotations

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.selector import DeviceSelector, DeviceSelectorConfig

from .const import DOMAIN


class TesseraVideoFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            device = dr.async_get(self.hass).async_get(user_input["device"])
            if device is None:
                return self.async_abort(reason="unknown_device")
            await self.async_set_unique_id(device.id)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title=device.name_by_user or device.name or "Screen", data={"device": device.id})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("device"): DeviceSelector(DeviceSelectorConfig(integration="esphome"))}),
        )
