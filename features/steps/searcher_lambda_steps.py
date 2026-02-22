"""
Step definitions for searcher_lambda.feature.

Requires in .env:
  - SEARCHER_LAMBDA_NAME  name of the deployed Lambda function
  - NEON_DATABASE_URL     for seeding test data and verifying results

Test photos are inserted into Neon with a unique prefix. The environment.py
after_scenario hook cleans them up via context.neon_test_s3_keys.
"""

import json
import os
import uuid

import boto3
import psycopg2
from behave import given, then, when


def _neon_conn():
    return psycopg2.connect(os.environ["NEON_DATABASE_URL"])


def _seed_photo(conn, s3_key, tags):
    """Insert a photo and its tags into Neon. Returns the photo id."""
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO photos (s3_key, processed_at) VALUES (%s, NOW()) RETURNING id",
            (s3_key,),
        )
        photo_id = cur.fetchone()[0]
        for tag_name in tags:
            cur.execute(
                """
                INSERT INTO tags (name) VALUES (%s)
                ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name
                RETURNING id
                """,
                (tag_name.strip().lower(),),
            )
            tag_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO photo_tags (photo_id, tag_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (photo_id, tag_id),
            )
    conn.commit()
    return photo_id


@given("the searcher Lambda is deployed")
def step_searcher_lambda_deployed(context):
    name = os.environ["SEARCHER_LAMBDA_NAME"]
    client = boto3.client("lambda")
    response = client.get_function(FunctionName=name)
    context.searcher_lambda_name = name
    context.searcher_lambda_state = response["Configuration"]["State"]


@given('a photo exists in the Neon database tagged with "{tags}"')
def step_seed_photo(context, tags):
    if not hasattr(context, "neon_test_s3_keys"):
        context.neon_test_s3_keys = []

    prefix = f"test-{uuid.uuid4().hex[:8]}-"
    s3_key = f"{prefix}photo.jpg"
    tag_list = [t.strip() for t in tags.split(",")]

    conn = _neon_conn()
    _seed_photo(conn, s3_key, tag_list)
    conn.close()

    context.neon_test_s3_keys.append(s3_key)
    # Track the "best" photo as the first seeded (most tags relative to search)
    if not hasattr(context, "best_photo_key"):
        context.best_photo_key = s3_key
    context.last_photo_key = s3_key


@when('the Lambda is invoked with tags "{tags}"')
def step_invoke_searcher(context, tags):
    tag_list = [t.strip() for t in tags.split(",")]
    client = boto3.client("lambda")
    response = client.invoke(
        FunctionName=context.searcher_lambda_name,
        InvocationType="RequestResponse",
        Payload=json.dumps({"tags": tag_list}),
    )
    assert response["StatusCode"] == 200, f"Lambda returned status {response['StatusCode']}"
    assert "FunctionError" not in response, (
        f"Lambda error: {json.loads(response['Payload'].read())}"
    )
    context.search_results = json.loads(response["Payload"].read())


@then("the searcher function should be active")
def step_searcher_active(context):
    assert context.searcher_lambda_state == "Active", (
        f"Expected Lambda state Active, got {context.searcher_lambda_state!r}"
    )


@then("the results should contain both photos")
def step_results_contain_both(context):
    result_keys = {r["s3_key"] for r in context.search_results}
    for key in context.neon_test_s3_keys:
        assert key in result_keys, f"Expected {key!r} in results, got: {result_keys}"


@then("the photo with more matching tags should rank higher")
def step_ranking(context):
    result_keys = [r["s3_key"] for r in context.search_results]
    best_idx = result_keys.index(context.best_photo_key)
    last_idx = result_keys.index(context.last_photo_key)
    assert best_idx < last_idx, (
        f"Expected {context.best_photo_key!r} to rank above {context.last_photo_key!r}"
    )
