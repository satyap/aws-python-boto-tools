import boto3
import time
import uuid
from typing import Dict, Any, List, Optional, Callable, Type, Literal

MIN_BATCH_COUNT = 1
MAX_BATCH_COUNT = 10
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 1_048_576
APPROX_AWS_METADATA_OVERHEAD = 50


class SQSBatcher:
    """SQS batch sender with count- and size-based flushing, context management, and success callback."""

    def __init__(
        self,
        queue_url: str,
        *,
        max_batch_count: int = 10,
        max_batch_size_bytes: int = 1_048_576,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        sqs_client: Optional[boto3.client] = None,
        on_success: Optional[Callable[[List[str]], None]] = None,
    ):
        if not (MIN_BATCH_COUNT <= max_batch_count <= MAX_BATCH_COUNT):
            raise ValueError(f"max_batch_count must be between 1 and {MAX_BATCH_COUNT}")
        if not (MIN_BATCH_SIZE <= max_batch_size_bytes <= MAX_BATCH_SIZE):
            raise ValueError(f"max_batch_size_bytes must be between 1 and {MAX_BATCH_SIZE}")

        self.queue_url = queue_url
        self.max_batch_count = max_batch_count
        self.max_batch_size_bytes = max_batch_size_bytes
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.on_success = on_success

        self.sqs = sqs_client or boto3.client("sqs")
        self._batch: List[Dict[str, Any]] = []
        self._batch_size = 0

    # ------------------ Context manager ------------------ #
    def __enter__(self) -> "SQSBatcher":
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[Any],
    ) -> Literal[False]:  # return type is a literal False as we _always_ return False.
        if self._batch:
            self.flush()
        return False

    # ------------------ Public API ------------------ #
    def add_message(
        self,
        body: str,
        attributes: Optional[Dict[str, Dict[str, Any]]] = None,
        message_id: Optional[str] = None,
        **sqs_fields: Any,
    ) -> None:
        attributes = attributes or {}
        if len(attributes) > 10:
            raise ValueError("SQS allows a maximum of 10 message attributes")

        msg_size = self._estimate_message_size(body, attributes)

        if len(self._batch) >= self.max_batch_count or self._batch_size + msg_size > self.max_batch_size_bytes:
            self.flush()

        entry = {
            "Id": message_id or self._generate_message_id(),
            "MessageBody": body,
            "MessageAttributes": attributes,
            **sqs_fields,
        }
        self._batch.append(entry)
        self._batch_size += msg_size

    def flush(self) -> None:
        """Send current batch immediately with simple retry logic and on_success callback."""
        if not self._batch:
            return

        entries = self._batch.copy()
        for attempt in range(1, self.max_retries + 2):
            try:
                resp = self.sqs.send_message_batch(QueueUrl=self.queue_url, Entries=entries)
                failed_ids = {f["Id"] for f in resp.get("Failed", [])}
                successful = [e["Id"] for e in entries if e["Id"] not in failed_ids]

                if self.on_success and successful:
                    self.on_success(successful)

                if not failed_ids:
                    break  # all success
                entries = [e for e in entries if e["Id"] in failed_ids]
            except Exception:
                if attempt == self.max_retries + 1:
                    raise
            else:
                if entries:  # still failed
                    time.sleep(self.backoff_factor * (2 ** (attempt - 1)))

        self._batch.clear()
        self._batch_size = 0

    # ------------------ Internal helpers ------------------ #
    @staticmethod
    def _generate_message_id() -> str:
        return uuid.uuid4().hex[:80]

    @staticmethod
    def _estimate_message_size(body: str, attributes: Dict[str, Dict[str, Any]]) -> int:
        size = len(body.encode("utf-8"))
        for name, attr in attributes.items():
            size += len(name.encode("utf-8"))
            size += len(attr.get("DataType", "").encode("utf-8"))

            if "StringValue" in attr:
                val = attr["StringValue"]
                size += len(str(val).encode("utf-8"))
            elif "BinaryValue" in attr:
                size += len(attr["BinaryValue"])
            elif "StringListValues" in attr:  # in case someone uses List
                for val in attr["StringListValues"]:
                    size += len(str(val).encode("utf-8"))
            elif "BinaryListValues" in attr:  # in case someone uses List
                for val in attr["BinaryListValues"]:
                    size += len(val)

            size += APPROX_AWS_METADATA_OVERHEAD
        return size
