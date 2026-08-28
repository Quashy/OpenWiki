import structlog

logger = structlog.get_logger(__name__)


class NoopSpan:
    def __enter__(self) -> "NoopSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def update(self, **kwargs: object) -> None:
        return None


class NoopTrace:
    def __init__(self, trace_id: str | None = None) -> None:
        self.id = trace_id

    def span(self, **kwargs: object) -> NoopSpan:
        return NoopSpan()

    def update(self, **kwargs: object) -> None:
        return None


class Observability:
    def __init__(self, *, host: str, public_key: str, secret_key: str) -> None:
        self.enabled = bool(host and public_key and secret_key)
        self._client = None
        if self.enabled:
            try:
                from langfuse import Langfuse

                self._client = Langfuse(
                    host=host,
                    public_key=public_key,
                    secret_key=secret_key,
                )
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("langfuse_init_failed", error=str(exc))
                self.enabled = False

    def trace(self, *, name: str, metadata: dict[str, object]) -> NoopTrace:
        if not self.enabled or self._client is None:
            return NoopTrace()
        try:
            return self._client.trace(name=name, metadata=metadata)
        except Exception as exc:  # pragma: no cover - network defensive fallback
            logger.warning("langfuse_trace_failed", name=name, error=str(exc))
            return NoopTrace()
