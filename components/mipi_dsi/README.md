# MIPI-DSI external component

Vendored from the `espcontrol` repository's MIPI-DSI component. The component is
based on ESPHome's MIPI-DSI implementation:

- Source repository: https://github.com/jtenniswood/espcontrol
- Upstream implementation: https://github.com/esphome/esphome/tree/2026.9.0/esphome/components/mipi_dsi
- Original license: `LICENSE` in this directory

The sole source change is in `MipiDsi::setup()`: value-initialize `phy_clk_src`
instead of assigning the deprecated `MIPI_DSI_PHY_CLK_SRC_DEFAULT` alias.
ESP-IDF 5.5.5's `esp_lcd_new_dsi_bus()` explicitly maps zero to the correct
default for the selected silicon: XTAL for production P4, PLL_F20M for legacy
P4. The deprecated alias always selects PLL_F20M, which aborts in the V3 HAL.
All display models, timings, initialization and drawing code are unchanged.

This copy is adapted for the ESPHome version pinned by this project. The
adaptation is described in the source history; the original license remains
applicable to the copied implementation. See `THIRD_PARTY_NOTICES.md` at the
repository root for the distribution notice.
