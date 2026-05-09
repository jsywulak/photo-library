"""Unit tests for exif.py — EXIF DateTimeOriginal extraction."""

import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "lambda"))
import exif


def _make_jpeg(width: int, height: int) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestExtractCapturedAt(unittest.TestCase):
    def test_corrupt_input_returns_none_and_logs(self):
        """Corrupt image bytes return None and emit a debug log — not a silent pass."""
        with self.assertLogs("exif", level="DEBUG") as cm:
            result = exif.extract_captured_at(b"not an image")
        self.assertIsNone(result)
        self.assertTrue(
            any("EXIF" in msg or "exif" in msg.lower() for msg in cm.output),
            f"Expected EXIF-related debug log, got: {cm.output}",
        )

    def test_valid_jpeg_without_exif_returns_none(self):
        """A valid JPEG with no EXIF data returns None without error."""
        data = _make_jpeg(10, 10)
        result = exif.extract_captured_at(data)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
