"""
Step definitions for photo_search.feature.

Steps interact only with:
  - The database (via the psycopg2 connection opened in environment.py)
  - The searcher module (lambda/searcher.py)
"""

import sys
from pathlib import Path

from behave import given, when, then

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------

@given('a photo "{s3_key}" tagged with "{tags}"')
def step_seed_photo(context, s3_key, tags):
    tag_names = [t.strip().lower() for t in tags.split(",")]
    with context.conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key) VALUES (%s) RETURNING id",
            (s3_key,),
        )
        photo_id = cur.fetchone()[0]

        for tag_name in tag_names:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name,),
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (photo_id, tag_id),
            )


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@when('I search for "{tags}"')
def step_search(context, tags):
    import searcher

    tag_list = [t.strip() for t in tags.split(",")]
    context.results = searcher.search(tag_list, context.conn)


# ---------------------------------------------------------------------------
# Then
# ---------------------------------------------------------------------------

@then("the results should be empty")
def step_results_empty(context):
    assert context.results == [], f"Expected empty results, got: {context.results}"


@then('the results should contain "{s3_key}"')
def step_results_contain(context, s3_key):
    keys = [r["s3_key"] for r in context.results]
    assert s3_key in keys, f"Expected {s3_key!r} in results, got: {keys}"


@then('the results should not contain "{s3_key}"')
def step_results_not_contain(context, s3_key):
    keys = [r["s3_key"] for r in context.results]
    assert s3_key not in keys, f"Expected {s3_key!r} absent from results, got: {keys}"


@then('"{higher}" should rank above "{lower}"')
def step_ranks_above(context, higher, lower):
    keys = [r["s3_key"] for r in context.results]
    assert higher in keys, f"{higher!r} not found in results: {keys}"
    assert lower in keys, f"{lower!r} not found in results: {keys}"
    assert keys.index(higher) < keys.index(lower), (
        f"Expected {higher!r} to rank above {lower!r}, got order: {keys}"
    )
