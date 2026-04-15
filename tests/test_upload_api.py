from __future__ import annotations

from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient

from App.agent import AgentRunReport
from App.api import create_app
from App.chat import ChatbotService


def test_upload_endpoint_saves_file_and_triggers_agent(tmp_dir, monkeypatch):
    raw_dir = tmp_dir / "Raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("App.api.REPO_ROOT", tmp_dir)
    monkeypatch.setattr("App.api.RAW_DIR", raw_dir)

    captured: dict[str, object] = {}

    def fake_maintain_wiki(*, input_path, use_llm=False, auto_publish_low_risk=True, **kwargs):
        captured["input_path"] = Path(input_path)
        captured["use_llm"] = use_llm
        captured["auto_publish_low_risk"] = auto_publish_low_risk
        return AgentRunReport(
            run_id="20260415120000",
            input_path=str(input_path),
            started_at="2026-04-15T12:00:00",
            completed_at="2026-04-15T12:00:05",
            manifests_seen=1,
            documents_parsed=["doc-1"],
            proposals_created=2,
            pages_published=1,
        )

    monkeypatch.setattr("App.api.maintain_wiki", fake_maintain_wiki)

    service = ChatbotService()
    monkeypatch.setattr(service, "reindex", lambda: {"pages": 0, "documents": 0, "fragments": 0})
    client = TestClient(create_app(service))

    response = client.post(
        "/agent/upload",
        files={
            "file": (
                "qms-policy.docx",
                BytesIO(b"qt-wiki-upload-test"),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
        data={"use_llm": "true", "auto_publish_low_risk": "false"},
    )
    assert response.status_code == 200
    payload = response.json()

    assert payload["status"] == "ok"
    assert payload["run_id"] == "20260415120000"
    assert payload["manifests_seen"] == 1
    assert payload["documents_parsed"] == 1
    assert payload["proposals_created"] == 2
    assert payload["pages_published"] == 1
    assert payload["stored_path"].startswith("Raw/")

    assert captured["use_llm"] is True
    assert captured["auto_publish_low_risk"] is False
    assert Path(captured["input_path"]).exists()

    stored_file = tmp_dir / payload["stored_path"]
    assert stored_file.exists()
    assert stored_file.read_bytes() == b"qt-wiki-upload-test"


def test_upload_endpoint_rejects_unsupported_suffix(tmp_dir, monkeypatch):
    raw_dir = tmp_dir / "Raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr("App.api.REPO_ROOT", tmp_dir)
    monkeypatch.setattr("App.api.RAW_DIR", raw_dir)

    called = {"value": False}

    def fake_maintain_wiki(*args, **kwargs):
        called["value"] = True
        raise AssertionError("should not be called")

    monkeypatch.setattr("App.api.maintain_wiki", fake_maintain_wiki)

    service = ChatbotService()
    monkeypatch.setattr(service, "reindex", lambda: {"pages": 0, "documents": 0, "fragments": 0})
    client = TestClient(create_app(service))

    response = client.post(
        "/agent/upload",
        files={"file": ("notes.txt", BytesIO(b"plain text"), "text/plain")},
    )

    assert response.status_code == 400
    assert "不支持的文件类型" in response.json()["detail"]
    assert called["value"] is False
