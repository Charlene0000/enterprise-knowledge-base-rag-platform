import json
from pathlib import Path

import pytest

from app.evaluation import evaluate_service
from app.standalone_rag import StandaloneRAGService


@pytest.mark.asyncio
async def test_evaluation_report_contains_retrieval_and_answer_metrics(tmp_path: Path) -> None:
    service = StandaloneRAGService()
    await service.ingest(
        "sample.md",
        "# AX-1 手册\n\n## 温度\nAX-1 最高工作温度为 120℃。".encode(),
        "text/markdown",
    )
    dataset = tmp_path / "eval.jsonl"
    dataset.write_text(
        json.dumps(
            {
                "id": "case-1",
                "question": "AX-1 最高工作温度是多少？",
                "expected_source": "AX-1",
                "expected_keywords": ["120", "℃"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    report = await evaluate_service(service, dataset, top_k=3)

    assert report["sample_count"] == 1
    assert report["metrics"]["recall@3"] == 1.0
    assert report["metrics"]["mrr"] == 1.0
    assert report["metrics"]["citation_coverage"] == 1.0
