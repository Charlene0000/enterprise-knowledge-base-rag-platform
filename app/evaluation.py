"""Reproducible retrieval and answer evaluation for the showcase dataset."""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path
from typing import Any

from app.contracts import RAGService
from app.standalone_rag import tokenize


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        try:
            row = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at line {line_number}: {exc}") from exc
        required = {"question", "expected_source", "expected_keywords"}
        if not required.issubset(row):
            raise ValueError(f"Missing fields at line {line_number}: {sorted(required - set(row))}")
        rows.append(row)
    if not rows:
        raise ValueError("Evaluation dataset is empty")
    return rows


async def evaluate_service(
    service: RAGService,
    dataset_path: Path,
    top_k: int = 5,
) -> dict[str, Any]:
    dataset = load_jsonl(dataset_path)
    reciprocal_ranks: list[float] = []
    retrieval_hits: list[float] = []
    keyword_coverages: list[float] = []
    citation_coverages: list[float] = []
    groundedness_scores: list[float] = []
    latencies: list[float] = []
    cases: list[dict[str, Any]] = []

    for index, row in enumerate(dataset, start=1):
        result = await service.query(
            query=str(row["question"]),
            session_id=f"evaluation-{index}",
            top_k=top_k,
        )
        source_titles = [source.title for source in result.sources]
        expected_source = str(row["expected_source"])
        matching_rank = next(
            (rank for rank, title in enumerate(source_titles, start=1) if expected_source.lower() in title.lower()),
            None,
        )
        hit = 1.0 if matching_rank is not None else 0.0
        reciprocal_rank = 1.0 / matching_rank if matching_rank else 0.0

        keywords = [str(keyword).lower() for keyword in row["expected_keywords"]]
        answer_lower = result.answer.lower()
        matched_keywords = [keyword for keyword in keywords if keyword in answer_lower]
        keyword_coverage = len(matched_keywords) / max(1, len(keywords))

        citations = {int(value) for value in re.findall(r"\[(\d+)]", result.answer)}
        valid_citations = {value for value in citations if 1 <= value <= len(result.sources)}
        citation_coverage = 1.0 if result.sources and valid_citations else 0.0

        source_terms = set(tokenize(" ".join(source.content for source in result.sources)))
        answer_terms = set(tokenize(re.sub(r"\[\d+]", "", result.answer)))
        groundedness = len(answer_terms & source_terms) / max(1, len(answer_terms))

        retrieval_hits.append(hit)
        reciprocal_ranks.append(reciprocal_rank)
        keyword_coverages.append(keyword_coverage)
        citation_coverages.append(citation_coverage)
        groundedness_scores.append(groundedness)
        latencies.append(result.latency_ms)
        cases.append(
            {
                "question": row["question"],
                "expected_source": expected_source,
                "retrieved_sources": source_titles,
                "rank": matching_rank,
                "answer": result.answer,
                "matched_keywords": matched_keywords,
                "latency_ms": result.latency_ms,
            }
        )

    sorted_latencies = sorted(latencies)
    p95_index = min(len(sorted_latencies) - 1, max(0, round(0.95 * len(sorted_latencies)) - 1))
    metrics = {
        f"recall@{top_k}": round(statistics.mean(retrieval_hits), 4),
        "mrr": round(statistics.mean(reciprocal_ranks), 4),
        "answer_keyword_coverage": round(statistics.mean(keyword_coverages), 4),
        "citation_coverage": round(statistics.mean(citation_coverages), 4),
        "heuristic_groundedness": round(statistics.mean(groundedness_scores), 4),
        "latency_p50_ms": round(statistics.median(latencies), 3),
        "latency_p95_ms": round(sorted_latencies[p95_index], 3),
    }
    return {
        "dataset": dataset_path.name,
        "sample_count": len(dataset),
        "metrics": metrics,
        "cases": cases,
        "notes": {
            "mode": service.mode,
            "groundedness": "deterministic token-support proxy; not an LLM judge or RAGAS Faithfulness",
        },
    }
