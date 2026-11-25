#!/usr/bin/env python3
"""The Xtensa literal margin of a firmware build, read from its linker map (docs/RELEASING.md, "The Xtensa literal range").

On the ESP32 and the ESP32-S3 an `l32r` loads a constant from at most 256 KB back, and ESP-IDF puts an object file's
literals in front of its code. Every header of the component compiles into main.cpp, so when main.cpp's code grows the
last of its functions moves out of reach of its literals and the link fails with "dangerous relocation: l32r: literal
target out of range" (2026-11-24: 13 KB over on the S3 boards). This prints, per object file, how far its farthest
code lies from its literals' start, and the margin left under the reach; `--floor` fails a build under that margin.

    tools/literal_margin.py BUILD.map [--floor KB] [--top N]

A map without .literal sections (an ESP32-P4, RISC-V) has no such limit and passes. Tested in tests/test_literal_margin.py.
"""
import argparse
import re
import sys

REACH = 256 * 1024
# An input section in the memory map: its name on its own line or with its address, size and object on the same line.
SECTION = re.compile(r'^ (\.(?:literal|text)\.?\S*)\s*(?:(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S.*))?$')
PLACED = re.compile(r'^\s+(0x[0-9a-f]+)\s+(0x[0-9a-f]+)\s+(\S.*)$')
OBJECT = re.compile(r'\(([^()]+\.obj)\)\s*$|([^/\s]+\.obj)\s*$')


OUTPUT = re.compile(r'^(\.[\w.]+)\s')


def sections(lines):
    """(kind, name, address, size, object, output section) of every placed .literal and .text input section of the
    memory map. The output section keeps literals in IRAM apart from code in flash: only the two in one output section
    are within each other's reach."""
    started, pending, output = False, None, ''
    for line in lines:
        if not started:
            started = line.startswith('Linker script and memory map')
            continue
        head = OUTPUT.match(line)
        if head:
            output = head.group(1)
        if pending is not None:
            placed = PLACED.match(line)
            if placed:
                yield (*pending, int(placed.group(1), 16), int(placed.group(2), 16), placed.group(3), output)
            pending = None
            continue
        found = SECTION.match(line.rstrip('\n'))
        if not found:
            continue
        full = found.group(1)
        kind = 'literal' if full.startswith('.literal') else 'text'
        name = full.split('.', 2)[2] if full.count('.') >= 2 else ''
        if found.group(2):
            yield kind, name, int(found.group(2), 16), int(found.group(3), 16), found.group(4), output
        else:
            pending = (kind, name)


def object_of(where):
    found = OBJECT.search(where)
    return (found.group(1) or found.group(2)) if found else where.strip()


def margins(lines):
    """[(margin in bytes, object, function)] for every function whose literals and code are both placed in one output
    section, the tightest first. An l32r in a function loads from that function's own literals (.literal.<name>); the
    farthest instruction is the end of its code (.text.<name>), so its margin is the reach less that distance."""
    literals, code = {}, {}
    for kind, name, address, size, where, output in sections(lines):
        if address == 0 or size == 0 or not name:
            continue
        key = (output, object_of(where), name)
        if kind == 'literal':
            literals[key] = min(address, literals.get(key, address))
        else:
            code[key] = max(address + size, code.get(key, 0))
    out = [(REACH - (code[key] - start), key[1], key[2]) for key, start in literals.items()
           if key in code and code[key] > start]
    return sorted(out)


def largest(lines, obj, top):
    """The `top` largest functions of `obj`'s code, by size: what a compilation unit of its own could take out."""
    sizes = [(size, name) for kind, name, address, size, where, _ in sections(lines)
             if kind == 'text' and address and object_of(where) == obj]
    return sorted(sizes, reverse=True)[:top]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('map')
    parser.add_argument('--floor', type=float, default=None, help='fail under this many KB of margin')
    parser.add_argument('--top', type=int, default=0, help="list main.cpp's largest functions")
    args = parser.parse_args(argv)
    with open(args.map, encoding='utf-8', errors='replace') as handle:
        lines = handle.readlines()
    found = margins(lines)
    if not found:
        print('literal margin: no literals in flash (not an Xtensa build): no limit')
        return 0
    for margin, obj, name in found[:5]:
        print(f'literal margin: {margin / 1024:.1f} KB: {obj} {name}')
    if args.top:
        for size, name in largest(lines, 'main.cpp.obj', args.top):
            print(f'  {size:>7} {name}')
    least = found[0][0]
    if args.floor is not None and least < args.floor * 1024:
        print(f'literal margin: {least / 1024:.1f} KB is under the floor of {args.floor:g} KB '
              '(docs/RELEASING.md, "The Xtensa literal range")', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
