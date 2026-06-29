from pydantic import BaseModel, Field


class RateLimitErrorDetail(BaseModel):
    """Detailed metadata about the rate limit violation."""

    message: str = Field(
        default="Rate limit exceeded. Please try again later.",
        description="Friendly message explaining the rejection.",
    )
    limit: int = Field(
        ..., description="The maximum requests allowed per window."
    )
    burst_limit: int = Field(
        ..., description="The absolute burst ceiling allowed."
    )
    current_count: int = Field(
        ..., description="The number of requests made by the client in this window."
    )
    reset_in_seconds: int = Field(
        ..., description="Seconds remaining until the rate limit resets."
    )


class RateLimitErrorResponse(BaseModel):
    """The JSON payload structure returned on HTTP 429 Too Many Requests."""

    detail: RateLimitErrorDetail = Field(
        ..., description="Rate limiting failure details."
    )
