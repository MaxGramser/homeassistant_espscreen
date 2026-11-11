"""Strict confirmation of a new firmware image, for a panel that is out of reach (README.md).

ESPHome's safe_mode confirms an image that was OTA'd after a minute of uptime, with or without a network.
`boot_guard:` confirms it only when the firmware has run `confirm_after`, Wi-Fi is up and (by default) a native API
client has connected since boot; if that has not happened by `deadline`, it asks the bootloader to go back to the
firmware from before. `hometiles_ota_descriptor` also writes the metadata HomeTiles' web OTA validates into the image.
"""
import esphome.codegen as cg
import esphome.config_validation as cv
import esphome.final_validate as fv
from esphome.components import text_sensor
from esphome.const import CONF_ID, CONF_SAFE_MODE, ENTITY_CATEGORY_DIAGNOSTIC
from esphome.core import CORE

CODEOWNERS = []
DEPENDENCIES = ["esp32", "wifi"]

CONF_CONFIRM_AFTER = "confirm_after"
CONF_DEADLINE = "deadline"
CONF_REQUIRE_API_CLIENT = "require_api_client"
CONF_HOMETILES_OTA_DESCRIPTOR = "hometiles_ota_descriptor"
CONF_STATE = "state"

boot_guard_ns = cg.esphome_ns.namespace("boot_guard")
BootGuard = boot_guard_ns.class_("BootGuard", cg.Component)


def _validate(config):
    if config[CONF_DEADLINE] <= config[CONF_CONFIRM_AFTER]:
        raise cv.Invalid(
            f"{CONF_DEADLINE} must be longer than {CONF_CONFIRM_AFTER}", path=[CONF_DEADLINE]
        )
    return config


def _final_validate(config):
    from esphome.const import CONF_FRAMEWORK

    full = fv.full_config.get()
    if config[CONF_REQUIRE_API_CLIENT] and "api" not in full:
        raise cv.Invalid(f"{CONF_REQUIRE_API_CLIENT} needs the api: component")
    advanced = full["esp32"][CONF_FRAMEWORK]["advanced"]
    if not advanced.get("enable_ota_rollback", False):
        # esp32's own final validation switches rollback off without safe_mode; the guard would never act.
        raise cv.Invalid(
            "boot_guard needs OTA rollback: esp32 framework advanced enable_ota_rollback with safe_mode and ota"
        )
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(BootGuard),
            cv.Optional(CONF_CONFIRM_AFTER, default="180s"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_DEADLINE, default="15min"): cv.positive_time_period_milliseconds,
            cv.Optional(CONF_REQUIRE_API_CLIENT, default=True): cv.boolean,
            cv.Optional(CONF_HOMETILES_OTA_DESCRIPTOR, default=False): cv.boolean,
            cv.Optional(CONF_STATE): text_sensor.text_sensor_schema(
                entity_category=ENTITY_CATEGORY_DIAGNOSTIC
            ),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    cv.only_on_esp32,
    _validate,
)

FINAL_VALIDATE_SCHEMA = _final_validate


async def to_code(config):
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_confirm_after(config[CONF_CONFIRM_AFTER]))
    cg.add(var.set_deadline(config[CONF_DEADLINE]))
    cg.add(var.set_require_api_client(config[CONF_REQUIRE_API_CLIENT]))
    if CONF_STATE in config:
        sens = await text_sensor.new_text_sensor(config[CONF_STATE])
        cg.add(var.set_state_sensor(sens))
    # safe_mode, when there is one: the guard confirms through it so its boot loop counter is cleared as well.
    safe_mode = CORE.config.get(CONF_SAFE_MODE)
    if safe_mode and CONF_ID in safe_mode:
        sm = await cg.get_variable(safe_mode[CONF_ID])
        cg.add(var.set_safe_mode(sm))
        cg.add_define("USE_SAFE_MODE_PRESENT_FOR_BOOT_GUARD")
    if config[CONF_HOMETILES_OTA_DESCRIPTOR]:
        cg.add_define("USE_BOOT_GUARD_HOMETILES_DESCRIPTOR")
