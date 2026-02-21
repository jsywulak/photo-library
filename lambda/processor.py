"""
processor.py — core photo tagging logic.

process() is the main entry point. It lists photos from a local directory,
skips any already recorded in the database, and calls the Anthropic vision
API to tag new ones. The caller is responsible for committing or rolling
back the transaction.
"""

import base64
import io
import json
import os
from pathlib import Path

from PIL import Image

# Anthropic's base64 image limit is 5 MB.
MAX_IMAGE_BYTES = 5 * 1024 * 1024


def process(location: str, db_conn, anthropic_client) -> dict:
    filenames = [f for f in os.listdir(location) if not f.startswith(".")]

    discovered = len(filenames)
    processed = 0
    skipped = 0

    with db_conn.cursor() as cur:
        for filename in filenames:
            cur.execute("SELECT id FROM photos WHERE s3_key = %s", (filename,))
            if cur.fetchone():
                skipped += 1
                continue

            _process_photo(cur, anthropic_client, location, filename)
            processed += 1

    return {"discovered": discovered, "processed": processed, "skipped": skipped}


def _prepare_image(path: Path) -> bytes:
    """Return image bytes resized to fit within Anthropic's 5 MB limit."""
    image_bytes = path.read_bytes()
    if len(image_bytes) <= MAX_IMAGE_BYTES:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))
    img = img.convert("RGB")

    # Halve dimensions until the encoded size fits.
    while True:
        img = img.resize((img.width // 2, img.height // 2), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=85)
        if buf.tell() <= MAX_IMAGE_BYTES:
            return buf.getvalue()


def _process_photo(cur, anthropic_client, location: str, filename: str) -> None:
    image_bytes = _prepare_image(Path(location, filename))
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
        (filename,),
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
