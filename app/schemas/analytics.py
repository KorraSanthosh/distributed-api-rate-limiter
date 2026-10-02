from typing import List

from pydantic import BaseModel, Field


class RequestAnalyticsLog(BaseModel):
    """Represents a traffic log event sent to and consumed from the Redis stream."""

    request_id: str = Field(..., description="Unique UUID for tracing.")
    timestamp: float = Field(..., description="Epoch timestamp of the request.")
    client_ip: str = Field(..., description="IP Address of the client.")
    method: str = Field(..., description="HTTP Method used (GET, POST, etc.).")
    endpoint: str = Field(..., description="Target API endpoint route path.")
    status_code: int = Field(..., description="HTTP Response status code.")
    latency_ms: float = Field(..., description="Latency of request processing in milliseconds.")
    allowed: bool = Field(..., description="Whether the request was allowed through or rate limited.")


class TrafficPoint(BaseModel):
    """Request volume inside one time bucket."""

    timestamp: float = Field(..., description="Bucket start (epoch seconds).")
    allowed: int = Field(..., description="Allowed requests in the bucket.")
    blocked: int = Field(..., description="Rate-limited requests in the bucket.")


class AbusiveClient(BaseModel):
    client_ip: str
    blocked: int


class EndpointShare(BaseModel):
    endpoint: str
    requests: int
    blocked: int
    share_pct: float


class StatusCount(BaseModel):
    status_code: int
    count: int


class SystemHealth(BaseModel):
    """Service health, bundled into the summary so the dashboard needs no extra polling."""

    redis_connected: bool
    environment: str
    version: str


class AnalyticsSummary(BaseModel):
    """Aggregated traffic analytics served to the dashboard."""

    generated_at: float
    system: SystemHealth
    window_seconds: int
    effective_window_seconds: float = Field(
        ..., description="Span actually covered; shorter than window_seconds when the read cap was hit."
    )
    window_truncated: bool = Field(..., description="True if the stream held more traffic than was read.")
    total_requests: int
    allowed_requests: int
    blocked_requests: int
    requests_per_second: float
    block_rate_pct: float
    active_ips: int
    avg_latency_ms: float
    p95_latency_ms: float
    timeseries: List[TrafficPoint]
    status_codes: List[StatusCount]
    top_abusive_clients: List[AbusiveClient]
    endpoints: List[EndpointShare]
    recent: List[RequestAnalyticsLog]
