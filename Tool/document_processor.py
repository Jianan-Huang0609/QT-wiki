"""文档处理工具 - 将 Raw 文档解析为 LLM 可用的结构化内容."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = REPO_ROOT / "Raw"
PARSED_DIR = REPO_ROOT / "Tool" / "output" / "parsed"


@dataclass
class ProcessedDocument:
    """处理后的文档，供 LLM 和 Agent 使用."""

    document_id: str
    title: str
    file_name: str
    doc_type: str
    source_type: str  # docx, pdf, pptx, xlsx
    content: str  # 纯文本内容，适合传给 LLM
    sections: list[dict] = field(default_factory=list)  # 结构化章节
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_llm_context(self, max_length: int | None = None) -> str:
        """转换为 LLM 可用的上下文.

        Args:
            max_length: 最大长度限制（None 表示不限制）
        """
        content = self.content[:max_length] if max_length else self.content
        lines = [
            f"文档标题: {self.title}",
            f"文档ID: {self.document_id}",
            f"文档类型: {self.doc_type}",
            "",
            "=== 内容 ===",
            content,
        ]
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_id": self.document_id,
            "title": self.title,
            "file_name": self.file_name,
            "doc_type": self.doc_type,
            "source_type": self.source_type,
            "content": self.content,
            "sections": self.sections,
            "metadata": self.metadata,
        }


def process_document(file_path: str | Path) -> ProcessedDocument:
    """处理单个文档，返回结构化内容.

    Args:
        file_path: 文档路径（Raw/ 下的文件）

    Returns:
        ProcessedDocument: 处理后的文档
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"文档不存在: {file_path}")

    # 先执行 ingest 和 parse 流程
    from Tool.pipelines.ingest import ingest
    from Tool.pipelines.parse import parse_one

    # 1. 入库
    manifests = ingest(str(path))
    if not manifests:
        raise ValueError(f"文档入库失败: {file_path}")

    manifest = manifests[0]
    document_id = manifest["document_id"]

    # 2. 解析
    parse_one(document_id)

    # 3. 加载解析结果并转换为 ProcessedDocument
    return load_processed_document(document_id)


def load_processed_document(document_id: str) -> ProcessedDocument:
    """加载已解析的文档为 ProcessedDocument.

    Args:
        document_id: 文档 ID

    Returns:
        ProcessedDocument: 处理后的文档
    """
    from Tool.contracts.canonical import load_canonical_document

    parsed_path = PARSED_DIR / f"{document_id}.json"
    if not parsed_path.exists():
        raise FileNotFoundError(f"文档未解析: {document_id}")

    canonical = load_canonical_document(str(parsed_path))

    # 构建纯文本内容
    content_parts = []
    sections = []

    # 从 fragments 构建内容
    for fragment in canonical.fragments:
        text = fragment.text.strip()
        if text:
            content_parts.append(text)
            sections.append({
                "type": fragment.fragment_type,
                "text": text,
                "anchors": fragment.anchors,
            })

    # 从 tables 添加表格内容
    for table in canonical.tables:
        if table.rows:
            table_text = "\n".join(
                " | ".join(cell.strip() for cell in row)
                for row in table.rows[:10]  # 限制行数
            )
            content_parts.append(f"\n[表格]\n{table_text}")

    full_content = "\n\n".join(content_parts)

    return ProcessedDocument(
        document_id=canonical.document.document_id,
        title=canonical.document.title,
        file_name=canonical.document.file_name,
        doc_type=canonical.document.doc_type,
        source_type=canonical.document.source_type,
        content=full_content,
        sections=sections,
        metadata={
            "parse_status": canonical.parse_status,
            "fragment_count": len(canonical.fragments),
            "table_count": len(canonical.tables),
            "section_count": len(canonical.sections),
        },
    )


def process_directory(input_dir: str | Path) -> list[ProcessedDocument]:
    """批量处理目录中的所有文档.

    Args:
        input_dir: 输入目录路径

    Returns:
        ProcessedDocument 列表
    """
    from Tool.pipelines.common import resolve_inputs

    results = []
    for file_path in resolve_inputs(str(input_dir)):
        try:
            doc = process_document(file_path)
            results.append(doc)
            print(f"[OK] {doc.title} ({doc.document_id})")
        except Exception as e:
            print(f"[ERROR] {file_path}: {e}")

    return results


def save_processed_document(doc: ProcessedDocument, output_dir: str | Path | None = None) -> Path:
    """保存处理后的文档.

    Args:
        doc: 处理后的文档
        output_dir: 输出目录（默认 Tool/output/processed/）

    Returns:
        保存的文件路径
    """
    if output_dir is None:
        output_dir = REPO_ROOT / "Tool" / "output" / "processed"

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    file_path = output_path / f"{doc.document_id}.json"
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(doc.to_dict(), f, ensure_ascii=False, indent=2)

    return file_path


if __name__ == "__main__":
    import argparse
    import sys

    parser = argparse.ArgumentParser(description="处理 Raw 文档为 LLM 可用的结构化内容")
    parser.add_argument("--input", "-i", required=True, help="输入文件或目录路径")
    parser.add_argument("--output-dir", "-o", help="输出目录（可选）")
    parser.add_argument("--list", "-l", action="store_true", help="只列出文档信息，不保存")

    args = parser.parse_args()

    input_path = Path(args.input)

    if input_path.is_file():
        try:
            doc = process_document(input_path)
            print(f"\n文档: {doc.title}")
            print(f"ID: {doc.document_id}")
            print(f"类型: {doc.doc_type}")
            print(f"片段数: {doc.metadata.get('fragment_count', 0)}")
            print(f"内容长度: {len(doc.content)} 字符")

            if not args.list:
                output_path = save_processed_document(doc, args.output_dir)
                print(f"已保存: {output_path}")

            # 显示部分内容
            print(f"\n内容预览（前500字符）:")
            print("-" * 40)
            print(doc.content[:500])
            print("-" * 40)

        except Exception as e:
            print(f"处理失败: {e}", file=sys.stderr)
            sys.exit(1)

    elif input_path.is_dir():
        docs = process_directory(input_path)
        print(f"\n共处理 {len(docs)} 个文档")

        if not args.list and docs:
            for doc in docs:
                save_processed_document(doc, args.output_dir)
            print(f"已保存到: {args.output_dir or 'Tool/output/processed/'}")

    else:
        print(f"路径不存在: {input_path}", file=sys.stderr)
        sys.exit(1)
