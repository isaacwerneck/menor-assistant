"""Sprite audit regressions: transparent, tiny, full and palette-heavy images."""
import io
from pathlib import Path
import tempfile
import unittest

from PIL import Image, ImageDraw

from src.tools import sprite_audit
from src.tools.file_analysis import service


def png(image):
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


class SpriteAuditTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "private"

    def store(self, image):
        return service.ingest(png(image), "sprite.png", root=self.root)["file"]["file_id"]

    def test_real_32x32_transparent_sprite_metrics(self):
        pic = Image.new("RGBA", (32, 32), (0, 0, 0, 0))
        ImageDraw.Draw(pic).rectangle((8, 8, 23, 23), fill=(130, 50, 190, 255))
        value = sprite_audit.audit(self.store(pic), expected_size=(32, 32), root=self.root)
        self.assertEqual(value["status"], "executed", value)
        self.assertTrue(value["technical_verified"])
        self.assertTrue(value["size_matches"])
        self.assertFalse(value["content_verified"])
        self.assertEqual(value["metrics"]["unique_rgba_colors"], 2)
        self.assertEqual(value["metrics"]["fully_transparent_pixels"], 768)
        self.assertEqual(value["metrics"]["nontransparent_bounds"], [8, 8, 24, 24])
        self.assertEqual(value["semantic_checks"]["recognizable_character"], "not_evaluated")

    def test_fully_transparent_sprite_has_no_visible_bounds(self):
        token = self.store(Image.new("RGBA", (32, 32), (0, 0, 0, 0)))
        value = sprite_audit.audit(token, root=self.root)
        self.assertIsNone(value["metrics"]["nontransparent_bounds"])
        self.assertEqual(value["metrics"]["fully_transparent_pixels"], 1024)
        self.assertFalse(value["content_verified"])

    def test_wrong_resolution_and_palette_unknown_beyond_256(self):
        pic = Image.new("RGB", (64, 64))
        for y in range(64):
            for x in range(64):
                pic.putpixel((x, y), (x, y, (x + y) % 256))
        value = sprite_audit.audit(self.store(pic), expected_size=(32, 32), root=self.root)
        self.assertFalse(value["size_matches"])
        self.assertTrue(value["metrics"]["more_than_256_colors"])
        self.assertIsNone(value["metrics"]["unique_rgba_colors"])

    def test_large_image_is_not_labeled_as_pixel_art(self):
        value = sprite_audit.audit(self.store(Image.new("RGB", (512, 512))),
                                   expected_size=(32, 32), root=self.root)
        self.assertEqual(value["status"], "executed")
        self.assertIsNone(value["metrics"])
        self.assertFalse(value["size_matches"])

    def test_text_is_not_sprite_and_errors_are_explicit(self):
        token = service.ingest(b"arquivo", "nota.txt", root=self.root)["file"]["file_id"]
        self.assertEqual(sprite_audit.audit(token, root=self.root)["status"], "unsupported")
        for size in ((8, 8), (256, 257), (True, 32), (32,), "32x32"):
            with self.subTest(size=size), self.assertRaises(ValueError):
                sprite_audit.audit(token, expected_size=size, root=self.root)

    def test_corrupted_stored_image_does_not_pass_audit(self):
        token = self.store(Image.new("RGB", (32, 32)))
        (self.root / "media" / "file_analysis" / f"{token}.blob").write_bytes(b"corrupted")
        from src.tools.file_analysis.contracts import FileRejected
        with self.assertRaises(FileRejected):
            sprite_audit.audit(token, root=self.root)


if __name__ == "__main__":
    unittest.main()
