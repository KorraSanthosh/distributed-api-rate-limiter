import asyncio
import logging
import time
from collections import Counter
from typing import List, Tuple

from app.core.config import settings
from app.repositories.redis_repository import RedisRepository
from app.schemas.analytics import (
    AbusiveClient,
    AnalyticsSummary,
    EndpointShare,
    RequestAnalyticsLog,
    StatusCount,
    SystemHealth,
    TrafficPoint,
)

logger = logging.getLogger("app")


class AnalyticsService:
    """Manages ingestion and querying of request logs in Redis Streams."""

    def __init__(self, redis_repository: RedisRepository) -> None:
        self.redis_repo = redis_repository
        self.stream_name = "api_traffic_stream"
        self.blocked_key = "api_blocked_events"
        # Short-lived cache so many dashboard viewers don't multiply the aggregation cost
        self._summary_cache: dict = {}
        self._summary_ttl = 1.0
        logger.info(f"AnalyticsService initialized with target stream '{self.stream_name}'.")

    async def log_request(self, log_event: RequestAnalyticsLog) -> None:
        """Publishes an API access log event to the Redis Stream.

        Args:
            log_event: Populated RequestAnalyticsLog schema.
        """
        try:
            # Convert schema to dict. Pydantic v2 model_dump() generates standard JSON types.
            payload = log_event.model_dump()
            
            # Publish to Redis
            await self.redis_repo.publish_analytics(self.stream_name, payload)
            # Blocked requests also go to a small capped list so they stay visible
            # on the dashboard regardless of overall traffic volume or time window.
            if not log_event.allowed:
                await self.redis_repo.push_blocked_event(self.blocked_key, payload)
        except Exception as e:
            # Non-blocking failure: logs should not disrupt API flow
            logger.error(f"Failed to record analytics event to Redis Stream: {e}", exc_info=True)

    async def fetch_recent_logs(
        self, count: int = 100, last_id: str = "0"
    ) -> List[Tuple[str, RequestAnalyticsLog]]:
        """Queries recent traffic records from the Redis Stream.

        Useful for real-time dashboards polling new data.

        Args:
            count: Number of recent items to fetch.
            last_id: Message ID offset to read from.

        Returns:
            List of tuples mapping [message_id, parsed_RequestAnalyticsLog].
        """
        raw_entries = await self.redis_repo.read_analytics(
            stream_name=self.stream_name, count=count, last_id=last_id
        )
        
        parsed_logs: List[Tuple[str, RequestAnalyticsLog]] = []
        for msg_id, payload in raw_entries:
            try:
                # Pydantic v2 automatically parses string values (e.g. float and bool) from Redis fields
                log_object = RequestAnalyticsLog.model_validate(payload)
                parsed_logs.append((msg_id, log_object))
            except Exception as e:
                logger.warning(
                    f"Corrupted or outdated log event structure in stream for ID {msg_id}: {e}"
                )
                continue
                
        return parsed_logs

    async def summarize(
        self,
        window_seconds: int = 60,
        history_seconds: int = 120,
        bucket_seconds: int = 2,
        max_events: int = 10000,
    ) -> AnalyticsSummary:
        """Aggregates recent stream events into dashboard-ready statistics.

        KPIs, endpoint split, status split and abusive clients cover the last
        `window_seconds`; the time series covers the last `history_seconds`.

        At most `max_events` entries are read. If that cap is hit the stream holds
        more traffic than was read, so the effective window shrinks to the span
        actually covered and rates are computed over that span (never under-reported).
        """
        cache_key = (window_seconds, history_seconds, bucket_seconds, max_events)
        cached = self._summary_cache.get(cache_key)
        if cached and time.time() - cached[0] < self._summary_ttl:
            return cached[1]

        raw = await self.redis_repo.read_recent_analytics(self.stream_name, count=max_events)
        blocked_raw = await self.redis_repo.read_blocked_events(self.blocked_key, count=25)
        recent_blocked = []
        for item in blocked_raw:
            try:
                recent_blocked.append(RequestAnalyticsLog.model_validate(item))
            except Exception as e:
                logger.warning(f"Skipping malformed blocked event: {e}")
        system = SystemHealth(
            redis_connected=await self.redis_repo.ping(),
            environment=settings.ENV,
            version=settings.VERSION,
        )
        # CPU-bound aggregation runs in a worker thread so it never stalls the event loop
        # that is also serving rate-limited traffic.
        summary = await asyncio.to_thread(
            self._aggregate, raw, system, recent_blocked, window_seconds, history_seconds, bucket_seconds, max_events
        )
        self._summary_cache[cache_key] = (time.time(), summary)
        return summary

    def _aggregate(
        self,
        raw: List[Tuple[str, dict]],
        system: SystemHealth,
        recent_blocked: List[RequestAnalyticsLog],
        window_seconds: int,
        history_seconds: int,
        bucket_seconds: int,
        max_events: int,
    ) -> AnalyticsSummary:
        # Parse raw stream fields directly: building a model per event is too slow here.
        events: List[dict] = []
        for msg_id, f in raw:
            try:
                events.append(
                    {
                        "request_id": f["request_id"],
                        "timestamp": float(f["timestamp"]),
                        "client_ip": f["client_ip"],
                        "method": f["method"],
                        "endpoint": f["endpoint"],
                        "status_code": int(f["status_code"]),
                        "latency_ms": float(f["latency_ms"]),
                        "allowed": f["allowed"] == "True",
                    }
                )
            except (KeyError, ValueError) as e:
                logger.warning(f"Skipping malformed analytics event {msg_id}: {e}")

        now = time.time()
        effective_window = float(window_seconds)
        truncated = len(raw) >= max_events and bool(events)
        if truncated:
            effective_window = max(1.0, min(effective_window, now - events[0]["timestamp"]))

        in_window = [e for e in events if e["timestamp"] >= now - effective_window]
        blocked = [e for e in in_window if not e["allowed"]]
        total = len(in_window)

        # Time series, zero-filled so charts have a continuous x-axis
        buckets = history_seconds // bucket_seconds
        end = int(now // bucket_seconds) * bucket_seconds
        start = end - (buckets - 1) * bucket_seconds
        allowed_by_bucket: Counter = Counter()
        blocked_by_bucket: Counter = Counter()
        for e in events:
            b = int(e["timestamp"] // bucket_seconds) * bucket_seconds
            if b < start:
                continue
            (allowed_by_bucket if e["allowed"] else blocked_by_bucket)[b] += 1
        timeseries = [
            TrafficPoint(
                timestamp=float(t),
                allowed=allowed_by_bucket[t],
                blocked=blocked_by_bucket[t],
            )
            for t in range(start, end + bucket_seconds, bucket_seconds)
        ]

        endpoint_totals = Counter(e["endpoint"] for e in in_window)
        endpoint_blocked = Counter(e["endpoint"] for e in blocked)
        latencies = sorted(e["latency_ms"] for e in in_window)
        p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else 0.0

        return AnalyticsSummary(
            generated_at=now,
            system=system,
            window_seconds=window_seconds,
            effective_window_seconds=round(effective_window, 1),
            window_truncated=truncated and effective_window < window_seconds,
            total_requests=total,
            allowed_requests=total - len(blocked),
            blocked_requests=len(blocked),
            requests_per_second=round(total / effective_window, 2),
            block_rate_pct=round(len(blocked) / total * 100, 2) if total else 0.0,
            active_ips=len({e["client_ip"] for e in in_window}),
            avg_latency_ms=round(sum(latencies) / len(latencies), 2) if latencies else 0.0,
            p95_latency_ms=round(p95, 2),
            timeseries=timeseries,
            status_codes=[
                StatusCount(status_code=code, count=n)
                for code, n in sorted(Counter(e["status_code"] for e in in_window).items())
            ],
            top_abusive_clients=[
                AbusiveClient(client_ip=ip, blocked=n)
                for ip, n in Counter(e["client_ip"] for e in blocked).most_common(10)
            ],
            endpoints=[
                EndpointShare(
                    endpoint=ep,
                    requests=n,
                    blocked=endpoint_blocked[ep],
                    share_pct=round(n / total * 100, 2),
                )
                for ep, n in endpoint_totals.most_common()
            ],
            recent=[RequestAnalyticsLog(**e) for e in reversed(events[-25:])],
            recent_blocked=recent_blocked,
        )
