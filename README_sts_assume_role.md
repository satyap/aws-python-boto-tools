# AWS Tools — Temporary Session Cache

A Python utility to manage temporary AWS session credentials with caching, role assumption, and least-recently-used (LRU) eviction for performance optimization.

---

## Features

* Caches temporary AWS session credentials with LRU eviction
* Supports assuming roles directly or via an intermediate role
* Thread-safe session management
* Configurable cache size
* Reusable session that integrates seamlessly with boto3 clients

---

## Installation

### From PyPI (once published)

`pip install aws-temp-session-cache`

### From source

```shell
git clone [https://github.com/yourusername/aws-temp-session-cache.git](https://github.com/yourusername/aws-temp-session-cache.git)
cd aws-temp-session-cache
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

---

## Quick Start

```python
import boto3
from src.temp_session_cache import get_session, configure_cache

# Configure cache size
configure_cache(50)

# Get session with role assumption (with optional intermediate role)
session = get_session(
    target_role_arn="arn:aws:iam::123456789012:role/MyTargetRole",
    session_name="MySession",
    intermediate_role_arn="arn:aws:iam::123456789012:role/MyIntermediateRole",
    duration_seconds=900,
)

# Use the session to create clients and interact with AWS services
s3_client = session.client("s3")
print(s3_client.list_buckets())
```

---

## Cache Configuration

You can adjust the cache size by calling `configure_cache(max_size)` where `max_size` is the maximum number of sessions to retain in the cache:

```python
configure_cache(128)  # Default is 128
```

---

## Role Assumption Example

You can assume a role directly or with an optional intermediate role. This is useful when chaining multiple roles together:

```python
session = get_session(
    target_role_arn="arn:aws:iam::123456789012:role/MyTargetRole",
    session_name="MySession",
    intermediate_role_arn="arn:aws:iam::123456789012:role/MyIntermediateRole",
    duration_seconds=900
)
```

---

## Caching & Expiration

This utility uses an in-memory LRU cache to store sessions. Sessions are automatically evicted when the cache exceeds the configured maximum size. Cached sessions are considered expired if their credentials have passed the expiration time.

---
