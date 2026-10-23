"""Service-layer contracts shared by standalone and full RAG implementations."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(slots=True)
class RetrievedSource:
    source_id: str
    document_id: str | None
    title: str
    section: str
    content: str
    score: float
    source_type: str = "local"
    url: str | None = None
    images: list[str] = field(default_factory=list)


@dataclass(slots=True)
class QueryResult:
    session_id: str
    query: str
    rewritten_query: str
    answer: str
    sources: list[RetrievedSource]
    retrieval_strategy: str
    latency_ms: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class DocumentRecord:
    document_id: str
    filename: str
    title: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: str
    status: str = "ready"


@dataclass(slots=True)
class HistoryRecord:
    role: str
    content: str
    created_at: str
    sources: list[str] = field(default_factory=list)


class RAGService(Protocol):
    mode: str

    async def ingest(self, filename: str, content: bytes, content_type: str) -> DocumentRecord: ...

    async def query(self, query: str, session_id: str, top_k: int) -> QueryResult: ...

    async def list_documents(self) -> list[DocumentRecord]: ...

    async def delete_document(self, document_id: str) -> bool: ...

    async def get_history(self, session_id: str, limit: int = 50) -> list[HistoryRecord]: ...

    async def clear_history(self, session_id: str) -> int: ...

    async def health(self) -> dict[str, Any]: ...
