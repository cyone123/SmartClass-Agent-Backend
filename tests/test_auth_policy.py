from __future__ import annotations

from datetime import datetime, timezone

from app.core.auth import create_access_token, hash_password
from app.models.user import User


def test_jwt_token_contains_user_id():
    user = User(
        id=12,
        username="teacher001",
        password_hash=hash_password("12345678"),
        display_name="王老师",
        role="teacher",
        is_active=True,
        is_superuser=False,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    token, expires_in = create_access_token(user=user)
    assert token
    assert expires_in > 0
