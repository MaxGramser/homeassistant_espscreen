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
// Mit einer Nachkommastelle und deutschem Komma: "11,4°" (Hoch und Tief im Panel)
inline std::string deg1(const std::string &s) {
  float v = num(s);
  if (std::isnan(v)) return "--°";
  char b[16];
  snprintf(b, sizeof(b), "%.1f°", v);
  std::string r = strcmp(b, "-0.0°") == 0 ? std::string("0.0°") : std::string(b);
  size_t p = r.find('.');
  if (p != std::string::npos) r[p] = ',';
  return r;
}

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


// Die Pille unter dem Wetterbild: eine Warnung gefüllt in der Farbe der Stufe, sonst eine Vorwarnung nur mit Rand.
// w und v sind die Attribute "warnung" und "vorwarnung" ("Stufe;Text;DWD-Name"). Passt der Text nicht in max_w,
// läuft er als Lauftext durch. Gibt zurück, ob die Pille zu sehen ist.
inline bool warn_pille(lv_obj_t *pille, lv_obj_t *icon, lv_obj_t *text, const std::string &w, const std::string &v,
                       int max_w) {
  bool warnung = num(part(w, 0)) >= 1;
  const std::string &q = warnung ? w : v;
  int stufe = (int) num(part(q, 0));
  if (!warnung && !(stufe >= 1)) {
    lv_obj_add_flag(pille, LV_OBJ_FLAG_HIDDEN);
    return false;
  }
  lv_color_t farbe = warn_color(stufe);
  if (warnung) {
    lv_obj_set_style_bg_opa(pille, LV_OPA_COVER, LV_PART_MAIN);
    lv_obj_set_style_bg_color(pille, farbe, LV_PART_MAIN);
    lv_obj_set_style_border_width(pille, 0, LV_PART_MAIN);
    lv_obj_set_style_text_color(icon, warn_text_color(stufe), LV_PART_MAIN);
    lv_obj_set_style_text_color(text, warn_text_color(stufe), LV_PART_MAIN);
  } else {
    lv_obj_set_style_bg_opa(pille, LV_OPA_TRANSP, LV_PART_MAIN);
    lv_obj_set_style_border_width(pille, 2, LV_PART_MAIN);
    lv_obj_set_style_border_color(pille, farbe, LV_PART_MAIN);
    lv_obj_set_style_text_color(icon, farbe, LV_PART_MAIN);
    lv_obj_set_style_text_color(text, lv_color_hex(0xFFFFFF), LV_PART_MAIN);
  }
  lv_label_set_text(icon, warn_icon(part(q, 2)).c_str());
  lv_label_set_text(text, part(q, 1).c_str());
  lv_point_t sz;
  lv_text_get_size(&sz, lv_label_get_text(text), lv_obj_get_style_text_font(text, LV_PART_MAIN), 0, 0, LV_COORD_MAX,
                   LV_TEXT_FLAG_NONE);
  lv_obj_set_width(text, sz.x > max_w ? max_w : LV_SIZE_CONTENT);
  lv_obj_remove_flag(pille, LV_OBJ_FLAG_HIDDEN);
  return true;
}

// ---------------------------------------------------------------- Tag und Nacht, das große Bild

// Tag (helles Design, Wetterbild mit Sonne), solange die Sonne über dem Horizont steht, und schon ab 30 Minuten
// vor dem Aufgang. Nachts ist Feld 0 von "sonne" der nächste Aufgang. Solange sun.sun nichts gemeldet hat: Tag.
inline bool ist_tag(const std::string &sonne_stand, const std::string &sonne, esphome::ESPTime jetzt) {
  if (sonne_stand != "below_horizon") return true;
  double auf = numd(part(sonne, 0));
  if (std::isnan(auf) || !jetzt.is_valid()) return false;
  return (double) jetzt.timestamp >= auf - 30 * 60;
}

// Das große Wetterbild ist ohne Warnung voll groß (Skala 256) und wird kleiner, sobald darunter eine Warnung steht.
// Es wächst und schrumpft um seine rechte obere Ecke; das kleine Bild auf dem Mond geht mit.
inline lv_obj_t *bild_gross_obj = nullptr;
inline lv_obj_t *bild_klein_obj = nullptr;
inline int32_t bild_skala = 256;
inline void bild_skala_setzen(void *, int32_t v) {
  bild_skala = v;
  if (bild_gross_obj) lv_image_set_scale(bild_gross_obj, v);
  if (bild_klein_obj) lv_image_set_scale(bild_klein_obj, v);
}
// px: x der rechten Kante der Zeichnung im großen Bild; off: Lage des kleinen Bildes im großen (x und y)
inline void bild_skalieren(lv_obj_t *gross, lv_obj_t *klein, int px, int off, int32_t ziel) {
  if (bild_gross_obj == nullptr) {
    bild_gross_obj = gross;
    bild_klein_obj = klein;
    lv_image_set_pivot(gross, px, 0);
    lv_image_set_pivot(klein, px - off, -off);
  }
  if (ziel == bild_skala) return;
  lv_anim_t a;
  lv_anim_init(&a);
  lv_anim_set_var(&a, gross);
  lv_anim_set_values(&a, bild_skala, ziel);
  lv_anim_set_duration(&a, 400);
  lv_anim_set_exec_cb(&a, bild_skala_setzen);
  lv_anim_set_path_cb(&a, lv_anim_path_ease_in_out);
  lv_anim_start(&a);
}

// ---------------------------------------------------------------- Raumklima (zweite Seite)

// Die Seite Raumklima gibt es erst, wenn mindestens ein Raum einen CO2-Wert hat.
inline bool innen_da(float a, float b, float c) { return !std::isnan(a) || !std::isnan(b) || !std::isnan(c); }

// CO2-Trend je Raum: alle 5 Minuten ein Wert, der älteste ist 15 Minuten alt. Ab 50 ppm Unterschied steigt oder
// fällt er. 0: noch keine 15 Minuten Werte, 1: steigt, -1: fällt, 2: stabil.
inline float co2_alt[3][4] = {{NAN, NAN, NAN, NAN}, {NAN, NAN, NAN, NAN}, {NAN, NAN, NAN, NAN}};
inline void co2_merken(int r, float v) {
  for (int i = 0; i < 3; ++i) co2_alt[r][i] = co2_alt[r][i + 1];
  co2_alt[r][3] = v;
}
inline int co2_trend(int r) {
  float a = co2_alt[r][0], b = co2_alt[r][3];
  if (std::isnan(a) || std::isnan(b)) return 0;
  float d = b - a;
  return d >= 50 ? 1 : d <= -50 ? -1 : 2;
}
inline std::string trend_icon(int t) {
  return t == 1 ? "\U000F005D" : t == -1 ? "\U000F0045" : t == 2 ? "\U000F0054" : "";
}
inline lv_color_t trend_color(int t) {
  return lv_color_hex(t == 1 ? 0xFFB25B : t == -1 ? 0x7DD39A : 0xB9CFC2);
}


// CO2 in ppm nach der Skala von ELV: 0 Hervorragend, 1 Gut, 2 Befriedigend, 3 Mittel (Lüften empfohlen),
// 4 Schlecht (Lüften erforderlich). Die Grenzen liegen in der Mitte zwischen den Hunderterstufen der Skala.
// -1 heißt: kein Wert.
inline int co2_stufe(float ppm) {
  if (std::isnan(ppm)) return -1;
  if (ppm < 650) return 0;
  if (ppm < 850) return 1;
  if (ppm < 1050) return 2;
  if (ppm < 1550) return 3;
  return 4;
}
inline std::string co2_name(int s) {
  static const char *const n[] = {"Hervorragend", "Gut", "Befriedigend", "Mittel", "Schlecht"};
  return s < 0 ? std::string("--") : std::string(n[s > 4 ? 4 : s]);
}
inline uint32_t co2_hex(int s) {
  static const uint32_t c[] = {0x1E7A3C, 0x2E9E4F, 0x7DBB42, 0xF2C230, 0xE8542C};
  return s < 0 ? 0x5F6B80 : c[s > 4 ? 4 : s];
}
inline lv_color_t co2_color(int s) { return lv_color_hex(co2_hex(s)); }
inline lv_color_t co2_text_color(int s) { return lv_color_hex(s == 3 ? 0x3A2A00 : 0xFFFFFF); }
// Skala von 400 bis 2000 ppm über "breite" Pixel; gibt die linke Kante des 12 px breiten Markers zurück.
inline int co2_marker_x(float ppm, int breite) {
  float f = std::isnan(ppm) ? 0 : (ppm - 400.0f) / 1600.0f;
  f = f < 0 ? 0 : f > 1 ? 1 : f;
  return (int) lroundf(f * breite) - 6;
}

// Zahl mit Komma, z. B. 21,4
inline std::string komma(float v, int stellen = 1) {
  if (std::isnan(v)) return "--";
  char b[16];
  snprintf(b, sizeof(b), "%.*f", stellen, v);
  std::string out = strcmp(b, "-0.0") == 0 ? std::string("0.0") : std::string(b);
  size_t dot = out.find('.');
  if (dot != std::string::npos) out[dot] = ',';
  return out;
}

// Relative Luftfeuchte nach dem Umweltbundesamt: 40 bis 60 % ideal (grün), 30 bis 40 und 60 bis 70 % gelb,
// darunter zu trocken und darüber Schimmelgefahr (rot).
inline lv_color_t feuchte_color(float v) {
  if (std::isnan(v)) return lv_color_hex(0x5F6B80);
  if (v >= 40 && v <= 60) return lv_color_hex(0x2E9E4F);
  if (v >= 30 && v <= 70) return lv_color_hex(0xD9A400);
  return lv_color_hex(0xE8542C);
}

// Feinstaub in µg/m³: PM1 und PM2.5 nach den Grenzen für PM2.5 (gut bis 15, mäßig bis 25), PM4 und PM10 nach
// denen für PM10 (gut bis 45, mäßig bis 80). Gibt 0 gut, 1 mäßig, 2 schlecht zurück.
inline int pm_stufe(float v, bool grob) {
  if (std::isnan(v)) return 0;
  float g1 = grob ? 45 : 15, g2 = grob ? 80 : 25;
  return v <= g1 ? 0 : v <= g2 ? 1 : 2;
}
// VOC-Index (Sensirion, 1 bis 500): normal bis 150, erhöht bis 250, hoch darüber.
// NOx-Index (1 bis 500): normal bis 20, erhöht bis 150, hoch darüber.
inline int voc_stufe(float v) { return std::isnan(v) ? 0 : v <= 150 ? 0 : v <= 250 ? 1 : 2; }
inline int nox_stufe(float v) { return std::isnan(v) ? 0 : v <= 20 ? 0 : v <= 150 ? 1 : 2; }
inline std::string gas_name(int s) { return s == 0 ? "normal" : s == 1 ? "erhöht" : "hoch"; }
// Ampelfarben der Balken: grün, gelb/orange, rot. "gelb" für Feinstaub (mäßig), orange für die Gase (erhöht).
inline lv_color_t ampel(int s, bool gelb = true) {
  if (s <= 0) return lv_color_hex(0x2E9E4F);
  if (s == 1) return lv_color_hex(gelb ? 0xF2C230 : 0xF08A24);
  return lv_color_hex(0xE8542C);
}
inline int balken(float v, float voll) {
  if (std::isnan(v) || voll <= 0) return 0;
  float f = v / voll * 100;
  return f < 0 ? 0 : f > 100 ? 100 : (int) lroundf(f);
}


// ---------------------------------------------------------------- Hunderunde (Easter Egg, Doppeltipp)
// Der Text kommt aus Home Assistant: "icon;klein;groß;slots;tipp;plan;jetzt" (home-assistant/wetter_display.yaml).
inline void sichtbar(lv_obj_t *o, bool an) {
  if (an) lv_obj_clear_flag(o, LV_OBJ_FLAG_HIDDEN);
  else lv_obj_add_flag(o, LV_OBJ_FLAG_HIDDEN);
}
inline uint32_t hund_farbe(char c) {
  switch (c) {
    case 't': return 0xFFD27A;   // trocken
    case 'n': return 0x5FA8FF;   // nass
    case 'h': return 0xFF7A45;   // heiß (ab 25 °C)
    default: return 0x5E7F6E;    // keine Vorhersage (vergangene Stunden)
  }
}
// Tagesstreifen 6 bis 22 Uhr: 16 Felder, die Stunden vor jetzt blass; der Strich steht auf der aktuellen Minute
inline void hund_streifen(const std::string &x, lv_obj_t *const *feld, lv_obj_t *strich, int x0, int breite,
                          int minute) {
  std::string plan = part(x, 5);
  std::string j = part(x, 6);
  int jetzt = j.empty() ? -1 : atoi(j.c_str());
  for (int i = 0; i < 16; i++) {
    char c = i < (int) plan.size() ? plan[i] : '-';
    lv_obj_set_style_bg_color(feld[i], lv_color_hex(hund_farbe(c)), 0);
    lv_obj_set_style_bg_opa(feld[i], (jetzt >= 0 && i < jetzt) ? LV_OPA_40 : LV_OPA_COVER, 0);
  }
  bool an = jetzt >= 0 && jetzt < 16;
  sichtbar(strich, an);
  if (an) lv_obj_set_x(strich, x0 + (jetzt * 60 + minute) * breite / (16 * 60) - 1);
}

// Der Hund springt beim Öffnen zweimal kurz hoch; sein Schatten wird schmaler, solange er in der Luft ist
inline int hund_schatten_mitte = 0;
inline void hund_y_setzen(void *o, int32_t v) { lv_obj_set_y((lv_obj_t *) o, v); }
inline void hund_schatten_setzen(void *o, int32_t w) {
  lv_obj_set_width((lv_obj_t *) o, w);
  lv_obj_set_x((lv_obj_t *) o, hund_schatten_mitte - w / 2);
}
inline void hund_huepfen(lv_obj_t *hund, int y0, lv_obj_t *schatten, int sx0, int sw0) {
  lv_anim_delete(hund, hund_y_setzen);
  lv_anim_delete(schatten, hund_schatten_setzen);
  lv_obj_set_y(hund, y0);
  lv_obj_set_width(schatten, sw0);
  lv_obj_set_x(schatten, sx0);
  hund_schatten_mitte = sx0 + sw0 / 2;
  for (int k = 0; k < 2; k++) {
    lv_anim_t a;
    lv_anim_init(&a);
    if (k == 0) {
      lv_anim_set_var(&a, hund);
      lv_anim_set_values(&a, y0, y0 - 14);
      lv_anim_set_exec_cb(&a, hund_y_setzen);
    } else {
      lv_anim_set_var(&a, schatten);
      lv_anim_set_values(&a, sw0, sw0 - 40);
      lv_anim_set_exec_cb(&a, hund_schatten_setzen);
    }
    lv_anim_set_duration(&a, 180);
    lv_anim_set_reverse_duration(&a, 180);
    lv_anim_set_repeat_count(&a, 2);
    lv_anim_set_delay(&a, 150);
    lv_anim_set_path_cb(&a, lv_anim_path_ease_out);
    lv_anim_start(&a);
  }
}

}  // namespace wx
