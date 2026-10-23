from pathlib import Path

from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from app.standalone_rag import StandaloneRAGService


def _build_client(*, auth_enabled: bool = False) -> TestClient:
    settings = Settings(
        app_mode="standalone",
        auth_enabled=auth_enabled,
        seed_standalone_data=True,
        standalone_data_dir=Path(__file__).resolve().parents[1] / "examples",
    )
    return TestClient(create_app(settings, StandaloneRAGService()))


def test_health_documents_query_and_history() -> None:
    with _build_client() as client:
        assert client.get("/health/live").status_code == 200
        documents = client.get("/api/v1/documents").json()
        assert len(documents) >= 3

        response = client.post(
            "/api/v1/query",
            json={"query": "HAK-180 最高工作温度是多少？", "session_id": "api-session", "top_k": 5},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["sources"][0]["title"].startswith("HAK-180")
        assert "[1]" in payload["answer"]

        history = client.get("/api/v1/sessions/api-session/history")
        assert history.status_code == 200
        assert len(history.json()["items"]) == 2


def test_upload_stream_and_evaluation() -> None:
    with _build_client() as client:
        upload = client.post(
            "/api/v1/documents",
            files={"file": ("custom.md", "# ZX-9\n\nZX-9 电压为 24V。", "text/markdown")},
        )
        assert upload.status_code == 201
        assert upload.json()["document"]["chunk_count"] == 1

        stream = client.post("/api/v1/query/stream", json={"query": "ZX-9 电压是多少？"})
        assert stream.status_code == 200
        assert "event: sources" in stream.text
        assert "event: final" in stream.text

        evaluation = client.post("/api/v1/evaluations/benchmark")
        assert evaluation.status_code == 200
        assert evaluation.json()["sample_count"] >= 8


def test_authentication_and_rbac() -> None:
    with _build_client(auth_enabled=True) as client:
        assert client.get("/api/v1/documents").status_code == 401

        token_response = client.post(
            "/api/v1/auth/token",
            json={"username": "local-admin", "password": "local-password"},
        )
        assert token_response.status_code == 200
        headers = {"Authorization": f"Bearer {token_response.json()['access_token']}"}
        assert client.get("/api/v1/documents", headers=headers).status_code == 200


def test_upload_size_limit() -> None:
    settings = Settings(app_mode="standalone", max_upload_bytes=1024, seed_standalone_data=False)
    with TestClient(create_app(settings, StandaloneRAGService())) as client:
        response = client.post(
            "/api/v1/documents",
            files={"file": ("large.md", b"x" * 2048, "text/markdown")},
        )
        assert response.status_code == 413


def test_application_page_explains_inputs_and_formats_validation_errors() -> None:
    with _build_client() as client:
        page = client.get("/app")

    assert page.status_code == 200
    assert "问题（必填）" in page.text
    assert "会话 ID（可选" in page.text
    assert "function apiError" in page.text
    assert "throw new Error(body.detail||" not in page.text
