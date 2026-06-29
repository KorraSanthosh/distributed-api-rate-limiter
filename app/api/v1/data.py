from typing import Any, Dict, List
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class DataResponse(BaseModel):
    """Schema representing generic queryable mock system metrics."""

    items: List[Dict[str, Any]] = Field(..., description="List of generic system statistics records.")
    total: int = Field(..., description="Total items available in data repository.")
    page: int = Field(..., description="Current page offset.")
    limit: int = Field(..., description="Maximum items per page requested.")


@router.get(
    "/data",
    response_model=DataResponse,
    summary="Query Mock System Metrics",
    description="Retrieve lists of server performance telemetry metrics (mocked). Controlled by pagination parameters.",
)
async def get_data(
    page: int = Query(default=1, ge=1, description="Page index parameter."),
    limit: int = Query(default=10, ge=1, le=100, description="Items limit parameter."),
) -> DataResponse:
    # Generate generic telemetry details
    mock_metrics = [
        {"metric_id": f"metric_{i}", "source": "node_exporter", "cpu_utilization": 12.5 + i * 2.1, "memory_free_bytes": 1024 * 1024 * (50 + i)}
        for i in range(1, 21)
    ]

    # Calculate pagination slice
    start_idx = (page - 1) * limit
    end_idx = start_idx + limit
    paginated_items = mock_metrics[start_idx:end_idx]

    return DataResponse(
        items=paginated_items,
        total=len(mock_metrics),
        page=page,
        limit=limit,
    )
