from __future__ import annotations

import json

from fastapi.testclient import TestClient

from App.api import create_app
from App.chat import ChatbotService
from wiki.index.local import LocalWikiIndex
from wiki.models.page import UpdateProposal


def _prepare_chat_data(tmp_dir):
    pages_dir = tmp_dir / "pages"
    parsed_dir = tmp_dir / "parsed"
    pages_dir.mkdir()
    parsed_dir.mkdir()

    (pages_dir / "文件和数据管理.json").write_text(
        json.dumps(
            {
                "page_id": "文件和数据管理",
                "title": "文件和数据管理",
                "page_type": "process",
                "summary": "文件和数据管理要求企业控制文件版本、记录保存以及电子化数据的可追溯性。",
                "sections": [
                    {
                        "heading": "核心要求",
                        "content": "企业应当建立文件控制和记录控制机制，确保可追溯。",
                        "source_refs": [],
                    }
                ],
                "aliases": ["文件控制", "电子记录"],
                "source_refs": [
                    {
                        "document_id": "doc-1",
                        "fragment_id": "frag-1",
                        "file_name": "qms-policy.pdf",
                        "anchor_label": "p.38",
                        "quote": "企业应当建立文件控制程序，确保版本受控。",
                    },
                    {
                        "document_id": "doc-1",
                        "fragment_id": "frag-2",
                        "file_name": "qms-policy.pdf",
                        "anchor_label": "p.39",
                        "quote": "记录应保存并可追溯，电子记录需要防止未经授权修改。",
                    },
                ],
                "linked_pages": ["质量管理体系"],
                "review_status": "published",
                "page_version": 1,
                "updated_at": "2026-04-15T10:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (pages_dir / "质量管理体系.json").write_text(
        json.dumps(
            {
                "page_id": "质量管理体系",
                "title": "质量管理体系",
                "page_type": "concept",
                "summary": "质量管理体系覆盖组织职责、文件控制、风险管理和持续改进。",
                "sections": [],
                "aliases": ["QMS"],
                "source_refs": [],
                "linked_pages": ["文件和数据管理"],
                "review_status": "published",
                "page_version": 1,
                "updated_at": "2026-04-15T10:00:00",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (parsed_dir / "doc-1.json").write_text(
        json.dumps(
            {
                "document": {
                    "document_id": "doc-1",
                    "title": "QMS 规范",
                    "source_path": "Raw/qms-policy.pdf",
                    "file_name": "qms-policy.pdf",
                    "source_type": "pdf",
                    "doc_type": "policy",
                    "language": "zh-CN",
                    "checksum": "abc",
                    "metadata": {},
                },
                "sections": [],
                "fragments": [
                    {
                        "fragment_id": "frag-1",
                        "section_id": None,
                        "fragment_type": "paragraph",
                        "text": "企业应当建立文件控制程序，确保版本受控。",
                        "anchors": {"page": 38, "paragraph_index": 1},
                    },
                    {
                        "fragment_id": "frag-2",
                        "section_id": None,
                        "fragment_type": "paragraph",
                        "text": "记录应保存并可追溯，电子记录需要防止未经授权修改。",
                        "anchors": {"page": 39, "paragraph_index": 1},
                    },
                ],
                "tables": [],
                "figures": [],
                "terms": ["文件控制", "电子记录"],
                "entities": [],
                "parse_status": "parsed",
                "source_anchors": [],
                "errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return pages_dir, parsed_dir


def test_local_index_retrieves_pages_and_citations(tmp_dir):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    index = LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir).refresh()

    page_hits = index.search_pages("文件控制要求是什么", top_k=3)
    assert len(page_hits) >= 1
    assert page_hits[0].page_id == "文件和数据管理"

    citation_hits = index.collect_citations("电子记录如何控制", page_hits, top_k=5)
    assert len(citation_hits) >= 1
    assert citation_hits[0].page_title == "文件和数据管理"
    assert "电子记录" in citation_hits[0].quote


def test_local_index_collect_citations_with_page_prior_fallback(tmp_dir):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    index = LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir).refresh()

    page_hits = index.search_pages("文件控制流程", top_k=3)
    assert len(page_hits) >= 1

    citation_hits = index.collect_citations("审批岗位责任矩阵", page_hits, top_k=5)
    assert len(citation_hits) >= 1
    assert citation_hits[0].page_id == "文件和数据管理"


def test_chat_service_returns_structured_answer_with_citations(tmp_dir):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    service = ChatbotService(index=LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir))

    answer = service.answer_question("文件控制和电子记录有哪些要求", use_llm=False)

    assert "文件和数据管理" in answer.answer
    assert len(answer.citations) >= 1
    assert answer.citations[0].citation_id == "c1"
    assert answer.matched_pages[0].page_id == "文件和数据管理"
    assert answer.used_llm is False
    assert answer.confidence in {"medium", "high"}


def test_chat_service_falls_back_when_llm_returns_insufficient(tmp_dir, monkeypatch):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    service = ChatbotService(index=LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir))

    monkeypatch.setattr("App.chat.ask_llm", lambda *args, **kwargs: "现有Wiki证据不足以回答该问题。")

    answer = service.answer_question("文件控制和电子记录有哪些要求", use_llm=True)

    assert "当前 Wiki 中可直接参考以下内容" in answer.answer
    assert len(answer.citations) >= 1
    assert answer.used_llm is False
    assert answer.confidence in {"medium", "high"}


def test_chat_service_confidence_is_low_for_insufficient_answer(tmp_dir, monkeypatch):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    service = ChatbotService(index=LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir))

    monkeypatch.setattr(
        ChatbotService,
        "_build_fallback_answer",
        lambda self, question, matched_pages, citations: "现有 Wiki 证据不足以回答该问题。",
    )

    answer = service.answer_question("文件控制和电子记录有哪些要求", use_llm=False)

    assert answer.confidence == "low"


def test_chat_api_returns_answer_and_citations(tmp_dir):
    pages_dir, parsed_dir = _prepare_chat_data(tmp_dir)
    service = ChatbotService(index=LocalWikiIndex(page_dir=pages_dir, parsed_dir=parsed_dir))
    client = TestClient(create_app(service))

    reindex_response = client.post("/chat/reindex")
    assert reindex_response.status_code == 200
    assert reindex_response.json()["pages"] == 2

    response = client.post(
        "/chat/query",
        json={
            "question": "电子记录需要注意什么",
            "use_llm": False,
            "top_k_pages": 3,
            "top_k_citations": 5,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["question"] == "电子记录需要注意什么"
    assert payload["used_llm"] is False
    assert len(payload["matched_pages"]) >= 1
    assert len(payload["citations"]) >= 1
    assert payload["citations"][0]["page_title"] == "文件和数据管理"


def test_pending_proposal_api_lists_only_pending_items(tmp_dir, monkeypatch):
    proposals_dir = tmp_dir / "proposals"
    proposals_dir.mkdir()
    (proposals_dir / "proposal-pending.json").write_text(
        json.dumps(
            {
                "proposal_id": "proposal-pending",
                "target_page_id": "文件和数据管理",
                "action": "append_evidence",
                "reason": "需要人工审核",
                "candidate_content": "candidate",
                "evidence_fragment_ids": [],
                "risk_level": "high",
                "change_scope": "medium",
                "review_mode": "human_required",
                "status": "pending_review",
                "review_notes": "制度类内容需要人工确认",
                "source_document_ids": ["doc-1"],
                "tool_trace": ["wiki.updaters.incremental.build_incremental_candidates", "wiki.review._heuristic_review"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (proposals_dir / "proposal-published.json").write_text(
        json.dumps(
            {
                "proposal_id": "proposal-published",
                "target_page_id": "质量管理体系",
                "action": "append_evidence",
                "reason": "已发布",
                "candidate_content": "candidate",
                "evidence_fragment_ids": [],
                "risk_level": "low",
                "status": "published",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("App.api.PROPOSAL_DIR", proposals_dir)
    client = TestClient(create_app(ChatbotService(index=LocalWikiIndex(page_dir=tmp_dir / "pages", parsed_dir=tmp_dir / "parsed"))))

    response = client.get("/agent/proposals/pending")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["items"]) == 1
    assert payload["items"][0]["proposal_id"] == "proposal-pending"
    assert payload["items"][0]["review_notes"] == "制度类内容需要人工确认"
    assert payload["items"][0]["tool_trace"] == [
        "wiki.updaters.incremental.build_incremental_candidates",
        "wiki.review._heuristic_review",
    ]


def test_approve_proposal_api_reindexes_after_manual_approval(tmp_dir, monkeypatch):
    service = ChatbotService(index=LocalWikiIndex(page_dir=tmp_dir / "pages", parsed_dir=tmp_dir / "parsed"))
    client = TestClient(create_app(service))
    called = {"reindex": 0}

    monkeypatch.setattr(
        "App.api.approve_proposal",
        lambda proposal_id: UpdateProposal(
            proposal_id=proposal_id,
            target_page_id="文件和数据管理",
            action="append_evidence",
            reason="人工批准",
            candidate_content="candidate",
            status="published",
            review_mode="manual",
            review_notes="人工审核通过后发布",
        ),
    )
    monkeypatch.setattr(service, "reindex", lambda: called.__setitem__("reindex", called["reindex"] + 1) or {"pages": 0, "documents": 0, "fragments": 0})

    response = client.post("/agent/proposals/proposal-123/approve")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["proposal_id"] == "proposal-123"
    assert payload["review_mode"] == "manual"
    assert called["reindex"] == 1


def test_approve_all_pending_api_reindexes_when_items_exist(tmp_dir, monkeypatch):
    service = ChatbotService(index=LocalWikiIndex(page_dir=tmp_dir / "pages", parsed_dir=tmp_dir / "parsed"))
    client = TestClient(create_app(service))
    called = {"reindex": 0}

    monkeypatch.setattr(
        "App.api.approve_all_pending_proposals",
        lambda: [
            UpdateProposal(
                proposal_id="proposal-1",
                target_page_id="文件和数据管理",
                action="append_evidence",
                reason="人工批准",
                candidate_content="candidate",
                status="published",
                review_mode="manual",
                review_notes="人工审核通过后发布",
            ),
            UpdateProposal(
                proposal_id="proposal-2",
                target_page_id="质量管理体系",
                action="append_evidence",
                reason="人工批准",
                candidate_content="candidate",
                status="published",
                review_mode="manual",
                review_notes="人工审核通过后发布",
            ),
        ],
    )
    monkeypatch.setattr(
        service,
        "reindex",
        lambda: called.__setitem__("reindex", called["reindex"] + 1) or {"pages": 0, "documents": 0, "fragments": 0},
    )

    response = client.post("/agent/proposals/approve-all")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["approved_count"] == 2
    assert payload["proposal_ids"] == ["proposal-1", "proposal-2"]
    assert called["reindex"] == 1

