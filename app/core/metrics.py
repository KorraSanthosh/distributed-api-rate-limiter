from prometheus_client import Counter, Histogram, Gauge

# Namespaces and Prefixes
NAMESPACE = "rate_limiter"

# 1. Total Requests Counter
HTTP_REQUESTS_TOTAL = Counter(
    name="http_requests_total",
    documentation="Total number of HTTP requests processed.",
    labelnames=["method", "endpoint", "status_code", "allowed"],
    namespace=NAMESPACE,
)

# 2. Blocked Requests Counter
HTTP_REQUESTS_BLOCKED_TOTAL = Counter(
    name="http_requests_blocked_total",
    documentation="Total number of HTTP requests blocked by rate limits.",
    labelnames=["method", "endpoint", "reason"],
    namespace=NAMESPACE,
)

# 3. HTTP Request Latency Histogram
HTTP_REQUEST_DURATION_SECONDS = Histogram(
    name="http_request_duration_seconds",
    documentation="Latency of HTTP requests in seconds.",
    labelnames=["method", "endpoint"],
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 10.0),
    namespace=NAMESPACE,
)

# 4. Redis Operations Counter
REDIS_OPERATIONS_TOTAL = Counter(
    name="redis_operations_total",
    documentation="Total number of Redis operations performed.",
    labelnames=["operation", "status"],
    namespace=NAMESPACE,
)

# 5. Redis Active Connections Gauge
REDIS_ACTIVE_CONNECTIONS = Gauge(
    name="redis_active_connections",
    documentation="Number of active connections in the Redis pool.",
    labelnames=["pool_name"],
    namespace=NAMESPACE,
)

# 6. Errors Counter
APP_ERRORS_TOTAL = Counter(
    name="app_errors_total",
    documentation="Total number of internal application errors.",
    labelnames=["exception_type", "endpoint"],
    namespace=NAMESPACE,
)
