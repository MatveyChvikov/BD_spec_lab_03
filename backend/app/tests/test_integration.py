"""
Integration tests for API endpoints.

These tests verify that the full stack works correctly.
They require a running database.

To run: pytest app/tests/test_integration.py -v
"""

import uuid

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport

from app.infrastructure.db import reset_engine_pool
from app.main import app


@pytest_asyncio.fixture(autouse=True)
async def _reset_app_engine_between_integration_tests():
    """pytest-asyncio даёт новый event loop на тест — пересоздаём пул приложения."""
    await reset_engine_pool()
    yield


class TestHealthEndpoint:
    """Test that the app starts correctly."""

    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """GET /health should return ok."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.get("/health")
            assert response.status_code == 200
            assert response.json() == {"status": "ok"}


class TestAPIEndpointsExist:
    """Test that all required endpoints exist."""

    @pytest.mark.asyncio
    async def test_users_endpoint_exists(self):
        """POST /api/users should exist."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            response = await client.post(
                "/api/users",
                json={
                    "email": f"apitest_{uuid.uuid4().hex}@example.com",
                    "name": "Test",
                },
            )
            # Should not be 404 (endpoint exists)
            # Will be 500 if not implemented, 201 if working
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_orders_endpoint_exists(self):
        """POST /api/orders should exist."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Create a user first (уникальный email — БД в Docker может переживать между прогонами)
            user_response = await client.post(
                "/api/users",
                json={
                    "email": f"ordertest_{uuid.uuid4().hex}@example.com",
                    "name": "Order Test",
                },
            )
            user_id = user_response.json()["id"]
            
            # Now create an order
            response = await client.post(
                "/api/orders",
                json={"user_id": user_id}
            )
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_pay_endpoint_exists(self):
        """POST /api/orders/{id}/pay should exist."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Create user and order first
            user_response = await client.post(
                "/api/users",
                json={
                    "email": f"paytest_{uuid.uuid4().hex}@example.com",
                    "name": "Pay Test",
                },
            )
            user_id = user_response.json()["id"]
            
            order_response = await client.post(
                "/api/orders",
                json={"user_id": user_id}
            )
            order_id = order_response.json()["id"]
            
            response = await client.post(
                f"/api/orders/{order_id}/pay"
            )
            assert response.status_code != 404

    @pytest.mark.asyncio
    async def test_cancel_endpoint_exists(self):
        """POST /api/orders/{id}/cancel should exist."""
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test"
        ) as client:
            # Create user and order first
            user_response = await client.post(
                "/api/users",
                json={
                    "email": f"canceltest_{uuid.uuid4().hex}@example.com",
                    "name": "Cancel Test",
                },
            )
            user_id = user_response.json()["id"]
            
            order_response = await client.post(
                "/api/orders",
                json={"user_id": user_id}
            )
            order_id = order_response.json()["id"]
            
            response = await client.post(
                f"/api/orders/{order_id}/cancel"
            )
            assert response.status_code != 404
