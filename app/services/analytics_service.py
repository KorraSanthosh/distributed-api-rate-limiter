import logging
from typing import List, Tuple

from app.repositories.redis_repository import RedisRepository
from app.schemas.analytics import RequestAnalyticsLog

logger = logging.getLogger("app")


class AnalyticsService:
    """Manages ingestion and querying of request logs in Redis Streams."""

    def __init__(self, redis_repository: RedisRepository) -> None:
        self.redis_repo = redis_repository
        self.stream_name = "api_traffic_stream"
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
