"""Adapter from the unified API to the original LangGraph production pipeline."""

from __future__ import annotations

import asyncio
import hashlib
import json
import threading
import time
import uuid
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.config import Settings
from app.contracts import DocumentRecord, HistoryRecord, QueryResult, RetrievedSource
from app.standalone_rag import ServiceError


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class FullRAGService:
    """Full BGE-M3/Milvus/MongoDB/MinIO service with lazy heavy imports."""

    mode = "full"
    retrieval_strategy = (
        "BGE-M3 dense+sparse hybrid (normal + HyDE) -> local RRF -> merge web -> Qwen3 rerank"
    )

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._catalog_path = settings.runtime_data_dir / "document_catalog.json"
        self._catalog_lock = threading.RLock()

    def _load_catalog(self) -> dict[str, DocumentRecord]:
        with self._catalog_lock:
            if not self._catalog_path.exists():
                return {}
            try:
                raw = json.loads(self._catalog_path.read_text(encoding="utf-8"))
                return {item["document_id"]: DocumentRecord(**item) for item in raw}
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                return {}

    def _save_catalog(self, catalog: dict[str, DocumentRecord]) -> None:
        with self._catalog_lock:
            self._catalog_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self._catalog_path.with_suffix(".tmp")
            temporary.write_text(
                json.dumps([asdict(item) for item in catalog.values()], ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self._catalog_path)

    @staticmethod
    def _upload_original(path: Path, document_id: str, content_type: str) -> None:
        from config.minio_config import minio_config
        from utils.minio_utils import get_minio_client

        client = get_minio_client()
        bucket = minio_config.bucket_name
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        client.fput_object(
            bucket_name=bucket,
            object_name=f"source-documents/{document_id}/{path.name}",
            file_path=str(path),
            content_type=content_type or "application/octet-stream",
        )

    async def ingest(self, filename: str, content: bytes, content_type: str) -> DocumentRecord:
        suffix = Path(filename).suffix.lower()
        if suffix not in {".pdf", ".md", ".markdown"}:
            raise ServiceError("完整模式仅支持PDF和Markdown文件", status_code=415)
        safe_name = Path(filename).name
        document_id = hashlib.sha256((safe_name + "\0").encode("utf-8") + content).hexdigest()[:16]
        task_id = str(uuid.uuid4())
        task_dir = self.settings.runtime_data_dir / "imports" / task_id
        task_dir.mkdir(parents=True, exist_ok=True)
        source_path = task_dir / safe_name
        source_path.write_bytes(content)

        try:
            from processor.import_processor.main_graph import KBImportWorkflow

            await asyncio.to_thread(self._upload_original, source_path, document_id, content_type)
            workflow = KBImportWorkflow()
            final_state = await asyncio.to_thread(
                workflow.run,
                {
                    "task_id": task_id,
                    "file_dir": str(task_dir),
                    "import_file_path": str(source_path),
                },
                False,
            )
        except Exception as exc:
            raise ServiceError(f"文档导入失败：{exc}", status_code=502) from exc

        chunks = final_state.get("chunks") or []
        record = DocumentRecord(
            document_id=document_id,
            filename=safe_name,
            title=final_state.get("file_title") or Path(safe_name).stem,
            content_type=content_type or "application/octet-stream",
            size_bytes=len(content),
            chunk_count=len(chunks),
            created_at=_utc_now(),
        )
        catalog = self._load_catalog()
        catalog[document_id] = record
        self._save_catalog(catalog)
        return record

    @staticmethod
    def _source_from_document(document: dict[str, Any], index: int) -> RetrievedSource:
        source_type = str(document.get("source_type") or document.get("source") or "local")
        source_id = str(
            document.get("source_id")
            or document.get("chunk_id")
            or document.get("url")
            or f"source-{index}"
        )
        title = str(document.get("title") or document.get("item_name") or "未命名来源")
        return RetrievedSource(
            source_id=source_id,
            document_id=str(document.get("document_id") or "") or None,
            title=title,
            section=str(document.get("section") or title),
            content=str(document.get("content") or document.get("snippet") or ""),
            score=round(float(document.get("score") or 0.0), 6),
            source_type=source_type,
            url=str(document.get("url") or "") or None,
        )

    async def query(self, query: str, session_id: str, top_k: int) -> QueryResult:
        started = time.perf_counter()
        try:
            from processor.query_processor.main_graph import KBQueryWorkflow

            workflow = KBQueryWorkflow()
            final_state = await asyncio.to_thread(
                workflow.run,
                {
                    "original_query": query,
                    "session_id": session_id,
                    "is_stream": False,
                },
                False,
            )
        except Exception as exc:
            raise ServiceError(f"知识库查询失败：{exc}", status_code=502) from exc

        documents = (final_state or {}).get("sources") or (final_state or {}).get("reranked_docs") or []
        sources = [self._source_from_document(document, index) for index, document in enumerate(documents[:top_k], 1)]
        answer = str((final_state or {}).get("answer") or "").strip()
        if not answer:
            raise ServiceError("查询流程没有返回答案", status_code=502)
        return QueryResult(
            session_id=session_id,
            query=query,
            rewritten_query=str((final_state or {}).get("rewritten_query") or query),
            answer=answer,
            sources=sources,
            retrieval_strategy=self.retrieval_strategy,
            latency_ms=round((time.perf_counter() - started) * 1000, 3),
            metadata={"mode": self.mode, "item_names": (final_state or {}).get("item_names") or []},
        )

    async def list_documents(self) -> list[DocumentRecord]:
        catalog = self._load_catalog()
        return sorted(catalog.values(), key=lambda item: item.created_at, reverse=True)

    async def delete_document(self, document_id: str) -> bool:
        catalog = self._load_catalog()
        record = catalog.get(document_id)
        if record is None:
            return False

        def delete_external_data() -> None:
            from config.milvus_config import milvus_config
            from config.minio_config import minio_config
            from utils.milvus_utils import escape_milvus_string, get_milvus_client
            from utils.minio_utils import get_minio_client

            title = escape_milvus_string(Path(record.filename).stem)
            get_milvus_client().delete(
                collection_name=milvus_config.chunks_collection,
                filter=f'file_title == "{title}"',
            )
            object_name = f"source-documents/{document_id}/{record.filename}"
            get_minio_client().remove_object(minio_config.bucket_name, object_name)

        try:
            await asyncio.to_thread(delete_external_data)
        except Exception as exc:
            raise ServiceError(f"删除外部存储数据失败：{exc}", status_code=502) from exc
        catalog.pop(document_id, None)
        self._save_catalog(catalog)
        return True

    async def get_history(self, session_id: str, limit: int = 50) -> list[HistoryRecord]:
        try:
            from utils.mongo_history_utils import get_recent_messages

            messages = await asyncio.to_thread(get_recent_messages, session_id, limit)
        except Exception as exc:
            raise ServiceError(f"读取会话历史失败：{exc}", status_code=502) from exc
        records: list[HistoryRecord] = []
        for message in messages:
            timestamp = message.get("ts")
            created_at = datetime.fromtimestamp(timestamp, UTC).isoformat() if timestamp else _utc_now()
            records.append(
                HistoryRecord(
                    role=str(message.get("role") or "unknown"),
                    content=str(message.get("text") or ""),
                    created_at=created_at,
                    sources=list(message.get("sources") or []),
                )
            )
        return records

    async def clear_history(self, session_id: str) -> int:
        try:
            from utils.mongo_history_utils import clear_history

            return await asyncio.to_thread(clear_history, session_id)
        except Exception as exc:
            raise ServiceError(f"清理会话历史失败：{exc}", status_code=502) from exc

    async def health(self) -> dict[str, Any]:
        checks: dict[str, Any] = {}

        def check_dependencies() -> None:
            from config.minio_config import minio_config
            from utils.milvus_utils import get_milvus_client
            from utils.minio_utils import get_minio_client
            from utils.mongo_history_utils import get_history_mongo_tool

            checks["milvus"] = bool(get_milvus_client().list_collections() is not None)
            checks["mongodb"] = bool(get_history_mongo_tool().client.admin.command("ping").get("ok"))
            checks["minio"] = get_minio_client().bucket_exists(minio_config.bucket_name)

        try:
            await asyncio.to_thread(check_dependencies)
            status = "ok" if all(checks.values()) else "degraded"
        except Exception as exc:
            checks["error"] = type(exc).__name__
            status = "degraded"
        return {"status": status, "mode": self.mode, **checks}
