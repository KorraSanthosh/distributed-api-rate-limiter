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
