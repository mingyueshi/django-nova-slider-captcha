import base64
import io
import warnings
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase
from PIL import Image
from PIL.PngImagePlugin import PngInfo

from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import HEIGHT, PIECE_SIZE, WIDTH, background_images
from nova_slider_captcha.images import MAX_IMAGE_ATTEMPTS, MAX_IMAGE_BYTES, _read_background, make_puzzle


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


class BackgroundPoolTests(SimpleTestCase):
    def test_config_check_and_offline_behavior_do_not_expose_paths(self):
        private = "https://private.example/image.png"
        for invalid in (private, [private], [True], ["/private\x00path"], ["/valid"] * 9):
            with self.subTest(invalid=invalid), self.settings(NOVA_SLIDER_BACKGROUND_IMAGES=invalid):
                errors = captcha_settings_check(None)
                self.assertEqual([error.id for error in errors], ["nova_slider_captcha.E010"])
                self.assertNotIn(private, str(errors[0]))
                with patch("nova_slider_captcha.images._background", return_value=Image.new("RGB", (WIDTH, HEIGHT))) as procedural:
                    make_puzzle()
                procedural.assert_called_once()
        with patch("nova_slider_captcha.conf.settings", SimpleNamespace(configured=False)):
            self.assertEqual(background_images(), ())

    def test_mixed_pool_resizes_and_flattens_and_redraws_each_puzzle(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "local.png"
            art = Image.new("RGBA", (80, 80), (190, 20, 40, 0))
            art.paste((80, 120, 160, 255), (0, 20, 25, 60))
            art.paste((165, 105, 75, 255), (25, 20, 80, 60))
            meta = PngInfo()
            meta.add_text("Comment", "private metadata")
            art.save(path, pnginfo=meta)
            with self.settings(NOVA_SLIDER_BACKGROUND_IMAGES=[str(path) + ".missing", str(path)]):
                with patch("nova_slider_captcha.images.secrets.randbelow", side_effect=(0, 0, 40, 32)), patch(
                    "nova_slider_captcha.images._background",
                ) as procedural:
                    first, second = make_puzzle(), make_puzzle()
                procedural.assert_not_called()
            self.assertEqual(first[:2], (60, 24))
            self.assertEqual(second[:2], (100, 56))
            self.assertNotEqual(first[2], second[2])
            for (x, y, background, piece), rgb in ((first, (80, 120, 160)), (second, (165, 105, 75))):
                bg, tile = [Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1]))) for data in (background, piece)]
                self.assertEqual((bg.mode, bg.size, bg.info), ("RGB", (WIDTH, HEIGHT), {}))
                self.assertEqual((tile.mode, tile.size, tile.info), ("RGBA", (PIECE_SIZE, PIECE_SIZE), {}))
                self.assertEqual(tile.getpixel((20, 25)), (*rgb, 255))
                self.assertNotEqual(bg.getpixel((x + 20, y + 25)), rgb)

    def test_bad_sources_use_real_procedural_background(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            corrupt = root / "corrupt"
            corrupt.write_bytes(b"corrupt")
            large = root / "large"
            with large.open("wb") as file:
                file.truncate(MAX_IMAGE_BYTES + 1)
            oversized = root / "oversized.png"
            Image.new("L", (2001, 2000)).save(oversized)
            animated = root / "animated.png"
            Image.new("RGB", (4, 4), "red").save(
                animated, save_all=True, append_images=[Image.new("RGB", (4, 4), "blue")],
            )
            jpeg = root / "photo"
            Image.new("RGB", (80, 40), "red").save(jpeg, format="JPEG")
            symlink = root / "link"
            symlink.symlink_to(jpeg)
            self.assertEqual(_read_background(jpeg).size, (WIDTH, HEIGHT))
            for path in (root, corrupt, large, oversized, animated, symlink, root / "missing"):
                with self.subTest(path=path.name), self.settings(NOVA_SLIDER_BACKGROUND_IMAGES=[str(path)]):
                    with patch("nova_slider_captcha.images.secrets.randbelow", side_effect=(0, 0)), patch(
                        "nova_slider_captcha.images.secrets.randbits", return_value=123,
                    ):
                        _, _, data, _ = make_puzzle()
                    image = Image.open(io.BytesIO(base64.b64decode(data.split(",", 1)[1])))
                    self.assertGreater(len(set(image.getdata())), 1000)

    def test_pool_attempt_budget(self):
        with self.settings(NOVA_SLIDER_BACKGROUND_IMAGES=[str(Path.cwd() / str(index)) for index in range(8)]):
            with patch("nova_slider_captcha.images._read_background", side_effect=PermissionError("private")) as read:
                make_puzzle()
        self.assertEqual(read.call_count, MAX_IMAGE_ATTEMPTS)

    def test_pillow_pixel_warning_as_error_uses_procedural_background(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "pixel-warning.png"
            Image.new("RGB", (50, 50)).save(path)
            original_threshold = Image.MAX_IMAGE_PIXELS
            with (
                self.settings(NOVA_SLIDER_BACKGROUND_IMAGES=[str(path)]),
                patch.object(Image, "MAX_IMAGE_PIXELS", 2000),
                warnings.catch_warnings(),
                patch("nova_slider_captcha.images._background",
                      return_value=Image.new("RGB", (WIDTH, HEIGHT))) as procedural,
            ):
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                filters = warnings.filters.copy()
                make_puzzle()
                procedural.assert_called_once()
                self.assertEqual(Image.MAX_IMAGE_PIXELS, 2000)
                self.assertEqual(warnings.filters, filters)
            self.assertEqual(Image.MAX_IMAGE_PIXELS, original_threshold)
