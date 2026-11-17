#!/usr/bin/env python3
"""Zeichnet die Wetterbilder des Displays als SVG und PNG (bilder/).

Aufruf aus eigenes-dashboard/:  python3 werkzeuge/bilder.py   (braucht: pip install cairosvg)

- tag_<zustand>.png   160 x 160  das große Bild bei Tag, je Wetterzustand von Home Assistant
- mond_<0..7>.png     160 x 160  die Mondphase bei Nacht (0 Neumond, 4 Vollmond, im Uhrzeigersinn zunehmend)
- nacht_<art>.png      93 x  93  das kleine Wetterbild, das nachts unten rechts auf dem Mond liegt (bei x 66, y 66)
- hund*.png, hr_*.png            das Easter Egg Hunderunde: der Hund (aus werkzeuge/hund_vorlage.png) und seine Wetterzeichen
Alle Zeichnungen nutzen einen viewBox von 0 bis 140. Das Display zeigt die Bilder in voller Größe, solange keine
Warnung gilt, und verkleinert sie auf 85 %, sobald darunter eine Warnung steht.
"""
import math
import os

import io

import cairosvg
from PIL import Image, ImageFilter

HIER = os.path.dirname(os.path.abspath(__file__))
ZIEL = os.path.join(os.path.dirname(HIER), "bilder")

# ---------- illustrations (viewBox 0 0 140 140) ----------
DEFS = """<defs>
<radialGradient id="glow"><stop offset=".45" stop-color="#FFD54A" stop-opacity=".55"/><stop offset="1" stop-color="#FFD54A" stop-opacity="0"/></radialGradient>
<linearGradient id="sun" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFE27A"/><stop offset="1" stop-color="#FFB224"/></linearGradient>
<linearGradient id="cw" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF"/><stop offset="1" stop-color="#D5E1F2"/></linearGradient>
<linearGradient id="cg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#C9D5E6"/><stop offset="1" stop-color="#93A6C2"/></linearGradient>
<linearGradient id="cd" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#9AA9C2"/><stop offset="1" stop-color="#5E6F8E"/></linearGradient>
<linearGradient id="moon" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF6D6"/><stop offset="1" stop-color="#F1DC9C"/></linearGradient>
<radialGradient id="mglow"><stop offset=".55" stop-color="#FFF3C4" stop-opacity=".25"/><stop offset="1" stop-color="#FFF3C4" stop-opacity="0"/></radialGradient>
</defs>"""


def sun(cx=70, cy=70, r=30, rays=True):
    s = [f'<circle cx="{cx}" cy="{cy}" r="{r * 1.9}" fill="url(#glow)"/>']
    if rays:
        for k in range(8):
            a = k * math.pi / 4
            x1, y1 = cx + math.cos(a) * r * 1.35, cy + math.sin(a) * r * 1.35
            x2, y2 = cx + math.cos(a) * r * 1.75, cy + math.sin(a) * r * 1.75
            s.append(f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="#FFC93C" '
                     f'stroke-width="{r * .2:.1f}" stroke-linecap="round"/>')
    s.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="url(#sun)"/>')
    return "".join(s)


def cloud(x=0, y=0, sc=1.0, fill="url(#cw)"):
    return (f'<g transform="translate({x},{y}) scale({sc})" fill="{fill}">'
            '<circle cx="50" cy="78" r="22"/><circle cx="78" cy="64" r="29"/><circle cx="104" cy="82" r="18"/>'
            '<rect x="28" y="78" width="94" height="26" rx="13"/></g>')


def drops(x, y, n=3, col="#4FA3FF", sc=1.0):
    s = []
    for k in range(n):
        dx = x + k * 20 * sc
        dy = y + (k % 2) * 8 * sc
        s.append(f'<path transform="translate({dx},{dy}) scale({sc})" d="M6 0 C6 0 12 9 12 13 a6 6 0 0 1-12 0 '
                 f'C0 9 6 0 6 0Z" fill="{col}"/>')
    return "".join(s)


def flakes(x, y, n=3):
    s = []
    for k in range(n):
        cx, cy = x + k * 20, y + (k % 2) * 8 + 6
        for a in (0, 60, 120):
            s.append(f'<line x1="{cx - 6}" y1="{cy}" x2="{cx + 6}" y2="{cy}" stroke="#EAF4FF" stroke-width="2.6" '
                     f'stroke-linecap="round" transform="rotate({a} {cx} {cy})"/>')
    return "".join(s)


def bolt(x, y):
    return f'<path transform="translate({x},{y})" d="M14 0 L0 22 H10 L4 40 L24 14 H13 L20 0Z" fill="#FFC93C"/>'


def picture(kind):
    """The day pictures, one per Home Assistant condition group."""
    if kind == "sunny":
        body = sun(70, 70, 30)
    elif kind == "partlycloudy":
        body = sun(52, 50, 24) + cloud(8, 12)
    elif kind == "cloudy":
        body = cloud(-14, -8, .8, "url(#cg)") + cloud(8, 14)
    elif kind == "rainy":
        body = cloud(2, -6, 1, "url(#cg)") + drops(44, 104)
    elif kind == "pouring":
        body = cloud(2, -6, 1, "url(#cd)") + drops(34, 102, 4, sc=1.1)
    elif kind == "lightning-rainy":
        body = cloud(2, -6, 1, "url(#cd)") + bolt(60, 92) + drops(36, 104, 1) + drops(96, 104, 1)
    elif kind == "snowy":
        body = cloud(2, -6, 1, "url(#cg)") + flakes(48, 104)
    elif kind == "fog":
        body = cloud(2, -14, 1, "url(#cg)") + "".join(
            f'<rect x="{26 + k * 6}" y="{98 + k * 12}" width="{88 - k * 12}" height="6" rx="3" fill="#C9D5E6"/>'
            for k in range(3))
    elif kind == "lightning":
        body = cloud(2, -6, 1, "url(#cd)") + f'<g transform="translate(70,92) scale(1.25) translate(-12,0)">{bolt(0, 0)}</g>'
    elif kind == "snowy-rainy":
        body = cloud(2, -6, 1, "url(#cg)") + drops(44, 104, 1) + flakes(70, 104, 1) + drops(84, 104, 1)
    elif kind == "hail":
        body = cloud(2, -6, 1, "url(#cd)") + "".join(
            f'<circle cx="{x}" cy="{y}" r="5" fill="#EAF4FF" stroke="#9FC4F0" stroke-width="1.5"/>'
            for x, y in ((50, 110), (70, 120), (90, 110), (60, 128) if False else (80, 126)))
    elif kind == "windy-variant":
        body = cloud(6, -16, .95, "url(#cg)") + "".join(
            f'<path d="M{24 + k * 10} {104 + k * 14} H{100 - k * 14} a9 9 0 1 0-9-9" fill="none" '
            f'stroke="#DCE6F5" stroke-width="6" stroke-linecap="round"/>' for k in range(2))
    elif kind == "exceptional":
        body = ('<g transform="translate(70,72) scale(.82) translate(-70,-67)"><path d="M70 18 L126 116 H14 Z" fill="#FFB224" stroke="#FFB224" stroke-width="10" '
                'stroke-linejoin="round"/><rect x="64" y="50" width="12" height="38" rx="6" fill="#3A2A00"/>'
                '<circle cx="70" cy="101" r="7" fill="#3A2A00"/></g>')
    elif kind == "windy":
        body = "".join(f'<path d="M{18 + k * 6} {50 + k * 22} H{92 - k * 10} a12 12 0 1 0-12-12" fill="none" '
                       f'stroke="#DCE6F5" stroke-width="7" stroke-linecap="round"/>' for k in range(3))
    else:
        body = cloud(8, 14)
    return body


def moon(phase, cx=62, cy=62, r=40):
    """phase 0 = new moon, .5 = full moon; lit side right while waxing (northern hemisphere)."""
    k = (1 - math.cos(2 * math.pi * phase)) / 2
    rx = abs(1 - 2 * k) * r
    sweep = 1 if k > .5 else 0
    path = (f"M{cx},{cy - r} A{r},{r} 0 0 1 {cx},{cy + r} A{rx:.1f},{r} 0 0 {sweep} {cx},{cy - r}Z")
    flip = f' transform="translate({2 * cx},0) scale(-1,1)"' if phase > .5 else ""
    return (f'<circle cx="{cx}" cy="{cy}" r="{r * 1.5}" fill="url(#mglow)"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#3A4F80"/>'
            f'<path d="{path}" fill="url(#moon)"{flip}/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#FFF6D6" stroke-opacity=".25"/>')




def svg(body, size=140):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{size}" height="{size}" viewBox="0 0 140 140">'
            f'{DEFS}{body}</svg>')


TAG = ["sunny", "partlycloudy", "cloudy", "fog", "rainy", "pouring", "lightning", "lightning-rainy", "snowy",
       "snowy-rainy", "hail", "windy", "windy-variant", "exceptional"]
# nachts: Wolken ohne Sonne; klar und sonnig haben kein kleines Bild
NACHT = {"wolke": cloud(8, 14), **{k: picture(k) for k in TAG if k not in ("sunny", "partlycloudy", "cloudy")}}


GROSS = 160                      # das große Bild in voller Größe (ohne Warnung)
KLEIN = round(86 / 148 * GROSS)  # 93: das kleine Wetterbild auf dem Mond


def schreibe(name, body, size):
    text = svg(body, size)
    os.makedirs(os.path.join(ZIEL, "svg"), exist_ok=True)
    with open(os.path.join(ZIEL, "svg", name + ".svg"), "w") as f:
        f.write(text)
    cairosvg.svg2png(bytestring=text.encode(), write_to=os.path.join(ZIEL, name + ".png"),
                     output_width=size, output_height=size)


# ---------- Hunderunde (Easter Egg, Doppeltipp) ----------
def schneeflocke(cx=70, cy=70, r=40, col="#D6EAFF"):
    arme = []
    for k in range(6):
        g = [f'<line x1="{cx}" y1="{cy}" x2="{cx}" y2="{cy - r}"/>']
        for t, l in ((.45, .3), (.74, .22)):
            y = cy - r * t
            g.append(f'<line x1="{cx}" y1="{y}" x2="{cx - r * l:.1f}" y2="{y - r * l:.1f}"/>'
                     f'<line x1="{cx}" y1="{y}" x2="{cx + r * l:.1f}" y2="{y - r * l:.1f}"/>')
        arme.append(f'<g transform="rotate({k * 60} {cx} {cy})">' + "".join(g) + "</g>")
    return f'<g stroke="{col}" stroke-width="6.5" stroke-linecap="round">' + "".join(arme) + "</g>"


def ohne_schein(body):
    """Die Sonne ohne ihren Schein (der Kreis mit url(#glow))."""
    import re
    return re.sub(r'<circle[^>]*fill="url\(#glow\)"/>', "", body)


def schirm():
    """Großer Schirm über dem Hund (240 x 200), Regen links und rechts daneben, der Stiel endet über dem Rücken."""
    ca = "M10 72 Q120 -14 230 72 Q202.5 58 175 72 Q147.5 58 120 72 Q92.5 58 65 72 Q37.5 58 10 72Z"
    body = ('<defs><linearGradient id="sg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFE27A"/>'
            '<stop offset="1" stop-color="#FFB224"/></linearGradient></defs>'
            '<line x1="120" y1="22" x2="120" y2="12" stroke="#FFB224" stroke-width="5" stroke-linecap="round"/>'
            '<line x1="120" y1="70" x2="120" y2="108" stroke="#FFD27A" stroke-width="5" stroke-linecap="round"/>'
            f'<path d="{ca}" fill="url(#sg)"/>'
            '<path d="M120 26 Q80 40 65 72 M120 26 Q160 40 175 72 M120 26 V72" fill="none" stroke="#C98A12" '
            'stroke-width="2.5" stroke-opacity=".5"/>')
    regen = "".join(drops(x, y, 1, sc=.75) for x, y in ((4, 92), (20, 128), (4, 150), (222, 96), (206, 132), (224, 150)))
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="240" height="200" viewBox="0 0 240 200">'
            f'{DEFS}{body}{regen}</svg>')


def png(text, w, h):
    return Image.open(io.BytesIO(cairosvg.svg2png(bytestring=text.encode(), output_width=w, output_height=h))).convert("RGBA")


def mit_rand(im, staerke=2):
    """Dezenter dunkler Rand um ein Zeichen (dunkles Grün, gut halb deckend)."""
    a = im.split()[3].point(lambda v: 255 if v > 40 else 0)
    rand = a.filter(ImageFilter.MaxFilter(2 * staerke + 1)).filter(ImageFilter.GaussianBlur(.5))
    out = Image.new("RGBA", im.size, (6, 30, 18, 0))
    out.putalpha(rand.point(lambda v: v * 150 // 255))
    out.alpha_composite(im)
    return out


def hunderunde():
    vorlage = Image.open(os.path.join(HIER, "hund_vorlage.png")).convert("RGBA")
    for name, breite in (("hund", 160), ("hund_klein", 128)):
        hoehe = round(vorlage.height * breite / vorlage.width)
        vorlage.resize((breite, hoehe), Image.LANCZOS).save(os.path.join(ZIEL, name + ".png"))
    # Zeichen in doppelter Größe gezeichnet, damit der Rand fein wird, dann verkleinert
    for name, body, px, rand in (("hr_sonne", ohne_schein(sun(70, 70, 30)), 84, True),
                                 ("hr_mix", ohne_schein(picture("partlycloudy")), 96, True),
                                 ("hr_flocke", schneeflocke(), 60, False),
                                 ("hr_flocke_m", schneeflocke(), 34, False),
                                 ("hr_flocke_s", schneeflocke(), 24, False)):
        im = png(svg(body), 2 * px, 2 * px)
        if rand:
            im = mit_rand(im, 2)
        im.resize((px, px), Image.LANCZOS).save(os.path.join(ZIEL, name + ".png"))
    png(schirm(), 420, 350).resize((210, 175), Image.LANCZOS).save(os.path.join(ZIEL, "hr_schirm.png"))


if __name__ == "__main__":
    for k in TAG:
        schreibe("tag_" + k.replace("-", "_"), picture(k), GROSS)
    for i in range(8):
        schreibe(f"mond_{i}", moon(i / 8), GROSS)
    for k, body in NACHT.items():
        schreibe("nacht_" + k.replace("-", "_"), body, KLEIN)
    hunderunde()
    print("Bilder geschrieben nach", ZIEL)
