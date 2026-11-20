# BTT Panda Touch, 800 x 480

This is the **BTT (BigTreeTech) Panda Touch**: a 5-inch 800 x 480 IPS panel on 16-bit RGB, GT911 capacitive touch, and an
ESP32-S3 with 16 MB flash and 8 MB of octal PSRAM. The USB-C port is a CH340K serial bridge on UART0, the USB-A port is
the chip's own USB host.

The board file takes its pins and panel timings from BTT's own firmware
([bigtreetech/PandaTouch_IDF](https://github.com/bigtreetech/PandaTouch_IDF), `include/pandatouch_board.h`), and they
agree with the ESPHome configuration of the Panda Touch thread on the Home Assistant forum (wish #40). It was tried on
**one** Panda Touch, lying down, which is why it starts as **experimental**.

## Install

Update Tessera Screen Manager and choose **BTT · Panda Touch** in **New screen**. Follow
[Easy setup](EASY_SETUP.md) for the rest: the screen gets its own name, Wi-Fi references and unique API/OTA keys.

The first flash goes over the USB-C cable (**Firmware & USB**); later updates go over Wi-Fi. Keep a copy of BTT's
firmware first if you want to be able to go back to it.

The remote package is `packages/pandatouch.yaml`; the checkout entry is `checkout/pandatouch.yaml`. Both combine
`packages/core.yaml` with `packages/boards/pandatouch.yaml`, which declares the glass, the grid and the packages the
board includes. Its own hardware (panel, touch, backlight and buses) is `packages/hardware/pandatouch.yaml`, which
takes the chip, its PSRAM and the ESP-IDF settings from `packages/hardware/esp32s3-rgb.yaml`.

## Layout and capabilities

- Lying down: 800 x 480, three columns of three cells (each tile about 34 x 14 mm); the screen settings also offer
  four by four.
- Standing up: 480 x 800, one column of five cells (not tried).
- The standard look at 186.6 dpi (933 diagonal pixels over 5 inches), so a tile, a letter and a key have the same size
  in millimetres as on every other board.
- GT911 reports pixels: no touch calibration. The touch panel is read every 20 ms; its interrupt line (GPIO40) is not
  used. Pages change with the swipe from the glass edge, like on every capacitive board.
- The backlight is a PWM pin (GPIO21, 30 kHz), so brightness, standby and night mode work: brightness 5 to 100 %,
  and 0 in standby or at night switches the backlight off.
- Camera pictures are included as on the other boards with PSRAM; they have not been tried here. There is no snapshot
  feature (the Waveshare 5-inch, with the same 800 x 480 glass, leaves it out too).

## Backlight floor

The backlight driver of the screen tried here shines down to a PWM duty of 0.1 % once it is lit, but from dark it came
on at 0.5 % and not at the lower steps tried. A floor below 0.5 % could leave the screen dark when it wakes or boots
straight onto the lowest brightness, so `min_power` is 0.005: that is the 5 % step of the brightness slider. The
backlight at full brightness is the full duty.

## Picture

The pixel clock is 16 MHz with BTT's porches (820 clocks a line, 516 lines a frame). BTT's own firmware runs 23 MHz
with PSRAM at 120 MHz and states 14 MHz as the panel's minimum. If the picture slips sideways, flickers or shows flat
colours, a screen's Override YAML can set another `pclk_frequency` with `!extend my_display`; 23 MHz and the 14.8 MHz of
the forum configuration have not been tried on the board file.

The screen tried here once flickered through flat colours (black, white, red, green and blue) after it had been without
power for a while, through cold starts, restarts and wake. It was gone after the firmware was flashed again, and did
not come back over several days that included a power cut. The cause has not been found.
