"""The painters picture_paint replaced (camera_feed's encoders and tile_art, app 0.4.89), frozen as they were.

tests/test_picture_paint.py paints the same pictures with the one painter and with these, and compares what a screen
would draw: proof that a screen sees the same pictures after the change. Nothing in the app imports this.
"""
import contextlib
import io
import json

COVER_RADIUS_SHARE = 12
LIVE_RADIUS_SHARE = 6
PICTURE_MAX_SIDE = 1024
PICTURE_MAX_BYTES = 1024 * 640 * 2


def capped(size, bounds=None, cap=None):
    width, height = size
    side, most = cap or (PICTURE_MAX_SIDE, PICTURE_MAX_BYTES)
    limits = [1.0, side / width, side / height, (most / (2 * width * height)) ** 0.5]
    if bounds:
        limits.extend((bounds[0] / width, bounds[1] / height))
    scale = min(limits)
    return (width, height) if scale >= 1 else (max(1, int(width * scale)), max(1, int(height * scale)))


def fit(size, box):
    """The largest size with the proportions of `size` that fits `box`, at least one pixel each way."""
    width, height = size
    scale = min(box[0] / width, box[1] / height)
    return max(1, min(box[0], round(width * scale))), max(1, min(box[1], round(height * scale)))


def encode(raw, box, exact=False):
    """Any snapshot Home Assistant hands out (JPEG, PNG, GIF, WebP) as a 24-bit BMP that fits `box`, the size of the
    screen's buffer. `exact` makes it exactly `box`: for a box that already has the picture's proportions to within a
    pixel of rounding (alert_box), so the picture and the frame the screen made for it are the same pixels."""
    from PIL import Image, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        # A JPEG decodes at a half, quarter or eighth of its size while that is still larger than the box.
        source.draft('RGB', box)
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            ground = Image.new('RGB', image.size)
            ground.paste(image, mask=image.getchannel('A'))
            image = ground
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        size = tuple(box) if exact else fit(image.size, box)
        if image.size != size:
            image = image.resize(size, Image.Resampling.LANCZOS)
        out = io.BytesIO()
        image.save(out, 'BMP')
    return out.getvalue()


# The screensaver (firmware 0.29.0+, screen_saver.py): one picture of exactly the screen's full box, the whole of it a
# little darker so the few words the screen writes over it always read, with no gradient (a 16-bit panel shows one as
# bands, GitHub #135). A camera fills the glass, cut to it the way a photo fills a frame. A cover fills it too while the
# glass is about square (SAVER_SQUARE: neither side a quarter longer than the other, saver_view.h has the same rule); on
# longer glass the cover takes the full height at the left (lying) or the full width at the top (standing), and the
# rest is the cover's own colour, where the screen writes the title.
SAVER_DIM = 0.3
SAVER_SQUARE = (5, 4)


def saver_shape(box):
    """'fill', 'side' (the cover at the left) or 'top' (the cover at the top) for a cover on glass of `box`."""
    width, height = box
    if width * SAVER_SQUARE[1] <= height * SAVER_SQUARE[0] and height * SAVER_SQUARE[1] <= width * SAVER_SQUARE[0]:
        return 'fill'
    return 'side' if width > height else 'top'


def encode_saver(raw, box, kind, ground=0):
    """The screensaver's picture of `kind` ('camera' or 'media') as a BMP of exactly `box`, darkened by SAVER_DIM;
    `ground` (0xRRGGBB) is the colour beside a cover on long glass. 8-bit on the picture's own palette, dithered, as live
    pictures go (tile_art.bmp): a third of the bytes of a full-screen picture."""
    from PIL import Image, ImageOps
    width, height = box
    with Image.open(io.BytesIO(raw)) as source:
        source.draft('RGB', box)
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            flat = Image.new('RGB', image.size)
            flat.paste(image, mask=image.getchannel('A'))
            image = flat
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        shape = 'fill' if kind == 'camera' else saver_shape(box)
        if shape == 'fill':
            picture = ImageOps.fit(image, box, Image.Resampling.LANCZOS)
        else:
            side = min(width, height)
            picture = Image.new('RGB', box, tuple((ground >> shift) & 0xFF for shift in (16, 8, 0)))
            picture.paste(ImageOps.fit(image, (side, side), Image.Resampling.LANCZOS), (0, 0))
        picture = Image.blend(picture, Image.new('RGB', box), SAVER_DIM)
    return bmp(picture, compact=True)


# A photo of the screensaver's photos step (app 0.4.89, saver_photos.py): exactly the screen's full box, not darkened
# (no words stand over it, and the standby level dims the glass already). `fit` 'auto' fills the glass with a photo about
# its shape (neither a quarter wider nor taller than the glass, the five-to-four rule of a cover) and shows a photo of
# another shape whole, on its own colour darkened; 'fill' always cuts, 'whole' never does. 8-bit on the photo's own
# palette, dithered, as every picture of the screensaver.
PHOTO_GROUND_DIM = 0.55
# A photo that moves (photos `motion: slow`, picture_motion.h) is cut this much larger than the glass on either side, the
# room the screen moves it in: 38 pixels on a 480 glass, a minute from one corner to the other at a pixel a second and a half.
MOTION_OVERSCAN = 0.08


def motion_box(box, cap=None):
    """The box a moving photo is cut to for glass of `box`: MOTION_OVERSCAN larger, or None when that does not fit the
    screen's picture memory (the 10-inch's 1280 x 800 does not: its photos stand still)."""
    big = (round(box[0] * (1 + MOTION_OVERSCAN)), round(box[1] * (1 + MOTION_OVERSCAN)))
    return big if capped(big, cap=cap) == big else None


def photo_fills(size, box, fit):
    """Whether a photo of `size` fills the glass of `box` (cut to it), or shows whole."""
    if fit == 'fill':
        return True
    if fit == 'whole':
        return False
    (pw, ph), (bw, bh) = size, box
    return pw * bh * SAVER_SQUARE[1] <= bw * ph * SAVER_SQUARE[0] and bw * ph * SAVER_SQUARE[1] <= pw * bh * SAVER_SQUARE[0]


def encode_photo(raw, box, fit='auto', moving=None):
    """The photos step's picture as a BMP of exactly `box`, or of `moving` (motion_box) for a photo that fills the glass
    and moves: the screen shows the glass's piece of it."""
    from PIL import Image, ImageOps, ImageStat
    import saver_photos
    saver_photos.heif()
    with Image.open(io.BytesIO(raw)) as source:
        if source.width * source.height > saver_photos.pixel_limit(source):
            raise ValueError('photo too large')
        source.draft('RGB', box)
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            flat = Image.new('RGB', image.size)
            flat.paste(image, mask=image.getchannel('A'))
            image = flat
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        if photo_fills(image.size, box, fit):
            picture = ImageOps.fit(image, moving or box, Image.Resampling.LANCZOS)
        else:
            whole = ImageOps.contain(image, box, Image.Resampling.LANCZOS)
            colour = tuple(int(c * (1 - PHOTO_GROUND_DIM)) for c in ImageStat.Stat(whole.resize((16, 16))).mean[:3])
            picture = Image.new('RGB', box, colour)
            picture.paste(whole, ((box[0] - whole.width) // 2, (box[1] - whole.height) // 2))
    return bmp(picture, compact=True)


def encode_cover(raw, size, background):
    """A media player's picture as a square 24-bit BMP of `size` pixels with rounded corners, the corners filled with
    `background` (0xRRGGBB): what the screen draws on its card without any work of its own. A picture that is not
    square is cut to its middle."""
    from PIL import Image, ImageDraw, ImageOps
    with Image.open(io.BytesIO(raw)) as source:
        source.draft('RGB', (size, size))
        image = ImageOps.exif_transpose(source)
        if image.mode in ('RGBA', 'LA', 'P', 'PA'):
            image = image.convert('RGBA')
            ground = Image.new('RGB', image.size, tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
            ground.paste(image, mask=image.getchannel('A'))
            image = ground
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        width, height = image.size
        side = min(width, height)
        if width != height:
            left, top = (width - side) // 2, (height - side) // 2
            image = image.crop((left, top, left + side, top + side))
        if image.size != (size, size):
            image = image.resize((size, size), Image.Resampling.LANCZOS)
        radius = max(4, size // COVER_RADIUS_SHARE)
        mask = Image.new('L', (size, size), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
        ground = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        ground.paste(image, mask=mask)
        out = io.BytesIO()
        ground.save(out, 'BMP')
    return out.getvalue()


def _square(image, size, background, radius_share):
    """The middle of `image` as a square of `size` pixels with rounded corners over `background` (0xRRGGBB)."""
    from PIL import Image, ImageDraw
    width, height = image.size
    side = min(width, height)
    if width != height:
        left, top = (width - side) // 2, (height - side) // 2
        image = image.crop((left, top, left + side, top + side))
    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    radius = max(4, size // radius_share)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    ground = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
    ground.paste(image, mask=mask)
    return ground


def _opaque(source, background):
    """An RGB image from any picture Home Assistant hands out, transparency landing on `background`."""
    from PIL import Image, ImageOps
    image = ImageOps.exif_transpose(source)
    if image.mode in ('RGBA', 'LA', 'P', 'PA'):
        image = image.convert('RGBA')
        ground = Image.new('RGB', image.size, tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        ground.paste(image, mask=image.getchannel('A'))
        return ground
    return image if image.mode == 'RGB' else image.convert('RGB')


def encode_live(raws, size, grounds, compact=False):
    """The strip a page's camera tiles share: one square of `size` pixels per tile, top to bottom, each the middle of
    its snapshot with rounded corners over that tile's colour (`grounds`, 0xRRGGBB each); a tile without a snapshot
    (None) gets a plain square of its colour. A 24-bit BMP of `size` by `size` times the number of tiles."""
    from PIL import Image
    strip = Image.new('RGB', (size, size * len(raws)))
    for n, (raw, background) in enumerate(zip(raws, grounds)):
        if raw is None:
            square = Image.new('RGB', (size, size), tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
        else:
            with Image.open(io.BytesIO(raw)) as source:
                source.draft('RGB', (size * 2, size * 2))
                square = _square(_opaque(source, background), size, background, LIVE_RADIUS_SHARE)
        strip.paste(square, (0, n * size))
    return bmp(strip, compact)


def parse(value, canvas, count, overlap=False):
    """Validated immutable (width, height, frames), or None for malformed input.

    Each frame is x, y, width, height, corner radius, darkening (0 or 170).
    The last two fields are baked into RGB pixels, avoiding device mask layers.
    Frames of different tiles never overlap; the places of one plugin tile may (`overlap`, plugin API 0.10): they are
    layers of one card, painted in their order (layers()).
    """
    if not isinstance(value, str) or len(value) > 8192 or not 1 <= count <= 64:
        return None
    try:
        frames = json.loads(value)
    except (ValueError, TypeError):
        return None
    if not isinstance(frames, list) or len(frames) != count:
        return None
    width, height = canvas
    if width <= 0 or height <= 0:
        return None
    checked = []
    right = bottom = 0
    for frame in frames:
        if not isinstance(frame, list) or len(frame) != 6 or any(type(n) is not int for n in frame):
            return None
        x, y, w, h, radius, shade = frame
        if x < 0 or y < 0 or w < 1 or h < 1 or x+w > width or y+h > height:
            return None
        if not 0 <= radius <= min(w, h)//2 or shade not in (0, 170):
            return None
        if not overlap and any(x < a+c and a < x+w and y < b+d and b < y+h for a,b,c,d,_,_ in checked):
            return None
        checked.append(tuple(frame))
        right, bottom = max(right, x+w), max(bottom, y+h)
    return right, bottom, tuple(checked)


# A plugin tile's picture turned in its place (plugin API 0.10, tessera::Turn), as the covers beside the middle one of a
# cover flow: the far edge this share of the near one's height. A reflection under a picture (tessera::ui mirror) takes
# MIRROR_PERCENT of the picture's height under it (plugin_api.h MIRROR_PERCENT, a test keeps them equal), starting at
# MIRROR_ALPHA of the picture and fading out.
FAR_EDGE = 0.70
MIRROR_PERCENT = 30
MIRROR_ALPHA = 0.38
TURNS = ('', 'left', 'right')


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


def layer(raw, w, h, radius, fit, turn='', mirror=False):
    """One place's picture as an RGBA layer of w x h: cut to the place (fit 'fill') or whole within it ('within'),
    corners rounded; with `mirror` the picture takes the top of the place and a reflection fades out under it; turned
    ('left' or 'right') the picture (and its reflection) is drawn whole in perspective, its near edge the place's height,
    its far edge FAR_EDGE of it. Transparent where nothing is drawn, so what lies under it shows."""
    from PIL import Image, ImageDraw, ImageOps
    picture_h = max(1, round(h * 100 / (100 + MIRROR_PERCENT))) if mirror else h
    with (contextlib.nullcontext(raw) if isinstance(raw, Image.Image) else Image.open(io.BytesIO(raw))) as source:
        source = ImageOps.exif_transpose(source).convert('RGBA')
        if turn:
            # Whole, at its own proportions: the turn squeezes it into the place as a cover turned away is squeezed.
            base = source.resize((max(1, round(picture_h * source.width / source.height)), picture_h), Image.Resampling.LANCZOS)
        elif fit == 'within':
            base = ImageOps.contain(source, (w, picture_h), method=Image.Resampling.LANCZOS)
        else:
            base = ImageOps.fit(source, (w, picture_h), method=Image.Resampling.LANCZOS)
    if radius:
        mask = Image.new('L', (base.width * 4, base.height * 4))
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, base.width * 4 - 1, base.height * 4 - 1), radius=radius * 4, fill=255)
        mask = mask.resize(base.size, Image.Resampling.LANCZOS)
        base.putalpha(Image.composite(base.getchannel('A'), Image.new('L', base.size), mask))
    total = base.height + (h - picture_h if mirror else 0)
    tall = Image.new('RGBA', (base.width, total))
    tall.paste(base, (0, 0))
    if mirror and total > base.height:
        reflection = base.transpose(Image.Transpose.FLIP_TOP_BOTTOM).crop((0, 0, base.width, total - base.height))
        ramp = Image.linear_gradient('L').resize((base.width, reflection.height))
        fade = ramp.point(lambda v: round((255 - v) * MIRROR_ALPHA))
        alpha = Image.composite(fade, Image.new('L', reflection.size), reflection.getchannel('A'))
        reflection.putalpha(alpha)
        tall.paste(reflection, (0, base.height))
    if not turn:
        out = Image.new('RGBA', (w, h))
        out.paste(tall, ((w - tall.width) // 2, (picture_h - base.height) // 2))
        return out
    # Turned: the near edge the full height, the far edge FAR_EDGE of the picture's height, both about the middle of
    # the picture (the reflection follows the same lines).
    inset = picture_h * (1 - FAR_EDGE) / 2
    far_total = total * FAR_EDGE
    if turn == 'left':    # facing left: the left edge far, the right edge near (a cover right of the middle)
        quad = [(0, inset), (w, 0), (w, total), (0, inset + far_total)]
    else:                 # facing right: the right edge far (a cover left of the middle)
        quad = [(0, 0), (w, inset), (w, inset + far_total), (0, total)]
    coefficients = _perspective(tall.size, quad)
    return tall.transform((w, h), Image.Transform.PERSPECTIVE, coefficients, Image.Resampling.BICUBIC)


def layers(raws, ground, atlas, styles, compact=False):
    """A plugin tile's atlas (plugin API 0.10): its places painted in their order, each over what the ones before it
    left, on the card's colour `ground` where nothing lies yet. `styles` gives each frame (fit, turn, mirror). The screen
    draws its places in the same order, the later over the earlier, and each place shows its piece of this one picture,
    so places that overlap show as layers."""
    from PIL import Image
    width, height, frames = atlas
    colour = tuple((ground >> shift) & 255 for shift in (16, 8, 0))
    image = Image.new('RGBA', (width, height), colour + (255,))
    for raw, frame, (fit, turn, mirror) in zip(raws, frames, styles):
        x, y, w, h, radius, _shade = frame
        if raw is None:
            continue
        try:
            painted = layer(raw, w, h, radius, fit, turn, mirror)
        except Exception:   # a picture Pillow cannot read stays the card's colour
            continue
        image.alpha_composite(painted, (x, y))
    return bmp(image.convert('RGB'), compact)


# The shade under a camera's name (app 0.3.8): the bottom share of the card, from clear to this much black.
FADE_SHARE = 0.42
FADE_DEPTH = 150


def bmp(image, compact=False):
    """A BMP of `image`: 24-bit, or with `compact` 8-bit on a palette of the picture's own 256 colours, dithered so a
    shade stays smooth (app 0.3.8). A third of the bytes, which is what a screen downloads and decodes in its main loop,
    at about the quality of its RGB565 glass; Pillow's fast octree keeps it cheap on a Raspberry Pi."""
    from PIL import Image
    if compact:
        palette = image.quantize(256, method=Image.Quantize.FASTOCTREE)
        image = image.quantize(palette=palette, dither=Image.Dither.FLOYDSTEINBERG)
    output = io.BytesIO()
    image.save(output, 'BMP')
    return output.getvalue()


def encode_atlas(raws, grounds, atlas, modes=None, compact=False):
    """A native-sized BMP, cropped, dimmed and rounded before transmission.

    `modes` gives each frame (fit, fade) for a camera that fills its card (app 0.3.8): fit 'fill' cuts the picture
    to the frame, 'contain' shows all of it on black and 'within' all of it on the frame's own ground (a plugin
    tile's picture, plugin API 0.10); fade darkens the bottom of the frame, where the screen writes the name. Without
    it every frame is filled, as the album covers of firmware 0.3.1 are."""
    from PIL import Image, ImageDraw, ImageOps
    width, height, frames = atlas
    image = Image.new('RGB', (width, height))
    modes = modes or [('fill', False)] * len(frames)
    for raw, background, frame, (fit, fade) in zip(raws, grounds, frames, modes):
        x, y, w, h, radius, shade = frame
        colour = tuple((background >> shift) & 255 for shift in (16, 8, 0))
        tile = Image.new('RGB', (w, h), colour)
        if raw is not None:
            # A picture the app drew itself comes as a picture, not as bytes (a map, app 0.4.33).
            with (contextlib.nullcontext(raw) if isinstance(raw, Image.Image) else Image.open(io.BytesIO(raw))) as source:
                if not isinstance(raw, Image.Image):
                    source.draft('RGB', (w*2, h*2))
                source = ImageOps.exif_transpose(source)
                # Transparent source pixels use the tile's ground, not black.
                rgba = source.convert('RGBA')
                opaque = Image.new('RGBA', rgba.size, colour + (255,))
                opaque.alpha_composite(rgba)
                if fit in ('contain', 'within'):
                    inner = ImageOps.contain(opaque.convert('RGB'), (w, h), method=Image.Resampling.LANCZOS)
                    cover = Image.new('RGB', (w, h), colour if fit == 'within' else (0, 0, 0))
                    cover.paste(inner, ((w - inner.width) // 2, (h - inner.height) // 2))
                else:
                    cover = ImageOps.fit(opaque.convert('RGB'), (w, h), method=Image.Resampling.LANCZOS)
            if fade:
                ramp = Image.linear_gradient('L').resize((w, max(1, round(h * FADE_SHARE))))
                shadow = Image.new('L', (w, h))
                shadow.paste(ramp.point(lambda v: v * FADE_DEPTH // 255), (0, h - ramp.height))
                cover = Image.composite(Image.new('RGB', (w, h)), cover, shadow)
            if shade:
                cover = Image.blend(cover, Image.new('RGB', cover.size), shade/255)
            mask = Image.new('L', (w*4, h*4))
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, w*4-1, h*4-1), radius=radius*4, fill=255)
            mask = mask.resize((w, h), Image.Resampling.LANCZOS)
            tile.paste(cover, mask=mask)
        image.paste(tile, (x, y))
    return bmp(image, compact)
