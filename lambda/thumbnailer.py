"""
thumbnailer.py — thumbnail generation logic for AWS Lambda.

generate_thumbnail() reads a photo from S3, center-crops it to a square,
resizes to 400x400, and writes a WebP to the thumbnail bucket. Skips if the
thumbnail already exists. The caller is responsible for passing an S3 client.
"""

import io
import logging

from botocore.exceptions import ClientError
from PIL import Image, ImageOps

from utils import thumbnail_key

logger = logging.getLogger(__name__)

THUMBNAIL_SIZE = (400, 400)
THUMBNAIL_QUALITY = 85


def generate_thumbnail(s3_key: str, source_bucket: str, thumbnail_bucket: str, s3_client) -> str:
    """Generate a thumbnail for a photo. Returns 'thumbnailed' or 'skipped'."""
    thumb_key = thumbnail_key(s3_key)

    # Skip if thumbnail already exists.
    try:
        s3_client.head_object(Bucket=thumbnail_bucket, Key=thumb_key)
        logger.info("Thumbnail already exists, skipping: %s", thumb_key)
        return "skipped"
    except ClientError as e:
        if e.response["Error"]["Code"] != "404":
            raise

    # Fetch source image.
    obj = s3_client.get_object(Bucket=source_bucket, Key=s3_key)
    image_bytes = obj["Body"].read()

    # Center-crop to square, then resize.
    img = ImageOps.exif_transpose(Image.open(io.BytesIO(image_bytes))).convert("RGB")
    w, h = img.size
    size = min(w, h)
    left = (w - size) // 2
    top = (h - size) // 2
    img = img.crop((left, top, left + size, top + size))
    img = img.resize(THUMBNAIL_SIZE, Image.LANCZOS)

    # Encode as WebP and upload.
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=THUMBNAIL_QUALITY)
    buf.seek(0)
    s3_client.put_object(
        Bucket=thumbnail_bucket,
        Key=thumb_key,
        Body=buf.read(),
        ContentType="image/webp",
    )

    logger.info("Thumbnailed %s -> %s", s3_key, thumb_key)
    return "thumbnailed"
