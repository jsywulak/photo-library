"""Step definitions for thumbnail_key.feature."""

import sys
from pathlib import Path

from behave import given, then

sys.path.insert(0, str(Path(__file__).parents[2] / "lambda"))

from utils import thumbnail_key
from common import thumbnail_key as common_thumbnail_key


@given('the s3_key is "{s3_key}"')
def step_set_s3_key(context, s3_key):
    context.s3_key = s3_key


@given('another s3_key is "{s3_key}"')
def step_set_other_s3_key(context, s3_key):
    context.other_s3_key = s3_key


@then('the thumbnail key should be "{expected}"')
def step_check_thumbnail_key(context, expected):
    actual = thumbnail_key(context.s3_key)
    assert actual == expected, f"Expected {expected!r}, got {actual!r}"


@then("their thumbnail keys should be different")
def step_check_keys_differ(context):
    key_a = thumbnail_key(context.s3_key)
    key_b = thumbnail_key(context.other_s3_key)
    assert key_a != key_b, (
        f"Expected different thumbnail keys but both produced {key_a!r}"
    )


@then("the steps helper thumbnail key should match the Lambda utility thumbnail key")
def step_helpers_agree(context):
    from_common = common_thumbnail_key(context.s3_key)
    from_utils = thumbnail_key(context.s3_key)
    assert from_common == from_utils, (
        f"common.py={from_common!r}, utils.py={from_utils!r}"
    )
