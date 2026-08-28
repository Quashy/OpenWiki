from collections.abc import AsyncIterator, Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.api.admin import get_ollama_client
from app.config import Settings, get_settings
from app.database import Base, get_session
from app.main import create_app


class FakeOllamaClient:
    def __init__(self) -> None:
        self.models: dict[str, dict[str, Any]] = {
            "bge-m3": {
                "digest": "sha256:bge",
                "capabilities": ["embedding"],
                "embedding": [0.1] * 1024,
            },
            "nomic-embed-text": {
                "digest": "sha256:nomic",
                "capabilities": ["embedding"],
                "embedding": [0.1] * 768,
            },
            "llama3": {
                "digest": "sha256:llama",
                "capabilities": ["completion"],
                "embedding": None,
            },
        }

    async def list_tags(self, base_url: str) -> list[dict[str, object]]:
        return [
            {"model": tag, "name": tag, "digest": data["digest"]}
            for tag, data in self.models.items()
        ]

    async def show_model(self, base_url: str, tag: str) -> dict[str, object]:
        data = self.models[tag]
        return {
            "digest": data["digest"],
            "capabilities": data["capabilities"],
            "model_info": {"bge.embedding_length": len(data["embedding"] or [])},
        }

    async def embed(self, base_url: str, tag: str, text: str) -> list[float]:
        embedding = self.models[tag]["embedding"]
        if embedding is None:
            raise ValueError("not an embedding model")
        return list(embedding)


def register_user(client: TestClient, username: str, password: str = "password123") -> dict:
    response = client.post(
        "/api/v1/auth/register",
        json={"username": username, "password": password},
    )
    assert response.status_code == 201
    return response.json()


def auth_header(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def client(tmp_path) -> Iterator[TestClient]:
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async def init_db() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def override_session() -> AsyncIterator[AsyncSession]:
        async with session_factory() as session:
            yield session

    import asyncio

    asyncio.run(init_db())
    app = create_app()
    test_settings = Settings(upload_dir=tmp_path / "uploads")
    app.state.session_factory = session_factory
    app.state.settings = test_settings
    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_ollama_client] = lambda: FakeOllamaClient()
    app.dependency_overrides[get_settings] = lambda: test_settings

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    asyncio.run(engine.dispose())
