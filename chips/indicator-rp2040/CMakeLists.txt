# Tessera's firmware for the RP2040 of a SenseCAP Indicator (docs/SECOND_CHIP.md): build.sh builds it, and CI puts the
# file New screen offers into the app (screen_manager/app/chips/).
cmake_minimum_required(VERSION 3.13)

set(PICO_BOARD pico CACHE STRING "The Indicator's RP2040 has the Pico's crystal and a flash chip its boot code reads")
include(pico_sdk_import.cmake)

# The version the chip reports in its hello; the app reads the same from version.txt.
file(STRINGS ${CMAKE_CURRENT_LIST_DIR}/version.txt CHIP_VERSION LIMIT_COUNT 1)
project(tessera_indicator_rp2040 VERSION ${CHIP_VERSION} LANGUAGES C CXX ASM)
set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

pico_sdk_init()

add_executable(tessera-indicator-rp2040 src/main.cpp src/sound_out.cpp)
target_include_directories(tessera-indicator-rp2040 PRIVATE src ${CMAKE_CURRENT_LIST_DIR}/../../components/chip_link)
target_compile_options(tessera-indicator-rp2040 PRIVATE -Wall -Wextra)
target_compile_definitions(tessera-indicator-rp2040 PRIVATE
  CHIP_VERSION_MAJOR=${PROJECT_VERSION_MAJOR}
  CHIP_VERSION_MINOR=${PROJECT_VERSION_MINOR}
  CHIP_VERSION_PATCH=${PROJECT_VERSION_PATCH}
  # The USB name the Indicator's second port has with Seeed's firmware, so a computer and Tessera know the port by it.
  USBD_VID=0x2886
  USBD_PID=0x0050
  USBD_MANUFACTURER="Seeed"
  "USBD_PRODUCT=\"INDICATOR RP2040\""
  # A computer that opened the port and reads nothing holds a reply for 2 ms, not for half a second.
  PICO_STDIO_USB_STDOUT_TIMEOUT_US=2000
  # A board that is no Pico gets its crystal the longer start other makers give theirs.
  PICO_XOSC_STARTUP_DELAY_MULTIPLIER=64
  PICO_FLASH_SIZE_BYTES=2097152
)
pico_set_program_name(tessera-indicator-rp2040 "tessera-indicator-rp2040")
pico_set_program_version(tessera-indicator-rp2040 "${CHIP_VERSION}")
pico_set_program_url(tessera-indicator-rp2040 "https://github.com/MaxGramser/homeassistant_espscreen")
target_link_libraries(tessera-indicator-rp2040 pico_stdlib pico_rand hardware_pwm hardware_dma hardware_uart hardware_irq hardware_watchdog)
pico_enable_stdio_usb(tessera-indicator-rp2040 1)
pico_enable_stdio_uart(tessera-indicator-rp2040 0)
pico_add_extra_outputs(tessera-indicator-rp2040)
