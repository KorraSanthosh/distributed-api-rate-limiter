from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitPolicy:
    """Represents the rate limiting rules applied to clients."""

    window_seconds: int
    max_requests: int
    burst_limit: Optional[int] = None


@dataclass
class ClientRequestContext:
    """Carries the HTTP metadata required to check limits and log analytics."""

    client_ip: str
    endpoint: str
    method: str
    timestamp: float
    request_id: str


@dataclass
class RateLimitResult:
    """Contains the outcome of a rate limiting evaluation."""

    allowed: bool
    current_count: int
    limit: int
    burst_limit: int
    reset_time: float  # Epoch timestamp when the rate limit window completely resets
    policy: RateLimitPolicy
