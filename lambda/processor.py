"""
processor.py — single-image tagging logic for AWS Lambda.

process_one() is the Lambda entry point. It receives an s3_key and the image
bytes, checks whether the photo has already been processed, and if not calls
the Anthropic vision API to tag it and stores the results. The caller is
responsible for fetching the image bytes and for committing or rolling back
the transaction.
"""

import base64
import io
import json
import logging

from PIL import Image

logger = logging.getLogger(__name__)

# Anthropic's base64 image limit is 5 MB.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def process_one(s3_key: str, image_bytes: bytes, db_conn, anthropic_client) -> str:
    """Process a single image. Returns 'processed' or 'skipped'."""
    with db_conn.cursor() as cur:
        # Atomically claim the row. ON CONFLICT means it's already processed.
        cur.execute(
            "INSERT INTO photos (s3_key) VALUES (%s) ON CONFLICT (s3_key) DO NOTHING RETURNING id",
            (s3_key,),
        )
        row = cur.fetchone()
        if row is None:
            return "skipped"
        photo_id = row[0]

        image_bytes = _prepare_image(image_bytes)
        _tag_photo(cur, anthropic_client, photo_id, image_bytes)

    return "processed"


def _prepare_image(image_bytes: bytes) -> bytes:
    """Resize image bytes to fit within Anthropic's 5 MB limit if needed."""
    if len(image_bytes) <= MAX_IMAGE_BYTES:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Halve dimensions until the encoded size fits.
    while True:
        if img.width < 2 or img.height < 2:
            raise ValueError(
                f"Image could not be resized below {MAX_IMAGE_BYTES} bytes "
                f"(final dimensions: {img.width}x{img.height})"
            )
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()


def _tag_photo(cur, anthropic_client, photo_id: int, image_bytes: bytes) -> None:
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    response = anthropic_client.messages.create(
        model="claude-opus-4-6",
        max_tokens=2048,
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": image_b64,
                    },
                },
                {
                    "type": "text",
                    "text": (
                        "Analyze this photo. Focus on the aesthetic elements and visual design of the room, especially the florals and the colors. Ignore any people in the photos. Ignore any technical aspects of the photography itself. If you recognize any specifically Indian ceremonianal items, please call those out. Respond with a JSON object containing:\n"
                        '  "summary": a one-sentence description\n'
                        '  "tags": a list of 20-30 descriptive single words (ideal) or short phases (less preferred)\n'
                        "Respond with JSON only, no other text."
                    ),
                },
            ],
        }],
    )

    if not response.content or not hasattr(response.content[0], "text"):
        raise ValueError(f"Unexpected Anthropic response structure: {response.content!r}")

    text = response.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()

    try:
        result = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Failed to parse Anthropic response as JSON: {e}\nRaw response: {text!r}"
        ) from e

    cur.execute("UPDATE photos SET processed_at = NOW() WHERE id = %s", (photo_id,))

    tags = result.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError(f"Expected 'tags' to be a list, got {type(tags)}: {tags!r}")

    for tag_name in tags:
        if not isinstance(tag_name, str):
            logger.warning("Skipping non-string tag: %r", tag_name)
            continue
        cur.execute(
            """
            INSERT INTO tags (name) VALUES (%s)
            ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (tag_name.lower().strip(),),
        )
        tag_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (photo_id, tag_id),
        )
