"""Procedural or host-supplied raster art; only flattened PNG bytes leave the server."""
import base64
import io
import math
import os
import random
import secrets
import stat

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageOps

from .conf import HEIGHT, PIECE_SIZE, WIDTH, background_images

MAX_IMAGE_BYTES = 4 * 1024 * 1024
MAX_IMAGE_PIXELS = 4_000_000
MAX_IMAGE_SIDE = 4096
MAX_IMAGE_ATTEMPTS = 3


def _read_background(path):
    # Check the file before opening, then validate the descriptor before reading.
    # Nonblocking and no-follow flags also protect against replacement on POSIX.
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode):
        return None
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as file:
        opened = os.fstat(file.fileno())
        if not stat.S_ISREG(opened.st_mode) or not os.path.samestat(before, opened) or not 0 < opened.st_size <= MAX_IMAGE_BYTES:
            return None
        data = file.read(MAX_IMAGE_BYTES + 1)
    if len(data) > MAX_IMAGE_BYTES:
        return None
    with Image.open(io.BytesIO(data), formats=("JPEG", "PNG")) as source:
        width, height = source.size
        if (not 0 < min(width, height) <= max(width, height) <= MAX_IMAGE_SIDE
                or width * height > MAX_IMAGE_PIXELS or getattr(source, "is_animated", False)):
            return None
        art = ImageOps.fit(source.convert("RGBA"), (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (WIDTH, HEIGHT), (45, 56, 65))
        canvas.paste(art, mask=art.getchannel("A"))
        return canvas


def _choose_background(rng):
    try:
        paths = list(dict.fromkeys(background_images()))
    except ValueError:
        paths = []
    if paths:
        rng.shuffle(paths)
        for path in paths[:MAX_IMAGE_ATTEMPTS]:
            try:
                canvas = _read_background(path)
            except (OSError, ValueError, SyntaxError, EOFError, Image.DecompressionBombError, Image.DecompressionBombWarning):
                continue
            if canvas is not None:
                return canvas
    return _background(rng)


def _data_uri(image):
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def _background(rng):
    palette = rng.choice([((15, 43, 61), (36, 153, 141)), ((28, 38, 82), (155, 119, 189)), ((33, 50, 72), (46, 136, 197))])
    phase = rng.random() * 6
    # Tiny ramps and a one-row sine lookup are expanded by Pillow's C kernels.
    # Avoid 51,200 Python pixel/tuple iterations without a NumPy dependency.
    ramp = Image.new("L", (2, 1))
    ramp.putdata((0, 255))
    horizontal = ramp.resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    vertical = ramp.transpose(Image.Transpose.ROTATE_270).resize((WIDTH, HEIGHT), Image.Resampling.BILINEAR)
    gradient = ImageChops.add(horizontal, vertical, scale=2)
    canvas = ImageOps.colorize(gradient, palette[0], palette[1])
    span = math.ceil(WIDTH + HEIGHT * 17 / 11) + 2
    wave = Image.new("L", (span, 1))
    wave.putdata([int(8 + math.sin(i / 17 + phase) * 8) for i in range(span)])
    wave = wave.transform((WIDTH, HEIGHT), Image.Transform.AFFINE,
                          (1, 17 / 11, 0, 0, 0, 0), Image.Resampling.BILINEAR)
    # randbytes uses this image's fresh decorative PRNG, never the answer RNG.
    noise = Image.frombytes("L", (WIDTH, HEIGHT), rng.randbytes(WIDTH * HEIGHT)).point(lambda value: value % 19)
    texture = ImageChops.add(noise, wave).convert("RGB")
    canvas = ImageChops.add(canvas, texture, offset=-17)
    art = ImageDraw.Draw(canvas, "RGBA")
    for _ in range(35):
        x, y, radius = rng.randrange(-30, WIDTH), rng.randrange(-30, HEIGHT), rng.randrange(8, 58)
        art.ellipse((x, y, x + radius, y + radius), fill=(rng.randrange(130, 250), rng.randrange(150, 250), 230, rng.randrange(12, 55)), outline=(210, 240, 255, 65), width=1)
    for _ in range(9):
        art.line([(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(3)], fill=(220, 255, 250, rng.randrange(30, 100)), width=rng.randrange(1, 3))
    return canvas


def make_puzzle():
    # Coordinates stay on secrets and are independent of all decorative PRNG
    # output. Every call uses a fresh 128-bit seed; there is no image-set cache.
    target_x = secrets.randbelow(WIDTH - PIECE_SIZE - 12 - 60) + 60
    piece_y = secrets.randbelow(HEIGHT - PIECE_SIZE - 20 - 24) + 24
    rng = random.Random(secrets.randbits(128))
    canvas = _choose_background(rng)
    mask = Image.new("L", (PIECE_SIZE, PIECE_SIZE), 0)
    shape = ImageDraw.Draw(mask)
    shape.rounded_rectangle((1, 9, 35, 42), radius=4, fill=255)
    shape.ellipse((13, 0, 26, 16), fill=255)
    shape.ellipse((28, 18, 43, 32), fill=255)
    shape.ellipse((-6, 18, 8, 31), fill=0)
    piece = canvas.crop((target_x, piece_y, target_x + PIECE_SIZE, piece_y + PIECE_SIZE)).convert("RGBA")
    piece.putalpha(mask)
    edge = Image.frombytes("L", mask.size, bytes(max(0, a - b) for a, b in zip(mask.tobytes(), mask.filter(ImageFilter.MinFilter(3)).tobytes())))
    piece.paste((240, 255, 255, 255), (0, 0), edge)
    dark = Image.new("RGB", mask.size, (11, 26, 40))
    canvas.paste(dark, (target_x, piece_y), mask.point(lambda v: int(v * .83)))
    canvas.paste((206, 248, 251), (target_x, piece_y, target_x + PIECE_SIZE, piece_y + PIECE_SIZE), edge)
    return target_x, piece_y, _data_uri(canvas), _data_uri(piece)
