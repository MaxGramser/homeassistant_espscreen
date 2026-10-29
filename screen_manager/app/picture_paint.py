"""One way to make a picture for its places (docs/PICTURES.md, "In ESP Screen Manager: one service").

A question (picture_question) names a box and places in it; each place gets its source's picture painted the way the
place says: filled or whole, rounded over its ground, shaded under words, darkened, turned, reflected. The screen draws
the result as it is, pixel for pixel, so nothing of this happens on a screen. Every picture a screen gets is painted
here: a camera's still, a cover, a tile's picture, a page of a library, the screensaver's, a plugin's places.

Pure functions of bytes (or a picture a source drew) in and bytes out, run in an executor: tests/test_picture_paint.py
checks them against the pictures the code they replaced made.
"""
import contextlib
import io

# The shade under a camera's name (app 0.3.8, live_view.h FADE_PERCENT and FADE_DEPTH): the bottom share of the place,
# from clear to this much black.
FADE_SHARE = 0.42
FADE_DEPTH = 150
# A place's picture turned (plugin API 0.10, tessera::Turn): its far edge this share of the near one. A reflection under
# a picture (`mirror`) takes MIRROR_PERCENT of the picture's height under it (plugin_api.h MIRROR_PERCENT, a test keeps
# them equal), starting at MIRROR_ALPHA and fading out.
FAR_EDGE = 0.70
MIRROR_PERCENT = 30
MIRROR_ALPHA = 0.38
# The screensaver's cover (fit `saver`): it fills the glass while the glass is about square (neither side a quarter
# longer than the other, saver_view.h has the same rule), else it takes the glass's height at the left (lying) or its
# width at the top (standing), on the cover's own colour, where the screen writes the title.
SQUARE = (5, 4)
# A photo shown whole (fit `auto`) lies on its own colour, darkened this much.
PHOTO_GROUND_DIM = 0.55
# Every rounded corner is drawn at this many times the place's size and brought down, so its edge is smooth.
CORNER_SUPERSAMPLE = 4
# A baseline JPEG for a screen whose decoder is the ESP32-P4's hardware (picture_question.FORMATS `jpeg`).
JPEG_QUALITY = 85


def rgb(colour):
    return tuple((colour >> shift) & 0xFF for shift in (16, 8, 0))


def heif():
    """Pillow reads HEIC (an iPhone's photos) once pillow-heif is registered; without it a HEIC is skipped."""
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        return True
    except ImportError:
        return False


_HEIF = []


@contextlib.contextmanager
def opened(raw, draft=None):
    """A source's picture as Pillow reads it, turned the way its EXIF says. `raw` is bytes, or a picture a source drew
    itself (a map). `draft` lets a JPEG decode at a half, quarter or eighth of its size while that is still larger."""
    from PIL import Image, ImageOps
    if isinstance(raw, Image.Image):
        yield raw
        return
    if not _HEIF:
        _HEIF.append(heif())
    with Image.open(io.BytesIO(raw)) as source:
        # Never more pixels than a photo may have (saver_photos.readable reads the same limit): a crafted picture of a
        # billion pixels is refused from its header, before it is decoded.
        import saver_photos
        if source.width * source.height > saver_photos.pixel_limit(source):
            raise ValueError('picture too large')
        if draft:
            source.draft('RGB', (max(1, draft[0]), max(1, draft[1])))
        yield ImageOps.exif_transpose(source)


def size_of(raw):
    """(width, height) of a picture as a screen will see it, read from its header without decoding it: a camera that
    writes its picture turned and says so in EXIF (orientations 5 to 8) is measured the way it will be shown."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as source:
        width, height = source.size
        try:
            turned = source.getexif().get(0x0112) in (5, 6, 7, 8)
        except Exception:  # noqa: BLE001 - a picture without readable EXIF is as it is
            turned = False
    return (height, width) if turned else (width, height)


def opaque(image, ground):
    """RGB of any picture Home Assistant hands out, transparency landing on `ground` (0xRRGGBB)."""
    from PIL import Image
    if image.mode in ('RGBA', 'LA', 'P', 'PA'):
        image = image.convert('RGBA')
        flat = Image.new('RGB', image.size, rgb(ground))
        flat.paste(image, mask=image.getchannel('A'))
        return flat
    return image if image.mode == 'RGB' else image.convert('RGB')


def fills(size, box):
    """Whether a picture of `size` is about the shape of `box`: neither a quarter wider nor taller (SQUARE)."""
    (pw, ph), (bw, bh) = size, box
    return pw * bh * SQUARE[1] <= bw * ph * SQUARE[0] and bw * ph * SQUARE[1] <= pw * bh * SQUARE[0]


def fitted(size, box):
    """The largest size with the proportions of `size` within `box`, at least one pixel each way."""
    width, height = size
    scale = min(box[0] / width, box[1] / height)
    return max(1, min(box[0], round(width * scale))), max(1, min(box[1], round(height * scale)))


def rounded(size, radius):
    """A mask of `size` with corners of `radius`, smooth at its edge (CORNER_SUPERSAMPLE)."""
    from PIL import Image, ImageDraw
    w, h = size
    n = CORNER_SUPERSAMPLE
    mask = Image.new('L', (w * n, h * n))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w * n - 1, h * n - 1), radius=radius * n, fill=255)
    return mask.resize((w, h), Image.Resampling.LANCZOS)


def _perspective(size, quad):
    """Pillow's PERSPECTIVE coefficients that draw a picture of `size` into `quad` (its top left, top right, bottom
    right and bottom left corners in the output): the transform maps each output point back to the picture."""
    w, h = size
    source = [(0, 0), (w, 0), (w, h), (0, h)]
    rows, rhs = [], []
    for (x, y), (u, v) in zip(quad, source):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y]); rhs.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y]); rhs.append(v)
    # Gaussian elimination with partial pivoting: eight equations, no numpy in the app.
    n = 8
    m = [row + [r] for row, r in zip(rows, rhs)]
    for c in range(n):
        pivot = max(range(c, n), key=lambda r: abs(m[r][c]))
        m[c], m[pivot] = m[pivot], m[c]
        for r in range(n):
            if r != c and m[c][c]:
                f = m[r][c] / m[c][c]
                m[r] = [a - f * b for a, b in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def _turned(place, raw):
    """A place's picture turned and or reflected (plugin API 0.10) as an RGBA layer of the place: whole (`cover` and
    `within` alike: a turned cover is squeezed whole, as a cover turned away is) or cut to the place, the reflection fading
    out under it, transparent where nothing is drawn."""
    from PIL import Image, ImageOps
    w, h = place.w, place.h
    picture_h = max(1, round(h * 100 / (100 + MIRROR_PERCENT))) if place.mirror else h
    with opened(raw) as source:
        source = source.convert('RGBA')
        if place.turn:
            base = source.resize((max(1, round(picture_h * source.width / source.height)), picture_h), Image.Resampling.LANCZOS)
        elif place.fit in ('within', 'contain'):
            base = ImageOps.contain(source, (w, picture_h), method=Image.Resampling.LANCZOS)
        else:
            base = ImageOps.fit(source, (w, picture_h), method=Image.Resampling.LANCZOS)
    if place.radius:
        base.putalpha(Image.composite(base.getchannel('A'), Image.new('L', base.size), rounded(base.size, place.radius)))
    total = base.height + (h - picture_h if place.mirror else 0)
    tall = Image.new('RGBA', (base.width, total))
    tall.paste(base, (0, 0))
    if place.mirror and total > base.height:
        reflection = base.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, 0, base.width, total - base.height))
        ramp = Image.linear_gradient('L').resize((base.width, reflection.height))
        fade = ramp.point(lambda v: round((255 - v) * MIRROR_ALPHA))
        reflection.putalpha(Image.composite(fade, Image.new('L', reflection.size), reflection.getchannel('A')))
        tall.paste(reflection, (0, base.height))
    if not place.turn:
        out = Image.new('RGBA', (w, h))
        out.paste(tall, ((w - tall.width) // 2, (picture_h - base.height) // 2))
        return out
    # The near edge the full height, the far edge FAR_EDGE of the picture's height, both about the picture's middle.
    inset = picture_h * (1 - FAR_EDGE) / 2
    far_total = total * FAR_EDGE
    if place.turn == 'left':    # facing left: the left edge far, the right edge near (a cover right of the middle)
        quad = [(0, inset), (w, 0), (w, total), (0, inset + far_total)]
    else:                       # facing right: the right edge far (a cover left of the middle)
        quad = [(0, 0), (w, inset), (w, inset + far_total), (0, total)]
    return tall.transform((w, h), Image.Transform.PERSPECTIVE, _perspective(tall.size, quad), Image.Resampling.BICUBIC)


def _darker(image, share):
    """`image` blended `share` (0 to 1) toward black, its transparency kept."""
    from PIL import Image
    alpha = image.getchannel('A')
    out = Image.blend(image.convert('RGB'), Image.new('RGB', image.size), share).convert('RGBA')
    out.putalpha(alpha)
    return out


def _flat(place, raw):
    """A place's picture as an RGBA layer of the place, filled or whole as its fit says, shaded, darkened and rounded.
    Transparent where nothing is drawn: outside its rounded corners, beside a picture shown whole on the place's own
    ground (`within`), and where the picture itself is transparent, so what lies under the place shows there (its ground,
    or a place under it). A picture shown whole on black (`contain`) has its own transparency on the place's ground."""
    from PIL import Image, ImageOps, ImageStat
    w, h = place.w, place.h
    with opened(raw, None if isinstance(raw, Image.Image) else (w * 2, h * 2)) as source:
        image = source.convert('RGBA')
    centre = lambda inner: ((w - inner.width) // 2, (h - inner.height) // 2)
    if place.fit == 'contain':
        inner = ImageOps.contain(opaque(image, place.ground), (w, h), method=Image.Resampling.LANCZOS)
        picture = Image.new('RGBA', (w, h), (0, 0, 0, 255))
        picture.paste(inner, centre(inner))
    elif place.fit == 'within':
        inner = ImageOps.contain(image, (w, h), method=Image.Resampling.LANCZOS)
        picture = Image.new('RGBA', (w, h))
        picture.paste(inner, centre(inner))
    elif place.fit == 'whole' or (place.fit == 'auto' and not fills(image.size, (w, h))):
        inner = ImageOps.contain(opaque(image, place.ground), (w, h), method=Image.Resampling.LANCZOS)
        colour = tuple(int(c * (1 - PHOTO_GROUND_DIM)) for c in ImageStat.Stat(inner.resize((16, 16))).mean[:3])
        picture = Image.new('RGBA', (w, h), colour + (255,))
        picture.paste(inner, centre(inner))
    elif place.fit == 'saver' and not fills((w, h), (1, 1)):
        side = min(w, h)
        picture = Image.new('RGBA', (w, h), rgb(place.ground) + (255,))
        picture.paste(ImageOps.fit(opaque(image, place.ground), (side, side), Image.Resampling.LANCZOS), (0, 0))
    elif place.fit == 'exact':
        picture = image if image.size == (w, h) else image.resize((w, h), Image.Resampling.LANCZOS)
    else:
        picture = ImageOps.fit(image, (w, h), method=Image.Resampling.LANCZOS)
    if place.fade:
        ramp = Image.linear_gradient('L').resize((w, max(1, round(h * FADE_SHARE))))
        shadow = Image.new('L', (w, h))
        shadow.paste(ramp.point(lambda v: v * FADE_DEPTH // 255), (0, h - ramp.height))
        alpha = picture.getchannel('A')
        picture = Image.composite(Image.new('RGB', (w, h)), picture.convert('RGB'), shadow).convert('RGBA')
        picture.putalpha(alpha)
    if place.shade:
        picture = _darker(picture, place.shade / 255)
    if place.dim:
        picture = _darker(picture, place.dim / 100)
    if place.radius:
        picture.putalpha(Image.composite(picture.getchannel('A'), Image.new('L', (w, h)), rounded((w, h), place.radius)))
    return picture


def _overlaps(a, b):
    return a.x < b.x + b.w and b.x < a.x + a.w and a.y < b.y + b.h and b.y < a.y + a.h


def picture(question, raws):
    """The question's picture (a Pillow RGB image) from one raw picture per place (bytes, a picture a source drew, or
    None for a place without one). A place lies over the places before it; one that lies over none is first filled with
    its ground, so its rounded corners show its own ground (a page's tiles of different colours); one over another shows
    what is under it beside its picture (a plugin's cover flow)."""
    from PIL import Image
    width, height = question.box
    first = question.places[0] if question.places else None
    if first is not None and len(question.places) == 1 and first.fit == 'shrink':
        return _shrunk(first, raws[0], (width, height))
    if first is not None and len(question.places) == 1 and first.move and first.fit in ('cover', 'auto'):
        moved = _moved(first, raws[0])
        if moved is not None:
            return moved
    canvas = Image.new('RGBA', (width, height), rgb(first.ground) + (255,) if first else (0, 0, 0, 255))
    for n, (place, raw) in enumerate(zip(question.places, raws)):
        if not any(_overlaps(place, earlier) for earlier in question.places[:n]):
            canvas.paste(Image.new('RGBA', (place.w, place.h), rgb(place.ground) + (255,)), (place.x, place.y))
        if raw is None:
            continue
        try:
            layer = _turned(place, raw) if place.turn or place.mirror else _flat(place, raw)
        except Exception:  # noqa: BLE001 - a picture Pillow cannot read stays its place's ground
            if len(question.places) == 1:
                raise
            continue
        canvas.alpha_composite(layer, (place.x, place.y))
    return canvas.convert('RGB')


def _shrunk(place, raw, box):
    """A full view's still (fit `shrink`): the picture at its own proportions within the box, as large as fits; the screen
    shows it in the middle of its glass."""
    from PIL import Image
    with opened(raw, box) as source:
        image = opaque(source, place.ground)
    size = fitted(image.size, box)
    return image if image.size == size else image.resize(size, Image.Resampling.LANCZOS)


def _moved(place, raw):
    """A photo that moves slowly (`move`, picture_motion.h): cut `move` percent larger than its place on either side when
    it fills the glass, so the screen moves it within that room; None for one shown whole, painted as any place."""
    from PIL import Image, ImageOps
    from dataclasses import replace
    with opened(raw, (place.w, place.h)) as source:
        image = opaque(source, place.ground)
    if place.fit == 'auto' and not fills(image.size, (place.w, place.h)):
        return None
    big = (round(place.w * (1 + place.move / 100)), round(place.h * (1 + place.move / 100)))
    picture = ImageOps.fit(image, big, Image.Resampling.LANCZOS)
    return _flat(replace(place, w=big[0], h=big[1], fit='exact', move=0), picture).convert('RGB')


MCU = 16
# The APP15 segment a JPEG goes with (picture_fetch.h, jpeg_notes): this, its own size (width, height: it may be made
# larger to whole MCUs), then how many corners and each corner's place (x, y, w, h), radius and ground (RGB565). JPEG
# rings where a corner's edge meets its ground (white flecks on a light page around a dark cover), so the screen sets what
# lies wholly outside each arc back to the ground, exactly as a BMP has it. Every value is big-endian, 2 bytes, the
# radius 1.
JPEG_SIZE = b'TSSR'
MAX_CORNERS = 64


def _whole_mcus(image):
    """`image` grown to a multiple of MCU each way, its last column and row carried on (no seam where the screen cuts)."""
    width, height = image.size
    full = (-(-width // MCU) * MCU, -(-height // MCU) * MCU)
    if full == image.size:
        return image
    out = image.crop((0, 0) + full)  # what lies beyond is black until it is filled below
    if full[0] > width:
        out.paste(image.crop((width - 1, 0, width, height)).resize((full[0] - width, height)), (width, 0))
    if full[1] > height:
        out.paste(out.crop((0, height - 1, full[0], height)).resize((full[0], full[1] - height)), (0, height))
    return out


def jpeg_notes(body):
    """((width, height), corners) a JPEG made by encode is shown at and with: its APP15 segment, else its own size and
    no corners. Each corner (x, y, w, h, radius, ground565)."""
    from PIL import Image
    if body[2:4] == b'\xff\xef' and body[6:10] == JPEG_SIZE:
        size = int.from_bytes(body[10:12], 'big'), int.from_bytes(body[12:14], 'big')
        count, corners, at = body[14], [], 15
        for _ in range(count):
            x, y, w, h = (int.from_bytes(body[at + 2 * i:at + 2 * i + 2], 'big') for i in range(4))
            corners.append((x, y, w, h, body[at + 8], int.from_bytes(body[at + 9:at + 11], 'big')))
            at += 11
        return size, tuple(corners)
    with Image.open(io.BytesIO(body)) as image:
        return image.size, ()


def jpeg_size(body):
    """(width, height) a JPEG made by encode is shown at."""
    return jpeg_notes(body)[0]


def rgb565(colour):
    r, g, b = rgb(colour)
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def corners_of(question, size):
    """The rounded corners a screen makes exact after a JPEG of `question` at `size`: each flat place's with a radius that
    no later place lies over (a corner under another place is that place's picture), (x, y, w, h, radius, ground565).
    None for a picture of another size than the question's box (a photo cut larger to move)."""
    if tuple(size) != tuple(question.box):
        return ()
    places = question.places
    found = [(p.x, p.y, p.w, p.h, min(p.radius, 255), rgb565(p.ground)) for n, p in enumerate(places)
             if p.radius > 0 and not p.turn and not p.mirror and not any(_overlaps(p, later) for later in places[n + 1:])]
    return tuple(found[:MAX_CORNERS])


def encode(image, fmt='bmp24', corners=()):
    """`image` in the format a screen takes: `bmp24`, `bmp8` (on a palette of the picture's own 256 colours, dithered so a
    shade stays smooth: a third of the bytes, at about the quality of an RGB565 glass; Pillow's fast octree keeps it cheap
    on a Raspberry Pi) or `jpeg` (baseline, for the ESP32-P4's hardware decoder)."""
    from PIL import Image
    out = io.BytesIO()
    if fmt == 'jpeg':
        # Whole MCUs: the P4's decoder refuses a picture whose sides do not divide (a cover of 226x254, 2026-10-20: "Picture
        # sizes not divisible by 8 are not supported"), so the picture is made a multiple of 16 each way, its last row and
        # column carried on, and its own size goes along in an APP15 segment (JPEG_SIZE) the screen shows it at.
        rgb = image.convert('RGB')
        width, height = rgb.size
        padded = _whole_mcus(rgb)
        padded.save(out, 'JPEG', quality=JPEG_QUALITY, optimize=True, progressive=False, subsampling='4:2:0')
        body = out.getvalue()
        if padded.size == rgb.size and not corners:
            return body
        segment = JPEG_SIZE + width.to_bytes(2, 'big') + height.to_bytes(2, 'big') + bytes([len(corners)])
        for x, y, w, h, radius, ground in corners:
            segment += b''.join(n.to_bytes(2, 'big') for n in (x, y, w, h)) + bytes([radius]) + ground.to_bytes(2, 'big')
        return body[:2] + b'\xff\xef' + (len(segment) + 2).to_bytes(2, 'big') + segment + body[2:]
    if fmt == 'bmp8':
        palette = image.quantize(256, method=Image.Quantize.FASTOCTREE)
        image = image.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
    image.save(out, 'BMP')
    return out.getvalue()


def paint(question, raws, fmt=None):
    """The bytes a screen downloads for a question: its picture (picture()) in `fmt`, the question's own when not given."""
    image = picture(question, raws)
    fmt = fmt or question.format
    return encode(image, fmt, corners_of(question, image.size) if fmt == 'jpeg' else ())
