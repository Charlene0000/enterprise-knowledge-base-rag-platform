from pathlib import Path

import pytest

from app.standalone_rag import ServiceError, StandaloneRAGService


@pytest.fixture
async def service() -> StandaloneRAGService:
    instance = StandaloneRAGService()
    examples = Path(__file__).resolve().parents[1] / "examples"
    await instance.seed_directory(examples)
    return instance


@pytest.mark.asyncio
async def test_hybrid_query_returns_grounded_citation(service: StandaloneRAGService) -> None:
    result = await service.query("HAK-180 最高工作温度是多少？", "test-session", top_k=5)

    assert result.sources
    assert result.sources[0].title.startswith("HAK-180")
    assert "180" in result.answer
    assert "[1]" in result.answer
    assert "RRF" in result.retrieval_strategy


@pytest.mark.asyncio
async def test_model_specific_question_does_not_mix_top_source(service: StandaloneRAGService) -> None:
    result = await service.query("LA-2608 的默认 IP 地址是什么？", "model-session", top_k=5)

    assert result.sources[0].title.startswith("LA2608")
    assert "192.168.0.100" in result.answer


@pytest.mark.asyncio
async def test_history_and_delete_document(service: StandaloneRAGService) -> None:
    result = await service.query("E07 如何处理？", "history-session", top_k=3)
    history = await service.get_history("history-session")

    assert len(history) == 2
    assert history[0].role == "user"
    assert history[1].sources

    document_id = result.sources[0].document_id
    assert await service.delete_document(document_id) is True
    assert await service.delete_document(document_id) is False


@pytest.mark.asyncio
async def test_standalone_rejects_pdf(service: StandaloneRAGService) -> None:
    with pytest.raises(ServiceError) as exc_info:
        await service.ingest("manual.pdf", b"not-a-pdf", "application/pdf")

    assert exc_info.value.status_code == 415
