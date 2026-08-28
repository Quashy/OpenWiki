import structlog
from typing import Any

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

    def finish(self, **kwargs: object) -> None:
        return None


class LangfuseSpan:
    def __init__(self, span: Any) -> None:
        self._span = span

    def __enter__(self) -> "LangfuseSpan":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc is not None:
            self.update(level="ERROR", status_message=str(exc))
        try:
            self._span.end()
        except Exception as end_exc:  # pragma: no cover - observability must not break jobs
            logger.warning("langfuse_span_end_failed", error=str(end_exc))
        return None

    def update(self, **kwargs: object) -> None:
        try:
            self._span.update(**kwargs)
        except Exception as exc:  # pragma: no cover - observability must not break jobs
            logger.warning("langfuse_span_update_failed", error=str(exc))


class LangfuseTrace:
    def __init__(self, *, trace_id: str, client: Any, root_observation: Any, close_root: bool) -> None:
        self.id = trace_id
        self._client = client
        self._root_observation = root_observation
        self._close_root = close_root
        self._finished = False

    def span(self, **kwargs: object) -> LangfuseSpan | NoopSpan:
        try:
            if hasattr(self._root_observation, "span"):
                return LangfuseSpan(self._root_observation.span(**kwargs))
            return LangfuseSpan(self._root_observation.start_observation(as_type="span", **kwargs))
        except Exception as exc:  # pragma: no cover - observability must not break jobs
            logger.warning("langfuse_span_start_failed", error=str(exc))
            return NoopSpan()

    def update(self, **kwargs: object) -> None:
        try:
            self._root_observation.update(**kwargs)
        except Exception as exc:  # pragma: no cover - observability must not break jobs
            logger.warning("langfuse_trace_update_failed", error=str(exc))

    def finish(self, **kwargs: object) -> None:
        if self._finished:
            return
        self._finished = True
        if kwargs and self._close_root:
            self.update(**kwargs)
        if self._close_root:
            try:
                self._root_observation.end()
            except Exception as exc:  # pragma: no cover - observability must not break jobs
                logger.warning("langfuse_trace_end_failed", error=str(exc))
        try:
            self._client.flush()
        except Exception as exc:  # pragma: no cover - observability must not break jobs
            logger.warning("langfuse_flush_failed", error=str(exc))


class Observability:
    def __init__(self, *, host: str, public_key: str, secret_key: str, client: Any | None = None) -> None:
        self.enabled = bool(host and public_key and secret_key)
        self._client = client
        if self.enabled:
            try:
                if self._client is None:
                    from langfuse import Langfuse

                    self._client = Langfuse(
                        host=host,
                        public_key=public_key,
                        secret_key=secret_key,
                    )
            except Exception as exc:  # pragma: no cover - defensive fallback
                logger.warning("langfuse_init_failed", error=str(exc))
                self.enabled = False

    def trace(self, *, name: str, metadata: dict[str, object]) -> NoopTrace | LangfuseTrace:
        if not self.enabled or self._client is None:
            return NoopTrace()
        try:
            if hasattr(self._client, "trace"):
                trace = self._client.trace(name=name, metadata=metadata)
                return LangfuseTrace(
                    trace_id=trace.id,
                    client=self._client,
                    root_observation=trace,
                    close_root=False,
                )

            trace_id = self._client.create_trace_id()
            root_observation = self._client.start_observation(
                trace_context={"trace_id": trace_id},
                name=name,
                as_type="span",
                metadata=metadata,
            )
            return LangfuseTrace(
                trace_id=trace_id,
                client=self._client,
                root_observation=root_observation,
                close_root=True,
            )
        except Exception as exc:  # pragma: no cover - network defensive fallback
            logger.warning("langfuse_trace_failed", name=name, error=str(exc))
            return NoopTrace()
