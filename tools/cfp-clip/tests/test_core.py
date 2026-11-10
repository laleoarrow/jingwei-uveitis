import io
import hashlib
import unittest

from PIL import Image

from core import load_image, make_circular_clip


class CropTests(unittest.TestCase):
    def test_draft_mask_and_rounding(self):
        image = Image.new("RGB", (20, 20), "white")
        result = make_circular_clip(image, (10, 6), (10, 10))
        self.assertEqual(result.size, (12, 12))
        self.assertEqual(result.getpixel((0, 0)), (0, 0, 0))
        self.assertEqual(result.getpixel((6, 6)), (255, 255, 255))
        # Fixed raster mask from the supplied draft, not a floating circle test.
        rows = ["000011111000", "000111111100", "001111111110", "011111111111",
                "111111111111", "111111111111", "111111111111", "111111111111",
                "111111111111", "011111111111", "001111111110", "000111111100"]
        observed = ["".join("1" if result.getpixel((x, y))[0] else "0" for x in range(12)) for y in range(12)]
        self.assertEqual(observed, rows)

    def test_edge_crop_keeps_native_pixels_and_input(self):
        source = Image.new("RGB", (12, 10))
        source.putdata([(x * 10, y * 10, 100) for y in range(10) for x in range(12)])
        before = source.tobytes()
        result = make_circular_clip(source, (4, 2), (1, 2))
        self.assertEqual(result.size, (6, 7))
        self.assertEqual(result.getpixel((1, 2)), source.getpixel((1, 2)))
        self.assertEqual(source.tobytes(), before)

    def test_fractional_points(self):
        result = make_circular_clip(Image.new("RGB", (100, 80), "red"), (42.25, 30.5), (49.75, 42.25))
        self.assertEqual(result.size, (43, 43))

    def test_pixels_match_supplied_draft_golden_results(self):
        # Computed by executing only make_circular_clip from the supplied draft.
        image = Image.new("RGB", (100, 80))
        image.putdata([(x * 2, y * 3, (x + y) % 256) for y in range(80) for x in range(100)])
        cases = [
            ((42.25, 30.5), (49.75, 42.25), "0255cf8af4eeecf94f54395ec871c638addcdfd50be881aba161fb4708962e72"),
            ((4, 2), (1, 2), "66ffdef374c5bc8eced4d93528b25875f5d1976ad6712148eb343a8df3df335d"),
            ((90, 1), (98, 2), "d6d3334bfb560418730d5af4fce60f2eae97a32f2ca0d4c76af64a56b2ef89ce"),
            ((0, 0), (99, 79), "bfe827c0f61bbb07e795fd87d6728d1a9be446c41fc1234839583ef73a1401b3"),
        ]
        for first, center, expected in cases:
            with self.subTest(first=first, center=center):
                result = make_circular_clip(image, first, center)
                self.assertEqual(hashlib.sha256(result.tobytes()).hexdigest(), expected)

    def test_invalid_points_rejected(self):
        image = Image.new("RGB", (20, 20))
        for point in (None, [1], [True, 2], ["1", 2], [float("nan"), 2], [float("inf"), 2], [10**1000, 2], [-1, 2], [20, 2]):
            with self.subTest(point=point), self.assertRaises(ValueError):
                make_circular_clip(image, point, (10, 10))
        with self.assertRaises(ValueError):
            make_circular_clip(image, (10, 10), (10, 10))

    def test_exif_orientation_is_applied(self):
        source = Image.new("RGB", (12, 8), "red")
        exif = Image.Exif()
        exif[274] = 6
        buffer = io.BytesIO()
        source.save(buffer, format="JPEG", exif=exif)
        image = load_image(buffer.getvalue())
        self.assertEqual(image.size, (8, 12))
        self.assertEqual(image.mode, "RGB")

    def test_first_frame_and_rgb(self):
        first = Image.new("P", (10, 10), 0)
        second = Image.new("P", (10, 10), 1)
        buffer = io.BytesIO()
        first.save(buffer, format="GIF", save_all=True, append_images=[second])
        self.assertEqual(load_image(buffer.getvalue()).mode, "RGB")


if __name__ == "__main__":
    unittest.main()
