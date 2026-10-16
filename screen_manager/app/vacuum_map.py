"""A robot vacuum's map, cleaned up and in the screen's colours, for the vacuum card (module_vacuum.h).

A robot's map comes as the integration draws it: Roborock's is a PNG of 1508 x 1116 of which 780 x 395 is drawn, every
cell of its grid four pixels wide, rooms in loud colours, a carpet hatched in green and a speck for every chair leg.
Next to the screen's soft cards it looked like a foreign object, and on a dark screen it was a bright block. So the map
is read for what it says, generically and without knowing a brand:

1. cut to what is drawn (the alpha's box), and brought back to the robot's own grid (the size every colour run along a
   row is a multiple of);
2. the large flat colours are rooms; the darkest of them is the walls; a colour in many tiny pieces (a carpet's hatch)
   is no room;
3. specks of any other colour inside a room take the room's colour, and wall islands of one or two cells go; the robot
   itself (the largest light blob) stays, at its full size;
4. rooms get soft tints in the screen's look, by size, walls one ink, and the inside of a thick wall a lighter mass,
   so a wall reads as its edge;
5. back to full size with a mode filter, which draws the grid's stairs as smooth contours.

A map that is no flat drawing (a photo-like render with more than eight large colours) is only cut and fitted. The
colours are the screen's own (theme.h: SLATE for the walls in the light look, MUTED in the dark one; the rooms are the
tile palette's soft tints), written here as map_card.py writes its own, since the picture is drawn here.
"""
import io
from collections import Counter, deque

# Light and dark: the rooms by size (the largest first), the walls and a thick wall's inside.
LIGHT = {'rooms': ((0xD3, 0xE6, 0xF7), (0xF6, 0xD9, 0xD2), (0xE4, 0xDA, 0xF4), (0xF7, 0xE3, 0xC8), (0xD5, 0xEE, 0xDF), (0xEE, 0xEE, 0xD0)),
         'walls': (0x5E, 0x6E, 0x7E), 'mass': (0xB4, 0xBF, 0xCA)}
DARK = {'rooms': ((0x24, 0x3A, 0x50), (0x4A, 0x2E, 0x2E), (0x37, 0x2D, 0x4E), (0x4A, 0x3A, 0x22), (0x22, 0x40, 0x31), (0x3E, 0x3E, 0x26)),
        'walls': (0xA9, 0xB6, 0xC3), 'mass': (0x5C, 0x67, 0x73)}
LARGE_SHARE = 0.02      # a colour on at least this share of the cells is a room or the walls
ROOM_PIECE = 0.01       # ...and a room has at least one piece this large (a hatch has none)
MAX_LARGE = 8           # more large colours than this: a picture, not a drawing


def grid(image):
    """The size of one map cell in pixels: the largest g that nearly every colour run along a row is a multiple of (the
    first run of a row, cut by the crop, and the robot's smooth edge don't count)."""
    px = image.load()
    runs = []
    for y in range(0, image.height, 5):
        row, run = [], 1
        for x in range(1, image.width):
            if px[x, y] == px[x - 1, y]:
                run += 1
            else:
                row.append(run)
                run = 1
        runs += row[1:]
    for g in (8, 6, 5, 4, 3, 2):
        if runs and sum(r % g == 0 for r in runs) >= 0.9 * len(runs):
            return g
    return 1


def components(cells, w, h, keep):
    """Connected areas (4-neighbour) of cells whose colour `keep` takes: [(colour, [indices])]."""
    seen = bytearray(w * h)
    out = []
    for i in range(w * h):
        if seen[i] or not keep(cells[i]):
            continue
        colour = cells[i]
        queue, part = deque([i]), []
        seen[i] = 1
        while queue:
            j = queue.popleft()
            part.append(j)
            x, y = j % w, j // w
            for k in ((j - 1) if x else -1, (j + 1) if x < w - 1 else -1, (j - w) if y else -1, (j + w) if y < h - 1 else -1):
                if k >= 0 and not seen[k] and cells[k] == colour:
                    seen[k] = 1
                    queue.append(k)
        out.append((colour, part))
    return out


class Drawing:
    """The map read once: its cells, which colour is which, and the robot. `styled(dark)` paints it in a look."""

    def __init__(self, image):
        from PIL import Image
        box = image.getchannel('A').getbbox()
        self.full = image.crop(box) if box else image
        self.g = grid(self.full)
        small = self.full.resize((max(1, self.full.width // self.g), max(1, self.full.height // self.g)), Image.Resampling.NEAREST)
        self.w, self.h = small.size
        cells = list(small.get_flattened_data() if hasattr(small, 'get_flattened_data') else small.getdata())
        n = self.w * self.h
        count = Counter(c for c in cells if c[3] == 255)
        large = [c for c, k in count.most_common() if k >= n * LARGE_SHARE]
        self.flat = 2 <= len(large) <= MAX_LARGE
        if not self.flat:
            return
        self.walls = min(large, key=lambda c: c[0] + c[1] + c[2])
        pieces = {c: max(len(p) for _, p in components(cells, self.w, self.h, lambda k, c=c: k == c)) for c in large if c != self.walls}
        self.rooms = sorted((c for c, size in pieces.items() if size >= n * ROOM_PIECE), key=lambda c: -count[c])
        rooms = set(self.rooms)
        w, h = self.w, self.h

        def around(i):
            x, y = i % w, i // w
            votes = Counter()
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    if 0 <= x + dx < w and 0 <= y + dy < h and cells[(y + dy) * w + x + dx] in rooms:
                        votes[cells[(y + dy) * w + x + dx]] += 1
            return votes.most_common(1)[0][0] if votes else None

        others = components(cells, w, h, lambda c: c[3] > 0 and c not in rooms and c != self.walls)
        robot = max((p for c, p in others if c[0] > 230 and c[1] > 230 and c[2] > 230), key=len, default=[])
        self.robot = None
        if robot:
            xs, ys = [i % w for i in robot], [i // w for i in robot]
            self.robot = (min(xs) - 3, min(ys) - 3, max(xs) + 3, max(ys) + 3)
        fixed = list(cells)
        for _, part in others:
            for i in part:
                if not self.in_robot(i) and (room := around(i)):
                    fixed[i] = room
        for _, part in components(cells, w, h, lambda c: c == self.walls):
            if len(part) <= 2:
                for i in part:
                    if (room := around(i)):
                        fixed[i] = room
        if self.robot:
            for i in range(n):
                if self.in_robot(i) and fixed[i] not in rooms and fixed[i] != self.walls and (room := around(i)):
                    fixed[i] = room

        def mass(i):
            x, y = i % w, i // w
            return all(0 <= x + dx < w and 0 <= y + dy < h and fixed[(y + dy) * w + x + dx] == self.walls
                       for dx in (-1, 0, 1) for dy in (-1, 0, 1))
        self.inner = {i for i in range(n) if fixed[i] == self.walls and mass(i)}
        self.cells = fixed

    def in_robot(self, i):
        if not self.robot:
            return False
        x, y = i % self.w, i // self.w
        return self.robot[0] <= x <= self.robot[2] and self.robot[1] <= y <= self.robot[3]

    def styled(self, dark):
        """The map in the screen's look, at its full size (RGBA): made once per look, whatever sizes are asked of it."""
        cache = self.__dict__.setdefault('_styled', {})
        if bool(dark) not in cache:
            cache[bool(dark)] = self._styled_once(dark)
        return cache[bool(dark)]

    def _styled_once(self, dark):
        from PIL import Image, ImageFilter
        if not self.flat:
            return self.full
        palette = DARK if dark else LIGHT
        tint = {c: palette['rooms'][k % len(palette['rooms'])] + (255,) for k, c in enumerate(self.rooms)}
        walls, mass = palette['walls'] + (255,), palette['mass'] + (255,)
        out = []
        for i, c in enumerate(self.cells):
            if i in self.inner:
                out.append(mass)
            elif c == self.walls:
                out.append(walls)
            else:
                out.append(tint.get(c, c if c[3] else (0, 0, 0, 0)))
        image = Image.new('RGBA', (self.w, self.h))
        image.putdata(out)
        g = self.g
        image = image.resize((self.w * g, self.h * g), Image.Resampling.NEAREST)
        if g > 1:
            image = image.filter(ImageFilter.ModeFilter(g + 1))
        if self.robot:
            # The robot as the integration drew it, at its full size, over the cleaned map.
            full, px = self.full.load(), image.load()
            ground = set(self.rooms) | {self.walls}
            x0, y0 = max(0, self.robot[0] * g), max(0, self.robot[1] * g)
            x1, y1 = min(image.width, (self.robot[2] + 1) * g), min(image.height, (self.robot[3] + 1) * g)
            for y in range(y0, min(y1, self.full.height)):
                for x in range(x0, min(x1, self.full.width)):
                    c = full[x, y]
                    if c[3] and c[:3] + (255,) not in ground:
                        a, b = c[3] / 255, px[x, y]
                        px[x, y] = tuple(round(c[k] * a + b[k] * (1 - a)) for k in range(3)) + (255,)
        return image


def read(raw):
    """The map Home Assistant hands out (PNG, JPEG, SVG rendered by the integration as PNG) read once."""
    from PIL import Image
    with Image.open(io.BytesIO(raw)) as source:
        return Drawing(source.convert('RGBA'))


def render(drawing, box, background, dark):
    """A 24-bit BMP of exactly `box` (width, height): the map fitted in the middle, on `background` (0xRRGGBB, the card's
    colour, which the map's empty parts take)."""
    from PIL import Image
    image = drawing.styled(dark)
    width, height = box
    scale = min(width / image.width, height / image.height)
    size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
    # Premultiplied while it is scaled, so the empty parts don't darken the edges they meet.
    fitted = image.convert('RGBa').resize(size, Image.Resampling.LANCZOS if scale > 1 else Image.Resampling.BOX).convert('RGBA')
    ground = Image.new('RGB', box, tuple((background >> shift) & 0xFF for shift in (16, 8, 0)))
    ground.paste(fitted, ((width - size[0]) // 2, (height - size[1]) // 2), fitted)
    out = io.BytesIO()
    ground.save(out, 'BMP')
    return out.getvalue()
