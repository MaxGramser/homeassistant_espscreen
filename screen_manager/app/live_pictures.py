"""What a screen gets of a camera's frame (docs/CAMERA.md, "Live on the P4 boards"; docs/PICTURE_ARCHITECTURE.md,
section 4).

A P4 screen asks for a camera in a room of its glass, "1280x728" (parse_box): the full view below its top bar, a live
tile's card, a plugin's live place. Every frame goes out as a baseline JPEG the screen's hardware decoder takes as it is:
at the frame's own size where it fits the room, the screen's PPA scaling it up, else as large as fits (size_for); for a
tile that fills its card, as small as still covers it (size_to_cover). A camera's own JPEG the decoder takes (jpeg_size)
goes out untouched when it is no larger than it needs to be; anything else is made into one (remake), and a frame of
video straight from the decoder's YUV (Encoder). Pictures makes each once per frame and room, for every screen that
watches the camera; where the frames come from is camera_source's, how they travel live_stream's.
"""
import asyncio
import fractions
import io
import time

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


def remake(raw, box, cover=False):
    """A picture the P4 does not take as it is (a progressive JPEG, a PNG, one too large) as a baseline JPEG that fits,
    or that covers a live tile's card: (JPEG, CPU ms this thread spent on it)."""
    from PIL import Image
    started = time.thread_time()
    image = Image.open(io.BytesIO(raw))
    width, height = (size_to_cover if cover else size_for)(image.width, image.height, box)
    if image.format == 'JPEG':
        image.draft('RGB', (width, height))  # decoded at a fraction of its size where that is enough
    image = image.convert('RGB')
    if image.size != (width, height):
        image = image.resize((width, height), Image.BILINEAR)
    out = io.BytesIO()
    image.save(out, 'JPEG', quality=80, subsampling='4:2:0')
    return out.getvalue(), (time.thread_time() - started) * 1000


# The frames of every stream that wait for a thread or have one now: picture_service's line on a slow still reads it.
encoding = 0
# Per camera, the pictures made here that the P4's decoder would refuse (jpeg_size None: empty, too large, not baseline,
# or a width times height that is not a multiple of 8) or that failed to be made at all; camera_source's frame watch
# says them in its line.
refused = {}

class Encoder:
    """JPEGs of decoded video frames at one size, made straight from the decoder's YUV (ffmpeg's mjpeg)."""

    def __init__(self, width, height):
        import av
        self.size = (width, height)
        self.codec = av.CodecContext.create('mjpeg', 'w')
        self.codec.width, self.codec.height, self.codec.pix_fmt = width, height, 'yuvj420p'
        self.codec.time_base = fractions.Fraction(1, 90000)
        # A fixed quality: the encoder's quantiser held at QSCALE (PyAV leaves -q:v's global_quality alone for mjpeg).
        self.codec.qmin = self.codec.qmax = QSCALE
        self.count = 0

    def encode(self, frame):
        """(JPEG, CPU ms this thread spent on it)."""
        started = time.thread_time()
        width, height = self.size
        scaled = (frame.width, frame.height) != (width, height)
        picture = frame.reformat(width=width, height=height, format='yuvj420p',
                                 interpolation='BILINEAR' if scaled else None)
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

    async def picture(self, frame, box, cover=False):
        """The JPEG of `frame` for a screen with room `box` (a live tile that fills its card: `cover`), made once per
        frame and room."""
        async with self.making:
            made = self.pictures.get((box, cover))
            if made and made[0] == frame.number:
                return made[1]
            jpeg = await self.make(frame, box, cover)
            self.pictures[(box, cover)] = (frame.number, jpeg)
            return jpeg

    async def make(self, frame, box, cover=False):
        global encoding
        loop = asyncio.get_running_loop()
        sizing = size_to_cover if cover else size_for
        if frame.jpeg is not None:
            size = jpeg_size(frame.jpeg)
            # A JPEG the P4 takes as it is goes out untouched, when it is no larger than it needs to be: the screen
            # scales and cuts it itself.
            if size and size == sizing(*size, box):
                jpeg, ms = frame.jpeg, 0.0
            else:
                encoding += 1
                try:
                    jpeg, ms = await loop.run_in_executor(None, remake, frame.jpeg, box, cover)
                finally:
                    encoding -= 1
        else:
            size = sizing(frame.video.width, frame.video.height, box)
            encoder = self.encoders.get(size)
            if encoder is None:
                encoder = self.encoders[size] = Encoder(*size)
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
