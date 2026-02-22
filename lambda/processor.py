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

from PIL import Image

# Anthropic's base64 image limit is 5 MB.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def process_one(s3_key: str, image_bytes: bytes, db_conn, anthropic_client) -> str:
    """Process a single image. Returns 'processed' or 'skipped'."""
    with db_conn.cursor() as cur:
        cur.execute("SELECT id FROM photos WHERE s3_key = %s", (s3_key,))
        if cur.fetchone():
            return "skipped"

        image_bytes = _prepare_image(image_bytes)
        _tag_photo(cur, anthropic_client, s3_key, image_bytes)

    return "processed"


def _prepare_image(image_bytes: bytes) -> bytes:
    """Resize image bytes to fit within Anthropic's 5 MB limit if needed."""
    if len(image_bytes) <= MAX_IMAGE_BYTES:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    # Halve dimensions until the encoded size fits.
    while True:
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()


def _tag_photo(cur, anthropic_client, s3_key: str, image_bytes: bytes) -> None:
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

    text = response.content[0].text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    result = json.loads(text)

    cur.execute(
        "INSERT INTO photos (s3_key, processed_at) VALUES (%s, NOW()) RETURNING id",
        (s3_key,),
    )
    photo_id = cur.fetchone()[0]

    for tag_name in result.get("tags", []):
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
