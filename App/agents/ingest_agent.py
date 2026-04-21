"""IngestAgent - 文档摄入智能体，处理 Raw → Wiki 的转换，含人工讨论环节."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Tool.document_processor import ProcessedDocument

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = REPO_ROOT / "App" / "candidates"
RAW_DIR = REPO_ROOT / "Raw"
PARSED_DIR = REPO_ROOT / "Tool" / "output" / "parsed"


@dataclass
class CandidatePage:
    """候选页面，等待人工确认."""

    candidate_id: str
    page_type: str
    title: str
    content: dict
    source_doc_ids: list[str]
    confidence: float
    status: str = "pending"


class IngestAgent:
    """文档摄入智能体."""

    def __init__(self):
        CANDIDATE_DIR.mkdir(parents=True, exist_ok=True)
        self.llm = None

    def _get_llm(self):
        if self.llm is None:
            from Tool.llm.client import LLMTool
            self.llm = LLMTool()
        return self.llm

    def interactive_workflow(self):
        """交互式工作流：自动发现文档，分析，然后交互式审批."""
        print("\n" + "=" * 60)
        print("IngestAgent 交互式工作流")
        print("=" * 60)

        # 1. 发现待处理的文档
        pending_docs = self._find_pending_documents()
        if not pending_docs:
            print("\n没有发现待处理的文档。")
            print(f"请将文档放入 {RAW_DIR} 目录")
            return

        print(f"\n发现 {len(pending_docs)} 个待处理文档:")
        for i, doc_info in enumerate(pending_docs, 1):
            status_icon = "✓" if doc_info["parsed"] else "○"
            print(f"  {i}. [{status_icon}] {doc_info['title']}")
            if doc_info["parsed"]:
                print(f"      ID: {doc_info['doc_id']}")
            print(f"      文件: {doc_info['file_name']}")

        # 2. 选择文档处理
        print("\n请选择要处理的文档编号（多个用逗号分隔，输入 'all' 处理全部，'q' 退出）:")
        try:
            choice = input("> ").strip()
            if choice.lower() == 'q':
                return
            if choice.lower() == 'all':
                selected = pending_docs
            else:
                indices = [int(x.strip()) - 1 for x in choice.split(",")]
                selected = [pending_docs[i] for i in indices if 0 <= i < len(pending_docs)]
        except (ValueError, IndexError):
            print("无效的选择")
            return

        # 3. 处理选中的文档
        for doc_info in selected:
            self._process_single_document(doc_info)

        # 4. 交互式审批候选
        self._interactive_approval()

    def _find_pending_documents(self) -> list[dict]:
        """发现待处理的文档（Raw 中有但 Wiki 中没有的）."""
        from Tool.pipelines.common import resolve_inputs

        pending = []

        # 获取所有 Raw 文件
        raw_files = list(resolve_inputs(str(RAW_DIR)))

        for file_path in raw_files:
            # 检查是否已解析
            doc_id = self._get_doc_id_from_file(file_path)
            parsed_path = PARSED_DIR / f"{doc_id}.json"
            is_parsed = parsed_path.exists()

            # 检查是否已有 Wiki 页面
            has_wiki = self._check_has_wiki(doc_id)

            if not has_wiki:
                pending.append({
                    "file_path": str(file_path),
                    "file_name": file_path.name,
                    "title": file_path.stem,
                    "doc_id": doc_id,
                    "parsed": is_parsed,
                })

        return pending

    def _get_doc_id_from_file(self, file_path: Path) -> str:
        """从文件路径生成文档 ID."""
        from datetime import datetime
        import hashlib

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        checksum = hashlib.md5(str(file_path).encode()).hexdigest()[:8]
        return f"doc-{timestamp}-{checksum}"

    def _check_has_wiki(self, doc_id: str) -> bool:
        """检查文档是否已有对应的 Wiki 页面."""
        # 检查候选中是否有来自该文档的已批准页面
        for candidate in self.list_candidates():
            if doc_id in candidate.source_doc_ids and candidate.status == "approved":
                return True
        return False

    def _process_single_document(self, doc_info: dict):
        """处理单个文档."""
        print(f"\n{'='*60}")
        print(f"处理文档: {doc_info['title']}")
        print(f"{'='*60}")

        try:
            if doc_info["parsed"]:
                # 已解析，直接分析
                print(f"文档已解析，直接分析...")
                doc = self._load_document(doc_info["doc_id"])
            else:
                # 未解析，先处理
                print(f"解析文档...")
                doc = self._process_file(doc_info["file_path"])

            # 生成候选
            print(f"生成候选页面...")
            candidates = self._extract_candidates_with_llm(doc)

            # 保存候选
            for candidate in candidates:
                self._save_candidate(candidate)

            if candidates:
                print(f"\n生成并保存 {len(candidates)} 个候选页面:")
                for c in candidates:
                    print(f"  - [{c.page_type}] {c.title} (置信度: {c.confidence:.2f})")
            else:
                print("未能生成候选页面")

        except Exception as e:
            print(f"处理失败: {e}")

    def _interactive_approval(self):
        """交互式审批候选."""
        while True:
            pending_candidates = [c for c in self.list_candidates() if c.status == "pending"]

            if not pending_candidates:
                print("\n没有待审批的候选页面。")
                break

            print(f"\n{'='*60}")
            print(f"待审批候选页面 ({len(pending_candidates)} 个)")
            print(f"{'='*60}")

            for i, c in enumerate(pending_candidates, 1):
                print(f"\n{i}. [{c.page_type}] {c.title}")
                print(f"   ID: {c.candidate_id}")
                print(f"   置信度: {c.confidence:.2f}")
                if c.content.get("summary"):
                    summary = c.content["summary"][:100] + "..." if len(c.content["summary"]) > 100 else c.content["summary"]
                    print(f"   摘要: {summary}")

            print(f"\n请选择操作:")
            print(f"  a. 批准全部")
            print(f"  r. 拒绝全部")
            print(f"  数字. 查看并审批单个候选 (1-{len(pending_candidates)})")
            print(f"  q. 退出")

            try:
                choice = input("> ").strip().lower()

                if choice == 'q':
                    break
                elif choice == 'a':
                    for c in pending_candidates:
                        self.approve_candidate(c.candidate_id)
                elif choice == 'r':
                    for c in pending_candidates:
                        self.reject_candidate(c.candidate_id)
                elif choice.isdigit():
                    idx = int(choice) - 1
                    if 0 <= idx < len(pending_candidates):
                        self._review_single_candidate(pending_candidates[idx])
                else:
                    print("无效的选择")

            except (EOFError, KeyboardInterrupt):
                break

    def _review_single_candidate(self, candidate: CandidatePage):
        """审查单个候选."""
        print(f"\n{'='*60}")
        print(f"候选详情: {candidate.title}")
        print(f"{'='*60}")
        print(f"类型: {candidate.page_type}")
        print(f"置信度: {candidate.confidence:.2f}")
        print(f"来源文档: {', '.join(candidate.source_doc_ids)}")

        if candidate.content.get("summary"):
            print(f"\n摘要:\n{candidate.content['summary']}")

        if candidate.content.get("keywords"):
            print(f"\n关键词: {', '.join(candidate.content['keywords'])}")

        print(f"\n请选择: [a]批准 [r]拒绝 [s]跳过 [q]返回")
        try:
            choice = input("> ").strip().lower()
            if choice == 'a':
                self.approve_candidate(candidate.candidate_id)
            elif choice == 'r':
                print("请输入拒绝原因（可选，直接回车跳过）:")
                reason = input("> ").strip()
                self.reject_candidate(candidate.candidate_id, reason)
            elif choice == 'q':
                return
        except (EOFError, KeyboardInterrupt):
            pass

    def _process_file(self, file_path: str) -> "ProcessedDocument":
        """处理文件."""
        from Tool.document_processor import process_document
        return process_document(file_path)

    def _load_document(self, document_id: str) -> "ProcessedDocument":
        """加载文档."""
        from Tool.document_processor import load_processed_document, process_document

        try:
            return load_processed_document(document_id)
        except FileNotFoundError:
            pass

        file_path = Path(document_id)
        if file_path.exists():
            return process_document(file_path)

        raw_file = RAW_DIR / document_id
        if raw_file.exists():
            return process_document(raw_file)

        raise FileNotFoundError(f"找不到文档: {document_id}")

    def ingest(self, document_id: str, use_llm: bool = True) -> list[CandidatePage]:
        """摄入文档（非交互式）."""
        doc = self._load_document(document_id)

        if use_llm:
            candidates = self._extract_candidates_with_llm(doc)
        else:
            candidates = self._extract_candidates_rule_based(doc)

        for candidate in candidates:
            self._save_candidate(candidate)

        print(f"[IngestAgent] 文档 {doc.title} 已分析")
        print(f"[IngestAgent] 生成 {len(candidates)} 个候选页面")

        return candidates

    def _extract_candidates_with_llm(self, doc: "ProcessedDocument") -> list[CandidatePage]:
        """使用 LLM 提取候选页面."""
        doc_content = doc.to_llm_context()
        prompt = self._build_discovery_prompt(doc_content)

        try:
            llm_response = self._get_llm().ask(prompt, max_tokens=2000, temperature=0.3)
            pages_data = self._parse_llm_response(llm_response)
        except Exception as e:
            print(f"[IngestAgent] LLM 调用失败，回退到规则提取: {e}")
            return self._extract_candidates_rule_based(doc)

        candidates = []
        for page_data in pages_data:
            candidate = CandidatePage(
                candidate_id=f"candidate-{uuid.uuid4().hex[:8]}",
                page_type=page_data.get("page_type", "overview"),
                title=page_data.get("title", "未命名页面"),
                content={
                    "summary": page_data.get("summary", ""),
                    "keywords": page_data.get("keywords", []),
                    "related_titles": page_data.get("related_titles", []),
                    "aliases": page_data.get("aliases", []),
                },
                source_doc_ids=[doc.document_id],
                confidence=page_data.get("confidence", 0.7),
            )
            candidates.append(candidate)

        if not candidates:
            return self._extract_candidates_rule_based(doc)

        return candidates

    def _build_discovery_prompt(self, doc_content: str) -> str:
        return f"""你是企业知识库建库专家。请分析以下文档，发现应该建立哪些 Wiki 页面。

文档内容：
{doc_content}

请输出 JSON 格式的页面列表，每个页面包含：
- title: 页面标题（中文，简洁明确）
- page_type: 页面类型（overview/entity/concept/comparison/index）
- summary: 页面摘要（2-4句话）
- keywords: 关键词列表
- related_titles: 相关页面标题列表
- aliases: 别名列表
- confidence: 置信度（0-1）

输出格式：
{{
  "pages": [
    {{
      "title": "页面标题",
      "page_type": "concept",
      "summary": "页面摘要...",
      "keywords": ["关键词1", "关键词2"],
      "related_titles": ["相关页面1"],
      "aliases": ["别名"],
      "confidence": 0.85
    }}
  ]
}}

只输出 JSON，不要其他解释。"""

    def _parse_llm_response(self, response: str) -> list[dict]:
        try:
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
            return data.get("pages", [])
        except json.JSONDecodeError:
            print(f"[IngestAgent] LLM 响应解析失败: {response[:200]}...")
            return []

    def _extract_candidates_rule_based(self, doc: "ProcessedDocument") -> list[CandidatePage]:
        """基于规则提取候选."""
        candidates = []

        overview = CandidatePage(
            candidate_id=f"candidate-{uuid.uuid4().hex[:8]}",
            page_type="overview",
            title=f"{doc.title} - 摘要" if doc.title else "文档摘要",
            content={
                "summary": doc.content[:500] if len(doc.content) > 500 else doc.content,
            },
            source_doc_ids=[doc.document_id],
            confidence=0.8,
        )
        candidates.append(overview)

        return candidates

    def _save_candidate(self, candidate: CandidatePage):
        file_path = CANDIDATE_DIR / f"{candidate.candidate_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump({
                "candidate_id": candidate.candidate_id,
                "page_type": candidate.page_type,
                "title": candidate.title,
                "content": candidate.content,
                "source_doc_ids": candidate.source_doc_ids,
                "confidence": candidate.confidence,
                "status": candidate.status,
            }, f, ensure_ascii=False, indent=2)

    def approve_candidate(self, candidate_id: str) -> bool:
        candidate = self._load_candidate(candidate_id)
        if not candidate or candidate.status != "pending":
            return False

        page_id = self._write_to_wiki(candidate)
        candidate.status = "approved"
        self._save_candidate(candidate)
        print(f"[已批准] {candidate.title} -> {page_id}")
        return True

    def reject_candidate(self, candidate_id: str, reason: str = "") -> bool:
        candidate = self._load_candidate(candidate_id)
        if not candidate:
            return False

        candidate.status = "rejected"
        self._save_candidate(candidate)
        print(f"[已拒绝] {candidate.title}")
        if reason:
            print(f"  原因: {reason}")
        return True

    def _load_candidate(self, candidate_id: str) -> CandidatePage | None:
        file_path = CANDIDATE_DIR / f"{candidate_id}.json"
        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        return CandidatePage(**data)

    def list_candidates(self) -> list[CandidatePage]:
        candidates = []
        for file_path in CANDIDATE_DIR.glob("*.json"):
            candidate = self._load_candidate(file_path.stem)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _write_to_wiki(self, candidate: CandidatePage) -> str:
        from wiki.store.files import PAGE_DIR
        from wiki.models.page import WikiPage, PageSection
        import datetime

        page_id = candidate.title.lower().replace(" ", "-").replace("_", "-")

        content = candidate.content
        sections = []

        if candidate.page_type == "overview":
            sections.append(PageSection(
                heading="摘要",
                content=content.get("summary", ""),
                source_refs=[{"document_id": did} for did in candidate.source_doc_ids],
            ))
        elif candidate.page_type == "entity":
            sections.append(PageSection(
                heading="描述",
                content=content.get("description", content.get("summary", "")),
                source_refs=[{"document_id": did} for did in candidate.source_doc_ids],
            ))
        elif candidate.page_type == "concept":
            sections.append(PageSection(
                heading="定义",
                content=content.get("definition", content.get("summary", "")),
                source_refs=[{"document_id": did} for did in candidate.source_doc_ids],
            ))
        else:
            sections.append(PageSection(
                heading="内容",
                content=content.get("summary", ""),
                source_refs=[{"document_id": did} for did in candidate.source_doc_ids],
            ))

        page = WikiPage(
            page_id=page_id,
            title=candidate.title,
            page_type=candidate.page_type,
            summary=content.get("summary", ""),
            sections=sections,
            aliases=content.get("aliases", []),
            source_refs=[{"document_id": did} for did in candidate.source_doc_ids],
            linked_pages=content.get("related_titles", []),
            review_status="published",
            page_version=1,
            updated_at=datetime.datetime.now().isoformat(),
        )

        PAGE_DIR.mkdir(parents=True, exist_ok=True)
        file_path = PAGE_DIR / f"{page_id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(page.to_dict(), f, ensure_ascii=False, indent=2)

        self._update_index(candidate.page_type, page_id, candidate.title)

        return page_id

    def _update_index(self, page_type: str, page_id: str, title: str):
        index_map = {
            "entity": "实体索引",
            "concept": "概念索引",
            "overview": "摘要索引",
            "comparison": "比较索引",
        }

        index_title = index_map.get(page_type)
        if not index_title:
            return

        from wiki.store.files import PAGE_DIR
        import datetime

        index_id = index_title.lower().replace(" ", "-")
        index_path = PAGE_DIR / f"{index_id}.json"

        if index_path.exists():
            with open(index_path, "r", encoding="utf-8") as f:
                index_page = json.load(f)
            items = index_page.get("linked_pages", [])
            if page_id not in items:
                items.append(page_id)
                index_page["linked_pages"] = items
                index_page["updated_at"] = datetime.datetime.now().isoformat()
                with open(index_path, "w", encoding="utf-8") as f:
                    json.dump(index_page, f, ensure_ascii=False, indent=2)
        else:
            index_page = {
                "page_id": index_id,
                "title": index_title,
                "page_type": "index",
                "summary": f"所有{index_title}的目录和导航",
                "sections": [{
                    "heading": "页面列表",
                    "content": f"- {title}",
                    "source_refs": [],
                }],
                "aliases": [],
                "source_refs": [],
                "linked_pages": [page_id],
                "review_status": "published",
                "page_version": 1,
                "updated_at": datetime.datetime.now().isoformat(),
            }
            with open(index_path, "w", encoding="utf-8") as f:
                json.dump(index_page, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys

    agent = IngestAgent()

    if len(sys.argv) < 2:
        # 默认进入交互式工作流
        agent.interactive_workflow()
    elif sys.argv[1] == "ingest" and len(sys.argv) >= 3:
        agent.ingest(sys.argv[2])
    elif sys.argv[1] == "list":
        candidates = agent.list_candidates()
        print(f"\n共有 {len(candidates)} 个候选页面:\n")
        for c in candidates:
            status_str = {"pending": "待审批", "approved": "已批准", "rejected": "已拒绝"}.get(c.status, c.status)
            print(f"  [{status_str}] {c.page_type:12} {c.title}")
    elif sys.argv[1] == "approve" and len(sys.argv) >= 3:
        agent.approve_candidate(sys.argv[2])
    elif sys.argv[1] == "reject" and len(sys.argv) >= 3:
        reason = sys.argv[3] if len(sys.argv) > 3 else ""
        agent.reject_candidate(sys.argv[2], reason)
    else:
        print("用法:")
        print("  python -m App.agents.ingest_agent              - 启动交互式工作流")
        print("  python -m App.agents.ingest_agent ingest <id>  - 分析指定文档")
        print("  python -m App.agents.ingest_agent list         - 列出所有候选")
        print("  python -m App.agents.ingest_agent approve <id> - 批准候选")
        print("  python -m App.agents.ingest_agent reject <id>  - 拒绝候选")
