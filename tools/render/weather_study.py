"""Design study of a week forecast card (10-09): tools/render/weather_study.h drawn by real LVGL on every board shape.

Host only: no firmware, storage or device changes. The data is real where it can be: the bench Home Assistant's
met.no entity (daily and hourly, .esphome/weather-study/data/), the reference card's own numbers, and a winter week.
Run with ESPHome's Python:  python tools/render/weather_study.py [build|sheets]
"""
import json, os, subprocess, sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from PIL import Image, ImageDraw, ImageFont
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools'))
import profiles
WORK = ROOT / '.esphome/weather-study'
OUT = Path(os.environ.get('WEATHER_RENDER_OUT', str(WORK / 'out'))).resolve()
# board, orientation, sizes. "full" is the whole page, "detail" the card a tap opens.
BOARDS = (('cyd', 'landscape', ['full', 'detail']), ('guition', 'landscape', ['2x2', 'full', 'detail']),
          ('waveshare43', 'landscape', ['2x2', '3x2', 'full', 'detail']), ('waveshare7', 'landscape', ['2x2', '4x2', 'full', 'detail']),
          ('jc8012p4a1', 'landscape', ['2x2', '3x2', '5x3', 'full', 'detail']), ('waveshare43', 'portrait', ['1x2', 'full', 'detail']))
DARK = ('guition', 'cyd', 'jc8012p4a1')
VARIANTS = {'A': 'A · the reference 1:1', 'B': 'B1 · B with the grid', 'C': 'C · the next 48 hours', 'D': 'B2 · B with row lines'}
SCENES = {'munich': 'The reference card\'s own week (7 days, rain and chance)',
          'thuis': 'Bench Home Assistant, met.no: 6 days, rain without chance, 48 hours hourly',
          'winter': 'A winter week below zero (widest numbers, snow and storm icons)'}
NAMES = {'cyd': 'CYD 2.8″ 320×240', 'guition': 'Guition 4″ 480×480', 'waveshare43': 'Waveshare 4.3″ 800×480',
         'waveshare7': 'Waveshare 7″ 800×480', 'jc8012p4a1': 'Guition P4 10.1″ 1280×800', 'waveshare43_portrait': 'Waveshare 4.3″ standing 480×800'}
TZ = ZoneInfo('Europe/Amsterdam')
WEEK = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')

def name(b, o): return b if o == 'landscape' else b + '_portrait'
def c(f): return round((f - 32) * 5 / 9, 1)

def scenes():
    """C++ for the three scenes. Hours count from today's midnight, local time."""
    munich = dict(key='munich', place='Munich', cond='cloudy', now=9.9, hour=10, days=[
        ('Sun', 'partlycloudy', 18.9, 9.9, 0, 9), ('Mon', 'partlycloudy', 18.5, 8.2, 0, 11), ('Tue', 'sunny', 20, 5.6, 0, 5),
        ('Wed', 'partlycloudy', 18.6, 7.2, 0, 5), ('Thu', 'rainy', 14.8, 8.7, 5.5, 55), ('Fri', 'rainy', 11.4, 6.7, 4, 52),
        ('Sat', 'cloudy', 11.5, 5.9, 0, 40)], hours=[], extra=(82, 11, 225, 1016, 10, 8.4))
    winter = dict(key='winter', place='Garmisch', cond='snowy', now=-3.4, hour=8, days=[
        ('Mon', 'snowy', -2, -7, 3.2, 80), ('Tue', 'cloudy', 0, -9, 0, 20), ('Wed', 'sunny', -4, -12, 0, 0),
        ('Thu', 'partlycloudy', 1, -6, 0, 10), ('Fri', 'snowy-rainy', 3, -1, 6.5, 90), ('Sat', 'lightning-rainy', 6, 2, 14, 95),
        ('Sun', 'fog', 4, 0, 0.2, 30)], hours=[], extra=(88, 19, 10, 1024, 2.5, -8))
    data = WORK / 'data'
    daily = json.loads((data / 'daily.json').read_text())['service_response']
    hourly = json.loads((data / 'hourly.json').read_text())['service_response']
    now = json.loads((data / 'now.json').read_text())
    entity = next(iter(daily))
    first = datetime.fromisoformat(hourly[entity]['forecast'][0]['datetime']).astimezone(TZ)
    midnight = first.replace(hour=0, minute=0)
    days = []
    for e in daily[entity]['forecast']:
        d = datetime.fromisoformat(e['datetime']).astimezone(TZ)
        days.append((WEEK[d.weekday()], e['condition'], c(e['temperature']), c(e['templow']), round(e.get('precipitation', 0) * 25.4, 1), None))
    hours = []
    for e in hourly[entity]['forecast']:
        d = datetime.fromisoformat(e['datetime']).astimezone(TZ)
        hours.append((int((d - midnight).total_seconds() // 3600), e['condition'], c(e['temperature']), round(e.get('precipitation', 0) * 25.4, 1)))
    thuis = dict(key='thuis', place='Home', cond=now['state'], now=c(now['attributes']['temperature']), hour=first.hour, days=days, hours=hours,
                 extra=(now['attributes']['humidity'], round(now['attributes']['wind_speed'] * 1.609, 1), now['attributes']['wind_bearing'], round(now['attributes']['pressure'] * 33.8639), None, None))
    def f(v): return 'NAN' if v is None else f'{float(v)}f'
    out = []
    for s in (munich, thuis, winter):
        ds = ', '.join(f'{{"{d[0]}", "{d[1]}", {f(d[2])}, {f(d[3])}, {f(d[4])}, {f(d[5])}}}' for d in s['days'])
        hs = ', '.join(f'{{{h[0]}, "{h[1]}", {f(h[2])}, {f(h[3])}, NAN}}' for h in s['hours'])
        out.append(f'{{"{s["key"]}", "{s["place"]}", "{s["cond"]}", "", {f(s["now"])}, {s["hour"]}, {{{ds}}}, {{{hs}}}, ' + ', '.join(f(v) for v in s['extra']) + '}')
    return 'std::vector<Scene> scenes = {' + ', '.join(out) + '};\n'

def project():
    shapes = json.loads((ROOT / 'screen_manager/app/boards.json').read_text())
    chars = ''.join(dict.fromkeys(''.join(chr(i) for i in range(32, 127)) + '°·'))
    icons = ''.join(chr(i) for i in (0xF0599, 0xF0594, 0xF0590, 0xF0595, 0xF0597, 0xF0596, 0xF0598, 0xF067F, 0xF0591, 0xF0592, 0xF0593,
                                     0xF059D, 0xF05D6, 0xF058C, 0xF0717, 0xF0241, 0xF0141, 0xF058E, 0xF029A, 0xF06D0))
    entries = (('label', 'LABEL', 'Roboto-700.ttf'), ('note', 'SUBLABEL', 'Roboto-400.ttf'), ('note_big', 'SUBLABEL_BIG', 'Roboto-400.ttf'),
               ('headline', 'HEADLINE', 'Roboto-500.ttf'), ('value', 'WATCH_VALUE', 'Roboto-400.ttf'),
               ('icon_watch', 'WATCH_ICON', 'materialdesignicons-webfont.ttf'), ('icon_mini', 'ICON_MINI', 'materialdesignicons-webfont.ttf'),
               ('icon', 'ICON', 'materialdesignicons-webfont.ttf'), ('icon_big', 'ICON_BIG', 'materialdesignicons-webfont.ttf'), ('hero', 'SETPOINT', 'Roboto-400.ttf'))
    fonts, boards, done = [], [], set()
    for b, o, sizes in BOARDS:
        s = profiles.substitutions(f'checkout/{b}.yaml'); side = shapes[f'checkout/{b}.yaml']['orientations'][o]
        if b not in done:
            done.add(b)
            for role, key, file in entries:
                fonts.append(f'  - file: "{ROOT}/fonts/{file}"\n    id: {b}_{role}\n    size: {s["FONT_" + key + "_SIZE"]}\n    bpp: 4\n'
                             f'    glyphs: {json.dumps(icons if "icon" in role else chars, ensure_ascii=False)}\n')
        nums = [side['width'], side['height'], round(float(s['DISPLAY_DPI'])), side['columns'], side['rows'],
                *[int(s[k]) for k in ('SCROLL_Y', 'PAGE_BAR_H', 'GRID_MARGIN', 'GRID_GAP_X', 'GRID_GAP_Y', 'TILE_RADIUS', 'TILE_PAD', 'TILE_ICON_SIZE')]]
        fs = ', '.join(f'id({b}_{role})->get_lv_font()' for role, _, _ in entries)
        boards.append('{"' + name(b, o) + '", "' + s['LOOK'] + '", ' + ', '.join(map(str, nums)) + ', {' + fs + '}}')
    (WORK / 'study.h').write_text((ROOT / 'tools/render/weather_study.h').read_text().replace('"../../components/', f'"{ROOT}/components/'))
    lam = 'using namespace weather_study;\n' + scenes()
    lam += 'std::vector<Board> boards = {' + ', '.join(boards) + '};\n'
    lam += 'for (auto &b : boards) for (auto &s : scenes) for (int v = 1; v < 4; ++v) {\n'
    for b, o, sizes in BOARDS:
        for z in sizes:
            cond = f'std::string(b.name)=="{name(b, o)}"'
            lam += f'  if ({cond} && (v!=2 || ((std::string("{z}")=="full" || std::string("{z}")=="detail") && !s.hours.empty()))) render(b,"{OUT}",s,"{z}",v,false);\n'
            if b in DARK and o == 'landscape':
                lam += f'  if ({cond} && (v!=2 || ((std::string("{z}")=="full" || std::string("{z}")=="detail") && !s.hours.empty()))) render(b,"{OUT}",s,"{z}",v,true);\n'
    lam += '}\nprintf("CUTS %d\\n", cuts);\nexit(0);'
    return f'''esphome:
  name: weather-study
  includes: ["{WORK}/study.h"]
  platformio_options:
    build_flags: [-DLV_USE_SNAPSHOT=1]
  on_boot:
    priority: -100
    then:
      - lambda: |-
{chr(10).join('          ' + line for line in lam.splitlines())}
host:
logger:
  level: WARN
display:
  - platform: sdl
    id: glass
    dimensions:
      width: 1280
      height: 1280
    auto_clear_enabled: false
    update_interval: never
font:
{''.join(fonts)}
lvgl:
  default_font: guition_note
  displays: glass
  pages:
    - id: study
      pad_all: 0
      scrollable: false
      widgets:
        - label:
            hidden: true
            text: ""
        - line:
            hidden: true
            points: ["0, 0", "1, 1"]
'''

def build():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.glob('*'): old.unlink()
    config = WORK / 'weather-study.yaml'; config.write_text(project())
    esphome = os.environ.get('ESPHOME', str(Path(sys.executable).with_name('esphome')))
    result = subprocess.run([esphome, 'compile', str(config)], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    (WORK / 'build.log').write_text(result.stdout)
    if result.returncode: print(result.stdout[-7000:]); raise SystemExit(result.returncode)
    program = WORK / '.esphome/build/weather-study/.pioenvs/weather-study/program'
    env = {**os.environ, 'SDL_VIDEODRIVER': 'dummy', 'SDL_RENDER_DRIVER': 'software'}
    result = subprocess.run([str(program)], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
    (WORK / 'render.log').write_text(result.stdout)
    print('\n'.join(l for l in result.stdout.splitlines() if l.startswith(('CUT', 'OVERFLOW')))[:4000])
    print([l for l in result.stdout.splitlines() if l.startswith('CUTS')])
    if result.returncode: print(result.stdout[-4000:]); raise SystemExit(result.returncode)

def sheets():
    for path in OUT.glob('*.ppm'):
        with Image.open(path) as im: im.save(path.with_suffix('.png'))
        path.unlink()
    font = ImageFont.truetype(str(ROOT / 'fonts/Roboto-500.ttf'), 26); small = ImageFont.truetype(str(ROOT / 'fonts/Roboto-400.ttf'), 18)
    def sheet(fname, title, cells, dark=False, maxw=2600):
        ims = [(label, Image.open(OUT / f'{f}.png').convert('RGB')) for label, f in cells if (OUT / f'{f}.png').exists()]
        if not ims: return
        ims = [(l, im.resize((im.width * 2, im.height * 2), Image.Resampling.NEAREST) if im.width <= 320 else im) for l, im in ims]
        cw = max(im.width for _, im in ims); chh = max(im.height for _, im in ims)
        cols = max(1, min(len(ims), maxw // (cw + 24))); rows = (len(ims) + cols - 1) // cols
        canvas = Image.new('RGB', (cols * (cw + 24) + 24, rows * (chh + 50) + 74), '#111' if dark else '#f5f6f8'); d = ImageDraw.Draw(canvas)
        d.text((24, 22), title, font=font, fill='#e8eaed' if dark else '#17202c')
        for i, (label, im) in enumerate(ims):
            x = 24 + (i % cols) * (cw + 24); y = 74 + (i // cols) * (chh + 50)
            d.text((x, y), label, font=small, fill='#9aa4ae' if dark else '#56616d'); canvas.paste(im, (x, y + 26))
        canvas.save(OUT / f'sheet-{fname}.png')
    for b, o, sizes in BOARDS:
        bn = name(b, o)
        for sc in SCENES:
            for dark in (False, True):
                if dark and not (b in DARK and o == 'landscape'): continue
                sfx = '-dark' if dark else ''
                cells = [(f'{z} · {VARIANTS[v]}', f'{bn}-{sc}-{z}-{v}{sfx}') for z in sizes for v in 'ABCD']
                sheet(f'{bn}-{sc}{sfx}', f'{NAMES[bn]} · {SCENES[sc]}' + (' · dark' if dark else ''), cells, dark)

if __name__ == '__main__':
    step = sys.argv[1] if len(sys.argv) > 1 else 'all'
    if step in ('build', 'all'): build()
    if step in ('sheets', 'all'): sheets()
