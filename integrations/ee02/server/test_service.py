import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from PIL import Image
import service


class PublicationTest(unittest.TestCase):
    def test_white_background_stays_white(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_data = service.DATA
            self.addCleanup(setattr, service, "DATA", old_data)
            service.DATA = Path(tmp)
            manifest = service.publish(Image.new("RGB", (1200, 1600), "white"), "ready", [])
            with Image.open(Path(tmp) / manifest["image"].lstrip("/")) as image:
                self.assertEqual(image.getextrema(), ((255, 255), (255, 255), (255, 255)))

    def test_publication_preserves_old_images_and_last_good_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            old_data = service.DATA
            self.addCleanup(setattr, service, "DATA", old_data)
            service.DATA = Path(tmp)
            first = service.publish(Image.new("RGB", (1200, 1600), "red"), "ready", [])
            first_path = Path(tmp) / first["image"].lstrip("/")
            first_bytes = first_path.read_bytes()
            self.assertEqual(first["version"], hashlib.sha256(first_bytes).hexdigest())
            second = service.publish(Image.new("RGB", (1200, 1600), (140, 170, 99)), "ready", [])
            self.assertNotEqual(first["version"], second["version"])
            self.assertEqual(first_path.read_bytes(), first_bytes)
            with Image.open(Path(tmp) / second["image"].lstrip("/")) as image:
                palette = {tuple(service.PALETTE[i:i + 3]) for i in range(0, 18, 3)}
                self.assertTrue(set(image.getdata()).issubset(palette))
            with self.assertRaises(ValueError):
                service.publish(Image.new("RGB", (1, 1)), "ready", [])
            self.assertEqual(json.loads((Path(tmp) / "manifest.json").read_text()), second)


if __name__ == "__main__":
    unittest.main()
