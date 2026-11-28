# GSL3680 touch for the JC8012P4A1 V3

The GSL3680 touch driver of kvj/esphome (`esphome/components/gsl3680` at `dca6f3eed895ee03b894a7d172855c919ee7eda1`,
an ESPHome fork, license alongside), for the Guition JC8012P4A1 V3 alone (`packages/hardware/guition-jc8012p4a1.yaml`,
`platform: gsl3680_v3`). It is a separate name so that no other board picks it up: the first JC8012P4A1 keeps ESPHome's
own `gsl3670`.

Why: on the V3, ESPHome 2026.9.0's `gsl3670` loads the touch firmware without an I2C error and then never reports a
touch, with or without a pull-up on the interrupt pin (GitHub #52). This driver is the one the community configurations
for the V3 run, and touch works there. It differs from ESPHome's in how it starts the chip: longer reset pulses, a check
that the chip answers before the firmware goes in and one that it runs after, no second reset once the firmware is
loaded, and Silead's own point tracking (`gsl_point_id.cpp`) on every read. The firmware table in
`gsl3680_firmware.h` is the same as the one ESPHome's `gsl3670` loads for this board.

It differs from kvj's copy in four places in `gsl3680.cpp`: a short wait around the first reset pulse,
`mark_failed(LOG_STR(...))` for the current ESPHome API, the watchdog fed while the firmware loads, and the touch
report read as its count (byte 0) and up to five points, where kvj read four bytes as the count and only two points.
The first finger is reported whenever there is one.

`gsl_point_id.cpp` is Silead's code from the Linux driver (GPL-2.0 or later, header in the file).

It goes away when ESPHome's own `gsl3670` works on the V3: then the hardware file goes back to `platform: gsl3670` with
`model: GUITION-JC8012P4A1`. Read on 2026-11-28: ESPHome 2026.11.1's `gsl3670` starts the chip as 2026.9.0's did (the
same order of steps, the same reset pulses of 1 ms low and 5 ms high through its new `pulse_reset` helper, no check
that the chip answers), so nothing says it works there now. What decides is a V3's glass: a build with
`platform: gsl3670` and a finger on it.
