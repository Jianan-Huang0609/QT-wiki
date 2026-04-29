FINAL_ONLY_SYSTEM_PROMPT = "Return only the final answer. No preamble."


def build_summary_prompt(title: str, snippets: list[str]) -> str:
    joined = "\n".join(f"- {snippet}" for snippet in snippets if snippet.strip())
    return (
        f"请基于以下材料，为企业 Wiki 页面《{title}》生成一段简短摘要。"
        "只输出 2-4 句中文摘要，不要编造材料里没有的内容。\n"
        f"{joined}"
    )


def build_object_extraction_prompt(fragments_context: str, document_identity: dict) -> str:
    """Build prompt for extracting structured objects from document fragments.

    Args:
        fragments_context: JSON or text representation of document fragments with text and anchors.
        document_identity: Dict with business_type, title, is_binding, etc.
    """
    return (
        "你是企业合规知识建模专家。你的任务是从文档片段中抽取六类关键对象，"
        "并输出严格的 JSON。\n\n"
        f"文档身份: {document_identity}\n\n"
        "文档片段:\n"
        f"{fragments_context}\n\n"
        "请抽取以下六类对象（每类都要有，没有则留空数组）：\n"
        "1. process_step: 流程节点/步骤（如'设计策划'、'设计验证'、'文件控制'）\n"
        "2. role: 角色/责任人（如'质量负责人'、'放行审核人'、'生产部门'）\n"
        "3. deliverable: 交付物/记录（如'设计验证报告'、'检验记录'、'偏差处置单'）\n"
        "4. regulation_clause: 法规条款（如'第三十六条'、'第5.2条'，必须包含条款编号）\n"
        "5. pep_node: 内部 PEP/SOP 节点（如'PEP-设计控制'、'SOP-文件控制'）\n"
        "6. concept: 核心概念（如'风险管理'、'变更控制'、'CAPA'、'数据完整性'）\n\n"
        "输出格式（严格 JSON，不要其他内容）:\n"
        "{\n"
        '  "objects": [\n'
        '    {\n'
        '      "object_type": "process_step",\n'
        '      "name": "设计验证",\n'
        '      "confidence": 0.92,\n'
        '      "review_risk": "medium",\n'
        '      "evidence_fragment_ids": ["frag-1", "frag-2"],\n'
        '      "aliases": ["设计确认", "设计评审"]\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "规则:\n"
        "- name 必须简洁明确，来自原文或合理概括\n"
        "- confidence: 0.0-1.0，基于原文明确程度\n"
        "- review_risk: low/medium/high，对象合并风险越高则越高\n"
        "- evidence_fragment_ids: 必须引用片段 ID，不能空\n"
        "- aliases: 该对象在文中的其他叫法\n"
        "- 不要编造材料中没有的对象\n"
        "- 每个对象必须能追溯到至少一个 fragment_id"
    )


def build_relation_extraction_prompt(objects_context: str, fragments_context: str, document_identity: dict) -> str:
    """Build prompt for extracting typed relations between objects.

    Args:
        objects_context: JSON representation of extracted objects.
        fragments_context: Document fragments for evidence.
        document_identity: Document identity info.
    """
    return (
        "你是企业合规知识建模专家。基于已抽取的对象和文档片段，"
        "建立对象之间的有向关系。关系必须有明确类型和方向。\n\n"
        f"文档身份: {document_identity}\n\n"
        "已抽取对象:\n"
        f"{objects_context}\n\n"
        "文档片段:\n"
        f"{fragments_context}\n\n"
        "关系类型定义:\n"
        "- requires: 法规/要求 → 流程步骤（法规要求某个步骤）\n"
        "- produces: 流程步骤 → 交付物/记录（步骤产出某记录）\n"
        "- responsible_for: 角色 → 流程步骤（角色负责某步骤）\n"
        "- implements: 内部流程/PEP → 法规条款（内部流程实现法规要求）\n"
        "- explains: 解读材料 → 法规条款（解读材料解释法规）\n"
        "- constrains: 概念/风险管理 → 流程步骤（某概念约束某步骤）\n"
        "- references: 对象 → 来源（对象引用某片段）\n\n"
        "输出格式（严格 JSON）:\n"
        "{\n"
        '  "relations": [\n'
        '    {\n'
        '      "relation_type": "requires",\n'
        '      "from_object_type": "regulation_clause",\n'
        '      "from_object_name": "第三十六条",\n'
        '      "to_object_type": "process_step",\n'
        '      "to_object_name": "文件控制",\n'
        '      "claim_type": "mandatory",\n'
        '      "direction": "forward",\n'
        '      "confidence": 0.88,\n'
        '      "human_required": true,\n'
        '      "evidence_fragment_ids": ["frag-3"]\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "规则:\n"
        "- claim_type: mandatory(强制)/recommendation(建议)/explanation(解释)\n"
        "- human_required: 关系涉及跨文档映射或语义等价判断时必须为 true\n"
        "- 只输出有明确证据支持的关系\n"
        "- 同类型关系不要重复\n"
        "- 每个关系必须能追溯到至少一个 fragment_id"
    )


def build_gap_analysis_prompt(objects_context: str, relations_context: str, document_identity: dict) -> str:
    """Build prompt for identifying gaps and conflicts in extracted knowledge."""
    return (
        "你是企业合规知识审计专家。基于已抽取的对象和关系，"
        "分析知识缺口和潜在冲突。\n\n"
        f"文档身份: {document_identity}\n\n"
        "已抽取对象:\n"
        f"{objects_context}\n\n"
        "已建立关系:\n"
        f"{relations_context}\n\n"
        "请输出两类发现:\n"
        "1. gaps: 知识缺口（如'法规条款无对应内部流程'、'流程步骤无责任人'）\n"
        "2. conflicts: 潜在冲突（如'同一术语在不同片段中定义矛盾'、'要求与建议边界模糊'）\n\n"
        "输出格式（严格 JSON）:\n"
        "{\n"
        '  "gaps": [\n'
        '    {\n'
        '      "gap_type": "missing_implementation",\n'
        '      "detail": "第三十六条要求建立文件控制程序，但未发现对应内部SOP",\n'
        '      "severity": "high",\n'
        '      "related_object_names": ["第三十六条", "文件控制"]\n'
        '    }\n'
        '  ],\n'
        '  "conflicts": [\n'
        '    {\n'
        '      "conflict_type": "boundary_ambiguity",\n'
        '      "detail": "片段A使用\\"应当\\"，片段B使用\\"可以\\"，边界模糊",\n'
        '      "severity": "medium",\n'
        '      "related_fragment_ids": ["frag-1", "frag-5"]\n'
        '    }\n'
        '  ]\n'
        "}\n\n"
        "规则:\n"
        "- severity: high/medium/low\n"
        "- 只输出有明确证据支持的发现\n"
        "- 不要编造不存在的问题"
    )


def build_page_discovery_prompt(document_contexts: list[str]) -> str:
    joined = "\n\n".join(
        f"### 文档 {index}\n{context}"
        for index, context in enumerate(document_contexts, start=1)
        if context.strip()
    )
    return (
        "你是企业知识库建库代理。任务不是总结单一页面，而是先从文档中发现应该建立哪些 Wiki 页面。\n"
        "请基于输入材料，输出 4-12 个最值得建立的页面主题，优先保留稳定、可复用、适合长期维护的主题，"
        "不要输出“目录”“总则”“培训讲义”“本页要点”这类噪声标题。\n"
        "只输出 JSON，不要输出解释。格式如下：\n"
        "{"
        '"pages":['
        '{"title":"页面标题","page_type":"policy|concept|process|role","aliases":["别名"],'
        '"keywords":["用于匹配证据的关键词"],"section_keywords":["相关章节标题"],'
        '"related_titles":["应建立链接的其他页面标题"]}'
        "]}"
        "\n\n"
        "要求：\n"
        "1. 标题必须是中文主题，不要使用英文 slug。\n"
        "2. 若两个主题高度相近，保留更稳定、更上位的那个，并把另一个放到 aliases。\n"
        "3. keywords 与 section_keywords 必须来自材料，不要编造。\n"
        "4. related_titles 只写本次输出中也应存在的主题。\n\n"
        f"{joined}"
    )
