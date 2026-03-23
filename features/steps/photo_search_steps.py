"""
Step definitions for photo_search.feature.

Steps interact only with:
  - The database (via the psycopg2 connection opened in environment.py)
  - The searcher module (lambda/searcher.py)
"""

import sys
from pathlib import Path

from behave import given, when, then

from common import seed_photo

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))


# ---------------------------------------------------------------------------
# Given
# ---------------------------------------------------------------------------

@given('a photo "{s3_key}" tagged with "{tags}"')
def step_seed_photo(context, s3_key, tags):
    tag_names = [t.strip() for t in tags.split(",")]
    seed_photo(context.conn, s3_key, tag_names)
    # no commit — context.conn is rolled back after each scenario


# ---------------------------------------------------------------------------
# When
# ---------------------------------------------------------------------------

@given('the tag "{tag}" is removed from "{s3_key}"')
def step_remove_tag(context, tag, s3_key):
    import searcher
    searcher.remove_tag(s3_key, tag, context.conn)


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


@then('the results for "{s3_key}" should not include the tag "{tag}"')
def step_result_tags_exclude(context, s3_key, tag):
    result = next((r for r in context.results if r["s3_key"] == s3_key), None)
    assert result is not None, f"{s3_key!r} not found in results"
    assert tag not in result.get("tags", []), (
        f"Expected tag {tag!r} to be absent from {s3_key!r} tags, got: {result['tags']}"
    )


@then('"{higher}" should rank above "{lower}"')
def step_ranks_above(context, higher, lower):
    keys = [r["s3_key"] for r in context.results]
    assert higher in keys, f"{higher!r} not found in results: {keys}"
    assert lower in keys, f"{lower!r} not found in results: {keys}"
    assert keys.index(higher) < keys.index(lower), (
        f"Expected {higher!r} to rank above {lower!r}, got order: {keys}"
    )
