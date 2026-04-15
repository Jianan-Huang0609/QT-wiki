FINAL_ONLY_SYSTEM_PROMPT = "Return only the final answer. No preamble."


def build_summary_prompt(title: str, snippets: list[str]) -> str:
    joined = "\n".join(f"- {snippet}" for snippet in snippets if snippet.strip())
    return (
        f"请基于以下材料，为企业 Wiki 页面《{title}》生成一段简短摘要。"
        "只输出 2-4 句中文摘要，不要编造材料里没有的内容。\n"
        f"{joined}"
    )
