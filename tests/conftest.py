"""
Shared pytest fixtures for the test suite.

Uses a **separate** test PostgreSQL database (``test_certificates_db``)
and mocks Celery so tests run without Redis.
"""

import asyncio
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

# Point at a dedicated test database
TEST_DATABASE_URL = settings.DATABASE_URL.replace(
    "/certificates_db", "/test_certificates_db"
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionFactory = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def _override_get_db():
    async with TestSessionFactory() as session:
        try:
            yield session
        finally:
            await session.close()


# Override the dependency globally for all tests
app.dependency_overrides[get_db] = _override_get_db


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def event_loop():
    """Create a single event loop for the whole test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test and drop them after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client():
    """Provide an async HTTP client bound to the FastAPI app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def mock_celery():
    """
    Patch the Celery task so it doesn't require a running Redis broker.
    The ``.delay()`` call becomes a no-op that returns a fake task id.
    """
    with patch(
        "app.routers.certificates.process_batch_request"
    ) as mock_task:
        mock_task.delay = MagicMock(
            return_value=MagicMock(id="mock-task-id")
        )
        yield mock_task


@pytest.fixture
def valid_payload():
    """A well-formed batch request payload."""
    return {
        "course_name": "Advanced Python Programming",
        "issue_date": "2026-10-08",
        "recipients": [
            {"name": "Alice Johnson", "email": "alice@example.com"},
            {"name": "Bob Smith", "email": "bob@example.com"},
            {"name": "Charlie Lee", "email": "charlie@example.com"},
        ],
    }
