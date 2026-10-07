import esphome.codegen as cg
from esphome.components import i2c
from esphome.components.audio_adc import AudioAdc
import esphome.config_validation as cv
from esphome.const import CONF_BITS_PER_SAMPLE, CONF_ID, CONF_MIC_GAIN, CONF_SAMPLE_RATE
from esphome.types import ConfigType

CODEOWNERS = ["@kahrendt"]
DEPENDENCIES = ["i2c"]

CONF_DIGITAL_GAIN = "digital_gain"
CONF_ENABLED = "enabled"
CONF_ALC = "alc"
CONF_MAX_GAIN = "max_gain"
CONF_MIN_LEVEL = "min_level"
CONF_MAX_LEVEL = "max_level"
CONF_RAMP_RATE = "ramp_rate"
CONF_TDM = "tdm"
CONF_REFERENCE = "reference"
CONF_CHANNEL = "channel"
CONF_GAIN = "gain"

ALC_LEVELS = [
    -30.1,
    -24.1,
    -20.6,
    -18.1,
    -16.1,
    -14.5,
    -13.2,
    -12,
    -11,
    -10.1,
    -9.3,
    -8.5,
    -7.8,
    -7.2,
    -6.6,
    -6,
]
validate_digital_gain = cv.All(
    cv.decibel, cv.one_of(*(step / 2 for step in range(-191, 65)))
)
validate_alc_level = cv.All(cv.decibel, cv.one_of(*ALC_LEVELS))


def validate_alc(config: ConfigType) -> ConfigType:
    if config[CONF_MIN_LEVEL] > config[CONF_MAX_LEVEL]:
        raise cv.Invalid("min_level must not exceed max_level")
    return config


ALC_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.Optional(CONF_ENABLED, default=False): cv.boolean,
            cv.Optional(CONF_MAX_GAIN, default="12dB"): validate_digital_gain,
            cv.Optional(CONF_MIN_LEVEL, default="-12dB"): validate_alc_level,
            cv.Optional(CONF_MAX_LEVEL, default="-6dB"): validate_alc_level,
            cv.Optional(CONF_RAMP_RATE, default=6): cv.int_range(min=0, max=15),
        }
    ),
    validate_alc,
)

es7210_ns = cg.esphome_ns.namespace("es7210")
ES7210 = es7210_ns.class_("ES7210", AudioAdc, cg.Component, i2c.I2CDevice)


es7210_bits_per_sample = es7210_ns.enum("ES7210BitsPerSample")
ES7210_BITS_PER_SAMPLE_ENUM = {
    16: es7210_bits_per_sample.ES7210_BITS_PER_SAMPLE_16,
    24: es7210_bits_per_sample.ES7210_BITS_PER_SAMPLE_24,
    32: es7210_bits_per_sample.ES7210_BITS_PER_SAMPLE_32,
}


ES7210_MIC_GAINS = [0, 3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 34.5, 36, 37.5]

_validate_bits = cv.float_with_unit("bits", "bit")

CONFIG_SCHEMA = (
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(ES7210),
            cv.Optional(CONF_BITS_PER_SAMPLE, default="16bit"): cv.All(
                _validate_bits, cv.enum(ES7210_BITS_PER_SAMPLE_ENUM)
            ),
            cv.Optional(CONF_MIC_GAIN, default="24db"): cv.All(
                cv.decibel, cv.one_of(*ES7210_MIC_GAINS)
            ),
            cv.Optional(CONF_SAMPLE_RATE, default=16000): cv.int_range(min=1),
            cv.Optional(CONF_DIGITAL_GAIN, default="0dB"): validate_digital_gain,
            cv.Optional(CONF_ALC, default={}): ALC_SCHEMA,
            cv.Optional(CONF_TDM, default=False): cv.boolean,
            cv.Optional(CONF_REFERENCE): cv.Schema(
                {
                    cv.Required(CONF_CHANNEL): cv.int_range(min=1, max=4),
                    cv.Optional(CONF_GAIN, default="0dB"): cv.All(
                        cv.decibel, cv.one_of(*ES7210_MIC_GAINS)
                    ),
                }
            ),
        }
    )
    .extend(cv.COMPONENT_SCHEMA)
    .extend(i2c.i2c_device_schema(0x40))
)


async def to_code(config: ConfigType) -> None:
    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    await i2c.register_i2c_device(var, config)

    cg.add(var.set_bits_per_sample(config[CONF_BITS_PER_SAMPLE]))
    cg.add(var.set_mic_gain(config[CONF_MIC_GAIN]))
    cg.add(var.set_sample_rate(config[CONF_SAMPLE_RATE]))
    cg.add(var.set_tdm(config[CONF_TDM]))
    if (reference := config.get(CONF_REFERENCE)) is not None:
        cg.add(var.set_reference(reference[CONF_CHANNEL], reference[CONF_GAIN]))
    cg.add(var.set_digital_gain(config[CONF_DIGITAL_GAIN]))
    alc = config[CONF_ALC]
    cg.add(var.set_alc_max_gain(alc[CONF_MAX_GAIN]))
    cg.add(
        var.set_alc_target(
            (ALC_LEVELS.index(alc[CONF_MAX_LEVEL]) << 4)
            | ALC_LEVELS.index(alc[CONF_MIN_LEVEL])
        )
    )
    cg.add(var.set_alc_ramp_rate(alc[CONF_RAMP_RATE]))
    cg.add(var.set_alc_enabled(alc[CONF_ENABLED]))
