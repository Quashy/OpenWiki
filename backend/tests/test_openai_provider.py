import httpx
import pytest

from app.services.llm.openai_provider import OpenAILLMProvider


class StubAsyncClient:
    def __init__(self, responses: list[httpx.Response], requests: list[dict[str, object]]) -> None:
        self._responses = responses
        self._requests = requests

    async def __aenter__(self) -> "StubAsyncClient":
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        return None

    async def post(self, url: str, *, headers: dict[str, str], json: dict[str, object]) -> httpx.Response:
        self._requests.append({"url": url, "headers": headers, "json": json})
        return self._responses.pop(0)


def chat_response(*, content: str, finish_reason: str, total_tokens: int) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": f"chatcmpl-{total_tokens}",
            "model": "deepseek-v4-flash",
            "choices": [
                {
                    "index": 0,
                    "finish_reason": finish_reason,
                    "message": {"role": "assistant", "content": content},
                }
            ],
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": max(total_tokens - 100, 0),
                "total_tokens": total_tokens,
            },
        },
    )


@pytest.mark.asyncio
async def test_openai_provider_retries_empty_content_once(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        chat_response(content="", finish_reason="stop", total_tokens=100),
        chat_response(content='{"ok": true}', finish_reason="stop", total_tokens=108),
    ]
    requests: list[dict[str, object]] = []

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *, timeout: StubAsyncClient(responses, requests),
    )

    provider = OpenAILLMProvider(base_url="https://api.deepseek.com/v1", api_key="key", model="deepseek-v4-flash")

    content = await provider.complete([{"role": "user", "content": "hello"}])

    assert content == '{"ok": true}'
    assert len(requests) == 2
    assert provider.last_response_metadata["llm_response_attempt_count"] == 2
    assert provider.last_response_metadata["llm_response_empty_retry_count"] == 1
    assert provider.last_response_metadata["llm_response_content_empty"] is False
    attempts = provider.last_response_metadata["llm_response_attempts"]
    assert [attempt["llm_response_content_empty"] for attempt in attempts] == [True, False]
    assert [attempt["llm_response_finish_reason"] for attempt in attempts] == ["stop", "stop"]


@pytest.mark.asyncio
async def test_openai_provider_returns_empty_after_retry_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    responses = [
        chat_response(content="", finish_reason="stop", total_tokens=100),
        chat_response(content="", finish_reason="stop", total_tokens=100),
        chat_response(content="", finish_reason="content_filter", total_tokens=100),
    ]
    requests: list[dict[str, object]] = []

    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda *, timeout: StubAsyncClient(responses, requests),
    )

    provider = OpenAILLMProvider(base_url="https://api.deepseek.com/v1", api_key="key", model="deepseek-v4-flash")

    content = await provider.complete([{"role": "user", "content": "hello"}])

    assert content == ""
    assert len(requests) == 3
    assert provider.last_response_metadata["llm_response_attempt_count"] == 3
    assert provider.last_response_metadata["llm_response_empty_retry_count"] == 2
    assert provider.last_response_metadata["llm_response_content_empty"] is True
    assert provider.last_response_metadata["llm_response_finish_reason"] == "content_filter"
