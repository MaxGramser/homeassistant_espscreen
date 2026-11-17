#!/usr/bin/env python3
"""How deep the loop task's stack goes, from the compiler's own figures (docs/ARCHITECTURE.md, "The loop's stack").

Builds a board's checkout entry with SCREEN_STACK_USAGE set, which makes components/smart_display add -fstack-usage
and -fcallgraph-info=su to every C++ compile (ESPHome passes only -D and -W build flags to an ESP-IDF build), then
reads the .su files (each function's frame, in bytes) and the .ci call graphs, and prints:

- the loop task's chains: each a fixed run of frames down to an anchor (the loop, the API, the parser), then the
  deepest path the call graph has below it. A call through std::function or a function pointer is not in the graph,
  which is why a chain names its anchors instead of searching from the top;
- the largest frames of the component.

    python3 tools/stack_chains.py jc8012p4a1v3                     # build, then the chains
    python3 tools/stack_chains.py jc8012p4a1v3 --no-build          # the last build's figures again
    python3 tools/stack_chains.py guition --esphome 2026.9.0 --budget 12000

LVGL is C and is compiled without the flags: its own depth (a label drawn off the glass, a layout pass) comes on top
of these sums. --budget fails (exit 1) when a chain passes it.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKOUT = ROOT / 'checkout'

# Each chain: the frames on the way down (a pattern each, matched against the demangled name), the last of them the
# one the deepest static path starts from.
CHAINS = {
    'a message from the app (the API, the parser, the deepest op)': [
        r'^esphome::loop_task\(',
        r'^esphome::api::APIServer::loop\(',
        r'^esphome::api::APIConnection::loop\(',
        r'^esphome::api::APIConnection::read_message_\(',
        r'^esphome::api::APIConnection::on_execute_service_request\(',
        r'^esphome::api::UserServiceBase<esphome::StringRef>::execute_service\(esphome::api::ExecuteServiceRequest const&, unsigned',
        r"^runtime_tiles::receive\(std::[^']*const&\)$",
        r'^esphome::json::parse_json\(unsigned char const\*, unsigned int, std::function',
        r"^runtime_tiles::receive\(std::.*\)::'lambda'\(ArduinoJson::[^)]*JsonObject\)::operator\(\)\(ArduinoJson::[^)]*JsonObject\) const$",
    ],
    'a page built from the loop (show_page and its cards)': [
        r'^esphome::loop_task\(',
        r'^runtime_tiles::show_page\(',
    ],
}


def build(board, esphome):
    entry = CHECKOUT / f'{board}.yaml'
    if not entry.exists():
        sys.exit(f'no checkout entry {entry.relative_to(ROOT)}')
    env = dict(os.environ, SCREEN_STACK_USAGE='1')
    command = ['uvx', '--quiet', '--python', '3.13', '--from', f'esphome=={esphome}', 'esphome', 'compile', entry.name]
    print('building', board, 'with ESPHome', esphome, '...', file=sys.stderr)
    if subprocess.run(command, cwd=CHECKOUT, env=env).returncode:
        sys.exit('the build failed')


def build_dir(board):
    """The build of this board's entry: the newest compile_commands.json naming its smart_display sources."""
    found = sorted(CHECKOUT.glob('.esphome/build/*/build/compile_commands.json'), key=lambda p: p.stat().st_mtime, reverse=True)
    for commands in found:
        if (commands.parent / 'esp-idf').exists() and any((commands.parent.parent / 'src').glob('esphome/components/smart_display')):
            name = commands.parent.parent.name
            text = (CHECKOUT / f'{board}.yaml').read_text()
            if board in name or name in text:
                return commands.parent
    return found[0].parent if found else None


def demangle(names):
    out = subprocess.run(['c++filt'], input='\n'.join(names), capture_output=True, text=True).stdout.splitlines()
    return dict(zip(names, out)) if len(out) == len(names) else {n: n for n in names}


def read(build):
    node = re.compile(r'node:\s*\{\s*title:\s*"([^"]+)"\s*label:\s*"([^"]*)"')
    edge = re.compile(r'edge:\s*\{\s*sourcename:\s*"([^"]+)"\s*targetname:\s*"([^"]+)"')
    key = lambda title: title.rsplit(':', 1)[-1]
    size, calls, files = {}, {}, {}
    for ci in build.rglob('*.ci'):
        text = ci.read_text(errors='replace')
        for title, label in node.findall(text):
            m = re.search(r'(\d+) bytes', label)
            k = key(title)
            size[k] = max(size.get(k, 0), int(m.group(1)) if m else 0)
            if m and 'smart_display' in str(ci):
                files[k] = ci.name.split('.')[0]
        for a, b in edge.findall(text):
            calls.setdefault(key(a), set()).add(key(b))
    if not size:
        sys.exit(f'no call graphs under {build}: build with SCREEN_STACK_USAGE set (this tool does, without --no-build)')
    return size, calls, files


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('board', help='a checkout entry: checkout/<board>.yaml')
    parser.add_argument('--esphome', default='2026.9.0', help='the ESPHome to build with (the packages\' min_version)')
    parser.add_argument('--no-build', action='store_true', help='read the last build again')
    parser.add_argument('--top', type=int, default=15, help='how many of the component\'s largest frames to list')
    parser.add_argument('--budget', type=int, help='fail when a chain passes this many bytes')
    parser.add_argument('--json', action='store_true', help='print the figures as JSON')
    args = parser.parse_args()
    if not args.no_build:
        build(args.board, args.esphome)
    folder = build_dir(args.board)
    if not folder:
        sys.exit('no build of this board found')
    size, calls, files = read(folder)
    names = sorted(set(size) | set(calls))
    plain = demangle(names)
    sys.setrecursionlimit(100000)
    memo = {}

    def deepest(name, path):
        if name in memo:
            return memo[name]
        best, best_path = 0, []
        path.add(name)
        for callee in calls.get(name, ()):
            if callee not in path:
                d, p = deepest(callee, path)
                if d > best:
                    best, best_path = d, p
        path.discard(name)
        memo[name] = (size.get(name, 0) + best, [name] + best_path)
        return memo[name]

    report, failed = {'board': args.board, 'chains': {}, 'frames': []}, False
    for title, anchors in CHAINS.items():
        frames, missing = [], []
        for i, pattern in enumerate(anchors):
            match = [n for n in names if re.search(pattern, plain[n])]
            if not match:
                missing.append(pattern)
                continue
            top = max(match, key=lambda n: size.get(n, 0))
            if i < len(anchors) - 1:
                frames.append((size.get(top, 0), plain[top]))
            else:
                total, path = deepest(top, set())
                frames += [(size.get(n, 0), plain[n]) for n in path]
        total = sum(s for s, _ in frames)
        report['chains'][title] = {'bytes': total, 'frames': frames, 'missing': missing}
        if args.budget and total > args.budget:
            failed = True
    component = sorted(((s, plain[n], files[n]) for n, s in size.items() if n in files), reverse=True)[:args.top]
    report['frames'] = component
    if args.json:
        print(json.dumps(report, indent=1))
    else:
        for title, chain in report['chains'].items():
            print(f'== {title}: {chain["bytes"]} bytes')
            for s, name in chain['frames']:
                if s >= 32:
                    print(f'  {s:6d}  {name[:140]}')
            for pattern in chain['missing']:
                print(f'  (no function matches {pattern})')
        print(f'== the component\'s {args.top} largest frames')
        for s, name, f in component:
            print(f'  {s:6d}  {f[:22]:22s} {name[:120]}')
    if failed:
        sys.exit(f'a chain passes the budget of {args.budget} bytes')


if __name__ == '__main__':
    main()
