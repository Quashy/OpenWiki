import httpx

from app.errors import ApiError
from app.services.llm.base import LLMProvider


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

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float | None = None,
        timeout_seconds: int | None = None,
    ) -> str:
        if not self.api_key:
            raise ApiError("llm_not_configured", "LLM API Key 未配置", 409)
        try:
            async with httpx.AsyncClient(timeout=timeout_seconds or self.default_timeout_seconds) as client:
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
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, str):
                raise ApiError("llm_invalid_response", "LLM 响应缺少 content", 503)
            return content
        except httpx.TimeoutException as exc:
            raise ApiError("llm_timeout", "LLM 响应超时", 503) from exc
        except httpx.HTTPError as exc:
            raise ApiError("llm_network_error", "LLM 网络请求失败", 503) from exc
