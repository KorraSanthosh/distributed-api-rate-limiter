import json
import logging
from typing import Dict, List, Tuple, Any
import redis.asyncio as aioredis
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.metrics import REDIS_OPERATIONS_TOTAL, REDIS_ACTIVE_CONNECTIONS

logger = logging.getLogger("app")


class RedisRepository:
    """Encapsulates data access and atomic operations on Redis."""

    def __init__(self) -> None:
        # Blocking pool: when all connections are busy, callers wait (up to REDIS_POOL_TIMEOUT)
        # instead of failing immediately, so bursts do not make the limiter fail open.
        self.pool = aioredis.BlockingConnectionPool(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASSWORD,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
            timeout=settings.REDIS_POOL_TIMEOUT,
            socket_timeout=settings.REDIS_TIMEOUT,
            decode_responses=True,  # Automatically decode bytes to str
        )
        self.redis: aioredis.Redis = aioredis.Redis(connection_pool=self.pool)

        # Configurable burst window (typically 2 seconds to prevent micro-burst abuse)
        self.burst_window_seconds = 2.0

        # Register Lua script for rate limiting
        # Returns: {allowed_flag (0 or 1), main_window_count, burst_window_count}
        self.rate_limit_lua = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local burst_window = tonumber(ARGV[4])
        local burst_limit = tonumber(ARGV[5])
        
        local clear_before = now - window
        
        -- 1. Clean up old logs outside the sliding window
        redis.call('ZREMRANGEBYSCORE', key, '-inf', clear_before)
        
        -- 2. Count total requests in the current window
        local current_requests = redis.call('ZCARD', key)
        
        -- 3. Count total requests in the smaller burst window
        local burst_clear_before = now - burst_window
        local burst_requests = redis.call('ZCOUNT', key, burst_clear_before, '+inf')
        
        -- 4. Check against both normal limits and burst limits
        if current_requests < limit and burst_requests < burst_limit then
            -- Record current request timestamp (using score and member as timestamp)
            redis.call('ZADD', key, now, now)
            -- Set Key TTL to the window duration to automatically prune idle keys
            redis.call('EXPIRE', key, math.ceil(window))
            return {1, current_requests + 1, burst_requests + 1}
        else
            return {0, current_requests, burst_requests}
        end
        """
        self._lua_script = self.redis.register_script(self.rate_limit_lua)
        logger.info("RedisRepository initialized with Lua rate limiting script.")

    async def close(self) -> None:
        """Closes the Redis client connection pool."""
        logger.info("Closing Redis connection pool...")
        await self.pool.disconnect()

    async def ping(self) -> bool:
        """Checks Redis server availability."""
        try:
            is_alive = await self.redis.ping()
            REDIS_OPERATIONS_TOTAL.labels(operation="ping", status="success").inc()
            # Update connection gauge
            try:
                in_use = len(self.redis.connection_pool._in_use_connections) # type: ignore
                REDIS_ACTIVE_CONNECTIONS.labels(pool_name="default").set(in_use)
            except AttributeError:
                pass
            return is_alive
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="ping", status="failure").inc()
            logger.error(f"Redis healthcheck failed: {e}")
            return False

    async def check_rate_limit(
        self,
        key: str,
        now: float,
        window: int,
        limit: int,
        burst_limit: int,
    ) -> Tuple[bool, int, int]:
        """Atomically checks and records request in Redis using Lua script.

        Args:
            key: Rate limiter key (e.g. rate_limit:127.0.0.1)
            now: Current timestamp (epoch float)
            window: Rate limiter window size in seconds
            limit: Normal request limit inside the window
            burst_limit: Maximum burst limit inside the 2-second burst window

        Returns:
            Tuple of (allowed, current_main_count, current_burst_count)
        """
        try:
            # Execute Lua Script
            result = await self._lua_script(
                keys=[key],
                args=[
                    str(now),
                    str(window),
                    str(limit),
                    str(self.burst_window_seconds),
                    str(burst_limit),
                ],
            )
            REDIS_OPERATIONS_TOTAL.labels(operation="check_rate_limit", status="success").inc()
            
            allowed = bool(result[0])
            main_count = int(result[1])
            burst_count = int(result[2])
            return allowed, main_count, burst_count
            
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="check_rate_limit", status="failure").inc()
            logger.error(f"Redis error while checking rate limit for key {key}: {e}")
            # Fail-safe open: If Redis fails, allow traffic in production, or raise error.
            # Here we raise the error to let the middleware handle standard fallbacks.
            raise e

    async def publish_analytics(self, stream_name: str, data: Dict[str, Any]) -> str:
        """Appends a structured analytics log event to a Redis Stream.

        Args:
            stream_name: The target Redis Stream key
            data: Key-value log entries (must be flat dictionary of strings)

        Returns:
            The generated message ID
        """
        try:
            # Stream payload must consist of strings
            flat_payload = {k: str(v) for k, v in data.items()}
            
            # Send message to Stream, auto-trimming to keep memory bounded (max 50,000 entries)
            msg_id = await self.redis.xadd(
                name=stream_name,
                fields=flat_payload,
                maxlen=50000,
                approximate=True,
            )
            REDIS_OPERATIONS_TOTAL.labels(operation="publish_analytics", status="success").inc()
            return msg_id
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="publish_analytics", status="failure").inc()
            logger.error(f"Redis error writing to stream {stream_name}: {e}")
            raise e

    async def read_analytics(
        self, stream_name: str, count: int = 100, last_id: str = "0"
    ) -> List[Tuple[str, Dict[str, str]]]:
        """Reads logs from the Redis stream starting from a specific offset ID.

        Args:
            stream_name: The Redis Stream key
            count: Max items to fetch
            last_id: ID offset (e.g. '0' for everything, or a specific timestamp ID)

        Returns:
            List of tuples (message_id, data_dictionary)
        """
        try:
            # Fetch stream entries
            streams = await self.redis.xread({stream_name: last_id}, count=count)
            REDIS_OPERATIONS_TOTAL.labels(operation="read_analytics", status="success").inc()
            
            if not streams:
                return []
            
            # Parse streams result structure: [[stream_name, [[msg_id, fields_dict]]]]
            results = []
            for _, messages in streams:
                for msg_id, fields in messages:
                    results.append((msg_id, fields))
            return results
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="read_analytics", status="failure").inc()
            logger.error(f"Redis error reading from stream {stream_name}: {e}")
            return []

    async def push_blocked_event(self, key: str, data: Dict[str, Any], max_len: int = 50) -> None:
        """Keeps the newest `max_len` blocked-request events in a capped Redis list (newest first)."""
        try:
            async with self.redis.pipeline(transaction=False) as pipe:
                pipe.lpush(key, json.dumps(data))
                pipe.ltrim(key, 0, max_len - 1)
                await pipe.execute()
            REDIS_OPERATIONS_TOTAL.labels(operation="push_blocked_event", status="success").inc()
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="push_blocked_event", status="failure").inc()
            logger.error(f"Redis error pushing blocked event to {key}: {e}")

    async def read_blocked_events(self, key: str, count: int = 25) -> List[Dict[str, Any]]:
        """Returns up to `count` newest blocked-request events (newest first)."""
        try:
            raw = await self.redis.lrange(key, 0, count - 1)
            REDIS_OPERATIONS_TOTAL.labels(operation="read_blocked_events", status="success").inc()
            return [json.loads(item) for item in raw]
        except (RedisError, ValueError) as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="read_blocked_events", status="failure").inc()
            logger.error(f"Redis error reading blocked events from {key}: {e}")
            return []

    async def read_recent_analytics(
        self, stream_name: str, count: int = 5000
    ) -> List[Tuple[str, Dict[str, str]]]:
        """Reads the newest `count` entries of a stream, returned oldest-first."""
        try:
            entries = await self.redis.xrevrange(stream_name, count=count)
            REDIS_OPERATIONS_TOTAL.labels(operation="read_recent_analytics", status="success").inc()
            return [(msg_id, fields) for msg_id, fields in reversed(entries)]
        except RedisError as e:
            REDIS_OPERATIONS_TOTAL.labels(operation="read_recent_analytics", status="failure").inc()
            logger.error(f"Redis error reading recent entries from stream {stream_name}: {e}")
            return []

    async def get_ttl(self, key: str) -> int:
        """Returns the TTL remaining (in seconds) for a key."""
        try:
            ttl = await self.redis.ttl(key)
            # If key does not exist or has no TTL, return 0
            return max(0, ttl)
        except RedisError:
            return 0
