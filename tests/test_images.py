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
