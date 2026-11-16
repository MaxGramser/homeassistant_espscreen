#pragma once
// Hilfsfunktionen für das Wetter-Dashboard (wetter-display.yaml).
// Home Assistant liefert jeden Vorhersage-Tag und jede Stunde als einen Text mit Semikolons
// (siehe home-assistant/wetter_display.yaml); hier wird er zerlegt und in Icon, Farbe und Text übersetzt.
#include <cmath>
#include <cstdio>
#include <string>
#include <lvgl.h>
#include "esphome/core/time.h"

namespace wx {

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
  if (s.empty() || s == "None" || s == "unknown") return NAN;
  char *end = nullptr;
  float v = strtof(s.c_str(), &end);
  return end == s.c_str() ? NAN : v;
}

// Material Design Icons, dieselben wie im Home-Assistant-Frontend.
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
  return "\U000F0590";
}

inline lv_color_t color(const std::string &c) {
  if (c == "sunny") return lv_color_hex(0xFFC53D);
  if (c == "clear-night") return lv_color_hex(0xB9C3FF);
  if (c == "partlycloudy") return lv_color_hex(0xFFD98A);
  if (c == "rainy" || c == "pouring") return lv_color_hex(0x5AAEFF);
  if (c == "lightning" || c == "lightning-rainy") return lv_color_hex(0xFFB020);
  if (c == "snowy" || c == "snowy-rainy" || c == "hail") return lv_color_hex(0xE6F2FF);
  if (c == "windy" || c == "windy-variant") return lv_color_hex(0x8FD6C9);
  if (c == "exceptional") return lv_color_hex(0xFF7A6B);
  return lv_color_hex(0xB4C2D3);
}

// Die Wörter, die Home Assistant auf Deutsch zeigt.
inline std::string text(const std::string &c) {
  if (c == "sunny") return "Sonnig";
  if (c == "clear-night") return "Klare Nacht";
  if (c == "partlycloudy") return "Teilweise bewölkt";
  if (c == "cloudy") return "Bewölkt";
  if (c == "fog") return "Nebel";
  if (c == "hail") return "Hagel";
  if (c == "lightning") return "Gewitter";
  if (c == "lightning-rainy") return "Gewitter mit Regen";
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

inline std::string deg(float v) {
  if (std::isnan(v)) return "--°";
  char b[12];
  snprintf(b, sizeof(b), "%.0f°", v);
  // "-0°" sieht falsch aus
  return std::string(b) == "-0°" ? "0°" : std::string(b);
}
inline std::string deg(const std::string &s) { return deg(num(s)); }

inline std::string percent(float v) {
  if (std::isnan(v)) return "--";
  char b[12];
  snprintf(b, sizeof(b), "%.0f %%", v);
  return b;
}

// Regen: die Wahrscheinlichkeit, wenn der Wetterdienst sie liefert (DWD, OpenWeatherMap ...), sonst die Menge (Met.no).
inline std::string rain(const std::string &probability, const std::string &mm) {
  float p = num(probability), m = num(mm);
  char b[16];
  if (!std::isnan(p)) {
    snprintf(b, sizeof(b), "%.0f %%", p);
    return b;
  }
  if (!std::isnan(m)) {
    if (m < 0.05f) return "0 mm";
    snprintf(b, sizeof(b), m < 10 ? "%.1f mm" : "%.0f mm", m);
    std::string out = b;
    size_t dot = out.find('.');
    if (dot != std::string::npos) out[dot] = ',';
    return out;
  }
  return "--";
}

inline std::string wind(float speed, float bearing) {
  if (std::isnan(speed)) return "--";
  static const char *const dirs[] = {"N", "NO", "O", "SO", "S", "SW", "W", "NW"};
  char b[24];
  if (std::isnan(bearing)) {
    snprintf(b, sizeof(b), "%.0f km/h", speed);
  } else {
    int i = (int) lroundf(fmodf(bearing + 360.0f, 360.0f) / 45.0f) % 8;
    snprintf(b, sizeof(b), "%.0f km/h %s", speed, dirs[i]);
  }
  return b;
}

inline std::string uhrzeit(esphome::ESPTime t) {
  if (!t.is_valid()) return "--:--";
  char b[8];
  snprintf(b, sizeof(b), "%02d:%02d", t.hour, t.minute);
  return b;
}

inline std::string datum(esphome::ESPTime t) {
  if (!t.is_valid()) return "";
  static const char *const tage[] = {"Sonntag", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag"};
  static const char *const monate[] = {"Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                                        "August", "September", "Oktober", "November", "Dezember"};
  char b[48];
  snprintf(b, sizeof(b), "%s, %d. %s", tage[(t.day_of_week + 6) % 7], t.day_of_month, monate[(t.month + 11) % 12]);
  return b;
}

}  // namespace wx
