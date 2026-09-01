import time
from typing import Any, Literal, Protocol

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.errors import ApiError
from app.models import ModelSetting
from app.schemas import LlmConfigResponse, ModelTestResult, OllamaConfig, OllamaModelProbeResult
from app.security import decrypt_secret, encrypt_secret, mask_secret
from app.services.audit_service import record_audit


class OllamaClient(Protocol):
    async def list_tags(self, base_url: str) -> list[dict[str, Any]]: ...

    async def show_model(self, base_url: str, tag: str) -> dict[str, Any]: ...

    async def embed(self, base_url: str, tag: str, text: str) -> list[float]: ...


class HttpOllamaClient:
    async def list_tags(self, base_url: str) -> list[dict[str, Any]]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{base_url.rstrip('/')}/api/tags")
            response.raise_for_status()
            data = response.json()
            models = data.get("models", [])
            return models if isinstance(models, list) else []

    async def show_model(self, base_url: str, tag: str) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(f"{base_url.rstrip('/')}/api/show", json={"model": tag})
            response.raise_for_status()
            data = response.json()
            return data if isinstance(data, dict) else {}

    async def embed(self, base_url: str, tag: str, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=20) as client:
            response = await client.post(
                f"{base_url.rstrip('/')}/api/embed",
                json={"model": tag, "input": text},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings")
            if not isinstance(embeddings, list) or not embeddings:
                raise ValueError("missing embeddings")
            first = embeddings[0]
            if not isinstance(first, list):
                raise ValueError("invalid embedding")
            return [float(item) for item in first]


async def get_or_create_settings(session: AsyncSession, settings: Settings) -> ModelSetting:
    row = await session.get(ModelSetting, "global")
    if row is not None:
        return row
    row = ModelSetting(
        id="global",
        provider="openai",
        model="gpt-4o-mini",
        base_url=settings.openai_base_url,
        ollama_base_url=settings.ollama_base_url,
    )
    session.add(row)
    await session.flush()
    return row


def llm_response(row: ModelSetting, settings: Settings) -> LlmConfigResponse:
    api_key = decrypt_secret(row.api_key_encrypted, settings) if row.api_key_encrypted else None
    return LlmConfigResponse(
        provider=row.provider,
        model=row.model,
        base_url=row.base_url,
        api_key_configured=api_key is not None,
        api_key_masked=mask_secret(api_key),
        temperature=row.temperature,
        max_tokens=row.max_tokens,
        timeout_seconds=row.timeout_seconds,
        updated_at=row.updated_at,
    )


async def update_llm_config(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_id: str,
    workspace_id: str,
    provider: str,
    model: str,
    base_url: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    timeout_seconds: int,
) -> LlmConfigResponse:
    row = await get_or_create_settings(session, settings)
    row.provider = provider
    row.model = model
    row.base_url = base_url
    if api_key is not None:
        row.api_key_encrypted = encrypt_secret(api_key, settings)
    row.temperature = temperature
    row.max_tokens = max_tokens
    row.timeout_seconds = timeout_seconds
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="model.llm_config_update",
        resource_type="model_setting",
        resource_id=row.id,
        details={"provider": provider, "model": model},
    )
    await session.commit()
    return llm_response(row, settings)


async def test_llm_config(
    session: AsyncSession,
    *,
    settings: Settings,
) -> ModelTestResult:
    row = await get_or_create_settings(session, settings)
    started_at = time.perf_counter()
    api_key = decrypt_secret(row.api_key_encrypted, settings) if row.api_key_encrypted else ""
    if not api_key:
        return ModelTestResult(
            ok=False,
            code="auth_error",
            message="API Key 未配置",
            latency_ms=0,
        )
    try:
        async with httpx.AsyncClient(timeout=row.timeout_seconds) as client:
            response = await client.post(
                f"{row.base_url.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}"},
                json={
                    "model": row.model,
                    "messages": [{"role": "user", "content": "ping"}],
                    "max_tokens": 1,
                },
            )
        latency = int((time.perf_counter() - started_at) * 1000)
        if response.status_code in {401, 403}:
            return ModelTestResult(
                ok=False,
                code="auth_error",
                message="认证失败",
                latency_ms=latency,
            )
        if response.status_code == 404:
            return ModelTestResult(
                ok=False,
                code="model_not_found",
                message="模型不存在",
                latency_ms=latency,
            )
        if response.status_code >= 400:
            return ModelTestResult(
                ok=False,
                code="invalid_response",
                message=f"模型服务返回 {response.status_code}",
                latency_ms=latency,
            )
        return ModelTestResult(ok=True, code="ok", message="连通性正常", latency_ms=latency)
    except httpx.TimeoutException:
        return ModelTestResult(ok=False, code="timeout", message="请求超时", latency_ms=0)
    except httpx.HTTPError:
        return ModelTestResult(ok=False, code="network_error", message="网络错误", latency_ms=0)


async def get_ollama_config(session: AsyncSession, settings: Settings) -> OllamaConfig:
    row = await get_or_create_settings(session, settings)
    return OllamaConfig(base_url=row.ollama_base_url, updated_at=row.updated_at)


async def update_ollama_config(
    session: AsyncSession,
    *,
    settings: Settings,
    actor_id: str,
    workspace_id: str,
    base_url: str,
) -> OllamaConfig:
    row = await get_or_create_settings(session, settings)
    row.ollama_base_url = base_url
    await record_audit(
        session,
        workspace_id=workspace_id,
        user_id=actor_id,
        action="model.ollama_config_update",
        resource_type="model_setting",
        resource_id=row.id,
        details={"base_url": base_url},
    )
    await session.commit()
    return OllamaConfig(base_url=row.ollama_base_url, updated_at=row.updated_at)


def find_embedding_dim(model_info: dict[str, Any], embedding: list[float] | None) -> int | None:
    if embedding is not None:
        return len(embedding)
    info = model_info.get("model_info")
    if isinstance(info, dict):
        for key, value in info.items():
            if key.endswith(".embedding_length") and isinstance(value, int):
                return value
    return None


async def probe_ollama_model(
    *,
    base_url: str,
    tag: str,
    client: OllamaClient,
) -> OllamaModelProbeResult:
    try:
        details = await client.show_model(base_url, tag)
        capabilities_raw = details.get("capabilities", [])
        capabilities = (
            [str(item) for item in capabilities_raw]
            if isinstance(capabilities_raw, list)
            else []
        )
        try:
            embedding = await client.embed(base_url, tag, "KnowWeave embedding probe")
        except (httpx.HTTPStatusError, ValueError):
            embedding = None
        model_info = details.get("model_info", {})
        basename = model_info.get("general.basename") if isinstance(model_info, dict) else None
        digest = str(details.get("digest") or basename or tag)
        dim = find_embedding_dim(details, embedding)
        if "embedding" not in capabilities and embedding is None:
            return OllamaModelProbeResult(
                tag=tag,
                digest=digest,
                capabilities=capabilities,
                embedding_dim=dim,
                usable_for_v1=False,
                unusable_reason="not_embedding_model",
            )
        if dim != 1024:
            return OllamaModelProbeResult(
                tag=tag,
                digest=digest,
                capabilities=capabilities,
                embedding_dim=dim,
                usable_for_v1=False,
                unusable_reason="dimension_incompatible",
            )
        if "embedding" not in capabilities:
            capabilities.append("embedding")
        return OllamaModelProbeResult(
            tag=tag,
            digest=digest,
            capabilities=capabilities,
            embedding_dim=dim,
            usable_for_v1=True,
            unusable_reason=None,
        )
    except httpx.HTTPStatusError as exc:
        reason: Literal["model_not_found", "probe_failed"] = (
            "model_not_found" if exc.response.status_code == 404 else "probe_failed"
        )
        return OllamaModelProbeResult(
            tag=tag,
            digest="",
            capabilities=[],
            embedding_dim=None,
            usable_for_v1=False,
            unusable_reason=reason,
        )
    except httpx.HTTPError:
        return OllamaModelProbeResult(
            tag=tag,
            digest="",
            capabilities=[],
            embedding_dim=None,
            usable_for_v1=False,
            unusable_reason="network_error",
        )


async def list_ollama_models(
    session: AsyncSession,
    *,
    settings: Settings,
    client: OllamaClient,
) -> list[OllamaModelProbeResult]:
    row = await get_or_create_settings(session, settings)
    try:
        tags = await client.list_tags(row.ollama_base_url)
    except httpx.HTTPError as exc:
        raise ApiError("service_unavailable", "Ollama 服务不可用", 503) from exc
    results: list[OllamaModelProbeResult] = []
    for model in tags:
        tag = str(model.get("model") or model.get("name") or "")
        if not tag:
            continue
        result = await probe_ollama_model(base_url=row.ollama_base_url, tag=tag, client=client)
        if not result.digest:
            result.digest = str(model.get("digest") or "")
        results.append(result)
    return results
