# AWS Tools — SQS Batcher

![Python Version](https://img.shields.io/badge/python-3.10%2B-blue)
![PyPI](https://img.shields.io/pypi/v/aws-tools?label=PyPI%20Package)
![CI](https://github.com/satyap/aws-tools/actions/workflows/ci.yml/badge.svg)

A Python utility for batching and sending messages to AWS SQS with size- and count-aware flushing, context management, retries, and optional success callbacks.

---

## Features

* Automatic batching based on message count and payload size
* Context manager support for automatic flushing
* Retry with exponential backoff for failed messages
* Support for SQS MessageAttributes, including strings and numbers
* Optional success callback that receives the message IDs

---

## Installation

### From PyPI (once published)

`pip install aws-tools`

### From source

git clone [https://github.com/satyap/aws-tools.git](https://github.com/satyap/aws-tools.git)
cd aws-tools
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

---

## Quick Start

```python
import boto3
from src.sqs_batch_send import SQSBatcher

sqs = boto3.client("sqs", region_name="us-east-1")
queue_url = "[https://sqs.us-east-1.amazonaws.com/123456789012/my-queue](https://sqs.us-east-1.amazonaws.com/123456789012/my-queue)"

def on_success(message_ids):
print("Successfully sent messages:", message_ids)

with SQSBatcher(queue_url, sqs_client=sqs, on_success=on_success) as batcher:
batcher.add_message("Hello World", attributes={"foo": {"DataType": "String", "StringValue": "bar"}})
batcher.add_message("Another message", attributes={"count": {"DataType": "Number", "StringValue": "42"}})
```
---

## Retry Example

You can supply a custom retry function instead of the default exponential backoff:

```python
def linear_retry(attempt: int) -> float:
return 0.5 * attempt  # wait 0.5s, 1s, 1.5s, ...

with SQSBatcher(queue_url, sqs_client=sqs, backoff_factor=0, retry_policy=linear_retry) as batcher:
batcher.add_message("Retry test")
```
---

## Testing

`pytest --cov=src --cov-report=term-missing tests/`

* Uses moto to mock AWS SQS
* Type-checked with mypy: mypy src tests

---

## Development & Contributing

* Fork the repo
* Create a feature branch
* Write tests for new functionality
* Submit a pull request

---

## License

See the [LICENSE](LICENSE) file for details

---
