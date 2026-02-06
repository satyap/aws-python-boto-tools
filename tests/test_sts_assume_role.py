import time
from datetime import datetime, timedelta
from unittest import mock

import pytest
import boto3
from moto import mock_aws
from src.aws_python_boto_tools.sts_assume_role import get_session, configure_cache, _STS_CACHE


# ----------------------
# Helpers
# ----------------------
def clear_cache() -> None:
    """Clear the internal cache for testing."""
    _STS_CACHE.clear()


# ----------------------
# Fixtures
# ----------------------
@pytest.fixture(autouse=True)
def setup_moto():
    with mock_aws():
        yield
    clear_cache()


# ----------------------
# Tests
# ----------------------
def test_basic_assume_role_session():
    """Test that get_session returns a session with valid creds."""
    configure_cache(10)
    session = get_session(
        target_role_arn="arn:aws:iam::123456789012:role/RoleA",
        session_name="TestSessionA",
        duration_seconds=900,
    )
    # Should return a boto3.Session object
    assert isinstance(session, boto3.session.Session)
    s3_client = session.client("s3")
    # Should be able to call S3 (mocked)
    s3_client.create_bucket(Bucket="test-bucket")
    buckets = s3_client.list_buckets()["Buckets"]
    assert len(buckets) == 1
    assert buckets[0]["Name"] == "test-bucket"


def test_intermediate_role_chain():
    """Test that intermediate role works and is cached."""
    configure_cache(10)
    target_arn = "arn:aws:iam::123456789012:role/TargetRole"
    intermediate_arn = "arn:aws:iam::123456789012:role/IntermediateRole"

    session = get_session(
        target_role_arn=target_arn,
        session_name="ChainSession",
        intermediate_role_arn=intermediate_arn,
        duration_seconds=900,
    )

    assert isinstance(session, boto3.session.Session)
    # The intermediate role should also be cached
    intermediate_key = (intermediate_arn, "ChainSession", None)
    assert intermediate_key in _STS_CACHE
    target_key = (target_arn, "ChainSession", intermediate_arn)
    assert target_key in _STS_CACHE


def test_lru_cache_eviction():
    """Test that cache respects max size and evicts oldest entries."""
    configure_cache(2)
    get_session("arn:aws:iam::123456789012:role/Role1", "s1", duration_seconds=900)
    get_session("arn:aws:iam::123456789012:role/Role2", "s2", duration_seconds=900)
    get_session("arn:aws:iam::123456789012:role/Role3", "s3", duration_seconds=900)
    # Max size is 2 → oldest entry should be evicted
    assert len(_STS_CACHE) == 2
    # Role1 should be evicted
    assert ("arn:aws:iam::123456789012:role/Role1", "s1", None) not in _STS_CACHE


def test_expiration_removes_from_cache(monkeypatch):
    """Test that expired sessions are removed from cache."""
    configure_cache(10)
    session = get_session("arn:aws:iam::123456789012:role/RoleExp", "exp", duration_seconds=900)
    key = ("arn:aws:iam::123456789012:role/RoleExp", "exp", None)
    assert key in _STS_CACHE

    # Fast-forward time to expire the credentials
    future_time = time.time() + 3600
    monkeypatch.setattr(time, "time", lambda: future_time)
    session2 = get_session("arn:aws:iam::123456789012:role/RoleExp", "exp", duration_seconds=900)
    # Old session should have been evicted and replaced
    assert session2 != session
    assert key in _STS_CACHE


def test_recursive_intermediate_roles():
    """Test that caching works across nested chains of intermediate roles."""
    configure_cache(5)  # Set cache size small for testing eviction

    # Define ARNs for roles
    target_arn = "arn:aws:iam::123456789012:role/TargetRole"
    intermediate_arn_1 = "arn:aws:iam::123456789012:role/IntermediateRole1"
    intermediate_arn_2 = "arn:aws:iam::123456789012:role/IntermediateRole2"

    # Call get_session for recursive role chaining
    session = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_1,
        duration_seconds=900,
    )

    # Check that the target role and intermediate roles are cached
    target_key = (target_arn, "TestSession", intermediate_arn_1)
    intermediate_key_1 = (intermediate_arn_1, "TestSession", None)

    # Intermediate role 1 should be cached as well as the target role
    assert intermediate_key_1 in _STS_CACHE
    assert target_key in _STS_CACHE

    # Now let's chain to the second intermediate role, and assume the target role again
    session2 = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_2,
        duration_seconds=900,
        session=session,  # passing the session from previous intermediate
    )

    # Intermediate role 2 should also be cached
    intermediate_key_2 = (intermediate_arn_2, "TestSession", intermediate_arn_1)

    # Check that all three roles are cached
    assert intermediate_key_2 in _STS_CACHE
    assert intermediate_key_1 in _STS_CACHE
    assert target_key in _STS_CACHE

    # Test that we can reuse the sessions
    # Intermediate 1 and Target session should still be valid
    session3 = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_1,
        duration_seconds=900,
    )

    assert session3 == session  # Reuse the session from the cache
    assert intermediate_key_1 in _STS_CACHE  # Ensure intermediate role is still cached


def test_recursive_intermediate_roles():
    """Test that caching works across nested chains of intermediate roles."""
    configure_cache(5)  # Set cache size small for testing eviction

    # Define ARNs for roles
    target_arn = "arn:aws:iam::123456789012:role/TargetRole"
    intermediate_arn_1 = "arn:aws:iam::123456789012:role/IntermediateRole1"
    intermediate_arn_2 = "arn:aws:iam::123456789012:role/IntermediateRole2"

    # Call get_session for recursive role chaining
    session = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_1,
        duration_seconds=900,
    )

    # Check that the intermediate role and target role are cached together
    target_key = (target_arn, "TestSession", intermediate_arn_1)
    intermediate_key_1 = (intermediate_arn_1, "TestSession", None)

    # Intermediate role 1 should be cached as well as the target role
    assert intermediate_key_1 in _STS_CACHE  # The intermediate role is cached
    assert target_key in _STS_CACHE  # The target role is cached with intermediate role

    # Now let's chain to the second intermediate role, and assume the target role again
    session2 = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_2,
        duration_seconds=900,
        session=session,  # passing the session from previous intermediate
    )

    # Check that the intermediate role 2 and target role are cached together
    intermediate_key_2 = (intermediate_arn_2, "TestSession", None)

    # Check that the cache contains the intermediate role chain
    assert intermediate_key_2 in _STS_CACHE  # The second intermediate role is cached
    assert intermediate_key_1 in _STS_CACHE  # The first intermediate role is cached
    assert target_key in _STS_CACHE  # The target role is cached with intermediate role chain

    # Now check that we can reuse the session and intermediate roles from the cache
    session3 = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        intermediate_role_arn=intermediate_arn_1,
        duration_seconds=900,
    )

    # Check that the intermediate role session is reused and target session is reused
    assert session3 == session  # Reuse the session from the cache for target role with intermediate 1
    assert intermediate_key_1 in _STS_CACHE  # Ensure intermediate role 1 is still cached
    assert target_key in _STS_CACHE  # Ensure target role with intermediate role 1 is still cached


def test_existing_session_usage():
    """Test that caching works when passing an existing session into get_session."""
    configure_cache(5)  # Set cache size small for testing eviction
    target_arn = "arn:aws:iam::123456789012:role/TargetRole"
    mock_session = mock.Mock(spec=boto3.Session)
    mock_sts_client = mock.Mock()
    mock_session.client.return_value = mock_sts_client
    creds = {
        "AccessKeyId": "TEMPACCESSKEY",
        "SecretAccessKey": "TEMPSECRETKEY",
        "SessionToken": "TEMPTOKEN",
        "Expiration": datetime.now() + timedelta(hours=1),
    }
    mock_sts_client.assume_role.return_value = {"Credentials": creds}

    session = get_session(
        target_role_arn=target_arn,
        session_name="TestSession",
        duration_seconds=900,
        session=mock_session,
    )
    assert session.get_credentials().access_key == creds["AccessKeyId"]  # same creds implies same session, probably

    mock_session.client.assert_called_once_with("sts")
    mock_sts_client.assume_role.assert_called_once_with(
        RoleArn=target_arn, RoleSessionName="TestSession", DurationSeconds=900
    )
