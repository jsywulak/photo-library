"""Unit tests for processor.py — image resizing logic."""

import io
import sys
import unittest
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parents[1] / "lambda"))
import processor


def _make_jpeg(width: int, height: int) -> bytes:
    """Create a minimal valid JPEG of the given dimensions."""
    img = Image.new("RGB", (width, height), color=(128, 64, 32))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


class TestPrepareImage(unittest.TestCase):
    def test_small_image_passthrough(self):
        """Images under the limit are returned unchanged."""
        data = _make_jpeg(100, 100)
        self.assertLessEqual(len(data), processor.MAX_IMAGE_BYTES)
        self.assertEqual(processor._prepare_image(data), data)

    def test_large_image_is_resized(self):
        """Images over the limit are resized until they fit."""
        data = _make_jpeg(100, 100)
        original_limit = processor.MAX_IMAGE_BYTES
        try:
            # Force resizing by setting the limit just below the actual image size.
            processor.MAX_IMAGE_BYTES = len(data) - 1
            result = processor._prepare_image(data)
            self.assertLessEqual(len(result), processor.MAX_IMAGE_BYTES)
            self.assertNotEqual(result, data)
            # Result must still be a valid JPEG.
            Image.open(io.BytesIO(result)).verify()
        finally:
            processor.MAX_IMAGE_BYTES = original_limit

    def test_corrupt_image_raises_during_resize(self):
        """Corrupt image data raises an exception when resizing is attempted."""
        original_limit = processor.MAX_IMAGE_BYTES
        try:
            processor.MAX_IMAGE_BYTES = 0  # Force the resize path.
            with self.assertRaises(Exception):
                processor._prepare_image(b"not a jpeg")
        finally:
            processor.MAX_IMAGE_BYTES = original_limit

    def test_image_too_small_to_resize_raises(self):
        """Images that cannot be halved small enough raise ValueError."""
        data = _make_jpeg(4, 4)
        original_limit = processor.MAX_IMAGE_BYTES
        try:
            processor.MAX_IMAGE_BYTES = 1  # Impossible to satisfy.
            with self.assertRaises(ValueError, msg="should raise when image can't shrink further"):
                processor._prepare_image(data)
        finally:
            processor.MAX_IMAGE_BYTES = original_limit


class TestExtractCapturedAt(unittest.TestCase):
    def test_corrupt_input_returns_none_and_logs(self):
        """Corrupt image bytes return None and emit a debug log — not a silent pass."""
        with self.assertLogs("processor", level="DEBUG") as cm:
            result = processor._extract_captured_at(b"not an image")
        self.assertIsNone(result)
        self.assertTrue(
            any("EXIF" in msg or "exif" in msg.lower() for msg in cm.output),
            f"Expected EXIF-related debug log, got: {cm.output}",
        )

    def test_valid_jpeg_without_exif_returns_none(self):
        """A valid JPEG with no EXIF data returns None without error."""
        data = _make_jpeg(10, 10)
        result = processor._extract_captured_at(data)
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
