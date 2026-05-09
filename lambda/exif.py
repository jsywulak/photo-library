"""EXIF helpers shared across Lambdas.

extract_captured_at() returns the EXIF DateTimeOriginal as a datetime, or None
if the tag is absent or unparseable. The value lives in the Exif Sub-IFD on
camera files but some encoders embed it in the main IFD; we check both.
"""

import io
import logging
from datetime import datetime

from PIL import Image

logger = logging.getLogger(__name__)

_EXIF_DATETIME_ORIGINAL = 36867
_EXIF_DATETIME_FORMAT = "%Y:%m:%d %H:%M:%S"
_EXIF_SUB_IFD = 34665


def extract_captured_at(image_bytes: bytes) -> datetime | None:
    try:
        img = Image.open(io.BytesIO(image_bytes))
        exif = img.getexif()
        raw = exif.get_ifd(_EXIF_SUB_IFD).get(_EXIF_DATETIME_ORIGINAL) or exif.get(_EXIF_DATETIME_ORIGINAL)
        if raw:
            return datetime.strptime(raw, _EXIF_DATETIME_FORMAT)
    except Exception as e:
        logger.debug("Could not extract EXIF captured_at: %s", e)
    return None
