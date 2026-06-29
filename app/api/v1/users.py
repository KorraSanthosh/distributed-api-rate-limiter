from typing import List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

router = APIRouter()


class UserProfile(BaseModel):
    """Schema representing a single user account profile."""

    id: str = Field(..., description="Unique user identifier.")
    username: str = Field(..., description="Unique alphanumeric username.")
    email: str = Field(..., description="Registered user email address.")
    role: str = Field(..., description="Access privileges group (e.g. admin, user, read-only).")
    is_active: bool = Field(..., description="Account verification status.")


class UsersListResponse(BaseModel):
    """Container schema for collections of user profiles."""

    users: List[UserProfile] = Field(..., description="List of user profiles.")
    count: int = Field(..., description="Total profiles matching request filters.")


@router.get(
    "/users",
    response_model=UsersListResponse,
    summary="Get User Profiles",
    description="List active or filtered system user profiles (mocked database).",
)
async def get_users(
    role: Optional[str] = Query(default=None, description="Filter profiles by access level."),
    is_active: Optional[bool] = Query(default=None, description="Filter profiles by active status."),
) -> UsersListResponse:
    # Static database mock
    mock_users = [
        UserProfile(id="usr_1", username="alice_dev", email="alice@company.internal", role="admin", is_active=True),
        UserProfile(id="usr_2", username="bob_ops", email="bob@company.internal", role="operator", is_active=True),
        UserProfile(id="usr_3", username="charlie_guest", email="charlie@company.internal", role="guest", is_active=False),
        UserProfile(id="usr_4", username="david_contractor", email="david@company.internal", role="user", is_active=True),
        UserProfile(id="usr_5", username="emma_exec", email="emma@company.internal", role="admin", is_active=True),
    ]

    # Apply filters
    filtered_users = mock_users
    if role:
        filtered_users = [u for u in filtered_users if u.role == role.lower()]
    if is_active is not None:
        filtered_users = [u for u in filtered_users if u.is_active == is_active]

    return UsersListResponse(
        users=filtered_users,
        count=len(filtered_users),
    )
