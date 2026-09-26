#pragma once
// Every colour the screens choose themselves, in one table (firmware 0.2.54+).
//
// A role is what a colour is for: the page, a card, the text on it, a key under a finger. Each role has its light value,
// the look the screens have always had, and its dark value, for a screen beside a bed: a black page, graphite cards,
// soft white text, and the colours of Home Assistant's states where they matter. Nothing else in the firmware or in the
// board profiles writes a colour of its own; the profiles name a paint (a shared LVGL style filled from this table) and
// the firmware asks for a role. docs/THEME.md is the recipe for a new colour.
//
// Home Assistant's state colours (the amber of a light that is on, the orange of heating) are not roles: they are data
// and pass through state() on their way to the glass. The values below are free of LVGL, so tests/test_theme.cpp checks
// the table and the contrast of both looks on a PC; the LVGL half is behind THEME_TEST.
#include <cstddef>
#include <cstdint>
#include <string>

namespace theme {

enum Role : uint8_t {
  // ---- surfaces
  PAGE,                 // the page behind the tiles, every card and the settings
  PAGE_SOFT,            // the page of the light's colour controls, a shade lighter
  PAGE_PRESSED,         // the Previous and Next bars under a finger
  CARD,                 // tiles, cards, rows, the alert
  CARD_PRESSED,         // a settings row under a finger
  LINE,                 // the hairline around a card
  RAISED,               // a card above everything else: the alert
  RAISED_LINE,
  KEY,                  // round keys (back, close), a white key under a finger
  KEY_PRESSED,          // a round key under a finger
  TRACK,                // segment tracks and grey keys inside a card, an unavailable tile's circle, empty history
  GRID,                 // the lines across a history graph
  TICK,                 // the small marks under a history graph
  BUTTON,               // the plain keys of a simple card (select options, media, timer)
  SETTING_KEY,          // -/+ keys and choice chips on the settings page
  SETTING_KEY_PRESSED,
  TOGGLE_OFF,           // a switch on the settings page while off
  SWITCH_OFF,           // the switch on a history card while off
  PANEL_TOGGLE_OFF,     // the toggle on a wide tile while off
  PANEL_TOGGLE_OFF_PRESSED,
  KNOB,                 // handles and knobs
  STEPPER_KEY,          // the - and + keys inside a thermostat's or a number's grey stepper (firmware 0.3.3)
  STEPPER_KEY_PRESSED,
  SLIDER_KNOB,          // the round knob of a card's number or volume slider
  SCRIM,                // behind an alert
  VEIL,                 // the sheet over a busy tile, the haze over the value card
  SPINNER_TRACK,        // the ring of the busy spinner
  // ---- text
  INK,                  // names, values, words on keys
  INK_SOFT,             // the alert's second line
  MUTED,                // secondary words: states, times beside a value
  SUBTLE,               // quiet words: axis labels, notes, "Target"
  SLATE,                // the top bar, units, a value on a coloured card, mode key icons
  ROW_ICON,             // icons at the start of a settings row
  CHEVRON,              // the arrow at the end of a settings row
  OFF,                  // something that is off: its icon, its circle and the fill of its slider
  ON_ACCENT,            // words and icons on a blue key and on the alert's key
  // ---- keys that stand out
  ACCENT,               // the screen's own blue: a chosen segment, the main key, a switch that is on
  ACCENT_PRESSED,
  ACCENT_BRIGHT,        // the value card's fill and a chosen climate chip
  ACCENT_TINT,          // pale blue: a choice under a finger, the value card's track, climate power on
  ACCENT_ICON,          // the climate power icon while on
  ICON_OFF,             // the climate power icon while off
  BUTTON_DARK,          // the alert's key
  BUTTON_DARK_PRESSED,
  // ---- drawings
  ROBOT_BODY,           // the vacuum seen from above
  ROBOT_RIM,
  ROBOT_TOP,
  ROBOT_LENS,
  BATTERY,              // a battery's outline and cap
  SUN_PATH,             // the arc the sun travels
  MOON,                 // the sun below the horizon
  AMBER_TRACK,          // the track of a light's brightness slider
  HISTORY_OFF,          // an off or away stretch on a timeline (the add-on's CFCFCF)
  HISTORY_EMPTY,        // a stretch without data on a timeline (the add-on's E6E6E6)
  // ---- a camera image: dark in both looks, like a photo viewer (firmware 0.2.57+)
  CAMERA_PAGE,          // behind the image full screen and in the alert's image frame
  CAMERA_INK,           // the camera's name over the image
  CAMERA_NOTE,          // "No image from this camera"
  CAMERA_TRACK,         // the ring of the spinner while the first image loads (firmware 0.2.73+)
  // ---- the CYD's touch calibration: dark in both looks, a yellow crosshair
  CALIBRATION_PAGE,
  CALIBRATION_INK,
  CALIBRATION_MARK,
  ROLE_COUNT
};

struct Pair { uint32_t light, dark; };

// light: the design as it always was. dark: RGB565-friendly values (a grey whose red, green and blue land on the same
// step of the panel), so dark greys stay neutral on both boards instead of turning green.
inline constexpr Pair ROLES[ROLE_COUNT] = {
  /* PAGE */                     {0xE7E7E7, 0x000000},
  /* PAGE_SOFT */                {0xF8F8F8, 0x101010},
  /* PAGE_PRESSED */             {0xE3E3E3, 0x1A1A1A},
  /* CARD */                     {0xFFFFFF, 0x1A1A1A},
  /* CARD_PRESSED */             {0xF1F1F1, 0x2A2A2A},
  /* LINE */                     {0xDDDDDD, 0x292929},
  /* RAISED */                   {0xFFFFFF, 0x282828},
  /* RAISED_LINE */              {0xDDDDDD, 0x393939},
  /* KEY */                      {0xEEEEEE, 0x2A2A2A},
  /* KEY_PRESSED */              {0xDDDDDD, 0x3A3A3A},
  /* TRACK */                    {0xF1F1F1, 0x2A2A2A},
  /* GRID */                     {0xEEEEEE, 0x292929},
  /* TICK */                     {0xCCCCCC, 0x4A4A4A},
  /* BUTTON */                   {0xD9E6F0, 0x222B32},
  /* SETTING_KEY */              {0xE9EFF4, 0x2A2F34},
  /* SETTING_KEY_PRESSED */      {0xC3D5E3, 0x3A4652},
  /* TOGGLE_OFF */               {0xC4C4C4, 0x484848},
  /* SWITCH_OFF */               {0xB0B0B0, 0x484848},
  /* PANEL_TOGGLE_OFF */         {0xD7DADF, 0x393C41},
  /* PANEL_TOGGLE_OFF_PRESSED */ {0xC5C9CF, 0x494D52},
  /* KNOB */                     {0xFFFFFF, 0xE8E8E8},
  /* STEPPER_KEY */              {0xFFFFFF, 0x3A3A3A},
  /* STEPPER_KEY_PRESSED */      {0xE4E4E4, 0x4A4A4A},
  /* SLIDER_KNOB */              {0x111111, 0xE8E8E8},
  /* SCRIM */                    {0x101820, 0x000000},
  /* VEIL */                     {0xFFFFFF, 0x1A1A1A},
  /* SPINNER_TRACK */            {0xD9DDE2, 0x393D42},
  /* INK */                      {0x1B1B1B, 0xDADADA},
  /* INK_SOFT */                 {0x3A3A3C, 0xBABABA},
  /* MUTED */                    {0x616161, 0x999999},
  /* SUBTLE */                   {0x6B6B6B, 0x8A8A8A},
  /* SLATE */                    {0x46525E, 0x9AA6B2},
  /* ROW_ICON */                 {0x4A4A4A, 0xB8B8B8},
  /* CHEVRON */                  {0xB0B0B0, 0x5A5A5A},
  /* OFF */                      {0x9E9E9E, 0x787878},
  /* ON_ACCENT */                {0xFFFFFF, 0xFFFFFF},
  /* ACCENT */                   {0x009FE3, 0x0A93D2},
  /* ACCENT_PRESSED */           {0x0075B0, 0x0A6FA3},
  /* ACCENT_BRIGHT */            {0x00A6ED, 0x0A9ADB},
  /* ACCENT_TINT */              {0xD5EEFC, 0x12384A},
  /* ACCENT_ICON */              {0x0B6E99, 0x6CCBF5},
  /* ICON_OFF */                 {0x8A8A8A, 0x7A7A7A},
  /* BUTTON_DARK */              {0x1B1B1B, 0x484848},
  /* BUTTON_DARK_PRESSED */      {0x3A3A3C, 0x585858},
  /* ROBOT_BODY */               {0xFFFFFF, 0x383D42},
  /* ROBOT_RIM */                {0xCEDDE6, 0x5A6972},
  /* ROBOT_TOP */                {0xE3EBEF, 0x4A5358},
  /* ROBOT_LENS */               {0xA8BCC8, 0x7E93A1},
  /* BATTERY */                  {0x7D858D, 0x8C959D},
  /* SUN_PATH */                 {0xCFD8DC, 0x3E494E},
  /* MOON */                     {0xB0BEC5, 0x90A4AE},
  /* AMBER_TRACK */              {0xFDEFC3, 0x483B16},
  /* HISTORY_OFF */              {0xCFCFCF, 0x4A4A4A},
  /* HISTORY_EMPTY */            {0xE6E6E6, 0x2A2A2A},
  /* CAMERA_PAGE */              {0x000000, 0x000000},
  /* CAMERA_INK */               {0xF2F2F2, 0xDADADA},
  /* CAMERA_NOTE */              {0x9E9E9E, 0x8A8A8A},
  /* CAMERA_TRACK */             {0x393D42, 0x393D42},
  /* CALIBRATION_PAGE */         {0x101820, 0x101820},
  /* CALIBRATION_INK */          {0xFFFFFF, 0xFFFFFF},
  /* CALIBRATION_MARK */         {0xFFD34D, 0xFFD34D},
};

// The look on screen. The board sets it through set_dark() (below) from the Dark mode setting; the table and the
// helpers only read it.
inline bool dark = false;
inline uint32_t hex(Role role) { return dark ? ROLES[role].dark : ROLES[role].light; }

// ---- mixing, exactly as LVGL 9 mixes two colours (lv_color_mix), so a value here is the value on the glass
inline uint32_t mix(uint32_t first, uint32_t second, uint8_t amount) {
  uint32_t out = 0;
  for (int shift = 16; shift >= 0; shift -= 8) {
    const uint32_t a = first >> shift & 0xFF, b = second >> shift & 0xFF;
    out |= (((a * amount + b * (255 - amount)) * 0x8081U) >> 23) << shift;
  }
  return out;
}

// ---- named card colours: what a tile's background or an alert's colour can be
// The add-on sends a name; a tile keeps the light value as the colour's identity (tile_palette.h), and surface() turns it
// into what this look draws. Light: the pastels chosen for dark text. Dark: the same hue deep enough for light text.
struct Swatch { const char *name; uint32_t light, dark; };
inline constexpr Swatch SWATCHES[] = {
  {"red", 0xFADADD, 0x4A2422},
  {"orange", 0xFFE1C6, 0x472F17},
  {"yellow", 0xFFF0C2, 0x3E3516},
  {"green", 0xD9EEDC, 0x243A26},
  {"mint", 0xD5F0EA, 0x163631},
  {"blue", 0xD9EAFB, 0x1C3448},
  {"purple", 0xE9DDF5, 0x342C40},
  {"pink", 0xF7DDEC, 0x46202E},
  {"gray", 0xE5E7EB, 0x2A2D32},
};
inline constexpr size_t SWATCH_COUNT = sizeof(SWATCHES) / sizeof(SWATCHES[0]);
inline uint32_t swatch(const std::string &name) {
  for (const auto &s : SWATCHES) if (name == s.name) return s.light;
  return 0;
}
// The same names on an alert's button (firmware 0.3.3+): a full key colour instead of a pastel, so a green Accept and a
// red Decline stand out on any card. Like Home Assistant's state colours they are the same in both looks; the words on
// them are white, or ink on the light ones (yellow), whichever reads.
struct KeySwatch { const char *name; uint32_t key, text; };
inline constexpr KeySwatch KEY_SWATCHES[] = {
  {"red", 0xD93A30, 0xFFFFFF},
  {"orange", 0xEF7D14, 0xFFFFFF},
  {"yellow", 0xF6C433, 0x1B1B1B},
  {"green", 0x3C9A4A, 0xFFFFFF},
  {"mint", 0x13897B, 0xFFFFFF},
  {"blue", 0x1F7FD6, 0xFFFFFF},
  {"purple", 0x7B55BE, 0xFFFFFF},
  {"pink", 0xD3437E, 0xFFFFFF},
  {"gray", 0x6B7078, 0xFFFFFF},
};
// The key colour of a name, 0 for none or an unknown one (the button keeps its own paint).
inline uint32_t key_swatch(const std::string &name) {
  for (const auto &s : KEY_SWATCHES) if (name == s.name) return s.key;
  return 0;
}
inline uint32_t key_text(uint32_t key) {
  for (const auto &s : KEY_SWATCHES) if (key == s.key) return s.text;
  return 0xFFFFFF;
}
// The key under a finger: a little darker, in both looks.
inline uint32_t key_pressed(uint32_t key) { return mix(key, 0x000000, 210); }
// A card's own colour (a swatch's light value, or 0 for none) as this look draws it.
inline uint32_t surface(uint32_t own) {
  if (!own) return hex(CARD);
  if (!dark) return own;
  for (const auto &s : SWATCHES) if (s.light == own) return s.dark;
  return hex(CARD);
}
// The hairline around a card: the card's own colour a little darker in light, a little lighter in dark.
inline uint32_t outline(uint32_t own) {
  if (!own) return hex(LINE);
  return dark ? mix(surface(own), 0xFFFFFF, 232) : mix(own, 0x000000, 220);
}

// ---- Home Assistant's state colours
// What a state looks like in Home Assistant's frontend (its --state-*-color and --*-color variables), the same in both
// looks: an amber light is amber at night too. They are data, drawn through state(), foreground(), tint() and icon().
namespace ha {
constexpr uint32_t AMBER = 0xFFC107;         // on: a light, switch, running script or timer, streaming camera; the sun; lux
constexpr uint32_t ORANGE = 0xFF9800;        // a paused robot, drying, a battery half full, the sun path by day
constexpr uint32_t DEEP_ORANGE = 0xFF6F22;   // temperature, heating
constexpr uint32_t RED = 0xF44336;           // an alarm going off, a robot in trouble, an empty battery
constexpr uint32_t PURPLE = 0x926BC7;        // covers, scenes, energy
constexpr uint32_t DEEP_PURPLE = 0x6E41AB;   // a clear night
constexpr uint32_t INDIGO = 0x3F51B5;        // selects, the sun below the horizon, pouring rain
constexpr uint32_t BLUE = 0x2196F3;          // cooling, rain, a robot on its way back, someone in a zone, everything else
constexpr uint32_t LIGHT_BLUE = 0x03A9F4;    // media players, sleet
constexpr uint32_t CYAN = 0x00BCD4;          // fans, hail
constexpr uint32_t TEAL = 0x009688;          // numbers, percentages, a robot at work
constexpr uint32_t GREEN = 0x4CAF50;         // someone at home, auto mode, wind, a full battery
constexpr uint32_t GREY = 0x9E9E9E;          // anything off or away, fog
// The rest of the weather, as Home Assistant colours a condition (--state-weather-*-color): clouds, a partly
// cloudy sky, lightning, lightning with rain, and snow, which Home Assistant writes as a value of its own.
constexpr uint32_t LIGHT_GREY = 0xBDBDBD, BLUE_GREY = 0x607D8B, YELLOW = 0xFFEB3B, LIME = 0xCDDC39, ICE = 0xC0E0FF;
constexpr uint32_t SKY = 0x00A6ED;           // a robot that is docked or idle
constexpr uint32_t SWITCH_ON = 0xFFB900;     // the switch on a history card while on
constexpr uint32_t PURPLE_PRESSED = 0x7552A8;  // a chosen cover key under a finger
// The weather card's conditions and the sun card.
constexpr uint32_t SUNNY = 0xFFB300, RAIN = 0x1E88E5, SNOW = 0x4FC3F7, LIGHTNING = 0xFFA000;
constexpr uint32_t PARTLY_CLOUDY = 0x7E9BB5, CLOUDY = 0x78909C, NIGHT_SKY = 0x5C6BC0;
// Warnings and good news drawn on a card: a low battery, the analog clock's second hand; charging.
constexpr uint32_t ALARM = 0xE53935, CHARGING = 0x43A047;
}  // namespace ha

// ---- Home Assistant's colours on their way to the glass
// Grey is what Home Assistant draws for something off; the add-on's timelines add a lighter grey for off and one for no
// data. In dark those greys come from the table; every other state colour stays itself.
// A temperature as a colour, from Home Assistant's own hues: indigo in a frost, blue and cyan in the cold, green in
// the mild, amber and orange in the warm, red in a heatwave. The weather tile draws a day's range from its low to its
// high in these (firmware 0.3.3), so a cold day reads as a cold day before the digits do. Degrees Celsius.
inline uint32_t temperature(float celsius) {
  struct Stop { float at; uint32_t color; };
  static constexpr Stop STOPS[] = {{-5, ha::INDIGO}, {5, ha::BLUE}, {11, ha::CYAN}, {16, ha::GREEN},
                                   {20, ha::AMBER}, {25, ha::ORANGE}, {32, ha::RED}};
  if (!(celsius > STOPS[0].at)) return STOPS[0].color;
  for (size_t i = 1; i < sizeof(STOPS) / sizeof(STOPS[0]); ++i) {
    if (celsius > STOPS[i].at) continue;
    const float share = (celsius - STOPS[i - 1].at) / (STOPS[i].at - STOPS[i - 1].at);
    return mix(STOPS[i].color, STOPS[i - 1].color, static_cast<uint8_t>(share * 255 + 0.5f));
  }
  return STOPS[sizeof(STOPS) / sizeof(STOPS[0]) - 1].color;
}

constexpr uint32_t STATE_OFF = ha::GREY;
inline uint32_t state(uint32_t color) {
  if (!dark) return color;
  if (color == STATE_OFF) return ROLES[OFF].dark;
  if (color == ROLES[HISTORY_OFF].light) return ROLES[HISTORY_OFF].dark;
  if (color == ROLES[HISTORY_EMPTY].light) return ROLES[HISTORY_EMPTY].dark;
  return color;
}
// Relative lightness 0-255 (Rec. 601 weights): enough to tell a colour that sinks into a dark card.
inline uint32_t lightness(uint32_t color) {
  return ((color >> 16 & 0xFF) * 299 + (color >> 8 & 0xFF) * 587 + (color & 0xFF) * 114) / 1000;
}
// A state colour drawn as a glyph, a line or words on the page or a card. Dark lifts the deep ones (indigo, purple)
// until they read on graphite.
inline uint32_t foreground(uint32_t color) {
  color = state(color);
  if (!dark) return color;
  const uint32_t l = lightness(color);
  return l >= 110 ? color : mix(color, 0xFFFFFF, static_cast<uint8_t>(255 - (110 - l) * 3 / 2));
}
// The pale circle behind a tile's icon, a halo, a slider's track: the colour at `amount` over white in light, and
// over the card in dark, where the same share would vanish, a little more.
inline uint32_t tint(uint32_t color, uint8_t amount) {
  color = state(color);
  if (!dark) return mix(color, 0xFFFFFF, amount);
  const unsigned stronger = amount + amount / 3 + 8;
  return mix(color, hex(CARD), static_cast<uint8_t>(stronger > 255 ? 255 : stronger));
}
// A tile's icon in its state colour: a touch darker in light, so a pale bulb still shows; a touch lighter in dark.
inline uint32_t icon(uint32_t color) {
  color = state(color);
  return dark ? mix(foreground(color), 0xFFFFFF, 230) : mix(color, 0x333333, 205);
}
// The soft area under a graph line: a fifth of the line's colour in light; less over graphite, where the same share
// turns a large brown or purple block.
inline uint8_t fill_opacity() { return dark ? 38 : 51; }
// Keys drawn inside a card of any colour (a wide tile's direct controls): a shade away from the card, towards the
// middle, so they read on white, on a pastel and on graphite alike.
inline uint32_t key_on(uint32_t card, uint8_t depth) {
  return dark ? mix(card, 0xFFFFFF, static_cast<uint8_t>(255 - (255 - depth) * 3 / 2)) : mix(card, 0x000000, depth);
}
// A card under a finger (firmware 0.2.95+): its own colour an eighth of the way to black in light and to white in
// dark, the same share on white, on a pastel and on graphite, so the press reads on every card in both looks.
inline uint32_t pressed(uint32_t card) { return mix(card, dark ? 0xFFFFFF : 0x000000, 224); }

}  // namespace theme

#ifndef THEME_TEST
#include "lvgl.h"
#include <array>

namespace theme {

inline lv_color_t color(Role role) { return lv_color_hex(hex(role)); }
inline lv_color_t rgb(uint32_t value) { return lv_color_hex(value); }
// The colour an object draws with, as the 24-bit value the table speaks in (what the media card names as the colour
// behind its cover's corners).
inline uint32_t of(lv_color_t value) { return lv_color_to_u32(value) & 0xFFFFFF; }

// ---- paints: shared styles filled from the table
// A board profile gives a widget a paint instead of a colour (`styles: paint_card`). Its style definitions carry no
// colour: the profile's `theme::paints` fills each one with fill(), at boot and after every change of look. The list
// is code, not a table in RAM, and a shared style costs a widget one style reference, about what the local colour it
// replaces cost. The firmware's own long-lived widgets take the same paints through style().
constexpr uint8_t NONE = 0xFF;
enum class Paint : uint8_t {
  page, page_soft, page_pressed, card, raised, key, key_pressed, track, ink, ink_soft, muted, subtle, slate,
  scrim, veil, accent_tint, accent_bright, button_dark, button_dark_pressed, knob, spinner, calibration, camera, COUNT
};
struct PaintRoles { uint8_t bg, border, text, line, arc; };
inline constexpr PaintRoles PAINTS[static_cast<size_t>(Paint::COUNT)] = {
  /* page */                {PAGE, NONE, INK, NONE, NONE},
  /* page_soft */           {PAGE_SOFT, NONE, INK, NONE, NONE},
  /* page_pressed */        {PAGE_PRESSED, NONE, NONE, NONE, NONE},
  /* card */                {CARD, LINE, INK, NONE, NONE},
  /* raised */              {RAISED, RAISED_LINE, INK, NONE, NONE},
  /* key */                 {KEY, NONE, INK, NONE, NONE},
  /* key_pressed */         {KEY_PRESSED, NONE, NONE, NONE, NONE},
  /* track */               {TRACK, NONE, INK, NONE, NONE},
  /* ink */                 {NONE, NONE, INK, NONE, NONE},
  /* ink_soft */            {NONE, NONE, INK_SOFT, NONE, NONE},
  /* muted */               {NONE, NONE, MUTED, NONE, NONE},
  /* subtle */              {NONE, NONE, SUBTLE, NONE, NONE},
  /* slate */               {NONE, SLATE, SLATE, SLATE, NONE},
  /* scrim */               {SCRIM, NONE, NONE, NONE, NONE},
  /* veil */                {VEIL, NONE, NONE, NONE, NONE},
  /* accent_tint */         {ACCENT_TINT, NONE, NONE, NONE, NONE},
  /* accent_bright */       {ACCENT_BRIGHT, NONE, NONE, NONE, NONE},
  /* button_dark */         {BUTTON_DARK, NONE, ON_ACCENT, NONE, NONE},
  /* button_dark_pressed */ {BUTTON_DARK_PRESSED, NONE, NONE, NONE, NONE},
  /* knob */                {KNOB, NONE, NONE, NONE, NONE},
  /* spinner */             {NONE, NONE, NONE, NONE, SPINNER_TRACK},
  /* calibration */         {CALIBRATION_PAGE, NONE, CALIBRATION_INK, NONE, NONE},
  /* camera */              {CAMERA_PAGE, NONE, CAMERA_NOTE, NONE, NONE},
};
// Fill a style with a paint in the current look. Setting a property the style already has allocates nothing.
inline void fill(lv_style_t *style, Paint paint) {
  if (!style) return;
  const PaintRoles &p = PAINTS[static_cast<size_t>(paint)];
  if (p.bg != NONE) lv_style_set_bg_color(style, color(static_cast<Role>(p.bg)));
  if (p.border != NONE) lv_style_set_border_color(style, color(static_cast<Role>(p.border)));
  if (p.text != NONE) lv_style_set_text_color(style, color(static_cast<Role>(p.text)));
  if (p.line != NONE) lv_style_set_line_color(style, color(static_cast<Role>(p.line)));
  if (p.arc != NONE) lv_style_set_arc_color(style, color(static_cast<Role>(p.arc)));
}
// The board profile's styles and the paint of each, as fill() calls. Set and run once in on_boot.
inline void (*paints)() = nullptr;
// The firmware's own shared style for a paint, made on first use.
inline std::array<lv_style_t *, static_cast<size_t>(Paint::COUNT)> own{};
inline lv_style_t *style(Paint paint) {
  auto *&s = own[static_cast<size_t>(paint)];
  if (!s) {
    s = new lv_style_t;
    lv_style_init(s);
    fill(s, paint);
  }
  return s;
}
// What the board draws again after a change of look: the tiles, an open card, the settings page. Set by the profile.
inline void (*redraw)() = nullptr;
// The one way the look changes. Every paint is filled again and LVGL is told once; what code painted itself follows
// through redraw(). A look the screen already has costs nothing, so the setting may be applied on every change.
inline void set_dark(bool on) {
  if (on == dark) return;
  dark = on;
  if (paints) paints();
  for (size_t i = 0; i < own.size(); ++i) if (own[i]) fill(own[i], static_cast<Paint>(i));
  // One walk over every widget instead of one per paint.
  lv_obj_report_style_change(nullptr);
  if (redraw) redraw();
}

}  // namespace theme
#endif
