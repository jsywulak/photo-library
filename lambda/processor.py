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
import os

from PIL import Image

logger = logging.getLogger(__name__)

# Anthropic's 5 MB limit applies to the base64-encoded image, not raw bytes.
# Base64 inflates size by ~33%, so the safe raw ceiling is 5 MB * 3/4 = 3.75 MB.
MAX_IMAGE_BYTES = int(5 * 1024 * 1024 * 3 / 4)  # 3,932,160 bytes

_DEFAULT_MODEL = "claude-sonnet-4-6"

# Preferred tags — the model is instructed to use these when relevant.
# Add new tags here; they will be included in the prompt automatically.
_PREFERRED_TAGS = [
    "aarti", "accessory", "acrylic", "acrylic floor", "ai", "aisle",
    "aisle decor", "aisle markers", "american wedding", "amisha", "metal trees",
    "apricot", "arabic", "arch", "arti", "baby shower", "babys breath",
    "backdrop", "backdrops and beyond", "bakery", "balloons", "balls", "banarsi",
    "baraat gate", "beaded", "beaded placemat", "behind the scenes", "beige",
    "bellevue", "bells", "bhandani", "birthday", "black", "blue",
    "blue lighting", "blush", "boat", "boho", "book club", "boston", "bouquet",
    "bout", "boutonniere", "boxwood", "brass bells", "brass pots",
    "bridal entrance", "bridal party", "bridal party flowers",
    "bridal procession", "bridal shower", "bride groom chairs",
    "bride's bouquet", "brown", "cake", "california", "candelabra",
    "candelabra glass", "candelabra gold", "candle", "candle ceremony",
    "candle stands", "candles", "capiz shell", "card box", "carved", "casino",
    "centerpiece", "centerpieces", "ceremony", "chaadar", "chairs",
    "chandelier", "chandni", "chanel", "charger", "charger plates",
    "chartreuse", "cherry blossom", "chiavari chair", "chicago", "chinese",
    "christian", "chuppah", "circular", "clear", "clear acrylic chair",
    "clear chairs", "clusters", "colorful", "column", "columns", "connecticut",
    "construction", "copper", "corporate", "corsage", "cottage", "couch",
    "crystal", "crystal tea room", "dance floor", "dance floor seating",
    "dance floor wrap", "dark brown", "dark moody", "deity", "delaware",
    "designer bouquet", "dessert station", "diamond dance floor", "dj",
    "dj booth", "dj table", "dome", "draping", "drum", "drums", "dusty pink",
    "dusty rose", "edgy", "elegant", "elephant", "elevated", "estate",
    "event props", "event signage", "fabrication", "facade", "fall", "fans",
    "favor cart", "favors", "fire pit", "floor cover", "floral",
    "floral garlands", "floral print", "florist", "focal", "focus light",
    "food", "food canopy", "food station", "forsythia", "french",
    "fresh floral garland", "fresh flowers", "fuzzy centerpiece", "ganesh",
    "ganesh puja", "garden", "garlands", "gemstone", "geometric", "gift box",
    "glass", "glossy", "gold", "gold beaded", "gold mirrored cart",
    "gold tables", "green", "greenery aisle", "greens", "grey", "gyp", "haldi",
    "hanging ganesh", "henna", "henna artist", "heritage",
    "hilton penns landing", "hindu", "hot pink", "impact", "indian american",
    "indianapolis", "indoor", "influencer", "inspiration", "intimate event",
    "iraq", "iraqui", "ivory", "jago", "jaimala", "jasmine", "jersey city",
    "jewelry", "jewish", "la rue", "lamiya", "lamp", "landsdowne", "lantern",
    "lavender", "lavender roses", "liberty house", "library", "lighting",
    "lightyear studio", "lime green", "logan", "lotti", "lotus", "lounge",
    "lounge canopy", "loveseat", "low centerpiece", "low seats",
    "madison avenue", "makeup artist", "mandap", "mandap furniture", "mansion",
    "marigold", "market", "maryam", "masquerade", "matte runner", "mayun",
    "mehndi", "mexican", "middle eastern", "mirrored", "mirrored table",
    "modern bouquet", "moroccan", "morocco", "movie set", "mumbai", "muslim",
    "neon", "neon yellow", "neutral draping", "new jersey", "new york",
    "nigerian", "notary", "orange", "organic", "ottoman", "outdoor",
    "outdoor ceremony", "outdoor install", "outdoor mandap", "pakistani",
    "palki", "pandit", "parents chairs", "parina", "patisserie", "peach",
    "peacock", "pedestals", "petal", "photo op", "photo prop", "photo shoot",
    "photos", "pillar candles", "pink", "pipe and drape", "pistachio", "plant",
    "planters", "pleated", "polka dot", "polyester", "pom pom", "pop up",
    "priest", "print", "procession", "production", "puff", "punjabi", "purple",
    "purple lighting", "reception", "red", "red chairs", "religious",
    "religious statue", "rental", "rental site", "rentals", "retail shop",
    "retro", "roses", "royal blue", "rug", "runner", "saloon", "sangeet",
    "sangeet furniture", "satin blue", "seating", "sette", "setup team",
    "sheetal", "shital", "shop", "side tables", "sign", "signage",
    "silk dupioni", "silk runner", "smilex", "sofa", "south american",
    "south asian ceremony", "speakeasy", "square", "stage", "stage cover",
    "stage fabric", "stairs", "stand", "station", "statue", "statues", "steel",
    "striped", "structure", "sweet sixteen", "swing", "tabla", "table linen",
    "tall centerpiece", "tapered", "tea party", "teal blue", "team",
    "team setup", "texture", "traditional", "trees", "tropical", "truck",
    "truck prop", "tufted", "tulsi", "tum hi ho", "turkish", "turmeric",
    "turquoise", "umbrella", "ushma", "vaishali", "velvet", "vintage",
    "virginia", "walima", "wall divider", "wedding", "wedding aisle", "welcome",
    "welcome entrance", "welcome table", "western", "white", "white chair",
    "white elephant", "white floor", "white wooden cart", "wood", "yellow",
]


def _get_model() -> str:
    return os.environ.get("ANTHROPIC_MODEL", _DEFAULT_MODEL)


_DEFAULT_BUCKET = "photo-tagging-photos"


def _build_prompt() -> str:
    preferred = ", ".join(_PREFERRED_TAGS)
    return (
        "Analyze this photo. Focus on the aesthetic elements and visual design "
        "of the room, especially the florals and the colors. Ignore any people "
        "in the photos. Ignore any technical aspects of the photography itself. "
        "If you recognize any specifically Indian ceremonial items, please call "
        "those out.\n\n"
        "When choosing tags, prefer terms from the list below whenever they are "
        "relevant — use the exact spelling shown. You may add tags not on the "
        "list if they describe something important that the list doesn't cover.\n\n"
        f"Preferred tags: {preferred}\n\n"
        "Respond with a JSON object containing:\n"
        '  "summary": a one-sentence description\n'
        '  "tags": a list of 25-30 tags\n'
        "Respond with JSON only, no other text."
    )


def record_error(conn, s3_key: str, error: Exception, bucket: str = _DEFAULT_BUCKET) -> None:
    """Best-effort write of a processing error to photos.last_error.

    Never raises — callers use this inside an except block and must not have
    the original exception masked by a secondary failure.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO photos (s3_key, bucket, last_error) VALUES (%s, %s, %s) "
                "ON CONFLICT (s3_key, bucket) DO UPDATE SET last_error = EXCLUDED.last_error",
                (s3_key, bucket, str(error)),
            )
        conn.commit()
    except Exception:
        pass


def process_one(
    s3_key: str,
    image_bytes: bytes,
    db_conn,
    anthropic_client,
    bucket: str = _DEFAULT_BUCKET,
) -> str:
    """Process a single image. Returns 'processed', 'skipped', or 'unsupported'.

    When bucket is the inbox bucket, only a DB record is inserted (no Anthropic
    tagging). For the default photos bucket, full tagging is performed.
    """
    if not s3_key.lower().endswith((".jpg", ".jpeg")):
        logger.info("Skipping unsupported file type: %s", s3_key)
        return "unsupported"

    with db_conn.cursor() as cur:
        # Atomically claim the row. ON CONFLICT means it's already processed.
        cur.execute(
            "INSERT INTO photos (s3_key, bucket) VALUES (%s, %s)"
            " ON CONFLICT (s3_key, bucket) DO NOTHING RETURNING id",
            (s3_key, bucket),
        )
        row = cur.fetchone()
        if row is None:
            # Row already exists. Skip if successfully processed; retry if previously failed.
            cur.execute(
                "SELECT id, processed_at FROM photos WHERE s3_key = %s AND bucket = %s",
                (s3_key, bucket),
            )
            existing = cur.fetchone()
            if existing[1] is not None:
                return "skipped"
            photo_id = existing[0]
        else:
            photo_id = row[0]

        if bucket == _DEFAULT_BUCKET:
            try:
                image_bytes = _prepare_image(image_bytes)
                _tag_photo(cur, anthropic_client, photo_id, s3_key, image_bytes)
            except Exception:
                logger.exception("Failed to process image: %s", s3_key)
                raise

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


def get_tags_from_image(image_bytes: bytes, anthropic_client) -> list[str]:
    """Call the Anthropic vision API and return a list of tags for the image."""
    image_b64 = base64.standard_b64encode(image_bytes).decode()

    response = anthropic_client.messages.create(
        model=_get_model(),
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
                    "text": _build_prompt(),
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

    tags = result.get("tags", [])
    if not isinstance(tags, list):
        raise ValueError(f"Expected 'tags' to be a list, got {type(tags)}: {tags!r}")

    return tags


def _tag_photo(cur, anthropic_client, photo_id: int, s3_key: str, image_bytes: bytes) -> None:
    tags = get_tags_from_image(image_bytes, anthropic_client)

    cur.execute(
        "UPDATE photos SET processed_at = NOW(), last_error = NULL WHERE id = %s",
        (photo_id,),
    )

    for tag_name in tags:
        if not isinstance(tag_name, str):
            logger.warning("Skipping non-string tag %r for image: %s", tag_name, s3_key)
            continue
        cur.execute(
            """
            INSERT INTO tags (name) VALUES (%s)
            ON CONFLICT (LOWER(name)) DO UPDATE SET name = EXCLUDED.name
            RETURNING id
            """,
            (tag_name.lower().strip(),),
        )
        tag_id = cur.fetchone()[0]
        cur.execute(
            "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (photo_id, tag_id),
        )
