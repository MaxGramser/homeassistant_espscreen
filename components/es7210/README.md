# Optional P4 ES7210 extension

Based on the ESPHome ES7210 component at
[`ff380e19d41d0671975a44dd433091b035d45888`](https://github.com/woozer/esphome/tree/ff380e19d41d0671975a44dd433091b035d45888/esphome/components/es7210),
which adds digital gain and automatic level control to the standard driver.
ESPHome's original combined MIT/Python and GPLv3/runtime license is preserved in
LICENSE. These files retain those terms.

The additional changes enable optional TDM and a separately configured playback
reference ADC. That channel keeps fixed analogue gain, unity digital gain and
no ALC while microphone gain and ALC remain adjustable. Default stereo behaviour
is retained when TDM/reference configuration is absent.

The Waveshare P4 audio package selects ADC3 as the reference, at 24 dB, and the
audio stack reads it in TDM slot 1. Physical ADC numbers and slot numbers differ.
`tests/test_es7210_registers.py` runs the actual driver against a fake I2C register
bank to check legacy behaviour, all four reference mappings, independent gain,
ALC exclusion and failed-write rollback. No AI provider is involved.
