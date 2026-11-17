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
BLOCK_PAD = 8   # Rand des CO2-Blocks links und rechts der Zahl
# breiter darf der Warntext neben dem Ort nicht werden (bis zum Wetterbild); längerer Text läuft durch
WARN_MAX = 112
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
# Das große Wetterbild: ohne Warnung 160 px, mit Warnung darunter auf 136 px verkleinert (um die rechte obere Ecke)
BILD = 160
BILD_PX = round(130 / 140 * BILD)   # 149: rechte Kante der Zeichnung im Bild
BILD_X, BILD_Y = W - P - BILD_PX, 2
BILD_KLEIN = round(136 / BILD * 256)  # Skala mit Warnung (256 = volle Größe)
BADGE = round(86 / 148 * BILD)      # 93: das kleine Wetterbild nachts auf dem Mond
BADGE_OFF = round(58 / 140 * BILD)  # 66
# Warnung oder Vorwarnung: Pille rechtsbündig unter dem (verkleinerten) Bild, über Hoch und Tief
PILL_Y, PILL_H, PILL_MAX = 144, 24, 260
PILL_TEXT_MAX = PILL_MAX - 7 - 10 - 16 - 5

# ---- Farben
BG, CARD, INK, MUTED, GOLD = "0xF3F5F9", "0xFFFFFF", "0x14213D", "0x5F6B80", "0xB8862B"
# Panel in British Racing Green, Akzente in Gold
PANEL_TAG, PANEL_NACHT = ("0x14583A", "0x004225"), ("0x082A1B", "0x02120B")
PMUTED, SONNE = "0xB9CFC2", "0xFFD27A"
LINIE, TRACK, FILL = "0x6B5420", "0xB8862B", "0xD4A548"
SPUR = "0xE9EDF4"   # Hintergrund der Balken für Feinstaub und Gase

# Hell und dunkel: diese Farben wechseln mit Tag und Nacht (Stile, die das Skript thema_setzen umschaltet).
# Rolle: (Eigenschaften bei Tag, bei Nacht)
THEMA = {
    "s_seite": (dict(bg_color=BG), dict(bg_color="0x070D0A")),
    "s_karte": (dict(bg_color=CARD, shadow_opa="10%"), dict(bg_color="0x121C17", shadow_opa="0%")),
    "s_panel": (dict(bg_color=PANEL_TAG[0], bg_grad_color=PANEL_TAG[1]),
                dict(bg_color=PANEL_NACHT[0], bg_grad_color=PANEL_NACHT[1])),
    "s_ink": (dict(text_color=INK), dict(text_color="0xE4EAE6")),
    "s_muted": (dict(text_color=MUTED), dict(text_color="0x8A9C92")),
    "s_gold": (dict(text_color=GOLD), dict(text_color="0xC9A04A")),
    "s_linie": (dict(bg_color=LINIE), dict(bg_color="0xC9A04A")),
    "s_kurve": (dict(line_color=LINIE), dict(line_color="0xC9A04A")),
    "s_spur": (dict(bg_color=SPUR), dict(bg_color="0x22302A")),
}
ROLLE = {INK: "s_ink", MUTED: "s_muted", GOLD: "s_gold"}   # Textfarben, die mit dem Thema wechseln
COND = ["F0599", "F0594", "F0595", "F0590", "F0591", "F0592", "F0593", "F067E", "F0596", "F0597", "F0598",
        "F067F", "F059D", "F059E", "F0F2F"]
UI = ["F059D", "F054A", "F058E", "F05A8", "F059C", "F059B", "F005D", "F0045", "F0054"]   # zuletzt: CO2-Trend
KLEIN_ICONS = ["F0164", "F0717"]   # Wolke durchgestrichen (keine Verbindung), Eiskristall (Frost)
WARN = ["F11DC", "F0026", "F1A71", "F0D64", "F0591", "F0593", "F059D", "F0596", "F0F36", "F18D6"]
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
    props.update(text=f'"{text}"', text_font=font)
    if color in ROLLE:
        props["styles"] = ROLLE[color]
    else:
        props["text_color"] = color
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
# Oben ein grünes Panel: Ort, Datum, Kalenderwoche, Temperatur, Sonnenauf- und -untergang, großes Wetterbild
# (nachts die Mondphase mit dem Wetter klein daneben), Hoch und Tief. Bei einer DWD-Warnung oder Vorwarnung wird das
# Bild kleiner und darunter steht ein Hinweis in der Farbe der Stufe. Darunter vier Kacheln (Wind mit Böen, Regen
# heute, Luftfeuchte, UV-Index), die Temperaturkurve der 5 Tage und der Regen der nächsten Stunden. Nachts (bis
# 30 Minuten vor Sonnenaufgang) ist alles dunkel.

substitutions:
  name: wetter-display
  friendly_name: Wetter-Display
  ort: Sassenberg
  # die Wetter-Entität (DWD oder Met.no) und der Sensor aus home-assistant/wetter_display.yaml
  wetter_entity: weather.controlroom_sassenberg
  # UV-Index von der Integration OpenUV (die DWD-Integration liefert ihn nicht mehr)
  uv_entity: sensor.controlroom_openuv_aktueller_uv_index
  vorhersage_entity: sensor.display_wetter
  # Raumklima (zweite Seite): Platzhalter, bis die drei Sensoren gebaut sind
  co2_wohnzimmer: sensor.luft_wohnzimmer_co2
  temp_wohnzimmer: sensor.luft_wohnzimmer_temperatur
  feuchte_wohnzimmer: sensor.luft_wohnzimmer_luftfeuchte
  co2_schlafzimmer: sensor.luft_schlafzimmer_co2
  temp_schlafzimmer: sensor.luft_schlafzimmer_temperatur
  feuchte_schlafzimmer: sensor.luft_schlafzimmer_luftfeuchte
  co2_buero: sensor.luft_buero_co2
  temp_buero: sensor.luft_buero_temperatur
  feuchte_buero: sensor.luft_buero_luftfeuchte
  pm1_buero: sensor.luft_buero_pm1
  pm25_buero: sensor.luft_buero_pm2_5
  pm4_buero: sensor.luft_buero_pm4
  pm10_buero: sensor.luft_buero_pm10
  voc_buero: sensor.luft_buero_voc_index
  nox_buero: sensor.luft_buero_nox_index
  # Vorschläge für die Regler in Home Assistant (Gerät Wetter-Display, Konfiguration); dort einstellen:
  # Sekunden bis zum Wechsel zwischen Wetter und Raumklima
  seitenwechsel: "45"
  # Minuten, die das Display an bleibt, wenn man es im Nachtmodus mit einem Tippen weckt
  weckdauer: "10"

esphome:
  name: ${{name}}
  friendly_name: ${{friendly_name}}
  min_version: 2026.6.2
  includes:
    - wetter.h
  on_boot:
    priority: -100
    then:
      # im Nachtmodus (Schalter, den eine Automation in HA setzt) bleibt das Licht aus
      - if:
          condition:
            switch.is_off: nachtmodus
          then:
            - light.turn_on:
                id: hintergrundlicht
                brightness: !lambda return id(helligkeit);
      - script.execute: seite_weiter
      - script.execute: punkte_zeichnen
      - script.execute: warn_zeichnen

globals:
  # Helligkeit, die Wischen hoch/runter einstellt; bleibt über einen Neustart erhalten
  - {{id: helligkeit, type: float, initial_value: "0.8"}}
  # Seite festgehalten (langer Druck): kein automatischer Wechsel, das Schloss ist zu sehen
  - {{id: seite_gehalten, type: bool, initial_value: "false"}}
  # Gesten: Start- und letzter Punkt einer Berührung, ob der lange Druck schon ausgelöst hat
  - {{id: t_x0, type: int, initial_value: "0"}}
  - {{id: t_y0, type: int, initial_value: "0"}}
  - {{id: t_x1, type: int, initial_value: "0"}}
  - {{id: t_y1, type: int, initial_value: "0"}}
  - {{id: t_lang, type: bool, initial_value: "false"}}
  # Tag oder Nacht (helles oder dunkles Design); ob das Thema schon einmal gesetzt wurde
  - {{id: ist_tag, type: bool, initial_value: "true"}}
  - {{id: thema_gesetzt, type: bool, initial_value: "false"}}
  # Verbindung zu Home Assistant: seit wann sie fehlt (millis, 0 = verbunden), ob das angezeigt wird, ab wann (Uhrzeit)
  - {{id: offline_seit, type: uint32_t, initial_value: "0"}}
  - {{id: offline_an, type: bool, initial_value: "false"}}
  - {{id: offline_text, type: std::string, initial_value: '""'}}

number:
  # Einstellungen, die Home Assistant als Regler zeigt (Gerät Wetter-Display, Konfiguration)
  - platform: template
    id: nr_seitenwechsel
    name: Seitenwechsel
    icon: mdi:timer-outline
    entity_category: config
    unit_of_measurement: s
    min_value: 10
    max_value: 300
    step: 5
    initial_value: ${{seitenwechsel}}
    optimistic: true
    restore_value: true
    on_value:
      - script.execute: seite_weiter
  - platform: template
    id: nr_weckdauer
    name: Weckdauer im Nachtmodus
    icon: mdi:timer-sand
    entity_category: config
    unit_of_measurement: min
    min_value: 1
    max_value: 60
    step: 1
    initial_value: ${{weckdauer}}
    optimistic: true
    restore_value: true
  - platform: template
    id: nr_helligkeit
    name: Helligkeit
    icon: mdi:brightness-6
    entity_category: config
    unit_of_measurement: "%"
    min_value: 10
    max_value: 100
    step: 10
    initial_value: 80
    optimistic: true
    restore_value: true
    on_value:
      - lambda: id(helligkeit) = x / 100.0f;
      - if:
          condition:
            lambda: return id(hintergrundlicht).remote_values.is_on();
          then:
            - light.turn_on:
                id: hintergrundlicht
                brightness: !lambda return id(helligkeit);
                transition_length: 200ms

button:
  - platform: restart
    name: Neustart

switch:
  # Nachtmodus: an = Licht aus, ein Tippen weckt das Display für ${{weckdauer}}. Wann es Nacht ist, entscheidet eine
  # Automation in Home Assistant (Beispiel in home-assistant/wetter_display.yaml).
  - platform: template
    id: nachtmodus
    name: Nachtmodus
    icon: mdi:weather-night
    optimistic: true
    restore_mode: RESTORE_DEFAULT_OFF
    on_turn_on:
      - script.stop: nacht_wecken
      - light.turn_off: hintergrundlicht
    on_turn_off:
      - script.stop: nacht_wecken
      - light.turn_on:
          id: hintergrundlicht
          brightness: !lambda return id(helligkeit);

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
  # ohne Home Assistant nicht neu starten, sondern weiter anzeigen (mit dem Hinweis "keine Verbindung")
  reboot_timeout: 0s
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
        - script.execute: tag_pruefen
        - script.execute: jetzt_zeichnen
    on_time:
      - seconds: 0
        then:
          - script.execute: uhr_zeichnen
          - script.execute: tag_pruefen
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
              if (!id(ist_tag) || c == "clear-night") {{
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
              return !id(ist_tag) && !wx::nacht_art(id(wetter_zustand).state).empty();
          then:
            - lvgl.widget.show: bild_klein
          else:
            - lvgl.widget.hide: bild_klein
      # UV-Index: OpenUV wird nur tagsüber abgefragt; nachts ist er 0
      - lvgl.label.update:
          id: lbl_uv
          text: !lambda 'return !id(ist_tag) ? std::string("0") : wx::percent(id(wetter_uv).state);'
      - lvgl.label.update:
          id: lbl_uv_text
          text: !lambda 'return wx::uv_text(!id(ist_tag) ? 0.0f : id(wetter_uv).state);'
          text_color: !lambda 'return wx::uv_color(!id(ist_tag) ? 0.0f : id(wetter_uv).state);'
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

w("""  # nach der Zeit des Reglers "Seitenwechsel" zwischen Wetter und Raumklima wechseln; ein Tippen wechselt sofort und
  # startet die Zeit neu
  - id: seite_weiter
    mode: restart
    then:
      - delay: !lambda 'return (uint32_t) (id(nr_seitenwechsel).state * 1000);'
      - if:
          condition:
            lambda: return !id(seite_gehalten);
          then:
            - script.execute: seite_wechseln
            - script.execute: seite_weiter

  # die Seite Raumklima gibt es erst, wenn ein Raum einen CO2-Wert hat; bis dahin bleibt das Wetter stehen
  - id: seite_wechseln
    then:
      - if:
          condition:
            lambda: |-
              return wx::innen_da(id(co2_wohnzimmer).state, id(co2_schlafzimmer).state, id(co2_buero).state) ||
                     id(seite_innen)->is_showing();
          then:
            - lvgl.page.next:
                animation: MOVE_LEFT
                time: 400ms

  # Nachtmodus: nach der Weckdauer (Regler, Minuten) ohne Berührung geht das Licht wieder aus
  - id: nacht_wecken
    mode: restart
    then:
      - delay: !lambda 'return (uint32_t) (id(nr_weckdauer).state * 60000);'
      - if:
          condition:
            switch.is_on: nachtmodus
          then:
            - light.turn_off: hintergrundlicht

  # langer Druck: nach 0,8 s ohne Bewegung die Seite festhalten oder wieder freigeben (schon während man drückt)
  - id: lang_warten
    mode: restart
    then:
      - delay: 800ms
      - if:
          condition:
            lambda: |-
              return abs(id(t_x1) - id(t_x0)) < 20 && abs(id(t_y1) - id(t_y0)) < 20 &&
                     id(hintergrundlicht).remote_values.is_on();
          then:
            - lambda: id(t_lang) = true;
            - script.execute:
                id: geste
                art: 3

  # Schloss kurz zeigen (sanft ein- und ausblenden); jede Berührung einer gehaltenen Seite startet es neu
  - id: schloss_zeigen
    mode: restart
    then:
      - lvgl.widget.show: schloss
      - lambda: lv_obj_fade_in(id(schloss), 200, 0);
      - delay: 3s
      - lambda: lv_obj_fade_out(id(schloss), 600, 0);
      - delay: 600ms
      - lvgl.widget.hide: schloss

  # Gesten: 0 = Tippen (nächste Seite), 1 = Wischen hoch (heller), 2 = Wischen runter (dunkler), 3 = lang (Seite halten)
  - id: geste
    parameters:
      art: int
    then:
      - if:
          # dunkel im Nachtmodus: jede Berührung weckt nur
          condition:
            lambda: return id(nachtmodus).state && !id(hintergrundlicht).remote_values.is_on();
          then:
            - light.turn_on:
                id: hintergrundlicht
                brightness: !lambda return id(helligkeit);
            - script.execute: nacht_wecken
          else:
            - if:
                condition:
                  switch.is_on: nachtmodus
                then:
                  - script.execute: nacht_wecken   # die Weckzeit zählt ab der letzten Berührung
            - if:
                condition:
                  lambda: return art == 1 || art == 2;
                then:
                  # über den Regler "Helligkeit", damit Home Assistant den neuen Wert sieht
                  - number.set:
                      id: nr_helligkeit
                      value: !lambda |-
                        float h = id(nr_helligkeit).state + (art == 1 ? 20 : -20);
                        return h > 100 ? 100 : (h < 10 ? 10 : h);
            - if:
                condition:
                  lambda: return art == 3;
                then:
                  # langer Druck: festhalten oder freigeben
                  - lambda: id(seite_gehalten) = !id(seite_gehalten);
                  - if:
                      condition:
                        lambda: return id(seite_gehalten);
                      then:
                        - script.stop: seite_weiter
                        - script.execute: schloss_zeigen
                      else:
                        - script.stop: schloss_zeigen
                        - lvgl.widget.hide: schloss
                        - script.execute: seite_weiter
                else:
                  - if:
                      # gehaltene Seite: jede Berührung zeigt kurz das Schloss, ein Tippen wechselt nicht
                      condition:
                        lambda: return id(seite_gehalten);
                      then:
                        - script.execute: schloss_zeigen
                      else:
                        - if:
                            condition:
                              lambda: return art == 0;
                            then:
                              - script.execute: seite_wechseln
                              - script.execute: seite_weiter
""")


# ---- Skripte für Thema, Warnung, Wind, Seitenpunkte und Verbindung
def thema_zweig(nacht):
    zeilen = []
    for sid, werte in THEMA.items():
        zeilen.append(f"            - lvgl.style.update:\n                id: {sid}")
        for k, v in werte[nacht].items():
            zeilen.append(f"                {k}: {v}")
    return "\n".join(zeilen)


BLASS_W = (["temp_zeile", "bild_jetzt", "bild_klein", "warn_pill", "lbl_hochtief", "karte_tage", "karte_regen"]
           + [f"kachel_{k}" for k in ("wind", "regen", "feuchte", "uv")])
BLASS_I = ([f"{t}_{r}" for r in ("wohnzimmer", "schlafzimmer", "buero") for t in ("lbl_co2", "block", "marker", "lbl_trend", "kachel")]
           + ["karte_feinstaub", "karte_gase"])
w(f"""  # Tag oder Nacht neu bestimmen (jede Minute und wenn sich die Sonne ändert); bei einem Wechsel Thema und Bild
  - id: tag_pruefen
    then:
      - if:
          condition:
            lambda: |-
              bool t = wx::ist_tag(id(sonne_zustand).state, id(wetter_sonne).state, id(ha_time).now());
              bool neu = t != id(ist_tag) || !id(thema_gesetzt);
              id(ist_tag) = t;
              id(thema_gesetzt) = true;
              return neu;
          then:
            - script.execute: thema_setzen
            - script.execute: jetzt_zeichnen

  # helles Design am Tag, dunkles in der Nacht
  - id: thema_setzen
    then:
      - if:
          condition:
            lambda: return id(ist_tag);
          then:
{thema_zweig(0)}
          else:
{thema_zweig(1)}

  # Warnung (gefüllt) oder Vorwarnung (nur Rand) unter dem Wetterbild; das Bild wird dafür kleiner
  - id: warn_zeichnen
    then:
      - lambda: |-
          bool an = wx::warn_pille(id(warn_pill), id(lbl_warn_icon), id(lbl_warn), id(wetter_warnung).state,
                                   id(wetter_vorwarnung).state, {PILL_TEXT_MAX});
          wx::bild_skalieren(id(bild_jetzt), id(bild_klein), {BILD_PX}, {BADGE_OFF}, an ? {BILD_KLEIN} : 256);

  # Titel der Wind-Kachel: Richtung und Böen ("SW · Böen 38"), ohne Böen "Wind SW"
  - id: wind_titel
    then:
      - lvgl.label.update:
          id: lbl_wind_titel
          text: !lambda |-
            auto r = wx::richtung(id(wetter_windrichtung).state);
            float b = id(wetter_boeen).state;
            if (!std::isnan(b)) return (r.empty() ? std::string("Böen ") : r + " · Böen ") + wx::percent(b);
            return r.empty() ? std::string("Wind") : "Wind " + r;

  # unten im Panel: die Seitenpunkte, oder bei fehlender Verbindung die Wolke mit der Uhrzeit. Auf der Wetterseite
  # gibt es die Punkte erst, wenn auch die Seite Raumklima Daten hat.
  - id: punkte_zeichnen
    then:
      - lambda: |-
          bool off = id(offline_an);
          bool innen = wx::innen_da(id(co2_wohnzimmer).state, id(co2_schlafzimmer).state, id(co2_buero).state);
          auto zeig = [](lv_obj_t *o, bool an) {{
            if (an) lv_obj_remove_flag(o, LV_OBJ_FLAG_HIDDEN); else lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
          }};
          zeig(id(punkte_w), !off && innen);
          zeig(id(punkte_i), !off);
          zeig(id(offline_w), off);
          zeig(id(offline_i), off);
          lv_label_set_text(id(lbl_offline_w), id(offline_text).c_str());
          lv_label_set_text(id(lbl_offline_i), id(offline_text).c_str());

  # ohne Verbindung zu Home Assistant: Werte blass, unten die Wolke mit der Uhrzeit
  - id: verbindung_zeichnen
    then:
      - lambda: |-
          lv_opa_t o = id(offline_an) ? LV_OPA_40 : LV_OPA_COVER;
          lv_obj_t *blass[] = {{{", ".join(f"id({b})" for b in BLASS_W + BLASS_I)}}};
          for (auto *b : blass) lv_obj_set_style_opa(b, o, LV_PART_MAIN);
      - script.execute: punkte_zeichnen
""")

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
  - {{file: fonts/Poppins-300.ttf, id: f_co2, size: 52, bpp: 4, glyphs: "-0123456789"}}
  - {{file: fonts/Poppins-500.ttf, id: f_28m, size: 28, bpp: 4, glyphs: {q(ZIFFERN)}}}
  - {{file: fonts/Poppins-600.ttf, id: f_22b, size: 22, bpp: 4, glyphs: {q(ZIFFERN)}}}
  - {{file: fonts/Poppins-500.ttf, id: f_20m, size: 20, bpp: 4, glyphs: {q(ZIFFERN)}}}
  - {{file: fonts/Poppins-600.ttf, id: f_13b, size: 13, bpp: 4, glyphs: {q(LATIN)}}}
  - {{file: fonts/Poppins-400.ttf, id: f_15, size: 15, bpp: 4, glyphs: {q("HochTief0123456789-°· ")}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_tag, size: 22, bpp: 4, glyphs: {mdi(COND)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_ui, size: 18, bpp: 4, glyphs: {mdi(UI)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_klein, size: 13, bpp: 4, glyphs: {mdi(KLEIN_ICONS)}}}
  - {{file: fonts/materialdesignicons-webfont.ttf, id: i_lock, size: 32, bpp: 4, glyphs: ["\U000F033E"]}}
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

w("""interval:
  # Verbindung zu Home Assistant: fehlt sie länger als eine Minute, zeigt das Display das an
  - interval: 15s
    then:
      - if:
          condition:
            api.connected:
          then:
            - lambda: id(offline_seit) = 0;
            - if:
                condition:
                  lambda: return id(offline_an);
                then:
                  - lambda: id(offline_an) = false;
                  - script.execute: verbindung_zeichnen
          else:
            - lambda: |-
                if (id(offline_seit) == 0) {
                  id(offline_seit) = millis() | 1;
                  auto t = id(ha_time).now();
                  id(offline_text) = t.is_valid() ? t.strftime("%H:%M") : std::string("");
                }
            - if:
                condition:
                  lambda: return !id(offline_an) && millis() - id(offline_seit) >= 60000;
                then:
                  - lambda: id(offline_an) = true;
                  - script.execute: verbindung_zeichnen
  # CO2-Trend: alle 5 Minuten die Werte merken und die Pfeile neben den Räumen setzen
  - interval: 5min
    then:
      - lambda: |-
          wx::co2_merken(0, id(co2_wohnzimmer).state);
          wx::co2_merken(1, id(co2_schlafzimmer).state);
          wx::co2_merken(2, id(co2_buero).state);
          lv_obj_t *pfeil[] = {id(lbl_trend_wohnzimmer), id(lbl_trend_schlafzimmer), id(lbl_trend_buero)};
          for (int r = 0; r < 3; ++r) {
            int t = wx::co2_trend(r);
            lv_label_set_text(pfeil[r], wx::trend_icon(t).c_str());
            lv_obj_set_style_text_color(pfeil[r], wx::trend_color(t), LV_PART_MAIN);
          }
""")

# ---------------------------------------------------------------- Daten aus Home Assistant

w(f"""# ---------------- Daten aus Home Assistant ----------------
text_sensor:
  - platform: homeassistant
    id: wetter_zustand
    entity_id: ${{wetter_entity}}
    on_value:
      then:
        - script.execute: jetzt_zeichnen
  - platform: homeassistant
    id: sonne_zustand
    entity_id: sun.sun
    on_value:
      then:
        - script.execute: tag_pruefen
        - script.execute: jetzt_zeichnen
  - platform: homeassistant
    id: wetter_sonne
    entity_id: ${{vorhersage_entity}}
    attribute: sonne
    on_value:
      then:
        - script.execute: uhr_zeichnen
        - script.execute: tag_pruefen
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
        - script.execute: warn_zeichnen
  - platform: homeassistant
    id: wetter_vorwarnung
    entity_id: ${{vorhersage_entity}}
    attribute: vorwarnung
    on_value:
      then:
        - script.execute: warn_zeichnen
  - platform: homeassistant
    id: wetter_regen_satz
    entity_id: ${{vorhersage_entity}}
    attribute: regen_satz
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_satz_a
            text: !lambda 'auto a = wx::part(x, 0); return a.empty() ? std::string("Regen") : a;'
        - lvgl.label.update:
            id: lbl_satz_b
            text: !lambda 'return wx::part(x, 1);'""")
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
            text: !lambda |-
              auto v = wx::rain_value(wx::part(x, 4), wx::part(x, 5));
              return wx::rain_unit(wx::part(x, 4), wx::part(x, 5)) == "%" ? v + "%" : v;
        - lvgl.label.update:
            id: lbl_icon_{d}
            text: !lambda 'return wx::icon(wx::part(x, 1));'
            text_color: !lambda 'return wx::icon_color(wx::part(x, 1));'
        - lvgl.label.update:
            id: lbl_name_{d}
            text: !lambda 'return wx::part(x, 0);'
        # Frost: Tief unter 0 Grad, ein kleiner Eiskristall am Wetter-Icon
        - if:
            condition:
              lambda: 'return wx::num(wx::part(x, 3)) < 0;'
            then:
              - lvgl.widget.show: lbl_frost_{d}
            else:
              - lvgl.widget.hide: lbl_frost_{d}""")
    if d == 0:
        w("""        - lvgl.label.update:
            id: lbl_legende_einheit
            text: !lambda 'auto u = wx::rain_unit(wx::part(x, 4), wx::part(x, 5)); return u.empty() ? std::string("%") : u;'
        - lvgl.label.update:
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
        - script.execute: wind_titel
  - platform: homeassistant
    id: wetter_boeen
    entity_id: ${wetter_entity}
    attribute: wind_gust_speed
    on_value:
      then:
        - script.execute: wind_titel
  - platform: homeassistant
    id: wetter_uv
    entity_id: ${uv_entity}
    on_value:
      then:
        - script.execute: jetzt_zeichnen
  # Diagnose in Home Assistant
  - platform: wifi_signal
    name: WLAN-Signal
    update_interval: 60s
    entity_category: diagnostic
  - platform: uptime
    name: Laufzeit
    entity_category: diagnostic
""")

# ---- Raumklima: Maße (wie im Entwurf) und Sensoren
RAEUME = [("wohnzimmer", "Wohnzimmer"), ("schlafzimmer", "Schlafzimmer"), ("buero", "Büro")]
TW = (W - 2 * G) / 3                      # drei Spalten: Panel und Kacheln stehen übereinander
SKALA_W = round(TW - 2 * P)
# CO2-Skala unter der Zahl: mittig zwischen Zahl (Block bis 152) und Panelunterkante (212)
SKALA_Y, SKALA_H, MARKER_D = 176, 12, 22
TILE2_H = 96
CARD2_Y = TILE_Y + TILE2_H + G
CARD2_H = 480 - M - CARD2_Y
PM = [("pm1", "PM1", 50, "false"), ("pm25", "PM2.5", 50, "false"), ("pm4", "PM4", 120, "true"),
      ("pm10", "PM10", 120, "true")]
GASE = [("voc", "VOC-Index", "voc_stufe"), ("nox", "NOx-Index", "nox_stufe")]


def spalte(i):
    return round(P + i * (TW + G))


for i, (r, name) in enumerate(RAEUME):
    w(f"""  - platform: homeassistant
    id: co2_{r}
    entity_id: ${{co2_{r}}}
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_co2_{r}
            text: !lambda 'return wx::zahl(x);'
        # ab "Mittel" liegt die Zahl in einem Block in der Farbe der Stufe, so breit wie die Zahl
        - lambda: |-
            int s = wx::co2_stufe(x);
            lv_obj_t *l = id(lbl_co2_{r}), *b = id(block_{r});
            if (s >= 3) {{
              lv_point_t sz;
              lv_text_get_size(&sz, lv_label_get_text(l), lv_obj_get_style_text_font(l, LV_PART_MAIN), 0, 0,
                               LV_COORD_MAX, LV_TEXT_FLAG_NONE);
              lv_obj_set_width(b, sz.x + 2 * {BLOCK_PAD});
              lv_obj_set_style_bg_color(b, wx::co2_color(s), LV_PART_MAIN);
              lv_obj_set_style_text_color(l, wx::co2_text_color(s), LV_PART_MAIN);
              lv_obj_remove_flag(b, LV_OBJ_FLAG_HIDDEN);
            }} else {{
              lv_obj_add_flag(b, LV_OBJ_FLAG_HIDDEN);
              lv_obj_set_style_text_color(l, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
            }}
        - lvgl.obj.update:
            id: marker_{r}
            x: !lambda 'return {spalte(i)} + wx::co2_marker_x(x, {SKALA_W}) + 6 - {MARKER_D // 2};'
            bg_color: !lambda 'return wx::co2_color(wx::co2_stufe(x));'
        - script.execute: punkte_zeichnen
  - platform: homeassistant
    id: temp_{r}
    entity_id: ${{temp_{r}}}
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_temp_{r}
            text: !lambda 'return wx::komma(x) + "°";'
  - platform: homeassistant
    id: feuchte_{r}
    entity_id: ${{feuchte_{r}}}
    on_value:
      then:
        - lvgl.label.update:
            id: lbl_feuchte_{r}
            text: !lambda 'return wx::zahl(x);'
            text_color: !lambda 'return wx::feuchte_color(x);'""")
for k, lab, voll, grob in PM:
    w(f"""  - platform: homeassistant
    id: {k}_buero
    entity_id: ${{{k}_buero}}
    on_value:
      then:
        - lvgl.bar.update:
            id: bar_{k}
            value: !lambda 'return wx::balken(x, {voll});'
            indicator:
              bg_color: !lambda 'return wx::ampel(wx::pm_stufe(x, {grob}));'
        - lvgl.label.update:
            id: lbl_{k}
            text: !lambda 'return wx::zahl(x);'""")
for k, lab, fn in GASE:
    w(f"""  - platform: homeassistant
    id: {k}_buero
    entity_id: ${{{k}_buero}}
    on_value:
      then:
        - lvgl.bar.update:
            id: bar_{k}
            value: !lambda 'return wx::balken(x, 500);'
            indicator:
              bg_color: !lambda 'return wx::ampel(wx::{fn}(x), false);'
        - lvgl.label.update:
            id: lbl_{k}
            text: !lambda 'return wx::zahl(x);'
        - lvgl.label.update:
            id: lbl_{k}_stufe
            text: !lambda 'return wx::gas_name(wx::{fn}(x));'
            text_color: !lambda 'return wx::ampel(wx::{fn}(x), false);'""")
w("")

# ---------------------------------------------------------------- Oberfläche

TILE = dict(styles="s_karte", bg_opa="COVER", border_width=0, radius=14, shadow_width=18, shadow_color=LINIE,
            shadow_offset_y=4)
CARDSTYLE = dict(TILE, radius=16)


def stil_definitionen():
    zeilen = ["  style_definitions:"]
    for sid, werte in THEMA.items():
        zeilen.append(f"    - id: {sid}")
        for k, v in werte[0].items():
            zeilen.append(f"      {k}: {v}")
    return "\n".join(zeilen)


w(f"""# ---------------- Oberfläche ----------------
lvgl:
  displays: [my_display]
  touchscreens: [ts_touch]
  buffer_size: 25%
  default_font: f_14
  # Farben, die zwischen Tag (hell) und Nacht (dunkel) wechseln; das Skript thema_setzen schaltet sie um
{stil_definitionen()}
  # das Schloss (Seite festgehalten) erscheint kurz in der Mitte über beiden Seiten und blendet sich wieder aus
  top_layer:
    widgets:
      - obj:
          id: schloss
          hidden: true
          align: CENTER
          width: 60
          height: 60
          radius: 30
          bg_color: {GOLD}
          bg_opa: COVER
          border_width: 3
          border_color: 0xFFFFFF
          shadow_width: 24
          shadow_color: 0x000000
          shadow_opa: 35%
          pad_all: 0
          clickable: false
          scrollable: false
          widgets:
            - label:
                align: CENTER
                text: "\\U000F033E"
                text_font: i_lock
                text_color: {PANEL_NACHT[0]}
  pages:
    - id: seite_wetter
      styles: s_seite
      bg_opa: COVER
      scrollable: false
      pad_all: 0
      widgets:""")
I, C = 8, 14   # Einrückung der Seitenteile und ihrer Kinder

# ---- Panel
kids = []
kids.append(label(C, "lbl_ort", P, y(14, 30, 24), "${ort}", "f_ort", "0xFFFFFF"))
kw_pill = widget("obj", C + 8, dict(
    height=20, width="SIZE_CONTENT", radius=10, bg_color="0xFFFFFF", bg_opa="16%", border_width=0, pad_left=8,
    pad_right=8, pad_top=0, pad_bottom=0, scrollable="false", clickable="false",
    layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: CENTER\n  flex_align_cross: CENTER\n"
           "  flex_align_track: CENTER"),
    [label(C + 12, "lbl_kw", None, None, "KW --", "f_14m", "0xFFFFFF")])
kids.append(row(C, None, P, y(46, 20, 16), [label(C + 8, "lbl_datum", None, None, "", "f_16", PMUTED), kw_pill], 8))
kids.append(row(C, "temp_zeile", P - 4, y(78, 80, 76), [
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
kids.append(label(C, "lbl_hochtief", RX, y(ROW, 20, 15), "", "f_15", PMUTED, width=RW, align="RIGHT"))
# Warnung oder Vorwarnung: rechtsbündig unter dem Bild; Farben, Rand und Text setzt wx::warn_pille()
kids.append(widget("obj", C, dict(
    id="warn_pill", hidden="true", align="TOP_RIGHT", x=-P, y=PILL_Y, height=PILL_H, width="SIZE_CONTENT",
    radius=PILL_H // 2, bg_color="0xF08A24", bg_opa="COVER", border_width=0, pad_left=7, pad_right=10, pad_top=0,
    pad_bottom=0, scrollable="false", clickable="false",
    layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: START\n  flex_align_cross: CENTER\n"
           "  flex_align_track: CENTER\n  pad_column: 5"),
    [label(C + 8, "lbl_warn_icon", None, None, "\\U000F0026", "i_warn", "0xFFFFFF"),
     label(C + 8, "lbl_warn", None, None, "", "f_pill", "0xFFFFFF", long_mode="SCROLL_CIRCULAR")]))


def status(ind, seite):
    """Unten in der Mitte des Panels: die Seitenpunkte (die aktive Seite als goldener Strich) und, an derselben
    Stelle, die durchgestrichene Wolke mit der Uhrzeit, seit der die Verbindung fehlt."""
    punkte = [widget("obj", ind + 8, dict(width=14 if k == seite else 6, height=6, radius=3,
                                          bg_color="0xD4A548" if k == seite else "0xFFFFFF",
                                          bg_opa="COVER" if k == seite else "35%", border_width=0))
              for k in range(2)]
    n = "wi"[seite]
    return [row(ind, f"punkte_{n}", 0, -7, punkte, 5, align="BOTTOM_MID"),
            row(ind, f"offline_{n}", 0, -2, [label(ind + 8, None, None, None, "\\U000F0164", "i_klein", SONNE),
                                              label(ind + 8, f"lbl_offline_{n}", None, None, "", "f_12", SONNE)],
                4, align="BOTTOM_MID", hidden="true")]


kids += status(C, 0)
w(box(I, "panel", M, M, W, PANEL_H, dict(styles="s_panel", bg_grad_dir="VER", bg_opa="COVER", border_width=0,
                                        radius=22, clip_corner="true"), kids))

# ---- Kacheln
tiles = [("wind", "\\U000F059D", "Wind", "km/h", "lbl_wind_titel"), ("regen", "\\U000F054A", "Regen heute", "%", None),
         ("feuchte", "\\U000F058E", "Luftfeuchte", "%", None), ("uv", "\\U000F05A8", "UV-Index", "", None)]
for k, (name, ic, titel, unit, tid) in enumerate(tiles):
    x = M + k * (COL + G)
    unit_label = (label(C + 8, "lbl_uv_text", None, None, "", "f_14m", "0x2EAF6A", pad_bottom=3) if name == "uv" else
                  label(C + 8, "lbl_regen_einheit" if name == "regen" else None, None, None, unit, "f_14", MUTED,
                        pad_bottom=3))
    kids = [label(C, tid, P, y(11, 16, 14), titel, "f_14", MUTED, **(dict(width=COL - P - 4, long_mode="DOT")
                                                                    if name == "wind" else {})),
            row(C, None, P - 1, 28, [
                label(C + 8, None, None, None, ic, "i_ui", GOLD, pad_right=3, pad_bottom=4),
                label(C + 8, f"lbl_{name}", None, None, "--", "f_wert", INK),
                unit_label], 3, cross="END")]
    w(box(I, f"kachel_{name}", x, TILE_Y, COL, TILE_H, TILE, kids))


# ---- Karten unten
def kopf(titel, rechts):
    return [label(C, None, P, y(12, 20, 17), titel, "f_17m", INK),
            row(C, None, -P, y(14, 16, 13), rechts, 5, align="TOP_RIGHT")]


legende = [widget("obj", C + 8, dict(width=10, height=3, radius=2, styles="s_linie", bg_opa="COVER", border_width=0)),
           label(C + 8, None, None, None, "Temp", "f_13", MUTED),
           label(C + 8, "lbl_legende_einheit", None, None, "%", "f_13m", GOLD, pad_left=6),
           label(C + 8, None, None, None, "Regen", "f_13", MUTED)]
kids = kopf("5 Tage", legende)
kids.append(box(C, None, P, 106, CARD2 - 2 * P, 1, dict(styles="s_linie", bg_opa="14%", border_width=0, radius=0)))
pts = ", ".join(f"[{round(16 + 19.6 + i * 39.2 / 8)}, 80]" for i in range(33))
kids.append(widget("line", C, dict(id="kurve", points=f"[{pts}]", styles="s_kurve", line_width=3,
                                   line_rounded="true")))
# das Icon mittig zwischen Regenwert (Oberkante 106, 18 hoch) und Wochentag, 22 px hoch
ICON_Y = round((106 + 18 + y(149, 18, 14)) / 2 - 11)
for d in range(5):
    cx = round(16 + 39.2 * (d + .5))
    heute = d == 0
    kids.append(box(C, f"punkt_{d}", cx - 5, 75, 10, 10, dict(radius=5, bg_opa="COVER", border_width=3,
                                                              border_color=GOLD,
                                                              **(dict(bg_color=GOLD) if heute else
                                                                 dict(styles="s_karte")))))
    kids.append(label(C, f"lbl_hoch_{d}", cx - 20, 50, "", "f_16m", GOLD if heute else INK, width=40, align="CENTER"))
    kids.append(label(C, f"lbl_regen_{d}", cx - 20, 106, "", "f_13m", GOLD, width=40, align="CENTER",
                      long_mode="CLIP"))
    kids.append(label(C, f"lbl_icon_{d}", cx - 20, ICON_Y, "", "i_tag", MUTED, width=40, align="CENTER"))
    # Frost (Tief unter 0 Grad): ein kleiner Eiskristall oben rechts am Icon
    kids.append(label(C, f"lbl_frost_{d}", cx + 8, ICON_Y - 4, "\\U000F0717", "i_klein", "0x7FA7D9", hidden="true"))
    kids.append(label(C, f"lbl_name_{d}", cx - 22, y(149, 18, 14), "", "f_14m" if heute else "f_14",
                      GOLD if heute else MUTED, width=44, align="CENTER"))
w(box(I, "karte_tage", M, CARD_Y, CARD2, CARD_H, CARDSTYLE, kids))

# Kopf als Satz: "Trocken bis 17 Uhr", der zweite Teil in Gold (aus dem Attribut regen_satz)
kids = [row(C, None, P, y(12, 20, 17), [label(C + 8, "lbl_satz_a", None, None, "Regen", "f_17m", INK),
                                        label(C + 8, "lbl_satz_b", None, None, "", "f_17m", GOLD)], 5)]
inner = CARD2 - 2 * P
WERT_W = 56  # "0,3 mm" ist 53 px breit (Poppins 500, 14 px)
bar_w = inner - 44 - WERT_W - 20
for h in range(5):
    r = 50 + h * 24
    kids.append(label(C, f"lbl_std_{h}", P, y(r, 16, 14), "", "f_14", MUTED, width=44))
    kids.append(widget("bar", C, dict(id=f"bar_std_{h}", x=P + 54, y=r + 2, width=bar_w, height=12, min_value=0,
                                      max_value=100, value=0, radius=6, bg_color=TRACK, bg_opa="12%",
                                      indicator="{radius: 6, bg_color: " + FILL + ", bg_opa: COVER}")))
    kids.append(label(C, f"lbl_std_wert_{h}", P + 54 + bar_w + 10, y(r, 16, 14), "", "f_14m", INK, width=WERT_W,
                      align="RIGHT", long_mode="CLIP"))
w(box(I, "karte_regen", M + CARD2 + G, CARD_Y, CARD2, CARD_H, CARDSTYLE, kids))

# ================================================================ Seite 2: Raumklima
from PIL import ImageFont  # nur zum Ausmessen eines festen Textes (Lage der "ppm"-Pille)
_f16 = ImageFont.truetype(os.path.join(os.path.dirname(HIER), "fonts", "Poppins-400.ttf"), 16)
_f12 = ImageFont.truetype(os.path.join(os.path.dirname(HIER), "fonts", "Poppins-400.ttf"), 12)
UNTER = round(_f16.getlength("CO") + _f12.getlength("2") + _f16.getlength(" in den Räumen"))

w(f"""    - id: seite_innen
      styles: s_seite
      bg_opa: COVER
      scrollable: false
      pad_all: 0
      widgets:""")

kids = [label(C, None, P, y(14, 30, 24), "Raumklima", "f_ort", "0xFFFFFF")]
# Untertitel "CO2 in den Räumen" mit tiefgestellter 2 (Poppins hat kein ₂) und die Pille "ppm"
ux = P
for text, font, top in (("CO", "f_16", y(46, 20, 16)), ("2", "f_12", y(46, 20, 16) + 8),
                        (" in den Räumen", "f_16", y(46, 20, 16))):
    kids.append(label(C, None, ux, top, text, font, PMUTED))
    ux += round((_f16 if font == "f_16" else _f12).getlength(text))
kids.append(widget("obj", C, dict(
    x=P + UNTER + 8, y=46, height=20, width="SIZE_CONTENT", radius=10, bg_color="0xFFFFFF", bg_opa="16%",
    border_width=0, pad_left=8, pad_right=8, pad_top=0, pad_bottom=0, scrollable="false", clickable="false",
    layout="\n  type: FLEX\n  flex_flow: ROW\n  flex_align_main: CENTER\n  flex_align_cross: CENTER\n"
           "  flex_align_track: CENTER"),
    [label(C + 8, None, None, None, "ppm", "f_14m", "0xFFFFFF")]))
SEG = [400, 650, 850, 1050, 1550, 2000]
for i, (r, name) in enumerate(RAEUME):
    x = spalte(i)
    if i:
        kids.append(box(C, None, round(i * (TW + G) - G / 2), 82, 1, 120,
                        dict(bg_color="0xFFFFFF", bg_opa="15%", border_width=0, radius=0)))
    # Raumname mit CO2-Trend (Pfeil, erst nach 15 Minuten Werten)
    kids.append(row(C, None, x, 79, [label(C + 8, None, None, None, name, "f_14", PMUTED),
                                     label(C + 8, f"lbl_trend_{r}", None, None, "", "i_ui", PMUTED)], 6))
    # Block hinter der Zahl (ab "Mittel"): umschließt die Ziffern (Oberkante 106, Unterkante 145) mit etwas Luft
    kids.append(box(C, f"block_{r}", x - 3 - BLOCK_PAD, 100, 60, 52, dict(radius=12, bg_color="0xF2C230",
                                                                        bg_opa="COVER", border_width=0),
                    hidden="true"))
    kids.append(label(C, f"lbl_co2_{r}", x - 3, y(96, 60, 52), "--", "f_co2", "0xFFFFFF"))
    for k in range(5):
        a = round((SEG[k] - 400) / 1600 * SKALA_W)
        b = round((SEG[k + 1] - 400) / 1600 * SKALA_W)
        gap = 2 if k else 0
        rad = SKALA_H // 2 if k in (0, 4) else 0
        kids.append(box(C, None, x + a + gap, SKALA_Y, b - a - gap, SKALA_H,
                        dict(bg_color="0x" + ["1E7A3C", "2E9E4F", "7DBB42", "F2C230", "E8542C"][k], bg_opa="COVER",
                             border_width=0, radius=rad)))
    # Marker: Kreis in der Farbe der Stufe mit weißem Ring
    kids.append(box(C, f"marker_{r}", x - MARKER_D // 2, SKALA_Y + SKALA_H // 2 - MARKER_D // 2, MARKER_D, MARKER_D,
                    dict(radius=MARKER_D // 2, bg_color="0x5F6B80", bg_opa="COVER", border_width=3,
                         border_color="0xFFFFFF", shadow_width=8, shadow_color="0x000000", shadow_opa="40%",
                         shadow_offset_y=1)))
kids += status(C, 1)
w(box(I, "panel_innen", M, M, W, PANEL_H, dict(styles="s_panel", bg_grad_dir="VER", bg_opa="COVER", border_width=0,
                                              radius=22, clip_corner="true"), kids))

# Kacheln: Temperatur groß, darunter die Luftfeuchte in Ampelfarbe
for i, (r, name) in enumerate(RAEUME):
    x = round(M + i * (TW + G))
    kids = [label(C, None, P, y(11, 16, 14), name, "f_14", MUTED),
            label(C, f"lbl_temp_{r}", P, 27, "--", "f_28m", INK),
            row(C, None, P, 62, [label(C + 8, f"lbl_feuchte_{r}", None, None, "--", "f_22b", MUTED),
                                 label(C + 8, None, None, None, "%", "f_16", MUTED, pad_bottom=3)], 2, cross="END")]
    w(box(I, f"kachel_{r}", x, TILE_Y, round(TW), TILE2_H, TILE, kids))

# Karte Feinstaub (Büro): Zeilen wie die Regenkarte
kids = kopf("Feinstaub", [label(C + 8, None, None, None, "Büro · µg/m³", "f_13", MUTED)])
for n, (k, lab, voll, grob) in enumerate(PM):
    r = 44 + n * 22
    kids.append(label(C, None, P, y(r, 16, 14), lab, "f_14", MUTED, width=44))
    kids.append(widget("bar", C, dict(id=f"bar_{k}", x=P + 54, y=r + 2, width=bar_w, height=12, min_value=0,
                                      max_value=100, value=0, radius=6, styles="s_spur", bg_opa="COVER",
                                      indicator="{radius: 6, bg_color: 0x2E9E4F, bg_opa: COVER}")))
    kids.append(label(C, f"lbl_{k}", P + 54 + bar_w + 10, y(r, 16, 14), "--", "f_14m", INK, width=34,
                      align="RIGHT"))
w(box(I, "karte_feinstaub", M, CARD2_Y, CARD2, CARD2_H, CARDSTYLE, kids))

# Karte Gase (Büro): VOC- und NOx-Index mit Einstufung
kids = kopf("Gase", [label(C + 8, None, None, None, "Büro · 3D-Drucker", "f_13", MUTED)])
for n, (k, lab, fn) in enumerate(GASE):
    r = 40 + n * 48
    kids.append(label(C, None, P, y(r, 21, 14), lab, "f_14", MUTED))
    kids.append(label(C, f"lbl_{k}_stufe", P, y(r, 21, 14), "", "f_pill", "0x2E9E4F", width=inner, align="RIGHT"))
    kids.append(label(C, f"lbl_{k}", P, y(r + 23, 26, 20), "--", "f_20m", INK, width=44))
    kids.append(widget("bar", C, dict(id=f"bar_{k}", x=P + 54, y=r + 30, width=inner - 54, height=12, min_value=0,
                                      max_value=100, value=0, radius=6, styles="s_spur", bg_opa="COVER",
                                      indicator="{radius: 6, bg_color: 0x2E9E4F, bg_opa: COVER}")))
w(box(I, "karte_gase", M + CARD2 + G, CARD2_Y, CARD2, CARD2_H, CARDSTYLE, kids))

open(ZIEL, "w").write("\n".join(out) + "\n")
print("geschrieben:", ZIEL)
