import os
import shutil

import boto3
import psycopg2
from dotenv import load_dotenv


def before_all(context):
    load_dotenv()
    context.db_url = os.environ["DATABASE_URL"]


def before_scenario(context, scenario):
    context.temp_dirs = []
    if "infrastructure" not in scenario.feature.tags:
        context.conn = psycopg2.connect(context.db_url)
        context.conn.autocommit = False


def after_scenario(context, scenario):
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
                cur.execute("DELETE FROM photos WHERE s3_key = %s", (context.test_s3_key,))
            conn.commit()
            conn.close()
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
            conn.commit()
            conn.close()
        except Exception:
            pass
