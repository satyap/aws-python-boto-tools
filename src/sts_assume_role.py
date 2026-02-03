import time
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Optional, Tuple
import boto3
from boto3.session import Session
from botocore.exceptions import BotoCoreError, ClientError


# ----------------------------
# Internal dataclass wrapper
# ----------------------------
@dataclass(frozen=True)
class CachedSession:
    session: Session
    expiration_ts: float  # Unix timestamp when credentials expire


# ----------------------------
# Module-level cache & lock
# ----------------------------
# Key: (target_role_arn, session_name, intermediate_role_arn)
# Value: CachedSession
_STS_CACHE: "OrderedDict[Tuple[str, str, Optional[str]], CachedSession]" = OrderedDict()
_CACHE_LOCK: Lock = Lock()
_MAX_CACHE_SIZE: int = 128  # default


# ----------------------------
# Public API
# ----------------------------
def configure_cache(max_size: int) -> None:
    """
    Configure the module-level STS cache max size.
    """
    global _MAX_CACHE_SIZE
    _MAX_CACHE_SIZE = max_size


def get_session(
    target_role_arn: str,
    session_name: str,
    *,
    intermediate_role_arn: Optional[str] = None,
    duration_seconds: int = 3600,
    session: Optional[Session] = None,
) -> Session:
    """
    Return a boto3.Session with temporary credentials for the target role.

    You can either provide:
      - intermediate_role_arn: role to assume first (optional)
      - session: existing boto3.Session (optional)

    Thread-safe and LRU-cached.
    """
    global _STS_CACHE
    key: Tuple[str, str, Optional[str]] = (target_role_arn, session_name, intermediate_role_arn)
    now: float = time.time()

    # Thread-safe cache lookup
    with _CACHE_LOCK:
        cached: Optional[CachedSession] = _STS_CACHE.get(key)
        if cached and cached.expiration_ts > now:
            _STS_CACHE.move_to_end(key)  # mark as recently used
            return cached.session
        elif cached:
            # Expired
            _STS_CACHE.pop(key)

    # Create a base session if none provided
    if session is None:
        session = boto3.Session()

    # Handle optional intermediate role
    if intermediate_role_arn:
        session = get_session(
            target_role_arn=intermediate_role_arn,
            session_name=session_name,
            duration_seconds=duration_seconds,
            session=session,  # pass current base session if any
        )

    # Assume into target role
    target_session: Session = _assume_role_session(session, target_role_arn, session_name, duration_seconds)
    expiration_ts: float = target_session.expiration_ts  # type: ignore[attr-defined]

    # Cache the session
    cached_session: CachedSession = CachedSession(session=target_session, expiration_ts=expiration_ts)
    with _CACHE_LOCK:
        _STS_CACHE[key] = cached_session
        # LRU eviction
        while len(_STS_CACHE) > _MAX_CACHE_SIZE:
            _STS_CACHE.popitem(last=False)

    return target_session


# ----------------------------
# Internal helper
# ----------------------------
def _assume_role_session(
    session: Session,
    role_arn: str,
    session_name: str,
    duration_seconds: int,
) -> Session:
    """
    Assume a role and return a boto3.Session with temporary credentials.
    Stores expiration_ts as an attribute on the session.
    """
    sts_client = session.client("sts")
    try:
        response: dict = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName=session_name,
            DurationSeconds=duration_seconds,
        )
    except (BotoCoreError, ClientError) as e:
        raise RuntimeError(f"Failed to assume role {role_arn}: {e}") from e

    creds: dict = response["Credentials"]
    new_session: Session = boto3.Session(
        aws_access_key_id=creds["AccessKeyId"],
        aws_secret_access_key=creds["SecretAccessKey"],
        aws_session_token=creds["SessionToken"],
    )

    # Attach expiration_ts using dataclass wrapper; we keep it for typing
    # For convenience, we can also attach it to the session for internal use
    setattr(new_session, "expiration_ts", creds["Expiration"].timestamp())  # type: ignore[attr-defined]

    return new_session


# ----------------------------
# Example usage
# ----------------------------
if __name__ == "__main__":
    configure_cache(50)

    g_session: Session = get_session(
        target_role_arn="arn:aws:iam::123456789012:role/MyTargetRole",
        session_name="MySession",
        intermediate_role_arn="arn:aws:iam::123456789012:role/MyIntermediateRole",
        duration_seconds=900,
    )

    # Use the session like a normal boto3 session
    s3_client = g_session.client("s3")
    print(s3_client.list_buckets())
