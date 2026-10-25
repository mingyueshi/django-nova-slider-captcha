"""Procedural raster art; only flattened PNG bytes leave the server."""
import base64
import io
import math
import random
import secrets

from PIL import Image, ImageDraw, ImageFilter

from .conf import HEIGHT, PIECE_SIZE, WIDTH


def _data_uri(image):
    output = io.BytesIO()
    image.save(output, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")


def make_puzzle():
    # Coordinates remain security-sensitive; decorative art uses its own fresh
    # seeded PRNG so pixel noise does not repeatedly consult the OS random source.
    target_x = secrets.randbelow(WIDTH - PIECE_SIZE - 12 - 60) + 60
    piece_y = secrets.randbelow(HEIGHT - PIECE_SIZE - 20 - 24) + 24
    rng = random.Random(secrets.randbits(128))
    palette = rng.choice([((15, 43, 61), (36, 153, 141)), ((28, 38, 82), (155, 119, 189)), ((33, 50, 72), (46, 136, 197))])
    canvas = Image.new("RGB", (WIDTH, HEIGHT))
    pixels = canvas.load()
    phase = rng.random() * 6
    for y in range(HEIGHT):
        for x in range(WIDTH):
            t = (x / WIDTH + y / HEIGHT) / 2
            noise = rng.randrange(-9, 10)
            wave = math.sin(x / 17 + y / 11 + phase) * 8
            pixels[x, y] = tuple(max(0, min(255, int(a * (1 - t) + b * t + noise + wave))) for a, b in zip(*palette))
    art = ImageDraw.Draw(canvas, "RGBA")
    for _ in range(35):
        x, y, radius = rng.randrange(-30, WIDTH), rng.randrange(-30, HEIGHT), rng.randrange(8, 58)
        art.ellipse((x, y, x + radius, y + radius), fill=(rng.randrange(130, 250), rng.randrange(150, 250), 230, rng.randrange(12, 55)), outline=(210, 240, 255, 65), width=1)
    for _ in range(9):
        art.line([(rng.randrange(WIDTH), rng.randrange(HEIGHT)) for _ in range(3)], fill=(220, 255, 250, rng.randrange(30, 100)), width=rng.randrange(1, 3))
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
