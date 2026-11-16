#!/usr/bin/env python3
"""Schreibt wetter-display.yaml aus dem Entwurf (die vielen gleichartigen Teile: Spalten, Zeilen, Bilder).

Aufruf aus eigenes-dashboard/:  python3 werkzeuge/yaml_bauen.py

Maße wie im abgestimmten Entwurf: 8 px Rand, 8 px Abstand, 16 px Innenabstand, kleinste Schrift 12 px.
Poppins hat eine Zeilenhöhe vom 1,4-Fachen der Schriftgröße; y() rechnet die Lage einer Textzeile aus dem Entwurf
(oberer Rand und Zeilenhöhe dort) in die Lage des LVGL-Labels um.
"""
import os

HIER = os.path.dirname(os.path.abspath(__file__))
ZIEL = os.path.join(os.path.dirname(HIER), "wetter-display.yaml")
HW = os.path.join(HIER, "hardware.yaml")

LATIN = (" !\"#$%&'()*+,-./0123456789:;<=>?@ABCDEFGHIJKLMNOPQRSTUVWXYZ[\\]^_`abcdefghijklmnopqrstuvwxyz{|}~"
         "°ÄÖÜäöüß–·…")
ZIFFERN = "-0123456789,.°% "

# ---- Raster
M, G, P = 8, 8, 16
W = 480 - 2 * M                     # 464
COL = (W - 3 * G) // 4              # 110
CARD2 = 2 * COL + G                 # 228
PANEL_H = 212
TILE_Y, TILE_H = M + PANEL_H + G, 62
CARD_Y = TILE_Y + TILE_H + G        # 298
CARD_H = 480 - M - CARD_Y           # 174
ROW = PANEL_H - 38                  # Zeile unten im Panel: Sonne links, Hoch/Tief rechts
RW = 164                            # rechte Spalte im Panel
RX = W - P - RW
BILD = 148
BILD_X, BILD_Y = W - P - round(130 / 140 * BILD), 5
BADGE = 86
BADGE_OFF = round(58 / 140 * BILD)  # 61

# ---- Farben
BG, CARD, INK, MUTED, BLUE = "0xF3F5F9", "0xFFFFFF", "0x14213D", "0x5F6B80", "0x2F6FED"
PANEL_TAG, PANEL_NACHT = ("0x2C5194", "0x0F2148"), ("0x1B2D57", "0x070F26")
PMUTED, SONNE = "0xB4C3DF", "0xFFD27A"
LINIE, TRACK, FILL = "0x1E3A6E", "0x2F6FED", "0x5B8FF5"

COND = ["F0599", "F0594", "F0595", "F0590", "F0591", "F0592", "F0593", "F067E", "F0596", "F0597", "F0598",
        "F067F", "F059D", "F059E", "F0F2F"]
UI = ["F059D", "F054A", "F058E", "F05A8", "F059C", "F059B"]
WARN = ["F0026", "F1A71", "F0D64", "F0591", "F0593", "F059D", "F0596", "F0F36", "F18D6"]
TAG_BILDER = ["sunny", "partlycloudy", "cloudy", "fog", "rainy", "pouring", "lightning", "lightning-rainy", "snowy",
              "snowy-rainy", "hail", "windy", "windy-variant", "exceptional"]
NACHT_BILDER = ["wolke"] + [k for k in TAG_BILDER if k not in ("sunny", "partlycloudy", "cloudy")]


def y(top, line, size):
    """Oberkante des LVGL-Labels für eine Textzeile, die im Entwurf bei top mit Zeilenhöhe line steht."""
    return round(top + (line - 1.4 * size) / 2)


def q(chars):
    return '"' + ''.join('\\' + c if c in '\\"' else c for c in chars) + '"'


def mdi(codes):
    return "[" + ", ".join(f'"\\U000{c}"' for c in codes) + "]"


def ident(k):
    return k.replace("-", "_")


out = []
w = out.append


# ---------------------------------------------------------------- Widgets als Text

def widget(kind, ind, props, children=None):
    p = " " * ind
    lines = [f"{p}- {kind}:"]
    for k, v in props.items():
        if isinstance(v, str) and "\n" in v:
            lines.append(f"{p}    {k}: {v.replace(chr(10), chr(10) + p + '      ')}")
        else:
            lines.append(f"{p}    {k}: {v}")
    if children:
        lines.append(f"{p}    widgets:")
        lines += children
    return "\n".join(lines)


def label(ind, ident_, x, y_, text, font, color, width=None, align=None, **extra):
    props = {}
    if ident_:
        props["id"] = ident_
    if x is not None:
        props["x"] = x
    if y_ is not None:
        props["y"] = y_
    if width is not None:
        props["width"] = width
    props.update(text=f'"{text}"', text_font=font, text_color=color)
    if align:
        props["text_align"] = align
    props.update(extra)
    return widget("label", ind, props)


def box(ind, ident_, x, y_, wd, ht, style, children=None, **extra):
    props = {}
    if ident_:
        props["id"] = ident_
    props.update(x=x, y=y_, width=wd, height=ht)
    props.update(style)
    props.update(dict(pad_all=0, scrollable="false", clickable="false"))
    props.update(extra)
    return widget("obj", ind, props, children)


def row(ind, ident_, x, y_, children, gap, cross="CENTER", **extra):
    """Eine Zeile, deren Teile nebeneinander stehen (Flex), ohne eigenen Hintergrund."""
    props = {}
    if ident_:
        props["id"] = ident_
    props.update(x=x, y=y_, width="SIZE_CONTENT", height="SIZE_CONTENT", bg_opa="TRANSP", border_width=0,
                 pad_all=0, scrollable="false", clickable="false",
                 layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: START\n"
                        f"  flex_align_cross: {cross}\n  flex_align_track: {cross}\n  pad_column: {gap}")
    props.update(extra)
    return widget("obj", ind, props, children)


# ---------------------------------------------------------------- Kopf, Hardware, Schriften, Bilder

w(f"""# Wetter-Dashboard für das Guition ESP32-S3-4848S040 (480 x 480, ST7701S + GT911).
# Eigenständige ESPHome-Konfiguration mit LVGL, ohne Tessera. README.md erklärt die Einrichtung.
# Diese Datei schreibt werkzeuge/yaml_bauen.py; Änderungen am Aufbau dort machen, Einstellungen hier oben.
#
# Oben ein blaues Panel: Ort, Datum, Kalenderwoche, Temperatur, Sonnenauf- und -untergang, großes Wetterbild
# (nachts die Mondphase mit dem Wetter klein daneben), Wettertext, Hoch und Tief. Bei einer DWD-Warnung ein Rahmen
# und ein Hinweis in der Farbe der Warnstufe. Darunter vier Kacheln (Wind, Regen heute, Luftfeuchte, UV-Index),
# die Temperaturkurve der 5 Tage und der Regen der nächsten Stunden.

substitutions:
  name: wetter-display
  friendly_name: Wetter-Display
  ort: Sassenberg
  # die Wetter-Entität (DWD oder Met.no) und der Sensor aus home-assistant/wetter_display.yaml
  wetter_entity: weather.dwd_wetter
  vorhersage_entity: sensor.display_wetter

esphome:
  name: ${{name}}
  friendly_name: ${{friendly_name}}
  min_version: 2026.6.2
  includes:
    - wetter.h
  on_boot:
    priority: -100
    then:
      - light.turn_on:
          id: hintergrundlicht
          brightness: 80%

esp32:
  board: esp32-s3-devkitc-1
  variant: esp32s3
  flash_size: 16MB
  cpu_frequency: 240MHz
  framework:
    type: esp-idf
    advanced:
      execute_from_psram: true
    sdkconfig_options:
      CONFIG_LCD_RGB_ISR_IRAM_SAFE: "y"
      CONFIG_ESP32S3_DATA_CACHE_LINE_64B: "y"

psram:
  mode: octal
  speed: 80MHz

logger:
  hardware_uart: UART0

api:
  encryption:
    key: !secret wetter_display_api_key

ota:
  - platform: esphome
    password: !secret wetter_display_ota_password

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password
  ap:
    ssid: "Wetter-Display Setup"

captive_portal:

time:
  - platform: homeassistant
    id: ha_time
    on_time_sync:
      then:
        - script.execute: uhr_zeichnen
        - script.execute: jetzt_zeichnen
    on_time:
      - seconds: 0
        then:
          - script.execute: uhr_zeichnen
      - seconds: 0
        minutes: 0
        then:
          - script.execute: jetzt_zeichnen   # die Mondphase wechselt langsam: einmal pro Stunde reicht
""")

# ---- Skripte
SONNE_A = "id(wetter_sonne).state"
w(f"""script:
  # jede Minute: Datum, Kalenderwoche, "vor/in ... Std" bei der Sonne
  - id: uhr_zeichnen
    then:
      - lvgl.label.update:
          id: lbl_datum
          text: !lambda 'return wx::datum(id(ha_time).now());'
      - lvgl.label.update:
          id: lbl_kw
          text: !lambda 'return wx::kw(id(ha_time).now());'
      - lvgl.label.update:
          id: lbl_auf_wann
          text: !lambda 'return wx::wann(wx::part({SONNE_A}, 0), wx::part({SONNE_A}, 1), id(ha_time).now());'
      - lvgl.label.update:
          id: lbl_unter_wann
          text: !lambda 'return wx::wann(wx::part({SONNE_A}, 1), wx::part({SONNE_A}, 0), id(ha_time).now());'
  # das große Bild: am Tag das Wetter, nachts die Mondphase und das Wetter klein daneben; dazu die Panelfarbe
  - id: jetzt_zeichnen
    then:
      - lvgl.image.update:
          id: bild_jetzt
          src: !lambda |-""")
tag_chain = "\n".join(f'              if (c == "{k}") return id(img_tag_{ident(k)});' for k in TAG_BILDER)
mond_chain = "\n".join(f"              if (m == {i}) return id(img_mond_{i});" for i in range(7))
w(f"""              auto c = id(wetter_zustand).state;
              if (id(sonne_zustand).state == "below_horizon" || c == "clear-night") {{
                int m = id(ha_time).now().is_valid() ? wx::mondphase(id(ha_time).now().timestamp) : 4;
{mond_chain}
                return id(img_mond_7);
              }}
{tag_chain}
              return id(img_tag_cloudy);
      - lvgl.image.update:
          id: bild_klein
          src: !lambda |-
              auto a = wx::nacht_art(id(wetter_zustand).state);""")
w("\n".join(f'              if (a == "{k}") return id(img_nacht_{ident(k)});' for k in NACHT_BILDER))
w(f"""              return id(img_nacht_wolke);
      - if:
          condition:
            lambda: |-
              return id(sonne_zustand).state == "below_horizon" && !wx::nacht_art(id(wetter_zustand).state).empty();
          then:
            - lvgl.widget.show: bild_klein
          else:
            - lvgl.widget.hide: bild_klein
      - lvgl.obj.update:
          id: panel
          bg_color: !lambda 'return lv_color_hex(id(sonne_zustand).state == "below_horizon" ? {PANEL_NACHT[0]} : {PANEL_TAG[0]});'
          bg_grad_color: !lambda 'return lv_color_hex(id(sonne_zustand).state == "below_horizon" ? {PANEL_NACHT[1]} : {PANEL_TAG[1]});'
  # die Temperaturkurve, ihre Punkte und Werte; läuft, wenn ein Tag neue Daten hat
  - id: kurve_zeichnen
    mode: restart
    then:
      - delay: 300ms  # die fünf Tage kommen kurz nacheinander: einmal zeichnen
      - lvgl.line.update:
          id: kurve
          points:""")
for i in range(4 * 8 + 1):
    w(f"            - x: !lambda 'return wx::kurve_x({i});'\n              y: !lambda 'return wx::kurve_y({i});'")
for d in range(5):
    w(f"""      - lvgl.widget.update:
          id: punkt_{d}
          y: !lambda 'return wx::punkt_y({d}) - 5;'
      - lvgl.widget.update:
          id: lbl_hoch_{d}
          y: !lambda 'return wx::punkt_y({d}) - 28;'""")
w("")

w(open(HW).read())

w(f"""# ---------------- Schriften: Poppins (wie im Entwurf), Icons von Material Design ----------------
font:
  - {{file: fonts/Poppins-300.ttf, id: f_temp, size: 76, bpp: 4, glyphs: "-0123456789"}}
  - {{file: fonts/Poppins-300.ttf, id: f_grad, size: 36, bpp: 4, glyphs: "°C"}}
  - {{file: fonts/Poppins-600.ttf, id: f_ort, size: 24, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-600.ttf, id: f_pill, size: 14, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_wert, size: 22, bpp: 4, glyphs: {q(ZIFFERN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_17m, size: 17, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_16m, size: 16, bpp: 4, glyphs: {q(ZIFFERN)}}}
  - {{file: fonts/Poppins-400.ttf, id: f_16, size: 16, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_14m, size: 14, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-400.ttf, id: f_14, size: 14, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_13m, size: 13, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-400.ttf, id: f_13, size: 13, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-400.ttf, id: f_12, size: 12, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_tag, size: 22, bpp: 4, glyphs: {mdi(COND)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_ui, size: 18, bpp: 4, glyphs: {mdi(UI)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_warn, size: 16, bpp: 4, glyphs: {mdi(WARN)}}}

# ---------------- Wetterbilder (werkzeuge/bilder.py zeichnet sie) ----------------
image:""")
for k in TAG_BILDER:
    w(f"  - {{file: bilder/tag_{ident(k)}.png, id: img_tag_{ident(k)}, type: RGB565, transparency: alpha_channel}}")
for i in range(8):
    w(f"  - {{file: bilder/mond_{i}.png, id: img_mond_{i}, type: RGB565, transparency: alpha_channel}}")
for k in NACHT_BILDER:
    w(f"  - {{file: bilder/nacht_{ident(k)}.png, id: img_nacht_{ident(k)}, type: RGB565, transparency: alpha_channel}}")
w("")

# ---------------------------------------------------------------- Daten aus Home Assistant

w(f"""# ---------------- Daten aus Home Assistant ----------------
text_sensor:
  - platform: homeassistant
    id: wetter_zustand
    entity_id: ${{wetter_entity}}
    on_value:
      then:
        - script.execute: jetzt_zeichnen
        - lvgl.label.update:
            id: lbl_zustand
            text: !lambda 'return wx::text(x);'
  - platform: homeassistant
    id: sonne_zustand
    entity_id: sun.sun
    on_value:
      then:
        - script.execute: jetzt_zeichnen
  - platform: homeassistant
    id: wetter_sonne
    entity_id: ${{vorhersage_entity}}
    attribute: sonne
    on_value:
      then:
        - script.execute: uhr_zeichnen
        - lvgl.label.update:
            id: lbl_auf
            text: !lambda 'return wx::uhr_epoch(wx::part(x, 0));'
        - lvgl.label.update:
            id: lbl_unter
            text: !lambda 'return wx::uhr_epoch(wx::part(x, 1));'
  - platform: homeassistant
    id: wetter_warnung
    entity_id: ${{vorhersage_entity}}
    attribute: warnung
    on_value:
      then:
        - if:
            condition:
              lambda: 'return wx::num(wx::part(x, 0)) >= 1;'
            then:
              - lvgl.obj.update:
                  id: rahmen
                  border_color: !lambda 'return wx::warn_color((int) wx::num(wx::part(x, 0)));'
              - lvgl.obj.update:
                  id: warn_pill
                  bg_color: !lambda 'return wx::warn_color((int) wx::num(wx::part(x, 0)));'
              - lvgl.label.update:
                  id: lbl_warn_icon
                  text: !lambda 'return wx::warn_icon(wx::part(x, 2));'
                  text_color: !lambda 'return wx::warn_text_color((int) wx::num(wx::part(x, 0)));'
              - lvgl.label.update:
                  id: lbl_warn
                  text: !lambda 'return wx::part(x, 1);'
                  text_color: !lambda 'return wx::warn_text_color((int) wx::num(wx::part(x, 0)));'
              - lvgl.widget.show: [rahmen, warn_pill]
            else:
              - lvgl.widget.hide: [rahmen, warn_pill]""")
for d in range(5):
    w(f"""  - platform: homeassistant
    id: tag_{d}
    entity_id: ${{vorhersage_entity}}
    attribute: tag_{d}
    on_value:
      then:
        - lambda: 'wx::hoch[{d}] = wx::num(wx::part(x, 2));'
        - script.execute: kurve_zeichnen
        - lvgl.label.update:
            id: lbl_hoch_{d}
            text: !lambda 'return wx::deg(wx::part(x, 2));'
        - lvgl.label.update:
            id: lbl_regen_{d}
            text: !lambda 'return wx::rain(wx::part(x, 4), wx::part(x, 5));'
        - lvgl.label.update:
            id: lbl_icon_{d}
            text: !lambda 'return wx::icon(wx::part(x, 1));'
            text_color: !lambda 'return wx::icon_color(wx::part(x, 1));'
        - lvgl.label.update:
            id: lbl_name_{d}
            text: !lambda 'return wx::part(x, 0);'""")
    if d == 0:
        w("""        - lvgl.label.update:
            id: lbl_hochtief
            text: !lambda 'return "Hoch " + wx::deg(wx::part(x, 2)) + " · Tief " + wx::deg(wx::part(x, 3));'
        - lvgl.label.update:
            id: lbl_regen
            text: !lambda 'return wx::rain_value(wx::part(x, 4), wx::part(x, 5));'
        - lvgl.label.update:
            id: lbl_regen_einheit
            text: !lambda 'return wx::rain_unit(wx::part(x, 4), wx::part(x, 5));'""")
for h in range(5):
    w(f"""  - platform: homeassistant
    id: stunde_{h}
    entity_id: ${{vorhersage_entity}}
    attribute: stunde_{h}
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_std_{h}
            text: !lambda 'auto t = wx::part(x, 0); return t.empty() ? t : t + " Uhr";'
        - lvgl.bar.update:
            id: bar_std_{h}
            value: !lambda 'return wx::rain_bar(wx::part(x, 1), wx::part(x, 2));'
        - lvgl.label.update:
            id: lbl_std_wert_{h}
            text: !lambda 'return wx::part(x, 0).empty() ? std::string("") : wx::rain(wx::part(x, 1), wx::part(x, 2));'""")

w("""
sensor:
  - platform: homeassistant
    id: wetter_temp
    entity_id: ${wetter_entity}
    attribute: temperature
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_temp
            text: !lambda 'return wx::zahl(x);'
  - platform: homeassistant
    id: wetter_feuchte
    entity_id: ${wetter_entity}
    attribute: humidity
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_feuchte
            text: !lambda 'return wx::percent(x);'
  - platform: homeassistant
    id: wetter_wind
    entity_id: ${wetter_entity}
    attribute: wind_speed
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_wind
            text: !lambda 'return wx::percent(x);'
  - platform: homeassistant
    id: wetter_windrichtung
    entity_id: ${wetter_entity}
    attribute: wind_bearing
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_wind_titel
            text: !lambda 'auto r = wx::richtung(x); return r.empty() ? std::string("Wind") : "Wind " + r;'
  - platform: homeassistant
    id: wetter_uv
    entity_id: ${wetter_entity}
    attribute: uv_index
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_uv
            text: !lambda 'return wx::percent(x);'
        - lvgl.label.update:
            id: lbl_uv_text
            text: !lambda 'return wx::uv_text(x);'
            text_color: !lambda 'return wx::uv_color(x);'
""")

# ---------------------------------------------------------------- Oberfläche

TILE = dict(bg_color=CARD, bg_opa="COVER", border_width=0, radius=14, shadow_width=18, shadow_color=LINIE,
            shadow_opa="10%", shadow_offset_y=4)
CARDSTYLE = dict(TILE, radius=16)

w(f"""# ---------------- Oberfläche ----------------
lvgl:
  displays: [my_display]
  touchscreens: [ts_touch]
  buffer_size: 25%
  default_font: f_14
  pages:
    - id: seite_wetter
      bg_color: {BG}
      bg_opa: COVER
      scrollable: false
      pad_all: 0
      widgets:""")
I, C = 8, 14   # Einrückung der Seitenteile und ihrer Kinder

# ---- Panel
kids = []
pill = widget("obj", C + 8, dict(
    id="warn_pill", hidden="true", height=24, width="SIZE_CONTENT", radius=12, bg_color="0xF08A24", bg_opa="COVER",
    border_width=0, pad_left=7, pad_right=10, pad_top=0, pad_bottom=0, scrollable="false",
    clickable="false",
    layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: START\n  flex_align_cross: CENTER\n"
           "  flex_align_track: CENTER\n  pad_column: 5"),
    [label(C + 12, "lbl_warn_icon", None, None, "\\U000F0026", "i_warn", "0xFFFFFF"),
     label(C + 12, "lbl_warn", None, None, "", "f_pill", "0xFFFFFF")])
kids.append(row(C, None, P, y(14, 30, 24), [label(C + 8, "lbl_ort", None, None, "${ort}", "f_ort", "0xFFFFFF"), pill],
                12))
kw_pill = widget("obj", C + 8, dict(
    height=20, width="SIZE_CONTENT", radius=10, bg_color="0xFFFFFF", bg_opa="16%", border_width=0, pad_left=8,
    pad_right=8, pad_top=0, pad_bottom=0, scrollable="false", clickable="false",
    layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: CENTER\n  flex_align_cross: CENTER\n"
           "  flex_align_track: CENTER"),
    [label(C + 12, "lbl_kw", None, None, "KW --", "f_14m", "0xFFFFFF")])
kids.append(row(C, None, P, y(46, 20, 16), [label(C + 8, "lbl_datum", None, None, "", "f_16", PMUTED), kw_pill], 8))
kids.append(row(C, None, P - 4, y(78, 80, 76), [
    label(C + 8, "lbl_temp", None, None, "--", "f_temp", "0xFFFFFF"),
    label(C + 8, None, None, None, "°C", "f_grad", "0xFFFFFF", pad_top=round(1.05 * 76 - 30 - 1.05 * 36),
          pad_left=2)], 0, cross="START"))
kids.append(row(C, None, P, y(ROW, 20, 17), [
    label(C + 8, None, None, None, "\\U000F059C", "i_ui", SONNE),
    label(C + 8, "lbl_auf", None, None, "--:--", "f_17m", "0xFFFFFF"),
    label(C + 8, "lbl_auf_wann", None, None, "", "f_12", PMUTED),
    widget("obj", C + 8, dict(width=6, height=1, bg_opa="TRANSP", border_width=0)),
    label(C + 8, None, None, None, "\\U000F059B", "i_ui", SONNE),
    label(C + 8, "lbl_unter", None, None, "--:--", "f_17m", "0xFFFFFF"),
    label(C + 8, "lbl_unter_wann", None, None, "", "f_12", PMUTED)], 6))
kids.append(widget("image", C, dict(id="bild_jetzt", x=BILD_X, y=BILD_Y, src="img_tag_cloudy")))
kids.append(widget("image", C, dict(id="bild_klein", x=BILD_X + BADGE_OFF, y=BILD_Y + BADGE_OFF, src="img_nacht_wolke",
                                    hidden="true")))
kids.append(label(C, "lbl_zustand", RX, y(ROW - 24, 20, 17), "", "f_17m", "0xFFFFFF", width=RW, align="RIGHT",
                  long_mode="DOT"))
kids.append(label(C, "lbl_hochtief", RX, y(ROW, 20, 14), "", "f_14", PMUTED, width=RW, align="RIGHT"))
# der Warnrahmen liegt über allem; Rahmen und Hinweis sind nur bei einer Warnung zu sehen
kids.append(box(C, "rahmen", 0, 0, W, PANEL_H, dict(bg_opa="TRANSP", border_width=4, border_color="0xF08A24",
                                                   radius=22), hidden="true"))
w(box(I, "panel", M, M, W, PANEL_H, dict(bg_color=PANEL_TAG[0], bg_grad_color=PANEL_TAG[1], bg_grad_dir="VER",
                                        bg_opa="COVER", border_width=0, radius=22, clip_corner="true"), kids))

# ---- Kacheln
tiles = [("wind", "\\U000F059D", "Wind", "km/h", "lbl_wind_titel"), ("regen", "\\U000F054A", "Regen heute", "%", None),
         ("feuchte", "\\U000F058E", "Luftfeuchte", "%", None), ("uv", "\\U000F05A8", "UV-Index", "", None)]
for k, (name, ic, titel, unit, tid) in enumerate(tiles):
    x = M + k * (COL + G)
    unit_label = (label(C + 8, "lbl_uv_text", None, None, "", "f_14m", "0x2EAF6A", pad_bottom=3) if name == "uv" else
                  label(C + 8, "lbl_regen_einheit" if name == "regen" else None, None, None, unit, "f_14", MUTED,
                        pad_bottom=3))
    kids = [label(C, tid, P, y(11, 16, 14), titel, "f_14", MUTED),
            row(C, None, P - 1, 28, [
                label(C + 8, None, None, None, ic, "i_ui", BLUE, pad_right=3, pad_bottom=4),
                label(C + 8, f"lbl_{name}", None, None, "--", "f_wert", INK),
                unit_label], 3, cross="END")]
    w(box(I, f"kachel_{name}", x, TILE_Y, COL, TILE_H, TILE, kids))


# ---- Karten unten
def kopf(titel, rechts):
    return [label(C, None, P, y(12, 20, 17), titel, "f_17m", INK),
            row(C, None, -P, y(14, 16, 13), rechts, 5, align="TOP_RIGHT")]


legende = [widget("obj", C + 8, dict(width=10, height=3, radius=2, bg_color=LINIE, bg_opa="COVER", border_width=0)),
           label(C + 8, None, None, None, "Temp", "f_13", MUTED),
           label(C + 8, None, None, None, "%", "f_13m", BLUE, pad_left=6),
           label(C + 8, None, None, None, "Regen", "f_13", MUTED)]
kids = kopf("5 Tage", legende)
kids.append(box(C, None, P, 106, CARD2 - 2 * P, 1, dict(bg_color=LINIE, bg_opa="14%", border_width=0, radius=0)))
pts = ", ".join(f"[{round(16 + 19.6 + i * 39.2 / 8)}, 80]" for i in range(33))
kids.append(widget("line", C, dict(id="kurve", points=f"[{pts}]", line_color=LINIE, line_width=3,
                                   line_rounded="true")))
for d in range(5):
    cx = round(16 + 39.2 * (d + .5))
    heute = d == 0
    kids.append(box(C, f"punkt_{d}", cx - 5, 75, 10, 10, dict(radius=5, bg_color=BLUE if heute else CARD,
                                                              bg_opa="COVER", border_width=3, border_color=BLUE)))
    kids.append(label(C, f"lbl_hoch_{d}", cx - 20, 50, "", "f_16m", BLUE if heute else INK, width=40, align="CENTER"))
    kids.append(label(C, f"lbl_regen_{d}", cx - 20, y(111, 18, 13), "", "f_13m", BLUE, width=40, align="CENTER"))
    kids.append(label(C, f"lbl_icon_{d}", cx - 20, 128, "", "i_tag", MUTED, width=40, align="CENTER"))
    kids.append(label(C, f"lbl_name_{d}", cx - 22, y(149, 18, 14), "", "f_14m" if heute else "f_14",
                      BLUE if heute else MUTED, width=44, align="CENTER"))
w(box(I, "karte_tage", M, CARD_Y, CARD2, CARD_H, CARDSTYLE, kids))

kids = kopf("Regen", [label(C + 8, None, None, None, "nächste Stunden", "f_13", MUTED)])
inner = CARD2 - 2 * P
bar_w = inner - 44 - 34 - 20
for h in range(5):
    r = 50 + h * 24
    kids.append(label(C, f"lbl_std_{h}", P, y(r, 16, 14), "", "f_14", MUTED, width=44))
    kids.append(widget("bar", C, dict(id=f"bar_std_{h}", x=P + 54, y=r + 2, width=bar_w, height=12, min_value=0,
                                      max_value=100, value=0, radius=6, bg_color=TRACK, bg_opa="12%",
                                      indicator="{radius: 6, bg_color: " + FILL + ", bg_opa: COVER}")))
    kids.append(label(C, f"lbl_std_wert_{h}", P + 54 + bar_w + 10, y(r, 16, 14), "", "f_14m", INK, width=34,
                      align="RIGHT"))
w(box(I, "karte_regen", M + CARD2 + G, CARD_Y, CARD2, CARD_H, CARDSTYLE, kids))

open(ZIEL, "w").write("\n".join(out) + "\n")
print("geschrieben:", ZIEL)
