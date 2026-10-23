"""Pydantic request and response schemas exposed by the unified API."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    password: str = Field(min_length=1, max_length=200)


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int
    role: str


class QueryRequest(BaseModel):
    query: str = Field(min_length=2, max_length=2000, description="用户问题")
    session_id: str | None = Field(default=None, min_length=3, max_length=128)
    top_k: int = Field(default=5, ge=1, le=10)


class SourceResponse(BaseModel):
    source_id: str
    document_id: str | None
    title: str
    section: str
    snippet: str
    score: float
    source_type: str
    url: str | None = None
    images: list[str] = Field(default_factory=list)


class QueryResponse(BaseModel):
    session_id: str
    query: str
    rewritten_query: str
    answer: str
    sources: list[SourceResponse]
    retrieval_strategy: str
    latency_ms: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class DocumentResponse(BaseModel):
    document_id: str
    filename: str
    title: str
    content_type: str
    size_bytes: int
    chunk_count: int
    created_at: str
    status: str


class UploadResponse(BaseModel):
    document: DocumentResponse
    message: str


class HistoryResponse(BaseModel):
    session_id: str
    items: list[dict[str, Any]]


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    mode: str
    version: str
    checks: dict[str, Any] = Field(default_factory=dict)


class EvaluationResponse(BaseModel):
    dataset: str
    sample_count: int
    metrics: dict[str, float]
    cases: list[dict[str, Any]]
