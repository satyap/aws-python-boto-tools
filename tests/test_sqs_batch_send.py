import boto3
import pytest
from unittest.mock import Mock

from src.aws_python_boto_tools.sqs_batch_send import (
    SQSBatcher,
    APPROX_AWS_METADATA_OVERHEAD,
    MAX_BATCH_COUNT,
    MAX_BATCH_SIZE,
)
from moto import mock_aws

# ---------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------


@pytest.fixture
def sqs_mock():
    mock = Mock()
    mock.send_message_batch.return_value = {"Successful": [], "Failed": []}
    return mock


@pytest.fixture
def batcher(sqs_mock):
    return SQSBatcher(queue_url="https://example.com/queue", sqs_client=sqs_mock, backoff_factor=0)


# ---------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------


def test_invalid_batch_count_raises():
    with pytest.raises(ValueError):
        SQSBatcher("url", max_batch_count=0)
    with pytest.raises(ValueError):
        SQSBatcher("url", max_batch_count=MAX_BATCH_COUNT + 1)


def test_invalid_batch_size_raises():
    with pytest.raises(ValueError):
        SQSBatcher("url", max_batch_size_bytes=0)
    with pytest.raises(ValueError):
        SQSBatcher("url", max_batch_size_bytes=MAX_BATCH_SIZE + 1)


# ---------------------------------------------------------------------
# Message size estimation
# ---------------------------------------------------------------------


def test_estimate_size_body_only():
    body = "hello"
    size = SQSBatcher._estimate_message_size(body, {})
    assert size == len(body.encode("utf-8"))


def test_estimate_size_string_attribute():
    body = "hi"
    attrs = {"a": {"DataType": "String", "StringValue": "b"}}
    size = SQSBatcher._estimate_message_size(body, attrs)
    expected = (
        len(body.encode())
        + len("a".encode())
        + len("String".encode())
        + len("b".encode())
        + APPROX_AWS_METADATA_OVERHEAD
    )
    assert size == expected


def test_estimate_size_binary_attribute():
    body = "hi"
    attrs = {"bin": {"DataType": "Binary", "BinaryValue": b"\x00\x01"}}
    size = SQSBatcher._estimate_message_size(body, attrs)
    expected = len(body.encode()) + len("bin".encode()) + len("Binary".encode()) + 2 + APPROX_AWS_METADATA_OVERHEAD
    assert size == expected


# ---------------------------------------------------------------------
# add_message validation
# ---------------------------------------------------------------------


def test_more_than_10_attributes_raises(batcher):
    attrs = {f"a{i}": {"DataType": "String", "StringValue": "x"} for i in range(11)}
    with pytest.raises(ValueError):
        batcher.add_message("msg", attributes=attrs)


def test_message_added_to_batch(batcher):
    batcher.add_message("hello")
    assert len(batcher._batch) == 1
    assert batcher._batch_size > 0


# ---------------------------------------------------------------------
# Automatic flushing
# ---------------------------------------------------------------------


def test_flush_on_max_batch_count(sqs_mock):
    sqs_mock.send_message_batch.return_value = {"Successful": [{"Id": "1"}], "Failed": []}
    batcher = SQSBatcher(queue_url="url", max_batch_count=1, sqs_client=sqs_mock, backoff_factor=0)
    batcher.add_message("a")
    batcher.add_message("b")  # triggers flush
    assert sqs_mock.send_message_batch.call_count == 1
    assert len(batcher._batch) == 1


def test_flush_on_max_batch_size(sqs_mock):
    sqs_mock.send_message_batch.return_value = {"Successful": [{"Id": "1"}], "Failed": []}
    batcher = SQSBatcher(queue_url="url", max_batch_size_bytes=5, sqs_client=sqs_mock, backoff_factor=0)
    batcher.add_message("12345")
    batcher.add_message("6")  # triggers flush
    assert sqs_mock.send_message_batch.call_count == 1


# ---------------------------------------------------------------------
# flush behavior
# ---------------------------------------------------------------------


def test_flush_noop_when_empty(batcher):
    batcher.flush()
    batcher.sqs.send_message_batch.assert_not_called()


def test_successful_flush_clears_batch(sqs_mock):
    sqs_mock.send_message_batch.return_value = {"Successful": [{"Id": "x"}], "Failed": []}
    batcher = SQSBatcher("url", sqs_client=sqs_mock)
    batcher.add_message("hello")
    batcher.flush()
    assert batcher._batch == []
    assert batcher._batch_size == 0


def test_on_success_called_with_ids(sqs_mock):
    callback = Mock()
    sqs_mock.send_message_batch.return_value = {"Successful": [{"Id": "a"}, {"Id": "b"}], "Failed": []}
    batcher = SQSBatcher("url", sqs_client=sqs_mock, on_success=callback)
    batcher.add_message("x", message_id="a")
    batcher.add_message("y", message_id="b")
    batcher.flush()
    callback.assert_called_once_with(["a", "b"])


# ---------------------------------------------------------------------
# Context manager behavior
# ---------------------------------------------------------------------


def test_context_manager_flush(sqs_mock):
    sqs_mock.send_message_batch.return_value = {"Successful": [{"Id": "1"}], "Failed": []}
    with SQSBatcher("url", sqs_client=sqs_mock) as b:
        b.add_message("hello")
    sqs_mock.send_message_batch.assert_called_once()


# ---------------------------------------------------------------------
# Integration with moto
# ---------------------------------------------------------------------


@pytest.fixture
def sqs_queue():
    with mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        resp = sqs.create_queue(QueueName="test-queue")
        yield sqs, resp["QueueUrl"]


def test_batch_send_success(sqs_queue):
    sqs, queue_url = sqs_queue
    batcher = SQSBatcher(queue_url, sqs_client=sqs, backoff_factor=0)
    batcher.add_message("a")
    batcher.add_message("b")
    batcher.flush()
    msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)["Messages"]
    bodies = {m["Body"] for m in msgs}
    assert bodies == {"a", "b"}


def test_context_manager_flush_moto(sqs_queue):
    sqs, queue_url = sqs_queue
    with SQSBatcher(queue_url, sqs_client=sqs) as b:
        b.add_message("hello")
    msgs = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1)["Messages"]
    assert msgs[0]["Body"] == "hello"


def test_fifo_queue_support(sqs_queue):
    sqs, _ = sqs_queue
    fifo_url = sqs.create_queue(
        QueueName="fifo-test.fifo",
        Attributes={"FifoQueue": "true", "ContentBasedDeduplication": "true"},
    )["QueueUrl"]
    batcher = SQSBatcher(fifo_url, sqs_client=sqs, backoff_factor=0)
    batcher.add_message("msg", MessageGroupId="group-1")
    batcher.flush()
    msgs = sqs.receive_message(QueueUrl=fifo_url, MaxNumberOfMessages=1)["Messages"]
    assert msgs[0]["Body"] == "msg"


def test_on_success_called_with_moto(sqs_queue):
    sqs, queue_url = sqs_queue
    called_ids = []

    def on_success(message_ids):
        called_ids.extend(message_ids)

    batcher = SQSBatcher(queue_url, sqs_client=sqs, on_success=on_success)
    batcher.add_message("msg1", message_id="m1")
    batcher.add_message("msg2", message_id="m2")
    batcher.flush()

    assert set(called_ids) == {"m1", "m2"}
