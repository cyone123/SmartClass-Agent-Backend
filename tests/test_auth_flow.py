from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.api.auth import router as auth_router
from app.api.plan import router as plan_router
from app.core.auth import create_access_token, hash_password
from app.dependencies.db import get_db
from app.models.plan import Plan
from app.models.user import User


class _Result:
    def __init__(self, items):
        self._items = items

    def scalar_one_or_none(self):
        return self._items[0] if self._items else None

    def scalars(self):
        return self

    def all(self):
        return self._items

    def first(self):
        return self._items[0] if self._items else None


class FakeSession:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)
        self.users: list[User] = [
            User(
                id=1,
                username="teacher_a",
                password_hash=hash_password("12345678"),
                display_name="A 老师",
                role="teacher",
                is_active=True,
                is_superuser=False,
                created_at=now,
                updated_at=now,
            ),
            User(
                id=2,
                username="teacher_b",
                password_hash=hash_password("87654321"),
                display_name="B 老师",
                role="teacher",
                is_active=True,
                is_superuser=False,
                created_at=now,
                updated_at=now,
            ),
        ]
        self.plans: list[Plan] = [
            Plan(id=101, user_id=1, name="A 的计划"),
            Plan(id=202, user_id=2, name="B 的计划"),
        ]
        self._next_user_id = 3
        self._next_plan_id = 303

    async def execute(self, stmt):
        text = str(stmt)
        if "FROM users" in text:
            if "username" in text:
                username = stmt.compile().params.get("username_1")
                items = [user for user in self.users if user.username == username]
                return _Result(items)
            return _Result(self.users)
        if "FROM teaching_plans" in text:
            params = stmt.compile().params
            user_id = params.get("user_id_1")
            plan_id = params.get("id_1")
            items = self.plans
            if user_id is not None:
                items = [plan for plan in items if plan.user_id == user_id]
            if plan_id is not None:
                items = [plan for plan in items if plan.id == plan_id]
            return _Result(items)
        return _Result([])

    async def get(self, model, record_id):
        if model is User:
            return next((user for user in self.users if user.id == record_id), None)
        if model is Plan:
            return next((plan for plan in self.plans if plan.id == record_id), None)
        return None

    def add(self, record):
        now = datetime.now(timezone.utc)
        if isinstance(record, User):
            record.id = record.id or self._next_user_id
            self._next_user_id += 1
            record.created_at = record.created_at or now
            record.updated_at = record.updated_at or now
            self.users.append(record)
        if isinstance(record, Plan):
            record.id = record.id or self._next_plan_id
            self._next_plan_id += 1
            record.sessions = []
            self.plans.append(record)

    def has_user(self, username: str) -> bool:
        return any(user.username == username for user in self.users)

    async def commit(self):
        return None

    async def refresh(self, record):
        return None


def _build_app(session: FakeSession) -> FastAPI:
    app = FastAPI()
    app.include_router(auth_router, prefix="/api")
    app.include_router(plan_router, prefix="/api")

    async def override_db():
        yield session

    app.dependency_overrides[get_db] = override_db
    return app


def _token(user: User) -> str:
    return create_access_token(user=user)[0]


def test_register_login_and_me_flow():
    session = FakeSession()
    app = _build_app(session)

    async def run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            register = await client.post(
                "/api/auth/register",
                json={"username": "teacher001", "password": "12345678", "display_name": "王老师"},
            )
            assert register.status_code == 200
            assert register.json()["data"]["role"] == "teacher"

            login = await client.post(
                "/api/auth/login",
                json={"username": "teacher001", "password": "12345678"},
            )
            assert login.status_code == 200
            token = login.json()["data"]["access_token"]

            me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
            assert me.status_code == 200
            assert me.json()["data"]["username"] == "teacher001"

    asyncio.run(run())


def test_auth_rejects_duplicate_short_admin_bad_password_and_invalid_token():
    session = FakeSession()
    app = _build_app(session)

    async def run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            assert (
                await client.post(
                    "/api/auth/register",
                    json={"username": "admin", "password": "12345678", "display_name": "管理员"},
                )
            ).status_code == 400
            assert (
                await client.post(
                    "/api/auth/register",
                    json={"username": "teacher_new", "password": "12345678", "display_name": "新老师"},
                )
            ).status_code == 200
            assert session.has_user("teacher_new")
            assert (
                await client.post(
                    "/api/auth/register",
                    json={"username": "teacher_new", "password": "12345678", "display_name": "重复"},
                )
            ).status_code == 400
            assert (
                await client.post(
                    "/api/auth/register",
                    json={"username": "short_pw", "password": "123", "display_name": "短密码"},
                )
            ).status_code == 422
            assert (
                await client.post(
                    "/api/auth/login",
                    json={"username": "teacher_a", "password": "wrong-password"},
                )
            ).status_code == 401
            assert (await client.get("/api/auth/me")).status_code == 401
            assert (
                await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid-token"})
            ).status_code == 401

    asyncio.run(run())


def test_plan_list_and_updates_are_scoped_to_current_user():
    session = FakeSession()
    app = _build_app(session)
    token_a = _token(session.users[0])
    token_b = _token(session.users[1])

    async def run() -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            list_a = await client.get("/api/plan", headers={"Authorization": f"Bearer {token_a}"})
            assert list_a.status_code == 200
            assert [item["id"] for item in list_a.json()["data"]] == [101]

            list_b = await client.get("/api/plan", headers={"Authorization": f"Bearer {token_b}"})
            assert list_b.status_code == 200
            assert [item["id"] for item in list_b.json()["data"]] == [202]

            foreign_update = await client.post(
                "/api/plan",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"id": 202, "name": "越权改名"},
            )
            assert foreign_update.status_code == 404

            own_update = await client.post(
                "/api/plan",
                headers={"Authorization": f"Bearer {token_a}"},
                json={"id": 101, "name": "A 的新计划名"},
            )
            assert own_update.status_code == 200

    asyncio.run(run())
