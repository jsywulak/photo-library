import os
import shutil

import boto3
import psycopg2
from dotenv import load_dotenv


def _delete_s3_prefix(s3_client, bucket, prefix):
    """Delete all objects in bucket matching prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            s3_client.delete_object(Bucket=bucket, Key=obj["Key"])


TEST_S3_PREFIX = "testA6FA7E1D-"


def _delete_s3_prefix(s3_client, bucket, prefix):
    """Delete all objects in bucket with the given prefix."""
    paginator = s3_client.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            s3_client.delete_object(Bucket=bucket, Key=obj["Key"])


def before_all(context):
    load_dotenv()
    context.db_url = os.environ["DATABASE_URL"]


def before_feature(context, feature):
    if "frontend" in feature.tags:
        from playwright.sync_api import sync_playwright
        context._playwright = sync_playwright().__enter__()
        context.browser = context._playwright.chromium.launch()


def after_feature(context, feature):
    if "frontend" in feature.tags:
        context.browser.close()
        context._playwright.stop()


def before_scenario(context, scenario):
    context.temp_dirs = []
    if "frontend" in scenario.feature.tags:
        # Default mock data — individual scenarios can override with Given steps.
        context.mock_tags = []
        context.mock_results = []
        context.mock_inbox_results = []
        context.mock_process_error = False
        context.mock_archive_error = False
        context.mock_remove_tag_error = False
        context.mock_add_tags_error = False
        context.mock_stats_error = False
        context.page = None
        return
    if "infrastructure" not in scenario.feature.tags:
        context.conn = psycopg2.connect(context.db_url)
        context.conn.autocommit = False


def after_scenario(context, scenario):
    if "frontend" in scenario.feature.tags:
        if context.page:
            context.page.close()
        return
    if hasattr(context, "conn"):
        # Roll back any DB writes made during the scenario so each test starts clean.
        context.conn.rollback()
        context.conn.close()
    for d in context.temp_dirs:
        shutil.rmtree(d, ignore_errors=True)
    # Clean up S3 object and Neon record written by processor Lambda tests.
    if hasattr(context, "test_s3_key"):
        try:
            boto3.client("s3").delete_object(
                Bucket=context.test_s3_bucket, Key=context.test_s3_key
            )
        except Exception:
            pass
        try:
            conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM photos WHERE s3_key = %s AND bucket = %s",
                    (context.test_s3_key, context.test_s3_bucket),
                )
                # Also clean up by content_hash to catch records reinserted by delayed
                # EventBridge Lambda invocations that fired after the primary s3_key cleanup.
                if hasattr(context, "test_content_hash"):
                    cur.execute(
                        "DELETE FROM photos WHERE content_hash = %s AND bucket = %s AND s3_key LIKE 'testA6FA7E1D-%%'",
                        (context.test_content_hash, context.test_s3_bucket),
                    )
                cur.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM photo_tags)")
            conn.commit()
            conn.close()
        except Exception:
            pass
    # Clean up thumbnail and source photo uploaded by thumbnailer Lambda tests.
    if hasattr(context, "test_thumbnail_key"):
        s3 = boto3.client("s3")
        try:
            s3.delete_object(Bucket=context.test_thumbnail_bucket, Key=context.test_thumbnail_key)
        except Exception:
            pass
    # Clean up S3 objects uploaded directly by searcher Lambda tests.
    if hasattr(context, "searcher_s3_uploads"):
        s3 = boto3.client("s3")
        for bucket, key in context.searcher_s3_uploads:
            try:
                s3.delete_object(Bucket=bucket, Key=key)
            except Exception:
                pass
    # Clean up Neon records seeded directly by searcher Lambda tests.
    if hasattr(context, "neon_test_s3_keys"):
        try:
            conn = psycopg2.connect(os.environ["NEON_DATABASE_URL"])
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM photos WHERE s3_key = ANY(%s)",
                    (context.neon_test_s3_keys,),
                )
                cur.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM photo_tags)")
            conn.commit()
            conn.close()
        except Exception:
            pass


def after_all(context):
    """Final sweep: delete any test-prefixed objects left in S3 by failed/slow cleanups."""
    if not os.environ.get("S3_BUCKET"):
        return
    try:
        s3 = boto3.client("s3")
        _delete_s3_prefix(s3, os.environ["S3_BUCKET"], TEST_S3_PREFIX)
        _delete_s3_prefix(s3, os.environ["THUMBNAIL_BUCKET"], f"thumbnails/{TEST_S3_PREFIX}")
        _delete_s3_prefix(s3, os.environ["INBOX_BUCKET"], TEST_S3_PREFIX)
    except Exception:
        pass
