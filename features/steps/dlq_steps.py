"""
Step definitions for dlq.feature (Slice 7a).

Requires in .env:
  - PROCESSOR_V2_LAMBDA_NAME — name of the deployed processor v2 Lambda
  - PROCESSOR_V2_DLQ_URL     — URL of the SQS Dead-Letter Queue attached to it

The test invokes the Lambda async with a payload that handler.py cannot extract
a bucket/key from. handler.py raises ValueError. With MaximumRetryAttempts=0
the failed invocation is published to the DLQ within ~30s.
"""

import json
import os
import time
import uuid

import boto3
from behave import given, then, when


def _drain_dlq(url: str) -> None:
    """Receive + delete all messages currently visible on the DLQ.

    Used as a fixture/teardown helper. PurgeQueue is avoided because of its
    60s cooldown which would break consecutive scenario runs.
    """
    sqs = boto3.client("sqs")
    while True:
        resp = sqs.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=1,
            VisibilityTimeout=10,
        )
        msgs = resp.get("Messages", [])
        if not msgs:
            return
        sqs.delete_message_batch(
            QueueUrl=url,
            Entries=[{"Id": str(i), "ReceiptHandle": m["ReceiptHandle"]} for i, m in enumerate(msgs)],
        )


def _poll_dlq_for_marker(url: str, marker: str, timeout_s: int = 90) -> str | None:
    """Poll DLQ until a message whose body contains `marker` arrives.

    Returns the message body (string) on hit; None on timeout.
    Re-queues non-matching messages by setting their visibility to 0 so other
    in-flight test invocations don't lose them.
    """
    sqs = boto3.client("sqs")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = sqs.receive_message(
            QueueUrl=url,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=5,
            VisibilityTimeout=5,
        )
        for msg in resp.get("Messages", []):
            body = msg.get("Body", "")
            if marker in body:
                sqs.delete_message(QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"])
                return body
            # Not ours — return to queue immediately for another consumer.
            sqs.change_message_visibility(
                QueueUrl=url, ReceiptHandle=msg["ReceiptHandle"], VisibilityTimeout=0,
            )
    return None


@given("the processor v2 Lambda's DLQ is reachable")
def step_dlq_reachable(context):
    url = os.environ["PROCESSOR_V2_DLQ_URL"]
    boto3.client("sqs").get_queue_attributes(QueueUrl=url, AttributeNames=["QueueArn"])
    context.dlq_url = url


@when("the processor v2 Lambda is invoked async with a payload that causes it to error")
def step_invoke_async_with_bad_payload(context):
    # Marker is embedded in the payload so we can pick our message out of the DLQ
    # even if other failing invocations are in-flight from parallel tests.
    context.dlq_marker = f"testA6FA7E1D-dlq-{uuid.uuid4().hex[:12]}"
    # handler.py:_extract_bucket_key returns (None, None) for unrecognised events,
    # then raises ValueError. With MaximumRetryAttempts=0 this goes straight to DLQ.
    payload = {"dlq_test_marker": context.dlq_marker}
    boto3.client("lambda").invoke(
        FunctionName=os.environ["PROCESSOR_V2_LAMBDA_NAME"],
        InvocationType="Event",
        Payload=json.dumps(payload),
    )


@then("a message should arrive on the processor v2 DLQ within {timeout:d} seconds")
def step_dlq_message_within(context, timeout):
    body = _poll_dlq_for_marker(context.dlq_url, context.dlq_marker, timeout_s=timeout)
    assert body is not None, (
        f"No DLQ message containing {context.dlq_marker!r} within {timeout}s"
    )
    context.dlq_message_body = body


@then("the DLQ message body should reference the failing payload marker")
def step_dlq_body_has_marker(context):
    assert context.dlq_marker in context.dlq_message_body, (
        f"Expected DLQ body to contain {context.dlq_marker!r}; body={context.dlq_message_body!r}"
    )
