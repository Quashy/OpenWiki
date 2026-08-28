from app.services.observability import NoopTrace, Observability


class FakeLangfuseSpan:
    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.children: list[FakeLangfuseSpan] = []
        self.updates: list[dict[str, object]] = []
        self.ended = False

    def start_observation(self, **kwargs: object) -> "FakeLangfuseSpan":
        child = FakeLangfuseSpan(**kwargs)
        self.children.append(child)
        return child

    def update(self, **kwargs: object) -> None:
        self.updates.append(kwargs)

    def end(self) -> None:
        self.ended = True


class FakeLangfuseClient:
    def __init__(self) -> None:
        self.root_span: FakeLangfuseSpan | None = None
        self.flush_count = 0

    def create_trace_id(self) -> str:
        return "0123456789abcdef0123456789abcdef"

    def start_observation(self, **kwargs: object) -> FakeLangfuseSpan:
        self.root_span = FakeLangfuseSpan(**kwargs)
        return self.root_span

    def flush(self) -> None:
        self.flush_count += 1


class FakeLegacyLangfuseClient:
    def __init__(self) -> None:
        self.trace_observation: FakeLangfuseSpan | None = None
        self.flush_count = 0

    def trace(self, **kwargs: object) -> FakeLangfuseSpan:
        self.trace_observation = FakeLangfuseSpan(**kwargs)
        self.trace_observation.id = "legacy-trace-id"
        return self.trace_observation

    def flush(self) -> None:
        self.flush_count += 1


def test_observability_returns_noop_when_langfuse_is_not_configured() -> None:
    observability = Observability(host="", public_key="", secret_key="")

    trace = observability.trace(name="document_process", metadata={})

    assert isinstance(trace, NoopTrace)
    assert trace.id is None


def test_observability_uses_legacy_langfuse_trace_api() -> None:
    client = FakeLegacyLangfuseClient()
    observability = Observability(
        host="http://langfuse:3000",
        public_key="pk-test",
        secret_key="sk-test",
        client=client,
    )

    trace = observability.trace(
        name="document_process",
        metadata={"kb_id": "kb_1", "document_id": "doc_1"},
    )
    with trace.span(name="embedding", metadata={"chunk_count": 3, "model": "bge-m3", "embedding_dim": 1024}):
        pass
    trace.finish(level="DEFAULT", status_message="completed")

    assert trace.id == "legacy-trace-id"
    assert client.trace_observation is not None
    assert client.trace_observation.kwargs["name"] == "document_process"
    assert client.trace_observation.kwargs["metadata"] == {"kb_id": "kb_1", "document_id": "doc_1"}
    assert client.trace_observation.children[0].kwargs["name"] == "embedding"
    assert client.trace_observation.children[0].kwargs["metadata"] == {
        "chunk_count": 3,
        "model": "bge-m3",
        "embedding_dim": 1024,
    }
    assert client.trace_observation.children[0].ended is True
    assert client.trace_observation.ended is False
    assert client.flush_count == 1


def test_observability_uses_langfuse_v4_observations() -> None:
    client = FakeLangfuseClient()
    observability = Observability(
        host="http://langfuse:3000",
        public_key="pk-test",
        secret_key="sk-test",
        client=client,
    )

    trace = observability.trace(
        name="document_process",
        metadata={"kb_id": "kb_1", "document_id": "doc_1"},
    )
    with trace.span(name="embedding", metadata={"chunk_count": 3, "model": "bge-m3", "embedding_dim": 1024}):
        pass
    trace.finish(level="DEFAULT", status_message="completed")

    assert trace.id == "0123456789abcdef0123456789abcdef"
    assert client.root_span is not None
    assert client.root_span.kwargs["trace_context"] == {"trace_id": trace.id}
    assert client.root_span.kwargs["name"] == "document_process"
    assert client.root_span.kwargs["metadata"] == {"kb_id": "kb_1", "document_id": "doc_1"}
    assert client.root_span.children[0].kwargs["name"] == "embedding"
    assert client.root_span.children[0].kwargs["metadata"] == {
        "chunk_count": 3,
        "model": "bge-m3",
        "embedding_dim": 1024,
    }
    assert client.root_span.children[0].ended is True
    assert client.root_span.updates[-1] == {"level": "DEFAULT", "status_message": "completed"}
    assert client.root_span.ended is True
    assert client.flush_count == 1
