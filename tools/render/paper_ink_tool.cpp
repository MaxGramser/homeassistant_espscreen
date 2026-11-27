// A picture as a paper glass prints it: a PPM (P6) of what LVGL drew comes in on stdin, a PGM (P5) of the panel's inks
// goes out on stdout. tools/render/run.py pipes every picture of a board whose glass is e-paper through it, so a
// render on a laptop shows what the glass shows (docs/PAPER.md, "Seeing it without a screen").
//
// It is the paper glass's own ink step (components/paper_glass/paper_ink.h), not a copy of it: LVGL's 24 bits a pixel
// are cut to the RGB565 the glass is flushed, and paper_ink::block() does the rest, edges, rasters and all.
//
//   c++ -std=c++17 -O2 -I. tools/render/paper_ink_tool.cpp -o paper_ink_tool && ./paper_ink_tool 2 < in.ppm > out.pgm
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <vector>

#include "components/paper_glass/paper_ink.h"

static int number(FILE *in) {
  int c = fgetc(in);
  while (c == ' ' || c == '\n' || c == '\r' || c == '\t' || c == '#') {
    if (c == '#') while (c != '\n' && c != EOF) c = fgetc(in);
    c = fgetc(in);
  }
  int value = 0;
  while (c >= '0' && c <= '9') {
    value = value * 10 + (c - '0');
    c = fgetc(in);
  }
  return value;
}

int main(int argc, char **argv) {
  const uint8_t inks = argc > 1 ? static_cast<uint8_t>(atoi(argv[1])) : 2;
  if (fgetc(stdin) != 'P' || fgetc(stdin) != '6') {
    fputs("paper_ink_tool: a P6 picture on stdin\n", stderr);
    return 2;
  }
  const int width = number(stdin), height = number(stdin), most = number(stdin);
  if (width <= 0 || height <= 0 || most != 255) {
    fputs("paper_ink_tool: a picture of 8 bits a colour\n", stderr);
    return 2;
  }
  const size_t pixels = static_cast<size_t>(width) * height;
  std::vector<uint8_t> rgb(pixels * 3), source(pixels * 2), ink(pixels * 2), out(pixels);
  if (fread(rgb.data(), 3, pixels, stdin) != pixels) {
    fputs("paper_ink_tool: the picture ends early\n", stderr);
    return 2;
  }
  for (size_t i = 0; i < pixels; ++i) {
    const uint16_t p = static_cast<uint16_t>(((rgb[i * 3] >> 3) << 11) | ((rgb[i * 3 + 1] >> 2) << 5) | (rgb[i * 3 + 2] >> 3));
    source[i * 2] = static_cast<uint8_t>(p >> 8);
    source[i * 2 + 1] = static_cast<uint8_t>(p & 0xFF);
  }
  paper_ink::block(source.data(), ink.data(), width, height, width, 0, height, 0, 0, true, inks);
  for (size_t i = 0; i < pixels; ++i) {
    const unsigned five = ink[i * 2] >> 3;  // the red of a grey: its five bits are the grey
    out[i] = static_cast<uint8_t>((five << 3) | (five >> 2));
  }
  printf("P5\n%d %d\n255\n", width, height);
  fwrite(out.data(), 1, pixels, stdout);
  return 0;
}
