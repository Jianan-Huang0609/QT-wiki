FINAL_ONLY_SYSTEM_PROMPT = "Return only the final answer. No preamble."


def build_summary_prompt(title: str, snippets: list[str]) -> str:
    joined = "\n".join(f"- {snippet}" for snippet in snippets if snippet.strip())
    return (
        f"请基于以下材料，为企业 Wiki 页面《{title}》生成一段简短摘要。"
        "只输出 2-4 句中文摘要，不要编造材料里没有的内容。\n"
        f"{joined}"
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
