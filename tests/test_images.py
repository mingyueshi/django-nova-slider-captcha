import base64
import io
from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image

from nova_slider_captcha.conf import HEIGHT, PIECE_SIZE, WIDTH
from nova_slider_captcha.images import make_puzzle


class PuzzleImageTests(SimpleTestCase):
    def test_secure_coordinates_are_independent_of_decorative_randomness(self):
        for offsets in ((0, 0), (WIDTH - PIECE_SIZE - 12 - 61, HEIGHT - PIECE_SIZE - 20 - 25)):
            with self.subTest(offsets=offsets), patch("nova_slider_captcha.images.secrets.randbelow", side_effect=offsets) as position, patch("nova_slider_captcha.images.secrets.randbits", return_value=123) as seed:
                x, y, background, piece = make_puzzle()
            self.assertEqual((x, y), (60 + offsets[0], 24 + offsets[1]))
            self.assertEqual([call.args[0] for call in position.call_args_list], [WIDTH - PIECE_SIZE - 12 - 60, HEIGHT - PIECE_SIZE - 20 - 24])
            seed.assert_called_once_with(128)
            decoded = []
            for data in (background, piece):
                self.assertTrue(data.startswith("data:image/png;base64,"))
                image = Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1])))
                image.load()
                decoded.append(image)
            self.assertEqual(decoded[0].size, (WIDTH, HEIGHT))
            self.assertEqual(decoded[0].mode, "RGB")
            self.assertEqual(decoded[1].size, (PIECE_SIZE, PIECE_SIZE))
            self.assertEqual(decoded[1].mode, "RGBA")
            self.assertEqual(decoded[1].getchannel("A").getextrema(), (0, 255))

    def test_each_seed_produces_fresh_flattened_pixels_without_metadata(self):
        samples = []
        for seed in (123, 124, 125):
            with patch("nova_slider_captcha.images.secrets.randbelow", side_effect=(20, 20)), patch("nova_slider_captcha.images.secrets.randbits", return_value=seed):
                _, _, data, _ = make_puzzle()
            image = Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1])))
            image.load()
            self.assertFalse(image.info)
            self.assertGreater(len(set(image.getdata())), 1000)
            samples.append(image.tobytes())
        self.assertEqual(len(set(samples)), 3)

    def test_piece_and_hole_preserve_alpha_and_source_interior(self):
        source = Image.new("RGB", (WIDTH, HEIGHT), (80, 120, 160))
        with patch("nova_slider_captcha.images._background", return_value=source.copy()), patch("nova_slider_captcha.images.secrets.randbelow", side_effect=(0, 0)):
            x, y, background, piece = make_puzzle()
        bg, tile = [Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) for data in (background, piece)]
        self.assertEqual(tile.getpixel((20, 25)), (80, 120, 160, 255))
        self.assertLess(sum(bg.getpixel((x + 20, y + 25))), sum(source.getpixel((0, 0))))
        self.assertEqual(bg.getpixel((0, 0)), source.getpixel((0, 0)))
        self.assertEqual(bg.getpixel((x, y)), source.getpixel((0, 0)))
        self.assertEqual(tile.getpixel((0, 0))[3], 0)
        alpha = tile.getchannel("A")
        self.assertTrue(500 < sum(value == 255 for value in alpha.getdata()) < PIECE_SIZE ** 2)
        self.assertEqual(alpha.getbbox(), (1, 0, 44, 43))
