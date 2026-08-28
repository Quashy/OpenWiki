from app.services.llm.openai_provider import OpenAILLMProvider


class DeepSeekLLMProvider(OpenAILLMProvider):
    """DeepSeek exposes an OpenAI-compatible Chat Completions API."""
