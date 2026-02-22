import os
import shutil

import psycopg2
from dotenv import load_dotenv


def before_all(context):
    load_dotenv()
    context.db_url = os.environ["DATABASE_URL"]


def before_scenario(context, scenario):
    context.conn = psycopg2.connect(context.db_url)
    context.conn.autocommit = False
    context.temp_dirs = []


def after_scenario(context, scenario):
    # Roll back any DB writes made during the scenario so each test starts clean.
    context.conn.rollback()
    context.conn.close()
    for d in context.temp_dirs:
        shutil.rmtree(d, ignore_errors=True)
