"""IngestAgent - 文档摄入智能体，处理 Raw → Wiki 的转换，含人工讨论环节."""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from Tool.document_processor import ProcessedDocument
    from Tool.contracts.canonical import CanonicalDocument

REPO_ROOT = Path(__file__).resolve().parents[2]
CANDIDATE_DIR = REPO_ROOT / "App" / "candidates"
CANDIDATE_MD_DIR = REPO_ROOT / "wiki" / "output" / "obsidian" / "Proposals"
RAW_DIR = REPO_ROOT / "Raw"
PARSED_DIR = REPO_ROOT / "Tool" / "output" / "parsed"

MAX_LLM_FRAGMENTS = 48
MAX_FRAGMENT_TEXT_LENGTH = 400


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
        CANDIDATE_MD_DIR.mkdir(parents=True, exist_ok=True)
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

            review_package = self._build_review_package(doc, candidates)
            self._save_review_package(review_package)

            # 保存候选
            for candidate in candidates:
                self._save_candidate(candidate)

            if candidates:
                print(f"\n生成并保存 {len(candidates)} 个候选页面，审批包: {review_package.package_id}")
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

        review_package = self._build_review_package(doc, candidates)
        self._save_review_package(review_package)

        for candidate in candidates:
            self._save_candidate(candidate)

        print(f"[IngestAgent] 文档 {doc.title} 已分析")
        print(f"[IngestAgent] 生成 {len(candidates)} 个候选页面")
        print(f"[IngestAgent] 生成审批包 {review_package.package_id}")

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

    def _build_review_package(self, doc: "ProcessedDocument", candidates: list[CandidatePage], use_llm: bool = True):
        from wiki.models import DocumentIdentity, HumanReviewQuestion, ReviewIssue, ReviewObject, ReviewPackage, ReviewRelation

        canonical = self._load_canonical_document(doc.document_id)
        evidence_refs = self._build_evidence_refs(canonical)
        document_identity = DocumentIdentity(
            business_type=self._classify_business_type(doc),
            title=doc.title,
            version=self._guess_version(doc),
            effective_level=self._effective_level(doc),
            scope=self._guess_scope(doc),
            is_binding=self._is_binding_document(doc),
            confidence=self._identity_confidence(doc),
            source_refs=evidence_refs[:3],
            notes=self._identity_notes(doc),
        )

        if use_llm:
            extracted_objects = self._extract_objects_with_llm(canonical, document_identity)
            if not extracted_objects:
                extracted_objects = self._extract_review_objects_rule_based(canonical, candidates)
            extracted_relations = self._extract_relations_with_llm(canonical, extracted_objects, document_identity)
            if not extracted_relations:
                extracted_relations = self._extract_relations_rule_based(canonical, extracted_objects, document_identity)
            gaps, conflicts = self._analyze_gaps_with_llm(extracted_objects, extracted_relations, document_identity)
        else:
            extracted_objects = self._extract_review_objects_rule_based(canonical, candidates)
            extracted_relations = self._extract_relations_rule_based(canonical, extracted_objects, document_identity)
            gaps = []
            conflicts = []

        issues = self._build_review_issues(doc, document_identity, evidence_refs, conflicts)
        human_questions = self._build_human_questions(doc, document_identity, evidence_refs, extracted_relations)
        timestamp = datetime.now().isoformat(timespec="seconds")
        return ReviewPackage(
            package_id=f"review-{doc.document_id}",
            document_id=doc.document_id,
            status="pending_review",
            document_identity=document_identity,
            relation_decision="pending" if extracted_relations else "not_applicable",
            evidence_refs=evidence_refs,
            extracted_objects=extracted_objects,
            extracted_relations=extracted_relations,
            issues=issues,
            human_questions=human_questions,
            candidate_page_titles=[candidate.title for candidate in candidates],
            created_at=timestamp,
            updated_at=timestamp,
            tool_trace=[
                "App.agents.ingest_agent._build_review_package",
                "App.agents.ingest_agent._classify_business_type",
            ],
        )

    def _extract_objects_with_llm(self, canonical: "CanonicalDocument", document_identity) -> list:
        from wiki.models import ReviewObject
        from Tool.llm.prompts import build_object_extraction_prompt

        fragments = self._prepare_fragments_for_llm(canonical)
        if not fragments:
            return []

        prompt = build_object_extraction_prompt(
            fragments_context=json.dumps(fragments, ensure_ascii=False),
            document_identity=document_identity.to_dict(),
        )

        try:
            response = self._get_llm().ask(prompt, max_tokens=3000, temperature=0.2)
            data = self._parse_json_from_llm(response)
            objects_data = data.get("objects", [])
        except Exception as exc:
            print(f"[IngestAgent] LLM 对象抽取失败: {exc}")
            return []

        result: list[ReviewObject] = []
        for idx, obj_data in enumerate(objects_data):
            evidence_refs = self._build_object_evidence_refs(canonical, obj_data.get("evidence_fragment_ids", []))
            result.append(ReviewObject(
                object_id=f"obj-{idx + 1}",
                object_type=obj_data.get("object_type", "unknown"),
                name=obj_data.get("name", "未命名"),
                evidence_refs=evidence_refs,
                confidence=float(obj_data.get("confidence", 0.7)),
                review_risk=obj_data.get("review_risk", "medium"),
            ))
        return result[:48]

    def _extract_relations_with_llm(self, canonical: "CanonicalDocument", objects: list, document_identity) -> list:
        from wiki.models import ReviewRelation
        from Tool.llm.prompts import build_relation_extraction_prompt

        if not objects:
            return []

        fragments = self._prepare_fragments_for_llm(canonical)
        objects_context = [{"object_type": o.object_type, "name": o.name} for o in objects[:32]]

        prompt = build_relation_extraction_prompt(
            objects_context=json.dumps(objects_context, ensure_ascii=False),
            fragments_context=json.dumps(fragments, ensure_ascii=False),
            document_identity=document_identity.to_dict(),
        )

        try:
            response = self._get_llm().ask(prompt, max_tokens=3000, temperature=0.2)
            data = self._parse_json_from_llm(response)
            relations_data = data.get("relations", [])
        except Exception as exc:
            print(f"[IngestAgent] LLM 关系抽取失败: {exc}")
            return []

        result: list[ReviewRelation] = []
        for idx, rel_data in enumerate(relations_data):
            evidence_refs = self._build_object_evidence_refs(canonical, rel_data.get("evidence_fragment_ids", []))
            from_object_id = self._resolve_object_id(objects, rel_data.get("from_object_id") or rel_data.get("from_object_name", ""))
            to_object_id = self._resolve_object_id(objects, rel_data.get("to_object_id") or rel_data.get("to_object_name", ""))
            if not from_object_id or not to_object_id:
                continue
            result.append(ReviewRelation(
                relation_id=f"rel-{idx + 1}",
                relation_type=rel_data.get("relation_type", "related_to"),
                from_object_id=from_object_id,
                to_object_id=to_object_id,
                claim_type=rel_data.get("claim_type", "explanation"),
                direction=rel_data.get("direction", "forward"),
                evidence_refs=evidence_refs,
                confidence=float(rel_data.get("confidence", 0.7)),
                human_required=bool(rel_data.get("human_required", True)),
            ))
        return result[:32]

    def _extract_relations_rule_based(self, canonical: "CanonicalDocument", objects: list, document_identity) -> list:
        from wiki.models import ReviewRelation

        object_lookup = {(item.object_type, item.name): item for item in objects}
        relations_by_key: dict[tuple[str, str, str], ReviewRelation] = {}

        for fragment in canonical.fragments:
            fragment_objects = self._objects_from_fragment_text(fragment.text)
            requirements = [name for obj_type, name, *_ in fragment_objects if obj_type == "requirement"]
            steps = [name for obj_type, name, *_ in fragment_objects if obj_type == "process_step"]
            records = [name for obj_type, name, *_ in fragment_objects if obj_type == "record"]
            roles = [name for obj_type, name, *_ in fragment_objects if obj_type == "role"]
            ref = {
                "document_id": canonical.document.document_id,
                "fragment_id": fragment.fragment_id,
                "file_name": canonical.document.file_name,
                "anchor_label": self._anchor_label(fragment.anchors),
                "quote": fragment.text[:220],
            }
            claim_type = self._relation_claim_type(fragment.text, document_identity)

            for requirement_name in requirements:
                for step_name in steps:
                    self._register_relation(
                        relations_by_key,
                        object_lookup,
                        relation_type="requires",
                        from_key=("requirement", requirement_name),
                        to_key=("process_step", step_name),
                        claim_type=claim_type,
                        ref=ref,
                        confidence=0.78,
                    )

            for step_name in steps:
                for record_name in records:
                    self._register_relation(
                        relations_by_key,
                        object_lookup,
                        relation_type="produces",
                        from_key=("process_step", step_name),
                        to_key=("record", record_name),
                        claim_type=claim_type,
                        ref=ref,
                        confidence=0.72,
                    )

            for role_name in roles:
                for step_name in steps:
                    self._register_relation(
                        relations_by_key,
                        object_lookup,
                        relation_type="responsible_for",
                        from_key=("role", role_name),
                        to_key=("process_step", step_name),
                        claim_type=claim_type,
                        ref=ref,
                        confidence=0.68,
                    )

        return list(relations_by_key.values())[:48]

    def _register_relation(
        self,
        relations_by_key: dict,
        object_lookup: dict,
        *,
        relation_type: str,
        from_key: tuple[str, str],
        to_key: tuple[str, str],
        claim_type: str,
        ref: dict,
        confidence: float,
    ) -> None:
        from_object = object_lookup.get(from_key)
        to_object = object_lookup.get(to_key)
        if from_object is None or to_object is None:
            return

        key = (relation_type, from_object.object_id, to_object.object_id)
        existing = relations_by_key.get(key)
        if existing is None:
            from wiki.models import ReviewRelation

            relations_by_key[key] = ReviewRelation(
                relation_id=f"rel-{len(relations_by_key) + 1}",
                relation_type=relation_type,
                from_object_id=from_object.object_id,
                to_object_id=to_object.object_id,
                claim_type=claim_type,
                direction="forward",
                evidence_refs=[ref],
                confidence=confidence,
                human_required=True,
            )
        elif len(existing.evidence_refs) < 5:
            existing.evidence_refs.append(ref)

    def _resolve_object_id(self, objects: list, raw_value: str) -> str:
        value = str(raw_value).strip()
        if not value:
            return ""
        for item in objects:
            if item.object_id == value or item.name == value:
                return item.object_id
        return ""

    def _relation_claim_type(self, text: str, document_identity) -> str:
        compact = re.sub(r"\s+", "", text)
        if "推荐" in compact or "建议" in compact:
            return "recommendation"
        if document_identity.is_binding or any(token in compact for token in ("应当", "必须", "不得")):
            return "mandatory"
        return "explanation"

    def _analyze_gaps_with_llm(self, objects: list, relations: list, document_identity) -> tuple[list, list]:
        from wiki.models import ReviewIssue
        from Tool.llm.prompts import build_gap_analysis_prompt

        if not objects:
            return [], []

        objects_context = [{"object_type": o.object_type, "name": o.name} for o in objects[:32]]
        relations_context = [{"relation_type": r.relation_type, "from": r.from_object_id, "to": r.to_object_id, "claim_type": r.claim_type} for r in relations[:24]]

        prompt = build_gap_analysis_prompt(
            objects_context=json.dumps(objects_context, ensure_ascii=False),
            relations_context=json.dumps(relations_context, ensure_ascii=False),
            document_identity=document_identity.to_dict(),
        )

        try:
            response = self._get_llm().ask(prompt, max_tokens=2000, temperature=0.2)
            data = self._parse_json_from_llm(response)
        except Exception as exc:
            print(f"[IngestAgent] LLM 缺口分析失败: {exc}")
            return [], []

        gaps: list[ReviewIssue] = []
        for gap_data in data.get("gaps", []):
            gaps.append(ReviewIssue(
                issue_id=f"gap-{len(gaps) + 1}",
                issue_type=gap_data.get("gap_type", "missing_implementation"),
                detail=gap_data.get("detail", ""),
                severity=gap_data.get("severity", "medium"),
            ))

        conflicts: list[ReviewIssue] = []
        for conflict_data in data.get("conflicts", []):
            conflicts.append(ReviewIssue(
                issue_id=f"conflict-{len(conflicts) + 1}",
                issue_type=conflict_data.get("conflict_type", "boundary_ambiguity"),
                detail=conflict_data.get("detail", ""),
                severity=conflict_data.get("severity", "medium"),
            ))

        return gaps, conflicts

    def _prepare_fragments_for_llm(self, canonical: "CanonicalDocument") -> list[dict]:
        result: list[dict] = []
        for fragment in canonical.fragments[:MAX_LLM_FRAGMENTS]:
            text = fragment.text[:MAX_FRAGMENT_TEXT_LENGTH]
            result.append({
                "fragment_id": fragment.fragment_id,
                "text": text,
                "anchors": fragment.anchors,
            })
        return result

    def _build_object_evidence_refs(self, canonical: "CanonicalDocument", fragment_ids: list[str]) -> list[dict]:
        fragment_map = {f.fragment_id: f for f in canonical.fragments}
        refs: list[dict] = []
        for fid in fragment_ids[:5]:
            fragment = fragment_map.get(fid)
            if fragment:
                refs.append({
                    "document_id": canonical.document.document_id,
                    "fragment_id": fragment.fragment_id,
                    "file_name": canonical.document.file_name,
                    "anchor_label": self._anchor_label(fragment.anchors),
                    "quote": fragment.text[:220],
                })
        return refs

    def _parse_json_from_llm(self, response: str) -> dict:
        json_str = response
        if "```json" in response:
            json_str = response.split("```json")[1].split("```")[0]
        elif "```" in response:
            json_str = response.split("```")[1].split("```")[0]
        return json.loads(json_str.strip())

    def _extract_review_objects_rule_based(self, canonical: "CanonicalDocument", candidates: list[CandidatePage]):
        from wiki.models import ReviewObject

        objects_by_key: dict[tuple[str, str], ReviewObject] = {}

        for fragment in canonical.fragments:
            ref = {
                "document_id": canonical.document.document_id,
                "fragment_id": fragment.fragment_id,
                "file_name": canonical.document.file_name,
                "anchor_label": self._anchor_label(fragment.anchors),
                "quote": fragment.text[:220],
            }
            for object_type, name, confidence, review_risk in self._objects_from_fragment_text(fragment.text):
                key = (object_type, name)
                existing = objects_by_key.get(key)
                if existing is None:
                    objects_by_key[key] = ReviewObject(
                        object_id=f"obj-{len(objects_by_key) + 1}",
                        object_type=object_type,
                        name=name,
                        evidence_refs=[ref],
                        confidence=confidence,
                        review_risk=review_risk,
                    )
                elif len(existing.evidence_refs) < 5:
                    existing.evidence_refs.append(ref)

        for candidate in candidates[:6]:
            key = ("candidate_page", candidate.title)
            if key not in objects_by_key:
                objects_by_key[key] = ReviewObject(
                    object_id=f"obj-{len(objects_by_key) + 1}",
                    object_type="candidate_page",
                    name=candidate.title,
                    evidence_refs=[],
                    confidence=candidate.confidence,
                    review_risk="medium",
                )

        return list(objects_by_key.values())[:32]

    def _objects_from_fragment_text(self, text: str) -> list[tuple[str, str, float, str]]:
        objects: list[tuple[str, str, float, str]] = []
        compact = re.sub(r"\s+", "", text)

        if any(token in compact for token in ("应当", "必须", "不得")):
            requirement_name = self._normalize_requirement_name(text)
            if requirement_name:
                objects.append(("requirement", requirement_name, 0.86, "high"))

        for step in self._extract_process_steps(compact):
            objects.append(("process_step", step, 0.72, "medium"))

        for record_name in self._extract_records(text):
            objects.append(("record", record_name, 0.7, "medium"))

        for role_name in self._extract_roles(text):
            objects.append(("role", role_name, 0.68, "medium"))

        return objects

    def _normalize_requirement_name(self, text: str) -> str:
        normalized = re.sub(r"\s+", "", text)
        match = re.match(r"(第[一二三四五六七八九十百零\d]+条[^。；]{0,80})", normalized)
        if match:
            return match.group(1)
        return normalized[:80]

    def _extract_process_steps(self, text: str) -> list[str]:
        step_terms = [
            "策划",
            "输入",
            "输出",
            "验证",
            "确认",
            "转换",
            "变更",
            "评审",
            "放行",
            "采购",
            "生产",
            "检验",
            "风险管理",
            "设计开发",
            "文件控制",
        ]
        return [term for term in step_terms if term in text]

    def _extract_records(self, text: str) -> list[str]:
        records: list[str] = []
        patterns = [
            r"([\u4e00-\u9fa5A-Za-z0-9]{2,24}(?:记录|报告|方案|台账|纪要|文档|表))",
            r"(产品技术要求)",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text):
                name = str(match).strip("，。；、 ")
                if len(name) >= 2 and name not in records:
                    records.append(name)
        return records[:8]

    def _extract_roles(self, text: str) -> list[str]:
        roles: list[str] = []
        patterns = [
            r"(企业)(?=应当)",
            r"([\u4e00-\u9fa5]{2,12}(?:审核人|负责人|部门|委托方|受托方|人员))",
        ]
        for pattern in patterns:
            for match in re.findall(pattern, text):
                name = str(match).strip("，。；、 ")
                if len(name) >= 2 and name not in roles:
                    roles.append(name)
        return roles[:6]

    def _save_review_package(self, review_package) -> None:
        from wiki.store import save_review_package

        save_review_package(review_package)

    def _load_canonical_document(self, document_id: str) -> "CanonicalDocument":
        from Tool.contracts.canonical import load_canonical_document

        return load_canonical_document(PARSED_DIR / f"{document_id}.json")

    def _build_evidence_refs(self, canonical: "CanonicalDocument") -> list[dict]:
        refs: list[dict] = []
        for fragment in canonical.fragments[:8]:
            anchor_label = self._anchor_label(fragment.anchors)
            refs.append(
                {
                    "document_id": canonical.document.document_id,
                    "fragment_id": fragment.fragment_id,
                    "file_name": canonical.document.file_name,
                    "anchor_label": anchor_label,
                    "quote": fragment.text[:220],
                }
            )
        return refs

    def _build_review_issues(self, doc: "ProcessedDocument", identity, evidence_refs: list[dict], conflicts: list | None = None):
        from wiki.models import ReviewIssue

        issues: list[ReviewIssue] = []
        if identity.business_type == "unknown":
            issues.append(
                ReviewIssue(
                    issue_id="issue-identity-unknown",
                    issue_type="identity_unclear",
                    detail="文档身份暂未可靠识别，需要人工确认其权威边界。",
                    severity="high",
                    evidence_refs=evidence_refs[:2],
                )
            )
        if doc.doc_type in {"guidance", "presentation"}:
            issues.append(
                ReviewIssue(
                    issue_id="issue-guidance-boundary",
                    issue_type="boundary_risk",
                    detail="当前文档更像解读或培训材料，后续不得直接作为强制要求发布。",
                    severity="high",
                    evidence_refs=evidence_refs[:2],
                )
            )
        if conflicts:
            for conflict in conflicts:
                issues.append(conflict)
        return issues

    def _build_human_questions(self, doc: "ProcessedDocument", identity, evidence_refs: list[dict], extracted_relations: list | None = None):
        from wiki.models import HumanReviewQuestion

        questions = [
            HumanReviewQuestion(
                question_id="q-doc-identity",
                question="这份文档的身份是否正确，属于法规、解读、内部受控文件、运行证据还是经验反馈？",
                rationale="文档身份会直接决定后续结论能否作为要求使用。",
                target=doc.document_id,
                evidence_refs=evidence_refs[:2],
            ),
            HumanReviewQuestion(
                question_id="q-authority-boundary",
                question="这份文档中的结论哪些可以视为要求，哪些只能视为解释或建议？",
                rationale="需要先定权威边界，才能继续做跨文档映射。",
                target=identity.business_type,
                evidence_refs=evidence_refs[:2],
            ),
        ]

        if extracted_relations:
            high_risk_relations = [r for r in extracted_relations if r.human_required]
            if high_risk_relations:
                relation_names = ", ".join(f"{r.from_object_id} → {r.to_object_id}" for r in high_risk_relations[:3])
                questions.append(
                    HumanReviewQuestion(
                        question_id="q-relation-mapping",
                        question=f"以下关键映射是否成立：{relation_names}？",
                        rationale="这些关系涉及法规与内部流程的映射，必须人工确认。",
                        target="cross_document_mapping",
                        evidence_refs=evidence_refs[:2],
                    )
                )

        return questions

    def _classify_business_type(self, doc: "ProcessedDocument") -> str:
        title = f"{doc.title} {doc.file_name}".lower()
        if any(token in title for token in ("sop", "pep", "wi", "程序", "规程", "流程", "模板")):
            return "internal_controlled"
        if any(token in title for token in ("capa", "偏差", "投诉", "audit", "finding", "复盘")):
            return "feedback"
        if any(token in title for token in ("记录", "报告", "纪要", "dhf", "放行")):
            return "operational_evidence"
        if any(token in title for token in ("解读", "指南", "讲义", "培训")) or doc.doc_type in {"guidance", "presentation"}:
            return "external_reference"
        if doc.doc_type in {"policy", "regulation", "standard"} or any(token in title for token in ("法规", "规范", "条例", "标准")):
            return "external_mandatory"
        return "unknown"

    def _guess_version(self, doc: "ProcessedDocument") -> str:
        for key in ("version", "revision", "edition"):
            value = doc.metadata.get(key)
            if value:
                return str(value)
        return ""

    def _effective_level(self, doc: "ProcessedDocument") -> str:
        business_type = self._classify_business_type(doc)
        if business_type == "external_mandatory":
            return "external_mandatory"
        if business_type == "internal_controlled":
            return "internal_controlled"
        if business_type == "external_reference":
            return "reference_only"
        if business_type == "operational_evidence":
            return "evidence_only"
        if business_type == "feedback":
            return "feedback_only"
        return "unknown"

    def _guess_scope(self, doc: "ProcessedDocument") -> str:
        if doc.sections:
            titles = [section.get("text", "")[:60] for section in doc.sections[:2]]
            titles = [title for title in titles if title]
            if titles:
                return " / ".join(titles)
        return ""

    def _is_binding_document(self, doc: "ProcessedDocument") -> bool:
        return self._classify_business_type(doc) in {"external_mandatory", "internal_controlled"}

    def _identity_confidence(self, doc: "ProcessedDocument") -> float:
        business_type = self._classify_business_type(doc)
        return 0.85 if business_type != "unknown" else 0.45

    def _identity_notes(self, doc: "ProcessedDocument") -> list[str]:
        notes: list[str] = []
        business_type = self._classify_business_type(doc)
        if business_type == "external_reference":
            notes.append("当前文档更像解释性材料，不能直接等同于法规正文。")
        if business_type == "unknown":
            notes.append("当前只能基于标题和解析类型做初判。")
        return notes

    def _anchor_label(self, anchors: dict) -> str:
        if anchors.get("page") is not None:
            return f"p.{anchors['page']}"
        if anchors.get("paragraph_index") is not None:
            return f"para.{anchors['paragraph_index']}"
        return "source"

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
        self._save_candidate_markdown(candidate)

    def _save_candidate_markdown(self, candidate: CandidatePage):
        source_refs = [{"document_id": did} for did in candidate.source_doc_ids]
        lines = [
            "---",
            f'candidate_id: "{candidate.candidate_id}"',
            f'page_type: "{candidate.page_type}"',
            f'title: "{candidate.title}"',
            f'status: "{candidate.status}"',
            f"confidence: {candidate.confidence:.3f}",
            "source_doc_ids:",
            *[f'  - "{doc_id}"' for doc_id in candidate.source_doc_ids],
            "---",
            "",
            f"# 候选页面: {candidate.title}",
            "",
            "## 审核状态",
            "",
            f"- 状态: {candidate.status}",
            f"- 类型: {candidate.page_type}",
            f"- 置信度: {candidate.confidence:.2f}",
            "",
            "## 摘要",
            "",
            candidate.content.get("summary", "暂无摘要。"),
            "",
            "## 关键词",
            "",
        ]
        keywords = candidate.content.get("keywords", [])
        lines.extend(f"- {keyword}" for keyword in keywords) if keywords else lines.append("暂无关键词。")
        lines.extend(["", "## 关联页面", ""])
        related_titles = candidate.content.get("related_titles", [])
        lines.extend(f"- [[{title}]]" for title in related_titles) if related_titles else lines.append("暂无关联页面。")
        lines.extend(["", "## 来源", ""])
        lines.extend(f"- `{ref['document_id']}`" for ref in source_refs) if source_refs else lines.append("暂无来源。")
        CANDIDATE_MD_DIR.mkdir(parents=True, exist_ok=True)
        (CANDIDATE_MD_DIR / f"{candidate.candidate_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def approve_candidate(self, candidate_id: str) -> bool:
        candidate = self._load_candidate(candidate_id)
        if not candidate or candidate.status != "pending":
            return False
        if not self._can_publish_candidate(candidate):
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

    def _can_publish_candidate(self, candidate: CandidatePage) -> bool:
        from wiki.store import list_review_packages

        packages = [
            item
            for item in list_review_packages()
            if item.document_id in candidate.source_doc_ids
        ]
        if not packages:
            return True
        return any(
            item.identity_decision == "confirmed"
            and (
                item.relation_decision in {"confirmed", "not_applicable"}
                or not getattr(item, "extracted_relations", [])
            )
            for item in packages
        )

    def can_approve_candidate(self, candidate_id: str) -> bool:
        candidate = self._load_candidate(candidate_id)
        if not candidate or candidate.status != "pending":
            return False
        return self._can_publish_candidate(candidate)

    def list_candidates(self) -> list[CandidatePage]:
        candidates = []
        for file_path in CANDIDATE_DIR.glob("*.json"):
            candidate = self._load_candidate(file_path.stem)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _write_to_wiki(self, candidate: CandidatePage) -> str:
        from wiki.models.page import WikiPage, PageSection
        from wiki.store.files import save_page
        from wiki.indexing import build_index
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

        save_page(page)
        self._update_index(candidate.page_type, page_id, candidate.title)
        build_index()

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

        from wiki.models.page import PageSection, WikiPage
        from wiki.store.files import PAGE_DIR, load_page, save_page
        import datetime

        index_id = index_title.lower().replace(" ", "-")
        index_path = PAGE_DIR / f"{index_id}.json"

        if index_path.exists():
            index_page = load_page(index_id)
            items = list(index_page.linked_pages)
            if page_id not in items:
                items.append(page_id)
                index_page.linked_pages = items
                index_page.updated_at = datetime.datetime.now().isoformat()
                save_page(index_page)
        else:
            index_page = WikiPage(
                page_id=index_id,
                title=index_title,
                page_type="index",
                summary=f"所有{index_title}的目录和导航",
                sections=[PageSection(heading="页面列表", content=f"- [[{title}]]", source_refs=[])],
                aliases=[],
                source_refs=[],
                linked_pages=[page_id],
                review_status="published",
                page_version=1,
                updated_at=datetime.datetime.now().isoformat(),
            )
            save_page(index_page)


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
