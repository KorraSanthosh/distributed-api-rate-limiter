from typing import List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class OrderItem(BaseModel):
    """Schema representing an itemized order purchase entry."""

    product_id: str = Field(..., description="Unique product stock identifier.")
    quantity: int = Field(..., description="Quantity purchased.", ge=1)
    price: float = Field(..., description="Price per unit currency.", ge=0.0)


class Order(BaseModel):
    """Schema representing a transaction order invoice."""

    order_id: str = Field(..., description="Unique invoice ID.")
    customer_id: str = Field(..., description="Target customer identifier.")
    items: List[OrderItem] = Field(..., description="List of purchase entries.")
    total_amount: float = Field(..., description="Calculated total order price.")
    status: str = Field(..., description="Shipping status (pending, shipped, cancelled).")


class OrdersResponse(BaseModel):
    """Container schema for collections of order records."""

    orders: List[Order] = Field(..., description="List of order records.")
    count: int = Field(..., description="Total orders matching request filters.")


@router.get(
    "/orders",
    response_model=OrdersResponse,
    summary="Get Customer Orders",
    description="List commerce transaction invoice logs (mocked database).",
)
async def get_orders(
    customer_id: Optional[str] = Query(default=None, description="Filter orders by customer ID."),
    status: Optional[str] = Query(default=None, description="Filter orders by status."),
) -> OrdersResponse:
    # Static database mock
    mock_orders = [
        Order(
            order_id="ord_101",
            customer_id="cust_88",
            items=[OrderItem(product_id="prod_a", quantity=2, price=29.99)],
            total_amount=59.98,
            status="shipped",
        ),
        Order(
            order_id="ord_102",
            customer_id="cust_99",
            items=[
                OrderItem(product_id="prod_b", quantity=1, price=199.99),
                OrderItem(product_id="prod_c", quantity=3, price=9.50),
            ],
            total_amount=228.49,
            status="pending",
        ),
        Order(
            order_id="ord_103",
            customer_id="cust_88",
            items=[OrderItem(product_id="prod_c", quantity=10, price=9.50)],
            total_amount=95.00,
            status="cancelled",
        ),
    ]

    # Apply filters
    filtered_orders = mock_orders
    if customer_id:
        filtered_orders = [o for o in filtered_orders if o.customer_id == customer_id]
    if status:
        filtered_orders = [o for o in filtered_orders if o.status == status.lower()]

    return OrdersResponse(
        orders=filtered_orders,
        count=len(filtered_orders),
    )
