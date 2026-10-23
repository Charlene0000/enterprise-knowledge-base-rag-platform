"""Unified FastAPI entry point for the GitHub showcase and full RAG modes."""

from __future__ import annotations

import json
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse

from app.config import PROJECT_ROOT, Settings
from app.contracts import DocumentRecord, QueryResult, RAGService
from app.evaluation import evaluate_service
from app.full_rag import FullRAGService
from app.models import (
    DocumentResponse,
    EvaluationResponse,
    HealthResponse,
    HistoryResponse,
    QueryRequest,
    QueryResponse,
    SourceResponse,
    TokenRequest,
    TokenResponse,
    UploadResponse,
)
from app.security import (
    AuthUser,
    build_current_user_dependency,
    create_access_token,
    require_roles,
    verify_admin_credentials,
)
from app.standalone_rag import ServiceError, StandaloneRAGService


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key in ("request_id", "method", "path", "status_code", "duration_ms"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False)


def _configure_logging(level: str) -> logging.Logger:
    logger = logging.getLogger("zhiku.api")
    logger.setLevel(level)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(_JsonFormatter())
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def _document_response(record: DocumentRecord) -> DocumentResponse:
    return DocumentResponse(**asdict(record))


def _query_response(result: QueryResult) -> QueryResponse:
    sources = [
        SourceResponse(
            source_id=source.source_id,
            document_id=source.document_id,
            title=source.title,
            section=source.section,
            snippet=source.content[:500],
            score=source.score,
            source_type=source.source_type,
            url=source.url,
            images=source.images,
        )
        for source in result.sources
    ]
    return QueryResponse(
        session_id=result.session_id,
        query=result.query,
        rewritten_query=result.rewritten_query,
        answer=result.answer,
        sources=sources,
        retrieval_strategy=result.retrieval_strategy,
        latency_ms=result.latency_ms,
        metadata=result.metadata,
    )


def _sse(event: str, payload: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def create_app(settings: Settings | None = None, service: RAGService | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    if service is None:
        service = StandaloneRAGService() if settings.app_mode == "standalone" else FullRAGService(settings)
    logger = _configure_logging(settings.log_level)

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if (
            settings.app_mode == "standalone"
            and settings.seed_standalone_data
            and isinstance(service, StandaloneRAGService)
        ):
            seeded = await service.seed_directory(settings.standalone_data_dir)
            logger.info("standalone data seeded", extra={"status_code": seeded})
        yield

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "面向设备说明书的多模态RAG知识库。提供文档导入、混合检索、引用回答、"
            "SSE流式输出、会话历史、权限控制与可复现评测。"
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
    )
    app.state.settings = settings
    app.state.rag_service = service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=settings.auth_enabled,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception(
                "request failed",
                extra={"request_id": request_id, "method": request.method, "path": request.url.path},
            )
            raise
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        response.headers["X-Request-ID"] = request_id
        logger.info(
            "request completed",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError):
        return JSONResponse(status_code=exc.status_code, content={"detail": str(exc)})

    current_user = build_current_user_dependency(settings)
    viewer_user = require_roles(current_user, "viewer", "admin")
    admin_user = require_roles(current_user, "admin")

    @app.get("/", tags=["system"])
    async def root():
        return {
            "name": settings.app_name,
            "version": settings.app_version,
            "mode": settings.app_mode,
            "docs": "/docs",
            "application": "/app",
            "health": "/health/ready",
        }

    @app.get("/app", include_in_schema=False)
    async def application_page():
        page = PROJECT_ROOT / "web" / "page" / "showcase.html"
        if not page.exists():
            raise HTTPException(status_code=404, detail="Application page is not available")
        return FileResponse(page)

    @app.get("/demo", include_in_schema=False)
    async def legacy_demo_page():
        return await application_page()

    @app.get("/health/live", response_model=HealthResponse, tags=["system"])
    async def liveness():
        return HealthResponse(status="ok", mode=settings.app_mode, version=settings.app_version, checks={"api": True})

    @app.get("/health/ready", response_model=HealthResponse, tags=["system"])
    async def readiness():
        checks = await service.health()
        ready_status = "ok" if checks.get("status") == "ok" else "degraded"
        return HealthResponse(status=ready_status, mode=settings.app_mode, version=settings.app_version, checks=checks)

    @app.get("/api/v1/system/info", tags=["system"])
    async def system_info(_: AuthUser = Depends(viewer_user)):
        return {
            "mode": settings.app_mode,
            "auth_enabled": settings.auth_enabled,
            "features": [
                "document-ingestion",
                "hybrid-retrieval",
                "rrf",
                "rerank",
                "citations",
                "sse",
                "evaluation",
            ],
        }

    @app.post("/api/v1/auth/token", response_model=TokenResponse, tags=["auth"])
    async def issue_token(payload: TokenRequest):
        if not verify_admin_credentials(settings, payload.username, payload.password):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
        token, expires_in = create_access_token(settings, payload.username, role="admin")
        return TokenResponse(access_token=token, expires_in=expires_in, role="admin")

    @app.post(
        "/api/v1/documents",
        response_model=UploadResponse,
        status_code=status.HTTP_201_CREATED,
        tags=["documents"],
    )
    async def upload_document(
        file: UploadFile = File(...),
        _: AuthUser = Depends(admin_user),
    ):
        if not file.filename:
            raise HTTPException(status_code=422, detail="缺少文件名")
        payload = bytearray()
        while chunk := await file.read(1024 * 1024):
            payload.extend(chunk)
            if len(payload) > settings.max_upload_bytes:
                raise HTTPException(status_code=413, detail="上传文件超过大小限制")
        record = await service.ingest(Path(file.filename).name, bytes(payload), file.content_type or "")
        return UploadResponse(document=_document_response(record), message="文档已完成解析、切分和索引")

    @app.get("/api/v1/documents", response_model=list[DocumentResponse], tags=["documents"])
    async def list_documents(_: AuthUser = Depends(viewer_user)):
        return [_document_response(record) for record in await service.list_documents()]

    @app.delete("/api/v1/documents/{document_id}", tags=["documents"])
    async def delete_document(document_id: str, _: AuthUser = Depends(admin_user)):
        if not await service.delete_document(document_id):
            raise HTTPException(status_code=404, detail="文档不存在")
        return {"deleted": True, "document_id": document_id}

    @app.post("/api/v1/query", response_model=QueryResponse, tags=["query"])
    async def query(payload: QueryRequest, _: AuthUser = Depends(viewer_user)):
        session_id = payload.session_id or str(uuid.uuid4())
        result = await service.query(payload.query, session_id, payload.top_k)
        return _query_response(result)

    @app.post("/api/v1/query/stream", tags=["query"])
    async def stream_query(payload: QueryRequest, _: AuthUser = Depends(viewer_user)):
        session_id = payload.session_id or str(uuid.uuid4())

        async def event_stream():
            yield _sse("accepted", {"session_id": session_id, "status": "processing"})
            try:
                result = await service.query(payload.query, session_id, payload.top_k)
            except Exception as exc:
                logger.exception("stream query failed", extra={"request_id": session_id})
                yield _sse("error", {"detail": str(exc), "session_id": session_id})
                return
            response = _query_response(result)
            yield _sse("metadata", {"session_id": session_id, "strategy": result.retrieval_strategy})
            for offset in range(0, len(result.answer), 12):
                yield _sse("delta", {"text": result.answer[offset : offset + 12]})
            yield _sse("sources", {"items": [source.model_dump() for source in response.sources]})
            yield _sse("final", {"answer": result.answer, "latency_ms": result.latency_ms})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @app.get("/api/v1/sessions/{session_id}/history", response_model=HistoryResponse, tags=["sessions"])
    async def history(session_id: str, limit: int = 50, _: AuthUser = Depends(viewer_user)):
        limit = max(1, min(limit, 100))
        items = [asdict(record) for record in await service.get_history(session_id, limit)]
        return HistoryResponse(session_id=session_id, items=items)

    @app.delete("/api/v1/sessions/{session_id}/history", tags=["sessions"])
    async def clear_history(session_id: str, _: AuthUser = Depends(admin_user)):
        deleted = await service.clear_history(session_id)
        return {"session_id": session_id, "deleted_count": deleted}

    @app.post("/api/v1/evaluations/benchmark", response_model=EvaluationResponse, tags=["evaluation"])
    async def run_benchmark_evaluation(_: AuthUser = Depends(admin_user)):
        if settings.app_mode != "standalone":
            raise HTTPException(status_code=409, detail="该端点仅用于确定性展示评测")
        dataset = settings.standalone_data_dir / "eval_dataset.jsonl"
        report = await evaluate_service(service, dataset, top_k=settings.default_top_k)
        return EvaluationResponse(**{key: report[key] for key in ("dataset", "sample_count", "metrics", "cases")})

    app.add_api_route(
        "/api/v1/evaluations/demo",
        run_benchmark_evaluation,
        methods=["POST"],
        include_in_schema=False,
    )

    return app


app = create_app()
