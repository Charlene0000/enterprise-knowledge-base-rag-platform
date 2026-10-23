"""Deterministic, dependency-light RAG engine used by the public showcase mode.

The full mode keeps the original BGE-M3/Milvus/LangGraph implementation.  This
module exists so reviewers can clone the repository and exercise the complete
API, retrieval, citations and evaluation flow without model downloads or keys.
"""

from __future__ import annotations

import hashlib
import math
import re
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from app.contracts import DocumentRecord, HistoryRecord, QueryResult, RetrievedSource

_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-_/][A-Za-z0-9]+)*|[\u4e00-\u9fff]+")
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)]+)\)")
_SENTENCE_RE = re.compile(r"(?<=[。！？!?；;])\s*|\n+")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _normalize_identifier(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def tokenize(text: str) -> list[str]:
    """Tokenize English/model identifiers and Chinese unigrams+bigrams."""
    tokens: list[str] = []
    for match in _TOKEN_RE.finditer(text.lower()):
        token = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(token)
            tokens.extend(token[index : index + 2] for index in range(len(token) - 1))
        else:
            tokens.append(token)
    return tokens


def _hashed_vector(terms: Iterable[str], dimensions: int = 256) -> tuple[float, ...]:
    vector = [0.0] * dimensions
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8"), digest_size=8).digest()
        raw = int.from_bytes(digest, "big")
        index = raw % dimensions
        sign = 1.0 if raw & 1 else -1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm:
        vector = [value / norm for value in vector]
    return tuple(vector)


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    return max(0.0, sum(a * b for a, b in zip(left, right, strict=True)))


def _clean_markdown(text: str) -> str:
    text = _IMAGE_RE.sub("", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"[`*_>|]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


@dataclass(slots=True)
class _Chunk:
    chunk_id: str
    document_id: str
    title: str
    section: str
    content: str
    parent_content: str
    position: int
    terms: tuple[str, ...]
    dense_vector: tuple[float, ...]
    images: list[str] = field(default_factory=list)


class ServiceError(RuntimeError):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.status_code = status_code


def _document_title(filename: str, content: str) -> str:
    for line in content.splitlines():
        match = _HEADING_RE.match(line.strip())
        if match and len(match.group(1)) == 1:
            return match.group(2).strip()
    return Path(filename).stem


def _markdown_sections(content: str, fallback_title: str) -> list[tuple[str, str]]:
    heading_stack: list[str] = []
    current_lines: list[str] = []
    sections: list[tuple[str, str]] = []

    def flush() -> None:
        text = "\n".join(current_lines).strip()
        if text:
            sections.append((" / ".join(heading_stack) or fallback_title, text))
        current_lines.clear()

    for raw_line in content.splitlines():
        match = _HEADING_RE.match(raw_line.strip())
        if match:
            flush()
            level = len(match.group(1))
            title = match.group(2).strip()
            heading_stack[:] = heading_stack[: level - 1]
            heading_stack.append(title)
            continue
        current_lines.append(raw_line)
    flush()
    return sections or [(fallback_title, content.strip())]


def _window_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    text = text.strip()
    if len(text) <= chunk_size:
        return [text] if text else []
    windows: list[str] = []
    start = 0
    while start < len(text):
        end = min(len(text), start + chunk_size)
        if end < len(text):
            boundary = max(text.rfind(mark, start + chunk_size // 2, end) for mark in ("。", "！", "？", "\n"))
            if boundary > start:
                end = boundary + 1
        windows.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [window for window in windows if window]


class StandaloneRAGService:
    """In-memory hybrid RAG implementation with deterministic retrieval."""

    mode = "standalone"
    retrieval_strategy = "hash-dense + BM25 -> RRF -> lexical rerank"

    def __init__(self) -> None:
        self._documents: dict[str, DocumentRecord] = {}
        self._chunks: list[_Chunk] = []
        self._history: dict[str, list[HistoryRecord]] = defaultdict(list)
        self._lock = threading.RLock()

    async def seed_directory(self, directory: Path) -> int:
        if not directory.exists():
            return 0
        seeded = 0
        for path in sorted(directory.iterdir()):
            if path.suffix.lower() not in {".md", ".txt"}:
                continue
            await self.ingest(path.name, path.read_bytes(), "text/markdown")
            seeded += 1
        return seeded

    async def ingest(self, filename: str, content: bytes, content_type: str) -> DocumentRecord:
        safe_name = Path(filename).name
        suffix = Path(safe_name).suffix.lower()
        if suffix not in {".md", ".markdown", ".txt"}:
            raise ServiceError("展示模式支持Markdown/TXT；PDF请使用APP_MODE=full", status_code=415)
        try:
            decoded = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ServiceError("文件必须使用UTF-8编码") from exc
        if not decoded.strip():
            raise ServiceError("不能导入空文档")

        document_id = hashlib.sha256((safe_name + "\0" + decoded).encode("utf-8")).hexdigest()[:16]
        title = _document_title(safe_name, decoded)
        new_chunks: list[_Chunk] = []
        position = 0
        for section, parent_content in _markdown_sections(decoded, title):
            for window in _window_text(parent_content):
                terms = tuple(tokenize(f"{title} {section} {window}"))
                new_chunks.append(
                    _Chunk(
                        chunk_id=f"{document_id}-c{position:03d}",
                        document_id=document_id,
                        title=title,
                        section=section,
                        content=window,
                        parent_content=parent_content,
                        position=position,
                        terms=terms,
                        dense_vector=_hashed_vector(terms),
                        images=list(dict.fromkeys(_IMAGE_RE.findall(parent_content))),
                    )
                )
                position += 1

        record = DocumentRecord(
            document_id=document_id,
            filename=safe_name,
            title=title,
            content_type=content_type or "text/plain",
            size_bytes=len(content),
            chunk_count=len(new_chunks),
            created_at=_utc_now(),
        )
        with self._lock:
            self._chunks = [chunk for chunk in self._chunks if chunk.document_id != document_id]
            self._chunks.extend(new_chunks)
            self._documents[document_id] = record
        return record

    def _bm25_scores(self, query_terms: list[str], chunks: list[_Chunk]) -> dict[str, float]:
        if not chunks or not query_terms:
            return {}
        document_frequency: Counter[str] = Counter()
        term_counts: dict[str, Counter[str]] = {}
        for chunk in chunks:
            counts = Counter(chunk.terms)
            term_counts[chunk.chunk_id] = counts
            document_frequency.update(counts.keys())
        average_length = sum(len(chunk.terms) for chunk in chunks) / len(chunks)
        scores: dict[str, float] = {}
        k1, b = 1.5, 0.75
        for chunk in chunks:
            score = 0.0
            counts = term_counts[chunk.chunk_id]
            length = max(1, len(chunk.terms))
            for term in set(query_terms):
                frequency = counts.get(term, 0)
                if not frequency:
                    continue
                df = document_frequency[term]
                inverse_frequency = math.log(1 + (len(chunks) - df + 0.5) / (df + 0.5))
                denominator = frequency + k1 * (1 - b + b * length / max(1.0, average_length))
                score += inverse_frequency * (frequency * (k1 + 1)) / denominator
            scores[chunk.chunk_id] = score
        return scores

    @staticmethod
    def _rrf(*rankings: list[str], k: int = 60) -> dict[str, float]:
        scores: dict[str, float] = defaultdict(float)
        for ranking in rankings:
            for rank, chunk_id in enumerate(ranking, start=1):
                scores[chunk_id] += 1.0 / (k + rank)
        return dict(scores)

    def _rewrite_query(self, query: str, session_id: str) -> str:
        pronouns = ("它", "这个", "该设备", "这台", "刚才")
        if not any(pronoun in query for pronoun in pronouns):
            return query
        with self._lock:
            previous = [item.content for item in self._history.get(session_id, []) if item.role == "user"]
        if not previous:
            return query
        return f"{previous[-1]}；追问：{query}"

    def _retrieve(self, query: str, top_k: int) -> list[RetrievedSource]:
        with self._lock:
            chunks = list(self._chunks)
        if not chunks:
            return []

        query_terms = tokenize(query)
        query_vector = _hashed_vector(query_terms)
        dense_scores = {chunk.chunk_id: _cosine(query_vector, chunk.dense_vector) for chunk in chunks}
        sparse_scores = self._bm25_scores(query_terms, chunks)
        dense_ranking = sorted(dense_scores, key=dense_scores.get, reverse=True)
        sparse_ranking = sorted(sparse_scores, key=sparse_scores.get, reverse=True)
        rrf_scores = self._rrf(dense_ranking, sparse_ranking)

        max_sparse = max(sparse_scores.values(), default=1.0) or 1.0
        max_rrf = max(rrf_scores.values(), default=1.0) or 1.0
        query_set = set(query_terms)
        identifiers = {
            _normalize_identifier(value)
            for value in re.findall(r"[A-Za-z]+-?\d+(?:-\d+)?", query)
        }
        asks_temperature = any(marker in query for marker in ("温度", "多少度", "最高", "预热"))
        asks_fault = bool(re.search(r"[A-Za-z]+-?\d+", query)) or any(
            marker in query for marker in ("故障", "告警", "报错")
        )
        reranked: list[tuple[_Chunk, float]] = []
        for chunk in chunks:
            chunk_set = set(chunk.terms)
            overlap = len(query_set & chunk_set) / max(1, len(query_set))
            phrase_bonus = 1.0 if query.strip().lower() in chunk.parent_content.lower() else 0.0
            searchable = f"{chunk.title} {chunk.section} {chunk.parent_content}".lower()
            normalized_title = _normalize_identifier(chunk.title)
            normalized_searchable = _normalize_identifier(searchable)
            title_identifier_match = sum(1.0 for identifier in identifiers if identifier in normalized_title)
            content_identifier_match = sum(
                1.0 for identifier in identifiers if identifier in normalized_searchable
            )
            identifier_bonus = 2.0 * title_identifier_match + 0.25 * content_identifier_match
            title_models = {
                _normalize_identifier(value)
                for value in re.findall(r"[A-Za-z]+-?\d+(?:-\d+)?", chunk.title)
            }
            wrong_model_penalty = 1.0 if identifiers and title_models and not (identifiers & title_models) else 0.0
            intent_bonus = 0.0
            if asks_temperature and any(marker in searchable for marker in ("温度", "预热", "℃")):
                intent_bonus += 0.5
            if "最高" in query and "范围" in searchable:
                intent_bonus += 2.5
            if asks_fault and any(marker in searchable for marker in ("故障", "告警", "e01", "e07", "net-04")):
                intent_bonus += 0.5
            score = (
                0.42 * dense_scores.get(chunk.chunk_id, 0.0)
                + 0.25 * sparse_scores.get(chunk.chunk_id, 0.0) / max_sparse
                + 0.13 * overlap
                + 0.03 * rrf_scores.get(chunk.chunk_id, 0.0) / max_rrf
                + 0.02 * phrase_bonus
                + 0.10 * identifier_bonus
                + 0.05 * intent_bonus
                - 0.18 * wrong_model_penalty
            )
            reranked.append((chunk, score))
        reranked.sort(key=lambda item: item[1], reverse=True)

        sources: list[RetrievedSource] = []
        seen_parents: set[tuple[str, str]] = set()
        for chunk, score in reranked:
            parent_key = (chunk.document_id, chunk.section)
            if parent_key in seen_parents:
                continue
            if score <= 0:
                continue
            seen_parents.add(parent_key)
            parent = chunk.parent_content.strip()
            sources.append(
                RetrievedSource(
                    source_id=chunk.chunk_id,
                    document_id=chunk.document_id,
                    title=chunk.title,
                    section=chunk.section,
                    content=parent[:1800],
                    score=round(score, 6),
                    images=chunk.images,
                )
            )
            if len(sources) >= top_k:
                break
        return sources

    @staticmethod
    def _answer_from_sources(query: str, sources: list[RetrievedSource]) -> str:
        if not sources or sources[0].score < 0.035:
            return "没有在已导入知识中找到足够可靠的依据，请补充设备型号或更具体的问题。"
        query_terms = set(tokenize(query))
        identifiers = {
            _normalize_identifier(value)
            for value in re.findall(r"[A-Za-z]+-?\d+(?:-\d+)?", query)
        }
        ascii_keywords = {
            value.lower()
            for value in re.findall(r"[A-Za-z][A-Za-z0-9-]+", query)
            if _normalize_identifier(value) not in identifiers
        }
        wants_number = any(marker in query for marker in ("多少", "多久", "最高", "地址"))
        matching_source_indexes = {
            index
            for index, source in enumerate(sources, start=1)
            if any(identifier in _normalize_identifier(source.title) for identifier in identifiers)
        }
        candidates: list[tuple[float, float, int, str]] = []
        for source_index, source in enumerate(sources, start=1):
            if matching_source_indexes and source_index not in matching_source_indexes:
                continue
            for sentence in _SENTENCE_RE.split(_clean_markdown(source.content)):
                sentence = sentence.strip(" -")
                if len(sentence) < 8:
                    continue
                sentence_terms = set(tokenize(sentence))
                overlap = len(query_terms & sentence_terms) / max(1, len(query_terms))
                normalized_sentence = _normalize_identifier(sentence)
                identifier_bonus = sum(0.5 for identifier in identifiers if identifier in normalized_sentence)
                ascii_bonus = sum(
                    0.8 for keyword in ascii_keywords if keyword in sentence.lower()
                )
                number_bonus = 0.4 if wants_number and re.search(r"\d", sentence) else 0.0
                intent_bonus = 0.0
                if "最高" in query and any(marker in sentence for marker in ("范围", "最高", "上限")):
                    intent_bonus += 0.8
                if "地址" in query and any(marker in sentence for marker in ("地址", "IP", "ip")):
                    intent_bonus += 0.8
                candidates.append(
                    (
                        2.0 * overlap
                        + 0.3 * source.score
                        + identifier_bonus
                        + ascii_bonus
                        + number_bonus
                        + intent_bonus,
                        overlap,
                        source_index,
                        sentence,
                    )
                )
        candidates.sort(key=lambda item: item[0], reverse=True)
        selected: list[tuple[int, str]] = []
        seen: set[str] = set()
        best_overlap = max((item[1] for item in candidates), default=0.0)
        for _, overlap, source_index, sentence in candidates:
            normalized = sentence.lower()
            if normalized in seen:
                continue
            if selected and source_index != selected[0][0]:
                continue
            if selected and overlap < max(0.03, best_overlap * 0.25):
                continue
            selected.append((source_index, sentence))
            seen.add(normalized)
            if len(selected) >= 2:
                break
        if not selected:
            return f"根据《{sources[0].title}》的相关章节，请查看来源内容后再进行操作。[1]"
        return "\n".join(f"{sentence} [{source_index}]" for source_index, sentence in selected)

    async def query(self, query: str, session_id: str, top_k: int) -> QueryResult:
        started = time.perf_counter()
        rewritten_query = self._rewrite_query(query.strip(), session_id)
        sources = self._retrieve(rewritten_query, top_k)
        answer = self._answer_from_sources(rewritten_query, sources)
        now = _utc_now()
        with self._lock:
            self._history[session_id].append(HistoryRecord(role="user", content=query, created_at=now))
            self._history[session_id].append(
                HistoryRecord(
                    role="assistant",
                    content=answer,
                    created_at=now,
                    sources=[source.source_id for source in sources],
                )
            )
            self._history[session_id] = self._history[session_id][-100:]
        latency_ms = (time.perf_counter() - started) * 1000
        return QueryResult(
            session_id=session_id,
            query=query,
            rewritten_query=rewritten_query,
            answer=answer,
            sources=sources,
            retrieval_strategy=self.retrieval_strategy,
            latency_ms=round(latency_ms, 3),
            metadata={"mode": self.mode, "candidate_count": len(self._chunks)},
        )

    async def list_documents(self) -> list[DocumentRecord]:
        with self._lock:
            return sorted(self._documents.values(), key=lambda item: item.created_at, reverse=True)

    async def delete_document(self, document_id: str) -> bool:
        with self._lock:
            existed = self._documents.pop(document_id, None) is not None
            if existed:
                self._chunks = [chunk for chunk in self._chunks if chunk.document_id != document_id]
            return existed

    async def get_history(self, session_id: str, limit: int = 50) -> list[HistoryRecord]:
        with self._lock:
            return list(self._history.get(session_id, []))[-limit:]

    async def clear_history(self, session_id: str) -> int:
        with self._lock:
            count = len(self._history.get(session_id, []))
            self._history.pop(session_id, None)
            return count

    async def health(self) -> dict[str, object]:
        with self._lock:
            return {
                "status": "ok",
                "mode": self.mode,
                "documents": len(self._documents),
                "chunks": len(self._chunks),
                "sessions": len(self._history),
            }
