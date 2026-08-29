import json
from collections.abc import AsyncIterator
from typing import Any

import httpx

from app.errors import ApiError
from app.services.llm.base import LLMProvider


MAX_EMPTY_CONTENT_ATTEMPTS = 3


class OpenAILLMProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        default_temperature: float = 0.7,
        default_timeout_seconds: int = 60,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.default_temperature = default_temperature
        self.default_timeout_seconds = default_timeout_seconds
        self.last_response_metadata: dict[str, Any] = {}

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> str:
        self.last_response_metadata = {}
        if not self.api_key:
            raise ApiError("llm_not_configured", "LLM API Key 未配置", 409)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds or self.default_timeout_seconds) as client:
                attempt_metadata: list[dict[str, Any]] = []
                for attempt_number in range(1, MAX_EMPTY_CONTENT_ATTEMPTS + 1):
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json={
                            "model": self.model,
                            "messages": messages,
                            "temperature": self.default_temperature
                            if temperature is None
                            else temperature,
                        },
                    )
                    if response.status_code in {401, 403}:
                        raise ApiError("llm_auth_error", "LLM 认证失败", 503)
                    if response.status_code == 404:
                        raise ApiError("llm_model_not_found", "LLM 模型不存在", 503)
                    if response.status_code >= 400:
                        raise ApiError(
                            "llm_invalid_response",
                            f"LLM 服务返回 {response.status_code}",
                            503,
                        )
                    data = response.json()
                    choices = data.get("choices")
                    if not isinstance(choices, list) or not choices:
                        raise ApiError("llm_invalid_response", "LLM 响应缺少 choices", 503)
                    choice = choices[0]
                    message = choice.get("message") if isinstance(choice, dict) else None
                    content = message.get("content") if isinstance(message, dict) else None
                    if not isinstance(content, str):
                        raise ApiError("llm_invalid_response", "LLM 响应缺少 content", 503)
                    response_metadata = build_response_metadata(
                        data,
                        choice,
                        content,
                        http_status_code=response.status_code,
                    )
                    response_metadata["llm_response_attempt_number"] = attempt_number
                    attempt_metadata.append(response_metadata)
                    if content.strip() or attempt_number == MAX_EMPTY_CONTENT_ATTEMPTS:
                        self.last_response_metadata = {
                            **response_metadata,
                            "llm_response_attempt_count": attempt_number,
                            "llm_response_empty_retry_count": attempt_number - 1,
                            "llm_response_attempts": attempt_metadata,
                        }
                        return content
            raise ApiError(
                "llm_invalid_response",
                "LLM 响应缺少 content",
                503,
            )
        except httpx.TimeoutException as exc:
            raise ApiError("llm_timeout", "LLM 响应超时", 503) from exc
        except httpx.HTTPError as exc:
            raise ApiError("llm_network_error", "LLM 网络请求失败", 503) from exc

    async def stream(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
        prompt_metadata: dict[str, str] | None = None,
    ) -> AsyncIterator[str]:
        self.last_response_metadata = {}
        if not self.api_key:
            raise ApiError("llm_not_configured", "LLM API Key 未配置", 409)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds or self.default_timeout_seconds) as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    json={
                        "model": self.model,
                        "messages": messages,
                        "temperature": self.default_temperature if temperature is None else temperature,
                        "stream": True,
                    },
                ) as response:
                    if response.status_code in {401, 403}:
                        raise ApiError("llm_auth_error", "LLM 认证失败", 503)
                    if response.status_code == 404:
                        raise ApiError("llm_model_not_found", "LLM 模型不存在", 503)
                    if response.status_code >= 400:
                        raise ApiError(
                            "llm_invalid_response",
                            f"LLM 服务返回 {response.status_code}",
                            503,
                        )
                    content_length = 0
                    async for line in response.aiter_lines():
                        if not line.startswith("data:"):
                            continue
                        data = line.removeprefix("data:").strip()
                        if data == "[DONE]":
                            break
                        try:
                            payload = json.loads(data)
                        except json.JSONDecodeError:
                            continue
                        choices = payload.get("choices")
                        if not isinstance(choices, list) or not choices:
                            continue
                        choice = choices[0]
                        delta = choice.get("delta") if isinstance(choice, dict) else None
                        token = delta.get("content") if isinstance(delta, dict) else None
                        if isinstance(token, str) and token:
                            content_length += len(token)
                            yield token
                    self.last_response_metadata = {
                        "llm_response_model": self.model,
                        "llm_response_content_length": content_length,
                        "llm_response_stream": True,
                    }
        except httpx.TimeoutException as exc:
            raise ApiError("llm_timeout", "LLM 响应超时", 503) from exc
        except httpx.HTTPError as exc:
            raise ApiError("llm_network_error", "LLM 网络请求失败", 503) from exc


def build_response_metadata(
    data: dict[str, Any],
    choice: object,
    content: str,
    *,
    http_status_code: int | None = None,
) -> dict[str, Any]:
    usage = data.get("usage")
    choice_metadata: dict[str, Any] = {}
    message_metadata: dict[str, Any] = {}
    if isinstance(choice, dict):
        choice_metadata = {key: value for key, value in choice.items() if key != "message"}
        message = choice.get("message")
        if isinstance(message, dict):
            message_metadata = {key: value for key, value in message.items() if key != "content"}
    return {
        "llm_response_http_status": http_status_code,
        "llm_response_id": data.get("id"),
        "llm_response_model": data.get("model"),
        "llm_response_created": data.get("created"),
        "llm_response_system_fingerprint": data.get("system_fingerprint"),
        "llm_response_service_tier": data.get("service_tier"),
        "llm_response_usage": usage if isinstance(usage, dict) else None,
        "llm_response_choice_metadata": choice_metadata,
        "llm_response_message_metadata": message_metadata,
        "llm_response_finish_reason": choice_metadata.get("finish_reason"),
        "llm_response_content_length": len(content),
        "llm_response_content_empty": not content.strip(),
    }
