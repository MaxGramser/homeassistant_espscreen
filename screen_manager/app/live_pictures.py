"""What a screen gets of a camera's frame (docs/CAMERA.md, "Live on the P4 boards"; docs/PICTURE_ARCHITECTURE.md,
section 4).

A P4 screen asks for a camera in a room of its glass, "1280x728" (parse_box): the full view below its top bar, a live
tile's card, a plugin's live place. Every frame goes out as a baseline JPEG the screen's hardware decoder takes as it is:
at the frame's own size where it fits the room, the screen's PPA scaling it up, else as large as fits (size_for); for a
tile that fills its card, as small as still covers it (size_to_cover). A camera's own JPEG the decoder takes (jpeg_size)
goes out untouched when it is no larger than it needs to be; anything else is made into one (remake), and a frame of
video straight from the decoder's YUV (Encoder). On a screen whose glass is turned and whose hello says it takes its
live pictures so (caps picture_turn, firmware hw.cpp), they go out turned as its glass is (turned): the screen copies
them onto its glass straight, and its PPA turns nothing per picture (docs/PLATFORM_PLAN.md 4.12). Pictures
makes each once per frame, room and turn, for every screen that watches the camera; where the frames come from is
camera_source's, how they travel live_stream's.
"""
import asyncio
import fractions
import io
import logging
import time

LOG = logging.getLogger(__name__)

# The largest picture a screen takes as it is (firmware live_view::MAX_SIDE is 2048 and MAX_PICTURE 1 MB), and larger
# frames are scaled down to the room the screen asked for.
MAX_SIDE = 1920
MAX_BYTES = 1024 * 1024
MIN_SIDE, MAX_BOX = 64, 4096
QSCALE = 5                # ffmpeg's mjpeg quality (2 best, 31 worst): about 80 KB a 1280 x 720 camera picture


def parse_box(text):
    """'1280x728' from a screen: (width, height), or None for anything else."""
    try:
        width, height = (int(part) for part in str(text).lower().split('x'))
    except (TypeError, ValueError):
        return None
    return (width, height) if MIN_SIDE <= width <= MAX_BOX and MIN_SIDE <= height <= MAX_BOX else None


def size_for(width, height, box):
    """The size a frame of width x height goes out at: its own where it fits the room (the screen scales it up), else as
    large as fits, its proportions kept. Even sides, and a multiple of 16 when scaled, as the JPEG's blocks are."""
    bw, bh = box
    if width <= bw and height <= bh and width <= MAX_SIDE and height <= MAX_SIDE:
        return width - width % 2, height - height % 2
    scale = min(bw / width, bh / height, MAX_SIDE / width, MAX_SIDE / height)
    return max(16, int(width * scale) // 16 * 16), max(16, int(height * scale) // 16 * 16)


def size_to_cover(width, height, box):
    """The size a frame of width x height goes out at for a live tile that fills its card: as small as still covers the
    card, its proportions kept (the screen cuts the middle of it), and never larger than the frame: a smaller one the
    screen's PPA scales up. Every side a multiple of 8: the P4's decoder refuses a picture whose width times height is
    not a multiple of 8 (ESP-IDF jpeg_parse_marker.c, "Picture sizes not divisible by 8"), and even sides are not
    enough for that. A Guition 10.1's right-hand tiles asked 494 x 277 and got 494 x 278 pictures, every one refused,
    while the left-hand ones asked 495 x 277 and got 496 x 280 (2026-10-27)."""
    bw, bh = box
    down = lambda n: max(16, int(n) // 8 * 8)
    if width <= bw or height <= bh:
        return down(width), down(height)
    scale = max(bw / width, bh / height)
    up = lambda n: min(int(-(-n // 8) * 8), 4096)
    return min(up(width * scale), down(width)), min(up(height * scale), down(height))


# How a picture is turned for a glass turned `turn` degrees (LVGL's rotation, clockwise): so that each pixel lands where
# the screen's glass::on_panel puts that pixel of its card, with the card itself as the panel. On a glass turned 90 the
# card's pixel (x, y) of a w x h card lies at (h - 1 - y, x): the picture turned a quarter clockwise; on one turned 270
# at (y, w - 1 - x), a quarter the other way; on one turned 180 at (w - 1 - x, h - 1 - y). Pillow's ROTATE_* turn
# counter-clockwise; FFmpeg's transpose filter turns `clock` and `cclock`.
TURNS = (90, 180, 270)
PILLOW_TURN = {90: 'ROTATE_270', 180: 'ROTATE_180', 270: 'ROTATE_90'}
FFMPEG_TURN = {90: (('transpose', 'clock'),), 180: (('hflip', None), ('vflip', None)), 270: (('transpose', 'cclock'),)}


def turned(size, turn):
    """The size of a picture of `size` (width, height) turned `turn` degrees."""
    width, height = size
    return (height, width) if turn in (90, 270) else (width, height)


def turn_image(image, turn):
    """A Pillow image turned for a glass turned `turn` degrees (TURNS), or as it is for any other."""
    from PIL import Image
    return image.transpose(getattr(Image.Transpose, PILLOW_TURN[turn])) if turn in PILLOW_TURN else image


def jpeg_size(raw):
    """(width, height) of a JPEG the P4's hardware decoder takes as it is (baseline, 8 bits, one or three components
    sampled 4:4:4, 4:2:2 or 4:2:0, ESP-IDF's jpeg_parse_marker.c), at most MAX_SIDE a side; None for anything else."""
    if not isinstance(raw, (bytes, bytearray)) or raw[:2] != b'\xff\xd8' or len(raw) > MAX_BYTES:
        return None
    at = 2
    while at + 4 <= len(raw):
        if raw[at] != 0xFF:
            return None
        marker = raw[at + 1]
        if marker == 0xFF:
            at += 1
            continue
        length = int.from_bytes(raw[at + 2:at + 4], 'big')
        if marker == 0xC0:
            segment = raw[at + 4:at + 2 + length]
            if len(segment) < 6 or segment[0] != 8:
                return None
            height, width, count = int.from_bytes(segment[1:3], 'big'), int.from_bytes(segment[3:5], 'big'), segment[5]
            if count not in (1, 3) or len(segment) < 6 + 3 * count:
                return None
            if count == 3:
                factors = [segment[7 + 3 * i] for i in range(3)]
                if factors[0] not in (0x11, 0x21, 0x22) or factors[1] != 0x11 or factors[2] != 0x11:
                    return None
            if not width or not height or width > MAX_SIDE or height > MAX_SIDE or width * height % 8:
                return None
            return width, height
        if 0xC1 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return None  # progressive, lossless, arithmetic: the decoder takes baseline only
        if marker == 0xDA:
            return None  # the picture's data, and no SOF0 before it
        at += 2 + length
    return None


def remake(raw, box, cover=False, turn=0):
    """A picture the P4 does not take as it is (a progressive JPEG, a PNG, one too large, one for a turned glass) as a
    baseline JPEG that fits, or that covers a live tile's card, turned `turn` degrees: (JPEG, CPU ms this thread spent on
    it)."""
    from PIL import Image
    started = time.thread_time()
    image = Image.open(io.BytesIO(raw))
    width, height = (size_to_cover if cover else size_for)(image.width, image.height, box)
    if image.format == 'JPEG':
        image.draft('RGB', (width, height))  # decoded at a fraction of its size where that is enough
    image = image.convert('RGB')
    if image.size != (width, height):
        image = image.resize((width, height), Image.BILINEAR)
    image = turn_image(image, turn)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=80, subsampling='4:2:0')
    return out.getvalue(), (time.thread_time() - started) * 1000


# The frames of every stream that wait for a thread or have one now: picture_service's line on a slow still reads it.
encoding = 0
# Per camera, the pictures made here that the P4's decoder would refuse (jpeg_size None: empty, too large, not baseline,
# or a width times height that is not a multiple of 8) or that failed to be made at all; camera_source's frame watch
# says them in its line.
refused = {}
# Per camera, the pictures for a turned glass that could not be turned and went upright (Pictures.picture), said there
# too.
not_turned = {}

class Encoder:
    """JPEGs of decoded video frames at one size, made straight from the decoder's YUV (ffmpeg's mjpeg), turned `turn`
    degrees on the way (TURNS: FFmpeg's own filters, in YUV) for a turned glass."""

    def __init__(self, width, height, turn=0):
        import av
        self.size = (width, height)
        self.codec = av.CodecContext.create('mjpeg', 'w')
        self.codec.width, self.codec.height = turned(self.size, turn)
        self.codec.pix_fmt = 'yuvj420p'
        self.codec.time_base = fractions.Fraction(1, 90000)
        # A fixed quality: the encoder's quantiser held at QSCALE (PyAV leaves -q:v's global_quality alone for mjpeg).
        self.codec.qmin = self.codec.qmax = QSCALE
        self.count = 0
        self.graph = None
        if turn in FFMPEG_TURN:
            import av.filter
            self.graph = av.filter.Graph()
            node = self.graph.add_buffer(width=width, height=height, format='yuvj420p', time_base=self.codec.time_base)
            for name, argument in FFMPEG_TURN[turn]:
                step = self.graph.add(name, argument)
                node.link_to(step)
                node = step
            node.link_to(self.graph.add('buffersink'))
            self.graph.configure()

    def encode(self, frame):
        """(JPEG, CPU ms this thread spent on it)."""
        started = time.thread_time()
        width, height = self.size
        scaled = (frame.width, frame.height) != (width, height)
        picture = frame.reformat(width=width, height=height, format='yuvj420p',
                                 interpolation='BILINEAR' if scaled else None)
        if self.graph is not None:
            picture.pts, picture.time_base = self.count, self.codec.time_base
            self.graph.push(picture)
            picture = self.graph.pull()
        self.count += 1
        picture.pts = self.count
        jpeg = b''.join(bytes(packet) for packet in self.codec.encode(picture))
        return jpeg, (time.thread_time() - started) * 1000


class Pictures:
    """The JPEGs of one camera's frames for the screens that watch it, made once per frame and room."""

    def __init__(self, entity=None):
        self.entity = entity
        self.encoders, self.pictures = {}, {}
        self.making = asyncio.Lock()  # one picture at a time: an encoder is not for two threads
        self.made = self.made_ms = 0
        self.told_turn = False

    async def picture(self, frame, box, cover=False, turn=0):
        """(JPEG, turn) of `frame` for a screen with room `box` (a live tile that fills its card: `cover`), turned `turn`
        degrees for a turned glass (TURNS; `box` as the screen's layout has it, upright), made once per frame, room and
        turn. The turn is what it went out with: a picture that could not be turned goes upright, its turn 0, and is
        counted (not_turned), so the screen turns it itself as it did before it took turned pictures, and never goes
        without one."""
        async with self.making:
            key = (box, cover, turn)
            made = self.pictures.get(key)
            if made and made[0] == frame.number:
                return made[1], made[2]
            done = turn if turn in TURNS else 0
            try:
                jpeg = await self.make(frame, box, cover, done)
            except Exception as error:  # noqa: BLE001 - whatever failed in turning, the upright picture goes instead
                if not done:
                    raise
                self.turn_failed(error)
                jpeg, done = await self.make(frame, box, cover, 0), 0
            self.pictures[key] = (frame.number, jpeg, done)
            return jpeg, done

    def turn_failed(self, error):
        if self.entity:
            not_turned[self.entity] = not_turned.get(self.entity, 0) + 1
        if not self.told_turn:
            self.told_turn = True
            LOG.warning('Live %s: a picture for a turned glass could not be turned (%s); it goes upright, and the screen '
                        'turns it', self.entity, error)

    async def make(self, frame, box, cover=False, turn=0):
        global encoding
        loop = asyncio.get_running_loop()
        sizing = size_to_cover if cover else size_for
        if frame.jpeg is not None:
            size = jpeg_size(frame.jpeg)
            # A JPEG the P4 takes as it is goes out untouched, when it is no larger than it needs to be and needs no
            # turn: the screen scales and cuts it itself.
            if size and size == sizing(*size, box) and turn not in TURNS:
                jpeg, ms = frame.jpeg, 0.0
            else:
                encoding += 1
                try:
                    jpeg, ms = await loop.run_in_executor(None, remake, frame.jpeg, box, cover, turn)
                finally:
                    encoding -= 1
        else:
            size = sizing(frame.video.width, frame.video.height, box)
            encoder = self.encoders.get((size, turn))
            if encoder is None:
                encoder = self.encoders[(size, turn)] = Encoder(*size, turn=turn)
            encoding += 1
            try:
                jpeg, ms = await loop.run_in_executor(None, encoder.encode, frame.video)
            except Exception:
                self.refuse()
                raise
            finally:
                encoding -= 1
        if jpeg is not frame.jpeg and jpeg_size(jpeg) is None:
            self.refuse()
        self.made += 1
        self.made_ms += ms
        return jpeg

    def refuse(self):
        if self.entity:
            refused[self.entity] = refused.get(self.entity, 0) + 1
