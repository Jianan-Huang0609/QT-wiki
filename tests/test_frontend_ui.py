from __future__ import annotations

from fastapi.testclient import TestClient

from App.api import create_app
from App.chat import ChatbotService


def test_frontend_root_serves_html():
    client = TestClient(create_app(ChatbotService()))
    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "证据驱动问答剧场" in response.text
    assert "上传文档并自动维护 Wiki" in response.text
    assert "id=\"upload-form\"" in response.text


def test_frontend_assets_are_served():
    client = TestClient(create_app(ChatbotService()))

    css_response = client.get("/assets/styles.css")
    js_response = client.get("/assets/app.js")

    assert css_response.status_code == 200
    assert "--bg:" in css_response.text
    assert js_response.status_code == 200
    assert "function renderEvidence" in js_response.text
    assert "function onUploadSubmit" in js_response.text
