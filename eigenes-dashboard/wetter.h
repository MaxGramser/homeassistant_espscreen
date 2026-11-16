#pragma once
// Hilfsfunktionen für das Wetter-Dashboard (wetter-display.yaml).
//
// Home Assistant liefert jeden Vorhersage-Tag, jede Stunde, die Sonne und die Warnung als einen Text mit Semikolons
// (home-assistant/wetter_display.yaml beschreibt die Felder); hier wird er zerlegt und in Texte, Farben und
// Positionen übersetzt. Die Wetterbilder selbst wählt wetter-display.yaml aus, weil nur dort die Bild-IDs bekannt sind.
#include <cmath>
#include <cstdio>
#include <cstring>
#include <ctime>
#include <string>
#include <lvgl.h>
#include "esphome/core/time.h"

namespace wx {

// ---------------------------------------------------------------- Texte zerlegen

// Das i-te Feld eines Textes wie "Mo;rainy;11;4;60;1.2" (ab 0), oder "" wenn es fehlt.
inline std::string part(const std::string &s, int i) {
  size_t start = 0;
  for (int n = 0; n < i; ++n) {
    start = s.find(';', start);
    if (start == std::string::npos) return "";
    ++start;
  }
  size_t end = s.find(';', start);
  return s.substr(start, end == std::string::npos ? std::string::npos : end - start);
}

inline float num(const std::string &s) {
  if (s.empty() || s == "None" || s == "unknown" || s == "unavailable") return NAN;
  char *end = nullptr;
  float v = strtof(s.c_str(), &end);
  return end == s.c_str() ? NAN : v;
}

// Für Unix-Zeiten: ein float ist bei Zahlen um 1,8 Milliarden nur auf etwa 2 Minuten genau.
inline double numd(const std::string &s) {
  if (s.empty() || s == "None" || s == "unknown" || s == "unavailable") return NAN;
  char *end = nullptr;
  double v = strtod(s.c_str(), &end);
  return end == s.c_str() ? NAN : v;
}

inline std::string deg(float v) {
  if (std::isnan(v)) return "--°";
  char b[12];
  snprintf(b, sizeof(b), "%.0f°", v);
  return strcmp(b, "-0°") == 0 ? std::string("0°") : std::string(b);  // "-0°" sieht falsch aus
}
inline std::string deg(const std::string &s) { return deg(num(s)); }

// Nur die Zahl, ohne Grad: für die große Temperatur (das "°C" steht daneben in kleinerer Schrift).
inline std::string zahl(float v) {
  if (std::isnan(v)) return "--";
  char b[12];
  snprintf(b, sizeof(b), "%.0f", v);
  return strcmp(b, "-0") == 0 ? std::string("0") : std::string(b);
}

// ---------------------------------------------------------------- Wetterzustand

// Die Wörter, die Home Assistant auf Deutsch zeigt.
inline std::string text(const std::string &c) {
  if (c == "sunny") return "Sonnig";
  if (c == "clear-night") return "Klare Nacht";
  if (c == "partlycloudy") return "Teilweise bewölkt";
  if (c == "cloudy") return "Bewölkt";
  if (c == "fog") return "Nebel";
  if (c == "hail") return "Hagel";
  if (c == "lightning") return "Gewitter";
  if (c == "lightning-rainy") return "Gewitter, Regen";
  if (c == "pouring") return "Starkregen";
  if (c == "rainy") return "Regen";
  if (c == "snowy") return "Schnee";
  if (c == "snowy-rainy") return "Schneeregen";
  if (c == "windy") return "Windig";
  if (c == "windy-variant") return "Windig, bewölkt";
  if (c == "exceptional") return "Unwetter";
  if (c == "unavailable" || c == "unknown" || c.empty()) return "Keine Daten";
  return c;
}

// Kleine Icons der 5-Tage-Karte (Material Design Icons wie im Home-Assistant-Frontend) und ihre Farben.
inline std::string icon(const std::string &c) {
  if (c == "sunny") return "\U000F0599";
  if (c == "clear-night") return "\U000F0594";
  if (c == "partlycloudy") return "\U000F0595";
  if (c == "cloudy") return "\U000F0590";
  if (c == "fog") return "\U000F0591";
  if (c == "hail") return "\U000F0592";
  if (c == "lightning") return "\U000F0593";
  if (c == "lightning-rainy") return "\U000F067E";
  if (c == "pouring") return "\U000F0596";
  if (c == "rainy") return "\U000F0597";
  if (c == "snowy") return "\U000F0598";
  if (c == "snowy-rainy") return "\U000F067F";
  if (c == "windy") return "\U000F059D";
  if (c == "windy-variant") return "\U000F059E";
  if (c == "exceptional") return "\U000F0F2F";
  return "";
}
inline lv_color_t icon_color(const std::string &c) {
  if (c == "sunny") return lv_color_hex(0xF5A623);
  if (c == "partlycloudy") return lv_color_hex(0xF5B83D);
  if (c == "clear-night") return lv_color_hex(0x6B7FD6);
  if (c == "rainy" || c == "pouring" || c == "hail") return lv_color_hex(0x4A90E2);
  if (c == "lightning" || c == "lightning-rainy") return lv_color_hex(0xE8A317);
  if (c == "snowy" || c == "snowy-rainy") return lv_color_hex(0x7FA7D9);
  if (c == "windy" || c == "windy-variant") return lv_color_hex(0x5FA3B3);
  if (c == "exceptional") return lv_color_hex(0xE5322D);
  return lv_color_hex(0x8A94A6);
}

// Welches kleine Bild nachts auf dem Mond liegt; "" heißt keines (klarer Himmel).
inline std::string nacht_art(const std::string &c) {
  if (c == "sunny" || c == "clear-night" || c.empty()) return "";
  if (c == "partlycloudy" || c == "cloudy") return "wolke";
  return c;
}

// ---------------------------------------------------------------- Werte

inline std::string percent(float v) {
  if (std::isnan(v)) return "--";
  char b[8];
  snprintf(b, sizeof(b), "%.0f", v);
  return b;
}

// Regen: die Wahrscheinlichkeit, wenn der Wetterdienst sie liefert (DWD), sonst die Menge.
// Gibt Zahl und Einheit getrennt zurück, damit die Einheit kleiner gesetzt werden kann.
inline std::string rain_value(const std::string &probability, const std::string &mm) {
  float p = num(probability), m = num(mm);
  char b[12];
  if (!std::isnan(p)) {
    snprintf(b, sizeof(b), "%.0f", p);
    return b;
  }
  if (!std::isnan(m)) {
    snprintf(b, sizeof(b), m < 10 ? "%.1f" : "%.0f", m);
    std::string out = b;
    size_t dot = out.find('.');
    if (dot != std::string::npos) out[dot] = ',';
    return out == "0,0" ? std::string("0") : out;
  }
  return "--";
}
inline std::string rain_unit(const std::string &probability, const std::string &mm) {
  if (!std::isnan(num(probability))) return "%";
  if (!std::isnan(num(mm))) return "mm";
  return "";
}
inline std::string rain(const std::string &probability, const std::string &mm) {
  auto v = rain_value(probability, mm);
  return v == "--" ? v : v + " " + rain_unit(probability, mm);
}
// Länge des Regenbalkens 0 bis 100: die Wahrscheinlichkeit, oder ohne sie die Menge (4 mm = voll).
inline int rain_bar(const std::string &probability, const std::string &mm) {
  float p = num(probability), m = num(mm);
  float v = !std::isnan(p) ? p : !std::isnan(m) ? m * 25.0f : 0;
  return v < 0 ? 0 : v > 100 ? 100 : (int) lroundf(v);
}

inline std::string richtung(float bearing) {
  if (std::isnan(bearing)) return "";
  static const char *const dirs[] = {"N", "NO", "O", "SO", "S", "SW", "W", "NW"};
  return dirs[(int) lroundf(fmodf(bearing + 360.0f, 360.0f) / 45.0f) % 8];
}

// UV-Index nach der Skala der WHO, wie sie auch der DWD verwendet.
inline std::string uv_text(float uv) {
  if (std::isnan(uv)) return "";
  if (uv < 3) return "niedrig";
  if (uv < 6) return "mäßig";
  if (uv < 8) return "hoch";
  if (uv < 11) return "sehr hoch";
  return "extrem";
}
inline lv_color_t uv_color(float uv) {
  if (std::isnan(uv) || uv < 3) return lv_color_hex(0x2EAF6A);
  if (uv < 6) return lv_color_hex(0xD9A400);
  if (uv < 8) return lv_color_hex(0xF08A24);
  if (uv < 11) return lv_color_hex(0xE5322D);
  return lv_color_hex(0x9B2FAE);
}

// ---------------------------------------------------------------- Datum, Woche, Sonne, Mond

inline std::string datum(esphome::ESPTime t) {
  if (!t.is_valid()) return "";
  static const char *const tage[] = {"Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"};
  static const char *const monate[] = {"Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                                        "August", "September", "Oktober", "November", "Dezember"};
  char b[48];
  snprintf(b, sizeof(b), "%s, %d. %s", tage[(t.day_of_week + 6) % 7], t.day_of_month, monate[(t.month + 11) % 12]);
  return b;
}

// Kalenderwoche nach ISO 8601 (Woche mit dem ersten Donnerstag ist KW 1), wie in deutschen Kalendern.
inline std::string kw(esphome::ESPTime t) {
  if (!t.is_valid()) return "KW --";
  int wd = (t.day_of_week + 5) % 7 + 1;   // ESPTime: 1 = Sonntag; hier 1 = Montag ... 7 = Sonntag
  int yday = t.day_of_year;               // 1 ... 366
  int week = (yday - wd + 10) / 7;
  int year = t.year;
  auto weeks_in = [](int y) {
    auto jan1 = [](int yy) {  // Wochentag des 1. Januar, 0 = Sonntag ... 4 = Donnerstag (Gauß)
      int y1 = yy - 1;
      return (1 + 5 * (y1 % 4) + 4 * (y1 % 100) + 6 * (y1 % 400)) % 7;
    };
    int d = jan1(y);
    bool leap = (y % 4 == 0 && y % 100 != 0) || y % 400 == 0;
    // 53 Wochen hat ein Jahr, das an einem Donnerstag beginnt, oder ein Schaltjahr, das an einem Mittwoch beginnt
    return (d == 4 || (leap && d == 3)) ? 53 : 52;
  };
  if (week < 1) week = weeks_in(year - 1);
  else if (week > weeks_in(year)) week = 1;
  char b[8];
  snprintf(b, sizeof(b), "KW %d", week);
  return b;
}

// Home Assistant schickt die Sonnenzeiten als Unix-Zeit (Sekunden).
inline std::string uhr_epoch(const std::string &s) {
  double v = numd(s);
  if (std::isnan(v) || v <= 0) return "--:--";
  auto t = esphome::ESPTime::from_epoch_local((time_t) v);
  char b[8];
  snprintf(b, sizeof(b), "%02d:%02d", t.hour, t.minute);
  return b;
}

// "vor 5 Std", "in 40 Min", "morgen": wann ein Sonnenereignis war oder ist. "andere" ist das andere Ereignis:
// liegt es näher, heißt dieses hier "morgen", sobald es nicht mehr heute ist.
inline std::string wann(const std::string &s, const std::string &andere, esphome::ESPTime jetzt) {
  double ts = numd(s), other = numd(andere);
  if (std::isnan(ts) || ts <= 0 || !jetzt.is_valid()) return "";
  double now = (double) jetzt.timestamp;
  long min = lround((ts - now) / 60.0);
  char b[32];
  if (min < 0) {
    min = -min;
    if (min < 60) snprintf(b, sizeof(b), "vor %ld Min", min);
    else snprintf(b, sizeof(b), "vor %ld Std", (min + 30) / 60);
    return b;
  }
  if (!std::isnan(other) && other > now && other < ts) {
    auto t = esphome::ESPTime::from_epoch_local((time_t) ts);
    if (t.day_of_year != jetzt.day_of_year) return "morgen";
  }
  if (min < 60) snprintf(b, sizeof(b), "in %ld Min", min < 1 ? 1 : min);
  else snprintf(b, sizeof(b), "in %ld Std", (min + 30) / 60);
  return b;
}

// Mondphase in 8 Stufen: 0 Neumond, 2 erstes Viertel, 4 Vollmond, 6 letztes Viertel.
// Mittlerer synodischer Monat ab dem Neumond am 6. Januar 2000, 18:14 UTC; genau auf etwa einen halben Tag.
inline int mondphase(time_t now) {
  const double monat = 29.530588853 * 86400.0;
  double phase = fmod((double) now - 947182440.0, monat) / monat;
  if (phase < 0) phase += 1;
  return (int) floor(phase * 8 + 0.5) % 8;
}

// ---------------------------------------------------------------- Temperaturkurve der 5 Tage

// hoch[d] ist das Tageshoch (Feld 2 von tag_d). Die Kurve läuft durch die 5 Punkte; zwischen zwei Tagen liegen
// SCHRITTE Stützpunkte (Catmull-Rom), damit sie rund aussieht. Koordinaten sind die der 5-Tage-Karte.
inline float hoch[5] = {NAN, NAN, NAN, NAN, NAN};
constexpr int SCHRITTE = 8;
constexpr float SPALTE = 39.2f, X0 = 16 + 39.2f / 2;  // 5 gleiche Spalten im Innenabstand von 16 px
constexpr float OBEN = 62, UNTEN = 88;                  // y für das wärmste und das kälteste Hoch

inline float wert(int d) {
  d = d < 0 ? 0 : d > 4 ? 4 : d;
  if (!std::isnan(hoch[d])) return hoch[d];
  for (int n = 1; n < 5; ++n) {  // fehlt ein Tag, den nächsten nehmen
    if (d - n >= 0 && !std::isnan(hoch[d - n])) return hoch[d - n];
    if (d + n <= 4 && !std::isnan(hoch[d + n])) return hoch[d + n];
  }
  return 0;
}
inline float y_von(float v) {
  float lo = wert(0), hi = wert(0);
  for (int d = 1; d < 5; ++d) {
    lo = fminf(lo, wert(d));
    hi = fmaxf(hi, wert(d));
  }
  float span = hi - lo < 1 ? 1 : hi - lo;
  return UNTEN - (v - lo) / span * (UNTEN - OBEN);
}
inline int punkt_x(int d) { return (int) lroundf(X0 + d * SPALTE); }
inline int punkt_y(int d) { return (int) lroundf(y_von(wert(d))); }
inline int kurve_x(int i) { return (int) lroundf(X0 + i * SPALTE / SCHRITTE); }
inline int kurve_y(int i) {
  int d = i / SCHRITTE;
  float t = float(i % SCHRITTE) / SCHRITTE;
  if (d >= 4) { d = 3; t = 1; }
  float p0 = y_von(wert(d - 1)), p1 = y_von(wert(d)), p2 = y_von(wert(d + 1)), p3 = y_von(wert(d + 2));
  float v = 0.5f * (2 * p1 + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t +
                    (-p0 + 3 * p1 - 3 * p2 + p3) * t * t * t);
  return (int) lroundf(v);
}

// ---------------------------------------------------------------- Warnungen des DWD

// Farbe nach Warnstufe: 1 gelb, 2 orange, 3 rot, 4 violett.
inline lv_color_t warn_color(int level) {
  if (level >= 4) return lv_color_hex(0x9B2FAE);
  if (level == 3) return lv_color_hex(0xE5322D);
  if (level == 2) return lv_color_hex(0xF08A24);
  return lv_color_hex(0xF2C230);
}
inline lv_color_t warn_text_color(int level) { return lv_color_hex(level <= 1 ? 0x3A2A00 : 0xFFFFFF); }

// Icon nach der Art der Warnung; der DWD nennt sie z. B. "STURMBÖEN", "STRENGER FROST", "GLÄTTE".
inline std::string warn_icon(std::string name) {
  for (auto &ch : name) ch = (char) toupper((unsigned char) ch);  // Umlaute bleiben, wie sie sind
  auto has = [&](const char *w) { return name.find(w) != std::string::npos; };
  if (has("FROST")) return "\U000F1A71";
  if (has("GLÄTTE") || has("GLATTEIS") || has("GLÄTT")) return "\U000F0D64";
  if (has("NEBEL")) return "\U000F0591";
  if (has("GEWITTER")) return "\U000F0593";
  if (has("BÖEN") || has("STURM") || has("ORKAN") || has("WIND")) return "\U000F059D";
  if (has("REGEN")) return "\U000F0596";
  if (has("SCHNEE")) return "\U000F0F36";
  if (has("HITZE")) return "\U000F18D6";
  return "\U000F0026";
}

}  // namespace wx
