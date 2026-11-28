// clang++ -std=c++17 -Wall -Wextra -Werror -I. tests/test_keyboard.cpp -o /tmp/test_keyboard && /tmp/test_keyboard
// The keyboard alone (components/smart_display/keyboard.h, docs/KEYBOARD.md), with no caller: what a key types, the
// limit of the field, and the sheet it plans on the faces of several boards. Everything a caller hands it is an
// argument: a second layout that lives only here (AZERTY, with rows of 10, 10 and 6 keys and accents of its own), the
// QWERTZ of a screen built in German (rows of 11, 11 and 7: tests/test_keyboard_qwertz.cpp builds as such a screen), a
// send key that is a word, the hint, the suggestions and whether their row keeps its room, a field of a text entity
// (a start value, the most and the fewest characters as Home Assistant counts them, and a masked field).
#include "../components/smart_display/keyboard.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <set>
#include <string>

using namespace keyboard;
using calendar_card::FACES;
using calendar_card::Measure;
using calendar_card::Scene;

// Roboto's line is 1.17 of its size; widths in em, near enough for layout (tests/test_todo.cpp has the same).
static int line(int size) { return (int) std::lround(size * 1.172); }
static int wide(const std::string &s, int size) {
  double em = 0;
  for (size_t i = 0; i < s.size(); ++i) {
    const unsigned char c = s[i];
    if (c == ' ') em += 0.25;
    else if (c >= 'A' && c <= 'Z') em += 0.65;
    else if ((c & 0xC0) != 0x80) em += 0.56;
  }
  return (int) std::lround(em * size);
}
struct Board { const char *name; int dpi, width, height; int sizes[FACES]; };
static const Board BOARDS[] = {
  {"jc3248w535", 165, 480, 320, {17, 16, 20, 26, 37, 47, 25, 41}},
  {"guition", 170, 480, 480, {18, 16, 21, 27, 38, 48, 26, 42}},
  {"waveshare43", 217, 800, 480, {23, 20, 27, 34, 49, 61, 33, 54}},
  {"waveshare7", 133, 800, 480, {14, 13, 16, 21, 30, 38, 20, 33}},
  {"jc8012p4a1", 149, 1280, 800, {16, 14, 18, 24, 33, 42, 23, 37}},
  {"jc3248w535 upright", 165, 320, 480, {17, 16, 20, 26, 37, 47, 25, 41}},
};
static Measure measure(const Board &b) {
  Measure m;
  for (int f = 0; f < FACES; ++f) m.line[f] = line(b.sizes[f]);
  const Board *bp = &b;
  m.width = [bp](calendar_card::Face f, const std::string &s) { return wide(s, bp->sizes[f]); };
  m.circle = ui::px(54);
  return m;
}

// A French layout, for this test alone: a second table is all a layout takes.
static const char *const AZ_LOWER[26] = {"a", "z", "e", "r", "t", "y", "u", "i", "o", "p", "q", "s", "d", "f", "g", "h", "j", "k", "l",
                                         "m", "w", "x", "c", "v", "b", "n"};
static const char *const AZ_UPPER[26] = {"A", "Z", "E", "R", "T", "Y", "U", "I", "O", "P", "Q", "S", "D", "F", "G", "H", "J", "K", "L",
                                         "M", "W", "X", "C", "V", "B", "N"};
static const char *const AZ_DIGITS[26] = {"1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "/", ":", ";", "(", ")", "€", "&", "@",
                                          "\"", ".", ",", "?", "!", "'", "+"};
static const char *const AZ_SIGNS[26] = {"[", "]", "{", "}", "#", "%", "^", "*", "=", "_", "\\", "|", "~", "<", ">", "$", "£", "·",
                                         "°", "…", ".", ",", "?", "!", "'", "«"};
static const Accents AZ_ACCENTS[] = {
    {"e", {"é", "è", "ê", "ë", nullptr, nullptr}, {"É", "È", "Ê", "Ë", nullptr, nullptr}},
    {"c", {"ç", nullptr, nullptr, nullptr, nullptr, nullptr}, {"Ç", nullptr, nullptr, nullptr, nullptr, nullptr}},
};
static const Layout AZERTY{"azerty", {10, 10, 6}, AZ_LOWER, AZ_UPPER, AZ_DIGITS, AZ_SIGNS, AZ_ACCENTS, 2, "123", "#+=", "abc"};

static int count(const Scene &s, calendar_card::HitKind kind) {
  int n = 0;
  for (const auto &h : s.hits) n += h.kind == kind;
  return n;
}
static const calendar_card::Hit *find(const Scene &s, calendar_card::HitKind kind, int arg = 0) {
  for (const auto &h : s.hits) if (h.kind == kind && h.arg == arg) return &h;
  return nullptr;
}
static bool has_text(const Scene &s, const std::string &part) {
  for (const auto &t : s.texts) if (t.s.find(part) != std::string::npos) return true;
  return false;
}
static void inside(const Scene &s, int w, int h, const Measure &m, const char *what, const char *board) {
  for (const auto &b : s.boxes)
    if (b.x < 0 || b.y < 0 || b.x + b.w > w || b.y + b.h > h) {
      printf("%s on %s: a box at %d,%d %dx%d leaves %dx%d\n", what, board, b.x, b.y, b.w, b.h, w, h);
      assert(false);
    }
  for (const auto &t : s.texts)
    if (t.x < 0 || t.x + t.w > w || t.y < 0 || t.y + m.line[t.face] > h || m.width(t.face, t.s) > t.w + m.line[t.face]) {
      printf("%s on %s: \"%s\" at %d,%d width %d leaves %dx%d\n", what, board, t.s.c_str(), t.x, t.y, t.w, w, h);
      assert(false);
    }
}

static void layouts() {
  assert(layout("qwerty") == &qwerty() && layout("qwertz") == &qwertz() && layout("dvorak") == nullptr);
  for (const Layout *l : {&qwerty(), &qwertz(), &AZERTY}) {
    // Three rows that fit the planner: eleven at most beside each other, seven between shift and backspace.
    assert(l->rows[0] <= 11 && l->rows[1] <= 11 && l->rows[2] <= 7 && keys(*l) == (l == &qwertz() ? 29 : 26));
    for (uint8_t page = 0; page < 3; ++page)
      for (bool shift : {false, true})
        for (int k = 0; k < keys(*l); ++k) assert(page_keys(*l, page, shift)[k] && *page_keys(*l, page, shift)[k]);
  }
  // A letter's accents come from its own layout's table.
  assert(accents_of(qwerty(), 2, false).size() == 5 && accents_of(AZERTY, 2, false).size() == 4);
  assert(accents_of(AZERTY, 22, true).size() == 1 && std::string(accents_of(AZERTY, 22, true)[0]) == "Ç");
  assert(accents_of(AZERTY, 0, false).empty() && accents_of(AZERTY, 99, false).empty());
  // QWERTZ: z and y change places, ü, ö and ä end the first two rows on a grid of eleven, ß stands beside the 0 and
  // is the first accent of s. QWERTY and AZERTY keep the grid of ten.
  const Layout &de = qwertz();
  assert(columns(qwerty()) == 10 && columns(AZERTY) == 10 && columns(de) == 11);
  assert(std::string(de.letters[5]) == "z" && std::string(de.letters[22]) == "y" && std::string(de.capitals[5]) == "Z");
  assert(std::string(de.letters[10]) == "ü" && std::string(de.letters[20]) == "ö" && std::string(de.letters[21]) == "ä");
  assert(std::string(de.capitals[10]) == "Ü" && std::string(de.capitals[20]) == "Ö" && std::string(de.capitals[21]) == "Ä");
  assert(std::string(de.digits[9]) == "0" && std::string(de.digits[10]) == "ß");
  assert(std::string(accents_of(de, 12, false)[0]) == "ß" && accents_of(de, 10, false).empty() && accents_of(de, 6, true).size() == 4);
  // The same accents on both: the strip of a letter does not depend on the layout it is on.
  assert(accents_of(de, 2, false).size() == accents_of(qwerty(), 2, false).size());
  // A screen's layout follows the language it is built in; this test builds without SCREEN_KEYBOARD_QWERTZ, so QWERTY.
  assert(&standard() == &qwerty() && &layout_of(Spec()) == &qwerty());
  for (const char *code : {"de", "de-AT", "de-CH"}) assert(std::string(layout_for(code)) == "qwertz");
  for (const char *code : {"en", "nl", "fr", "pt-BR", "ru", "deu", "dk", ""}) assert(std::string(layout_for(code)) == "qwerty");
  assert(std::string(layout_for(nullptr)) == "qwerty" && layout(layout_for("de")) == &qwertz());
}

static void typing() {
  Spec fr; fr.layout = &AZERTY; fr.most = 10;
  Entry e;
  reset(e);
  press(e, 0, fr); press(e, 1, fr); press(e, 19, fr);  // A z m
  assert(e.text == "Azm" && !e.shift);
  press(e, K_BACK, fr);
  assert(hold(e, 2, fr) && e.accents == 2);
  press(e, ACCENT + 1, fr);  // è
  assert(e.text == "Azè" && e.accents == -1);
  press(e, K_PAGE, fr); press(e, 19, fr); press(e, K_PAGE, fr);  // the digit page's 20th key is AZERTY's own
  assert(e.text == "Azè\"");
  // The field holds what the caller says, never half a character.
  for (int i = 0; i < 20; ++i) press(e, 2, fr);
  assert(e.text.size() <= 10);
  press(e, K_BACK, fr);
  assert(hold(e, 2, fr));
  assert(e.text == "Azè\"eeee");
  press(e, ACCENT, fr);  // é is two bytes: one is left, so it is left out whole
  assert(e.text == "Azè\"eeee" && e.accents == -1);
  // The same keys on the QWERTY of a Spec that names no layout.
  Spec any;
  Entry q;
  reset(q, "Hi");
  assert(!q.shift);
  press(q, K_SPACE, any); press(q, K_SPACE, any); press(q, 0, any);
  assert(q.text == "Hi q" && typed(q) == "Hi q");
  reset(q, "  x  ");
  assert(typed(q) == "x");
  // QWERTZ: an umlaut is a key of its own, ß is on the page of digits, and z is where QWERTY has y.
  Spec de;
  de.layout = &qwertz();
  Entry g;
  reset(g);
  press(g, 15, de); press(g, 3, de); press(g, 20, de);  // G r ö
  press(g, K_PAGE, de); press(g, 10, de); press(g, K_PAGE, de);  // ß
  press(g, 2, de);
  assert(g.text == "Größe");
  press(g, K_SPACE, de); press(g, 5, de); press(g, 22, de); press(g, K_SHIFT, de); press(g, 21, de);
  assert(g.text == "Größe zyÄ");
  assert(hold(g, 12, de));
  press(g, ACCENT, de);  // ß, the first accent of s
  assert(g.text == "Größe zyÄß");
}

static void sheets() {
  for (const auto &b : BOARDS) {
    ui::configure(b.dpi, "standard");
    const Measure m = measure(b);
    const int top = ui::px(120);
    Entry e;
    reset(e, "Ca");
    // QWERTY with the check that sends, a hint, and suggestions in their own row.
    Spec k;
    k.hint = "Search";
    k.suggestions = {"Calendar", "Camera"};
    Scene s;
    const Place p = plan(s, m, b.width, b.height, top, e, k);
    inside(s, b.width, b.height, m, "the sheet", b.name);
    assert(p.whole || p.top >= top);
    assert(count(s, KEY) == 31 && count(s, SEND) == 1 && count(s, SUGGESTION) >= 1 && count(s, PANEL) == 1);
    assert(count(s, HIDE) == (p.whole ? 1 : 0));
    for (const auto &h : s.hits)
      assert(h.kind == KEY || h.kind == SEND || h.kind == SUGGESTION || h.kind == PANEL || h.kind == HIDE);
    for (const auto &h : s.hits) if (h.kind == KEY && h.h < ui::mm(13) / 2) { printf("%s: a key of %d px\n", b.name, h.h); assert(false); }
    assert(has_text(s, I_CHECK) && has_text(s, "Calendar") && !has_text(s, "Search"));  // the hint shows in an empty field only
    const auto *glyph_send = find(s, SEND);
    // The send key as a word: wider than the round key, the field narrower by as much, and the keys where they were.
    Spec word = k;
    word.send_word = "Search";
    Scene w;
    const Place pw = plan(w, m, b.width, b.height, top, e, word);
    inside(w, b.width, b.height, m, "the word", b.name);
    const auto *word_send = find(w, SEND);
    assert(pw.top == p.top && pw.whole == p.whole && word_send->w > glyph_send->w && has_text(w, "Search"));
    assert(word_send->x + word_send->w == glyph_send->x + glyph_send->w);
    for (const auto &h : s.hits) if (h.kind == KEY) { const auto *o = find(w, KEY, h.arg); assert(o && o->x == h.x && o->y == h.y); }
    // A glyph of the caller's on the send key.
    Spec plus = k;
    plus.send_glyph = "\U000F0415";
    Scene ps;
    plan(ps, m, b.width, b.height, top, e, plus);
    assert(has_text(ps, "\U000F0415"));
    // The row of suggestions: gone without any, unless the caller keeps its room; kept, the keys never move.
    Spec none = k;
    none.suggestions.clear();
    Scene n;
    const Place pn = plan(n, m, b.width, b.height, top, e, none);
    assert(count(n, SUGGESTION) == 0 && (pn.whole || pn.top > p.top || p.whole));
    Spec kept = none;
    kept.keep_row = true;
    Scene kp;
    const Place pk = plan(kp, m, b.width, b.height, top, e, kept);
    assert(pk.top == p.top && pk.whole == p.whole && count(kp, SUGGESTION) == 0);
    for (const auto &h : s.hits) if (h.kind == KEY) { const auto *o = find(kp, KEY, h.arg); assert(o && o->x == h.x && o->y == h.y); }
    // AZERTY: its second row has ten keys under the first ten, its third six between shift and backspace.
    Spec fr = k;
    fr.layout = &AZERTY;
    Entry fe;
    reset(fe);
    Scene f;
    plan(f, m, b.width, b.height, top, fe, fr);
    inside(f, b.width, b.height, m, "AZERTY", b.name);
    assert(count(f, KEY) == 31 && has_text(f, "A") && has_text(f, "M"));
    for (int i = 0; i < 10; ++i) assert(find(f, KEY, 10 + i)->x == find(f, KEY, i)->x && find(f, KEY, 10 + i)->y > find(f, KEY, i)->y);
    const auto *shift = find(f, KEY, K_SHIFT), *back = find(f, KEY, K_BACK);
    assert(find(f, KEY, 20)->x >= shift->x + shift->w && find(f, KEY, 25)->x + find(f, KEY, 25)->w <= back->x);
    const int left = find(f, KEY, 20)->x - (shift->x + shift->w), right = back->x - (find(f, KEY, 25)->x + find(f, KEY, 25)->w);
    assert(std::abs(left - right) <= 1);  // in the middle between the two
    // Held, the c of its third row shows its own accent above it.
    assert(hold(fe, 22, fr));
    Scene fa;
    plan(fa, m, b.width, b.height, top, fe, fr);
    assert(count(fa, KEY) == 32 && has_text(fa, "Ç") && find(fa, KEY, ACCENT)->y < find(fa, KEY, 22)->y);
    // QWERTZ: eleven keys in each of the first two rows, one under the other, narrower than QWERTY's ten and still
    // keys a finger can hit; the third row of seven in the middle between shift and backspace, as QWERTY's.
    Spec de = k;
    de.layout = &qwertz();
    Entry ge;
    reset(ge);
    Scene z;
    const Place pz = plan(z, m, b.width, b.height, top, ge, de);
    inside(z, b.width, b.height, m, "QWERTZ", b.name);
    assert(pz.top == p.top && pz.whole == p.whole);
    assert(count(z, KEY) == 34 && has_text(z, "Ü") && has_text(z, "Ö") && has_text(z, "Ä") && has_text(z, "Z"));
    for (int i = 0; i < 11; ++i) assert(find(z, KEY, 11 + i)->x == find(z, KEY, i)->x && find(z, KEY, 11 + i)->y > find(z, KEY, i)->y);
    for (const auto &h : z.hits) if (h.kind == KEY && h.h < ui::mm(13) / 2) { printf("%s: a QWERTZ key of %d px\n", b.name, h.h); assert(false); }
    assert(find(z, KEY, 0)->w < find(s, KEY, 0)->w && find(z, KEY, 0)->h == find(s, KEY, 0)->h);
    // The same width for the row: it begins where QWERTY's does and ends within the pixels a key's width rounds away.
    const int zend = find(z, KEY, 10)->x + find(z, KEY, 10)->w, qend = find(s, KEY, 9)->x + find(s, KEY, 9)->w;
    assert(find(z, KEY, 0)->x == find(s, KEY, 0)->x && std::abs(zend - qend) < 11);
    const auto *zs = find(z, KEY, K_SHIFT), *zb = find(z, KEY, K_BACK);
    const int zl = find(z, KEY, 22)->x - (zs->x + zs->w), zr = zb->x - (find(z, KEY, 28)->x + find(z, KEY, 28)->w);
    assert(zl > 0 && zr > 0 && std::abs(zl - zr) <= 1);
    // The bottom row and the page keys stand where QWERTY has them.
    for (int code : {K_PAGE, K_SPACE, K_ENTER}) assert(find(z, KEY, code)->y == find(s, KEY, code)->y);
    // Held, the u shows its accents above it, inside the sheet.
    assert(hold(ge, 6, de));
    Scene za;
    plan(za, m, b.width, b.height, top, ge, de);
    inside(za, b.width, b.height, m, "QWERTZ accents", b.name);
    assert(count(za, KEY) == 34 + 4 && find(za, KEY, ACCENT)->y < find(za, KEY, 6)->y);
  }
  // Glass too short for keys under `top`: the whole glass, with a key that puts it away.
  ui::configure(165, "standard");
  const Measure m = measure(BOARDS[0]);
  Entry e;
  reset(e);
  Spec k;
  Scene s;
  const Place p = plan(s, m, 480, 320, 200, e, k);
  assert(p.whole && p.top == 0 && count(s, HIDE) == 1);
  inside(s, 480, 320, m, "the whole glass", "jc3248w535");
}

// A text entity's field (module text_edit, docs/TEXT_ENTITY.md): Home Assistant counts characters, not bytes, refuses
// fewer than its min, and a password shows dots.
static void entity_field() {
  assert(characters("") == 0 && characters("abc") == 3 && characters("Azè\"") == 4 && characters("€£") == 2);
  Spec k;
  k.most = 1020;
  k.chars = 4;
  k.least = 2;
  Entry e;
  reset(e, "é");
  // A start value: what is typed goes at its end, and it is no new sentence.
  assert(e.text == "é" && !e.shift && !sendable(e, k));
  assert(hold(e, 2, k));
  press(e, ACCENT, k);  // é, two bytes, one character
  assert(e.text == "éé" && sendable(e, k));
  press(e, 2, k); press(e, 2, k); press(e, 2, k);  // the fourth character is the last
  assert(e.text == "ééee" && characters(e.text) == 4);
  press(e, K_BACK, k); press(e, K_BACK, k); press(e, K_BACK, k);
  assert(e.text == "é" && !sendable(e, k));
  // Without `chars` the bytes are the limit, as before.
  Spec bytes;
  bytes.most = 3;
  Entry b;
  reset(b, "é");
  press(b, 2, bytes); press(b, 2, bytes);
  assert(b.text == "ée");
  // The cursor: a caller puts it anywhere (a finger in its own text), keys type there and backspace erases before it.
  Spec plain;
  Entry c;
  reset(c, "abc");
  assert(c.at == 3);
  place(c, 1);
  press(c, 0, plain);  // q
  assert(c.text == "aqbc" && c.at == 2);
  press(c, K_SPACE, plain);
  press(c, K_SPACE, plain);  // never two spaces side by side
  assert(c.text == "aq bc" && c.at == 3);
  press(c, K_BACK, plain); press(c, K_BACK, plain);
  assert(c.text == "abc" && c.at == 1);
  reset(c, "é€");
  place(c, 1);  // inside the é: the cursor goes to its start
  assert(caret(c) == 0);
  c.at = 9;  // past the end (a caller that changed the text itself): the cursor stays inside it
  assert(caret(c) == c.text.size());
  for (const auto &board : BOARDS) {
    ui::configure(board.dpi, "standard");
    const Measure m = measure(board);
    // Too short: the send key and the check key are faded, and the masked field shows a dot for each character.
    Spec pw = k;
    pw.mask = true;
    Entry one;
    reset(one, "Q");  // a capital: the keys show small letters after a start value
    Scene s;
    plan(s, m, board.width, board.height, ui::px(120), one, pw);
    inside(s, board.width, board.height, m, "a masked field", board.name);
    assert(has_text(s, MASK) && !has_text(s, "Q"));
    bool faded = false;
    for (const auto &t : s.texts) if (t.s == I_CHECK) faded = faded || t.paint.role == calendar_card::SUBTLE;
    assert(faded);
    // Long enough: both take the accent and the ink again.
    Entry two;
    reset(two, "QRS");
    Scene r;
    plan(r, m, board.width, board.height, ui::px(120), two, pw);
    int dots = 0;
    for (const auto &t : r.texts) for (size_t at = t.s.find(MASK); at != std::string::npos; at = t.s.find(MASK, at + 1)) ++dots;
    assert(dots == 3);
    for (const auto &t : r.texts) if (t.s == I_CHECK) assert(t.paint.role != calendar_card::SUBTLE);    // Without the field: the keys alone, the sheet lower by the field's row, the check at the bottom right sends.
    Spec bare = pw;
    bare.field = false;
    Scene b, f;
    const Place pb = plan(b, m, board.width, board.height, ui::px(120), two, bare), pf = plan(f, m, board.width, board.height, ui::px(120), two, pw);
    inside(b, board.width, board.height, m, "the keys alone", board.name);
    assert(count(b, SEND) == 0 && count(b, KEY) == 31 && !has_text(b, MASK));
    assert(pb.whole || pf.whole || pb.top > pf.top);
  }
}

int main() {
  layouts();
  typing();
  sheets();
  entity_field();
  printf("keyboard: ok\n");
  return 0;
}
