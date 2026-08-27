from typing import Annotated

from fastapi import APIRouter, Depends

from app.deps import Principal, SessionDep, SettingsDep, require_roles
from app.schemas import (
    LlmConfigResponse,
    LlmConfigUpdateRequest,
    ModelTestResult,
    OllamaConfig,
    OllamaConfigUpdateRequest,
    OllamaModelListResponse,
    OllamaModelProbeRequest,
    OllamaModelProbeResult,
)
from app.services.model_service import (
    HttpOllamaClient,
    OllamaClient,
    get_ollama_config,
    get_or_create_settings,
    list_ollama_models,
    llm_response,
    probe_ollama_model,
    test_llm_config,
    update_llm_config,
    update_ollama_config,
)

router = APIRouter(prefix="/admin", tags=["admin"])

AdminPrincipal = Annotated[Principal, Depends(require_roles("admin"))]


def get_ollama_client() -> OllamaClient:
    return HttpOllamaClient()


@router.get("/llm-config", response_model=LlmConfigResponse)
async def get_llm_config(
    _: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
) -> LlmConfigResponse:
    row = await get_or_create_settings(session, settings)
    return llm_response(row, settings)


@router.put("/llm-config", response_model=LlmConfigResponse)
async def put_llm_config(
    payload: LlmConfigUpdateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
) -> LlmConfigResponse:
    return await update_llm_config(
        session,
        settings=settings,
        actor_id=principal.user.id,
        workspace_id=principal.workspace.id,
        provider=payload.provider,
        model=payload.model,
        base_url=str(payload.base_url),
        api_key=payload.api_key,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        timeout_seconds=payload.timeout_seconds,
    )


@router.post("/llm-config/test", response_model=ModelTestResult)
async def post_llm_config_test(
    _: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
) -> ModelTestResult:
    return await test_llm_config(session, settings=settings)


@router.get("/ollama-config", response_model=OllamaConfig)
async def get_ollama(
    _: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
) -> OllamaConfig:
    return await get_ollama_config(session, settings)


@router.put("/ollama-config", response_model=OllamaConfig)
async def put_ollama(
    payload: OllamaConfigUpdateRequest,
    principal: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
) -> OllamaConfig:
    return await update_ollama_config(
        session,
        settings=settings,
        actor_id=principal.user.id,
        workspace_id=principal.workspace.id,
        base_url=str(payload.base_url),
    )


@router.get("/ollama/models", response_model=OllamaModelListResponse)
async def get_ollama_models(
    _: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> OllamaModelListResponse:
    return OllamaModelListResponse(
        items=await list_ollama_models(session, settings=settings, client=client)
    )


@router.post("/ollama/models/probe", response_model=OllamaModelProbeResult)
async def post_ollama_model_probe(
    payload: OllamaModelProbeRequest,
    _: AdminPrincipal,
    session: SessionDep,
    settings: SettingsDep,
    client: Annotated[OllamaClient, Depends(get_ollama_client)],
) -> OllamaModelProbeResult:
    config = await get_ollama_config(session, settings)
    return await probe_ollama_model(base_url=config.base_url, tag=payload.tag, client=client)
