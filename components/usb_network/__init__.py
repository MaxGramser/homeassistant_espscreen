"""Experimental CDC-NCM network interface on the ESP32-P4 high-speed USB port."""
import esphome.codegen as cg
import esphome.config_validation as cv
from esphome import const, final_validate as fv
from esphome.components import esp32, network
from esphome.core import CORE

CODEOWNERS = []
AUTO_LOAD = ["network"]
DEPENDENCIES = ["esp32"]
CONFLICTS_WITH = ["tinyusb", "usb_host", "ethernet", "modem", "openthread"]

usb_ns = cg.esphome_ns.namespace("usb_network")
USBNetwork = usb_ns.class_("USBNetwork", cg.Component)

CONFIG_SCHEMA = cv.All(
    cv.Schema({
        cv.GenerateID(): cv.declare_id(USBNetwork),
        cv.Optional(const.CONF_USE_ADDRESS, default=""): cv.string_strict,
        cv.Optional(const.CONF_MANUAL_IP): cv.Schema({
            cv.Required(const.CONF_STATIC_IP): cv.ipv4address,
            cv.Required(const.CONF_GATEWAY): cv.ipv4address,
            cv.Required(const.CONF_SUBNET): cv.ipv4address,
            cv.Optional(const.CONF_DNS1, default="0.0.0.0"): cv.ipv4address,
        }),
    }).extend(cv.COMPONENT_SCHEMA),
    esp32.only_on_variant(supported=[esp32.VARIANT_ESP32P4]),
    cv.require_esphome_version(2026, 9, 0),
)


def _validate(config):
    if CORE.target_framework != "esp-idf":
        raise cv.Invalid("USB networking requires the ESP-IDF framework")
    full = fv.full_config.get()
    if full.get("network", {}).get("priority"):
        raise cv.Invalid("USB networking currently uses USB first, then Wi-Fi; omit network.priority")
    if full.get("network", {}).get("enable_ipv6"):
        raise cv.Invalid("This initial USB network implementation supports IPv4 only")
    wifi = full.get("wifi", {})
    if wifi.get("reboot_timeout") and wifi["reboot_timeout"].total_milliseconds:
        raise cv.Invalid("Set wifi.reboot_timeout: 0s so USB-only operation does not reboot")
    if full.get("logger", {}).get("hardware_uart") == "USB_CDC":
        raise cv.Invalid("USB networking owns OTG; use UART0 for this board's logger")
    return config


FINAL_VALIDATE_SCHEMA = _validate


async def to_code(config):
    var = cg.new_Pvariable(config[const.CONF_ID])
    await cg.register_component(var, config)
    cg.add_define("USE_USB_NETWORK")
    cg.add_define("USE_NETWORK_DEFAULT_ROUTE")
    if address := config[const.CONF_USE_ADDRESS]:
        cg.add(var.set_use_address(address))
    if manual := config.get(const.CONF_MANUAL_IP):
        cg.add(var.set_manual_ip(*[
            network.ip_address_literal(str(manual[key]))
            for key in (const.CONF_STATIC_IP, const.CONF_GATEWAY, const.CONF_SUBNET, const.CONF_DNS1)
        ]))
    esp32.add_idf_component(name="espressif/esp_tinyusb", ref="2.2.1")
    for key, value in {
        "CONFIG_TINYUSB_NET_MODE_ECM_RNDIS": False,
        "CONFIG_TINYUSB_NET_MODE_NONE": False,
        "CONFIG_TINYUSB_NET_MODE_NCM": True,
        "CONFIG_TINYUSB_CDC_ENABLED": False,
        "CONFIG_TINYUSB_MSC_ENABLED": False,
        "CONFIG_ESP_NETIF_SET_DNS_PER_DEFAULT_NETIF": True,
        "CONFIG_MDNS_MAX_INTERFACES": 4,
    }.items():
        esp32.add_idf_sdkconfig_option(key, value)
