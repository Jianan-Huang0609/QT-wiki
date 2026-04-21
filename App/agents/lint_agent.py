"""LintAgent - 维护智能体，定期健康检查 Wiki."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass

REPO_ROOT = Path(__file__).resolve().parents[2]
PAGE_DIR = REPO_ROOT / "wiki" / "output" / "pages"
PROPOSAL_DIR = REPO_ROOT / "wiki" / "output" / "proposals"


@dataclass
class HealthIssue:
    """健康问题."""

    issue_type: str  # contradiction, stale, orphan, missing_ref, broken_link
    severity: str  # high, medium, low
    page_id: str
    description: str
    suggestion: str
    auto_fixable: bool = False


@dataclass
class HealthReport:
    """健康报告."""

    total_pages: int
    issues: list[HealthIssue]
    summary: dict = field(default_factory=dict)


class LintAgent:
    """维护智能体.

    检查项:
    - 矛盾检测：同一实体在不同页面的描述冲突
    - 过时检测：基于 Raw 更新日期检查页面 freshness
    - 孤儿页：没有入链的页面
    - 缺失引用：页面没有 source_refs
    - 断裂链接：指向不存在的页面

    工作流:
    1. 定期扫描全部页面
    2. 生成健康报告
    3. LLM 提出修复建议
    4. 等待人工确认后执行修复
    """

    def __init__(self):
        self.issues: list[HealthIssue] = []
        self.llm = None

    def _get_llm(self):
        """延迟初始化 LLM 客户端."""
        if self.llm is None:
            from Tool.llm.client import LLMTool
            self.llm = LLMTool()
        return self.llm

    def run_health_check(self, use_llm: bool = True) -> HealthReport:
        """运行完整健康检查.

        Args:
            use_llm: 是否使用 LLM 分析

        Returns:
            健康报告
        """
        print("[LintAgent] 开始健康检查...")
        self.issues = []

        pages = self._load_all_pages()
        print(f"[LintAgent] 加载了 {len(pages)} 个页面")

        # 1. 矛盾检测
        self._check_contradictions(pages)

        # 2. 过时检测
        self._check_stale_pages(pages)

        # 3. 孤儿页检测
        self._check_orphan_pages(pages)

        # 4. 缺失引用检测
        self._check_missing_refs(pages)

        # 5. 断裂链接检测
        self._check_broken_links(pages)

        # 6. LLM 深度分析（可选）
        if use_llm and len(pages) > 0:
            self._llm_deep_analysis(pages)

        # 生成报告
        report = HealthReport(
            total_pages=len(pages),
            issues=self.issues,
            summary={
                "contradictions": len([i for i in self.issues if i.issue_type == "contradiction"]),
                "stale": len([i for i in self.issues if i.issue_type == "stale"]),
                "orphan": len([i for i in self.issues if i.issue_type == "orphan"]),
                "missing_ref": len([i for i in self.issues if i.issue_type == "missing_ref"]),
                "broken_link": len([i for i in self.issues if i.issue_type == "broken_link"]),
            },
        )

        self._print_report(report)
        return report

    def _load_all_pages(self) -> list[dict]:
        """加载所有页面."""
        pages = []
        if not PAGE_DIR.exists():
            return pages

        for file_path in PAGE_DIR.glob("*.json"):
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    page = json.load(f)
                    page["_file"] = file_path.name
                    pages.append(page)
            except Exception:
                continue

        return pages

    def _check_contradictions(self, pages: list[dict]):
        """检测矛盾."""
        entity_definitions: dict[str, list[tuple[str, str]]] = {}

        for page in pages:
            page_id = page.get("page_id", "")
            title = page.get("title", "")

            if page.get("page_type") == "entity":
                desc = page.get("summary", "")
                if title in entity_definitions:
                    for existing_page, existing_desc in entity_definitions[title]:
                        if existing_desc and desc and existing_desc != desc:
                            self.issues.append(
                                HealthIssue(
                                    issue_type="contradiction",
                                    severity="high",
                                    page_id=page_id,
                                    description=f"实体 '{title}' 在页面 {existing_page} 和 {page_id} 中的定义不一致",
                                    suggestion="请人工审核并统一实体定义",
                                    auto_fixable=False,
                                )
                            )

                entity_definitions.setdefault(title, []).append((page_id, desc))

        print(f"[LintAgent] 矛盾检测完成，发现 {len([i for i in self.issues if i.issue_type == 'contradiction'])} 个问题")

    def _check_stale_pages(self, pages: list[dict]):
        """检测过时页面."""
        import datetime

        now = datetime.datetime.now()

        for page in pages:
            updated_at = page.get("updated_at", "")
            page_id = page.get("page_id", "")

            if updated_at:
                try:
                    updated = datetime.datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    days_old = (now - updated).days

                    if days_old > 90:
                        self.issues.append(
                            HealthIssue(
                                issue_type="stale",
                                severity="medium",
                                page_id=page_id,
                                description=f"页面已超过 {days_old} 天未更新",
                                suggestion="建议重新运行 Ingest 流程更新页面内容",
                                auto_fixable=False,
                            )
                        )
                except ValueError:
                    pass

        print(f"[LintAgent] 过时检测完成，发现 {len([i for i in self.issues if i.issue_type == 'stale'])} 个问题")

    def _check_orphan_pages(self, pages: list[dict]):
        """检测孤儿页."""
        all_links: set[str] = set()
        page_ids = {p.get("page_id", "") for p in pages}

        for page in pages:
            for linked in page.get("linked_pages", []):
                all_links.add(linked)

        for page in pages:
            page_id = page.get("page_id", "")
            if page_id and page_id not in all_links and len(page.get("linked_pages", [])) == 0:
                self.issues.append(
                    HealthIssue(
                        issue_type="orphan",
                        severity="low",
                        page_id=page_id,
                        description=f"页面 '{page.get('title', page_id)}' 是孤儿页（无入链也无出链）",
                        suggestion="建议在其他页面中添加对此页面的引用",
                        auto_fixable=False,
                    )
                )

        print(f"[LintAgent] 孤儿页检测完成，发现 {len([i for i in self.issues if i.issue_type == 'orphan'])} 个问题")

    def _check_missing_refs(self, pages: list[dict]):
        """检测缺失引用."""
        for page in pages:
            page_id = page.get("page_id", "")
            source_refs = page.get("source_refs", [])

            if not source_refs:
                self.issues.append(
                    HealthIssue(
                        issue_type="missing_ref",
                        severity="medium",
                        page_id=page_id,
                        description=f"页面 '{page.get('title', page_id)}' 没有来源引用",
                        suggestion="建议添加 source_refs 指向原始文档",
                        auto_fixable=False,
                    )
                )

        print(f"[LintAgent] 缺失引用检测完成，发现 {len([i for i in self.issues if i.issue_type == 'missing_ref'])} 个问题")

    def _check_broken_links(self, pages: list[dict]):
        """检测断裂链接."""
        page_ids = {p.get("page_id", "") for p in pages}

        for page in pages:
            page_id = page.get("page_id", "")
            for linked in page.get("linked_pages", []):
                if linked not in page_ids:
                    self.issues.append(
                        HealthIssue(
                            issue_type="broken_link",
                            severity="medium",
                            page_id=page_id,
                            description=f"页面 '{page.get('title', page_id)}' 链接到不存在的页面: {linked}",
                            suggestion="请创建目标页面或移除断裂链接",
                            auto_fixable=True,
                        )
                    )

        print(f"[LintAgent] 断裂链接检测完成，发现 {len([i for i in self.issues if i.issue_type == 'broken_link'])} 个问题")

    def _llm_deep_analysis(self, pages: list[dict]):
        """使用 LLM 进行深度分析."""
        # 构建页面摘要
        page_summaries = []
        for page in pages[:10]:  # 最多分析10个页面
            summary = f"- {page.get('title', '')} ({page.get('page_type', '')}): {page.get('summary', '')[:100]}..."
            page_summaries.append(summary)

        context = "\n".join(page_summaries)

        prompt = f"""你是企业知识库维护专家。请分析以下 Wiki 页面列表，发现潜在问题并提出建议。

当前页面:
{context}

请分析:
1. 是否有重复或高度相似的页面？
2. 是否有应该合并的页面？
3. 是否有缺失的关键概念或实体？
4. 页面类型分布是否合理？

输出 JSON 格式:
{{
  "issues": [
    {{
      "type": "duplicate|merge|missing|distribution",
      "description": "问题描述",
      "suggestion": "修复建议"
    }}
  ]
}}

只输出 JSON，不要其他解释。"""

        try:
            response = self._get_llm().ask(prompt, max_tokens=1500, temperature=0.3)
            llm_issues = self._parse_llm_analysis(response)

            for issue_data in llm_issues:
                self.issues.append(
                    HealthIssue(
                        issue_type=issue_data.get("type", "llm_suggestion"),
                        severity="low",
                        page_id="global",
                        description=issue_data.get("description", ""),
                        suggestion=issue_data.get("suggestion", ""),
                        auto_fixable=False,
                    )
                )

            print(f"[LintAgent] LLM 深度分析完成，发现 {len(llm_issues)} 个建议")
        except Exception as e:
            print(f"[LintAgent] LLM 深度分析失败: {e}")

    def _parse_llm_analysis(self, response: str) -> list[dict]:
        """解析 LLM 分析结果."""
        try:
            json_str = response
            if "```json" in response:
                json_str = response.split("```json")[1].split("```")[0]
            elif "```" in response:
                json_str = response.split("```")[1].split("```")[0]

            data = json.loads(json_str.strip())
            return data.get("issues", [])
        except (json.JSONDecodeError, IndexError):
            return []

    def _print_report(self, report: HealthReport):
        """打印健康报告."""
        print("\n" + "=" * 60)
        print("Wiki 健康报告")
        print("=" * 60)
        print(f"总页面数: {report.total_pages}")
        print(f"问题总数: {len(report.issues)}")
        print("-" * 60)

        for issue_type, count in report.summary.items():
            if count > 0:
                print(f"  {issue_type:15}: {count} 个")

        if report.issues:
            print("-" * 60)
            print("详细问题列表:")
            for i, issue in enumerate(report.issues[:10], 1):
                print(f"\n  {i}. [{issue.severity.upper()}] {issue.issue_type}")
                print(f"     页面: {issue.page_id}")
                print(f"     描述: {issue.description}")
                print(f"     建议: {issue.suggestion}")
                if issue.auto_fixable:
                    print(f"     [可自动修复]")

        print("=" * 60)

    def interact_fix(self, auto_fixable_only: bool = True) -> list[str]:
        """交互式修复模式，等待人工确认后执行修复.

        Args:
            auto_fixable_only: 只处理可自动修复的问题

        Returns:
            已修复的页面 ID 列表
        """
        fixed_pages = []
        pages = self._load_all_pages()

        print("\n" + "=" * 60)
        print("Wiki 交互式修复模式")
        print("=" * 60)

        auto_fixable = [i for i in self.issues if i.auto_fixable]
        manual_fixable = [i for i in self.issues if not i.auto_fixable]

        if auto_fixable_only:
            issues_to_fix = auto_fixable
        else:
            issues_to_fix = self.issues

        print(f"\n共 {len(issues_to_fix)} 个问题待处理")
        print(f"  - 可自动修复: {len(auto_fixable)} 个")
        print(f"  - 需人工处理: {len(manual_fixable)} 个")

        for i, issue in enumerate(issues_to_fix, 1):
            print(f"\n[{i}/{len(issues_to_fix)}] {issue.issue_type.upper()}")
            print(f"  页面: {issue.page_id}")
            print(f"  描述: {issue.description}")
            print(f"  建议: {issue.suggestion}")

            if issue.auto_fixable:
                print("\n  [a] 执行修复  [s] 跳过  [q] 退出")
                try:
                    choice = input("  > ").strip().lower()
                    if choice == "a":
                        if self._fix_single_issue(issue, pages):
                            fixed_pages.append(issue.page_id)
                            print("  [已修复]")
                    elif choice == "q":
                        break
                except (EOFError, KeyboardInterrupt):
                    break
            else:
                print("\n  此问题需要人工处理，已跳过")

        print("\n" + "=" * 60)
        print(f"修复完成，共处理 {len(fixed_pages)} 个问题")
        print("=" * 60)

        return fixed_pages

    def _fix_single_issue(self, issue: HealthIssue, pages: list[dict]) -> bool:
        """修复单个问题."""
        try:
            if issue.issue_type == "broken_link":
                page_ids = {p.get("page_id", "") for p in pages}
                for page in pages:
                    if page.get("page_id") == issue.page_id:
                        old_links = page.get("linked_pages", [])
                        new_links = [l for l in old_links if l in page_ids]
                        page["linked_pages"] = new_links
                        file_path = PAGE_DIR / f"{issue.page_id}.json"
                        with open(file_path, "w", encoding="utf-8") as f:
                            json.dump(page, f, ensure_ascii=False, indent=2)
                        return True
            elif issue.issue_type == "missing_ref":
                for page in pages:
                    if page.get("page_id") == issue.page_id:
                        if not page.get("source_refs"):
                            page["source_refs"] = [{"document_id": "pending", "note": "待补充来源"}]
                            file_path = PAGE_DIR / f"{issue.page_id}.json"
                            with open(file_path, "w", encoding="utf-8") as f:
                                json.dump(page, f, ensure_ascii=False, indent=2)
                            return True
            return False
        except Exception:
            return False

    def fix_broken_links(self, dry_run: bool = True) -> list[str]:
        """修复断裂链接.

        Args:
            dry_run: 是否为试运行模式

        Returns:
            修复的页面 ID 列表
        """
        fixed_pages = []
        pages = self._load_all_pages()
        page_ids = {p.get("page_id", "") for p in pages}

        for page in pages:
            page_id = page.get("page_id", "")
            linked_pages = page.get("linked_pages", [])
            valid_links = [link for link in linked_pages if link in page_ids]

            if len(valid_links) != len(linked_pages):
                if not dry_run:
                    page["linked_pages"] = valid_links
                    file_path = PAGE_DIR / f"{page_id}.json"
                    with open(file_path, "w", encoding="utf-8") as f:
                        json.dump(page, f, ensure_ascii=False, indent=2)
                    fixed_pages.append(page_id)
                    print(f"[LintAgent] 已修复页面 {page_id} 的断裂链接")
                else:
                    print(f"[LintAgent] [试运行] 将修复页面 {page_id} 的断裂链接")
                    fixed_pages.append(page_id)

        return fixed_pages

    def suggest_new_questions(self, pages: list[dict] | None = None) -> list[str]:
        """基于现有内容建议新问题和新来源.

        Args:
            pages: 页面列表（可选）

        Returns:
            建议的问题列表
        """
        if pages is None:
            pages = self._load_all_pages()

        suggestions = []

        # 1. 基于孤儿页建议问题
        orphan_pages = []
        all_links = set()
        for p in pages:
            for linked in p.get("linked_pages", []):
                all_links.add(linked)

        for p in pages:
            pid = p.get("page_id", "")
            if pid and pid not in all_links:
                orphan_pages.append(p)

        if orphan_pages:
            suggestions.append(f"有 {len(orphan_pages)} 个页面未被引用，建议创建索引页或添加关联")

        # 2. 基于页面类型分布建议
        type_counts = {}
        for p in pages:
            pt = p.get("page_type", "unknown")
            type_counts[pt] = type_counts.get(pt, 0) + 1

        if type_counts.get("comparison", 0) == 0:
            suggestions.append("建议创建比较页，对比相关概念或实体")

        if type_counts.get("index", 0) == 0:
            suggestions.append("建议创建索引页，方便导航")

        # 3. 基于内容覆盖度建议
        has_qa = any(p.get("page_type") == "qa" for p in pages)
        if not has_qa:
            suggestions.append("建议通过 QueryAgent 提出问题并将优质回答归档为 Q&A 页面")

        # 4. LLM 建议新问题
        try:
            topics = [p.get("title", "") for p in pages[:5]]
            prompt = f"""基于以下 Wiki 主题，建议 3-5 个可以深入探索的问题：

主题: {', '.join(topics)}

请输出问题列表，每个问题一行。"""

            response = self._get_llm().ask(prompt, max_tokens=500, temperature=0.7)
            llm_questions = [q.strip() for q in response.split('\n') if q.strip() and '?' in q]
            suggestions.extend(llm_questions[:3])
        except Exception:
            pass

        print("\n[LintAgent] LLM 建议:")
        for i, suggestion in enumerate(suggestions, 1):
            print(f"  {i}. {suggestion}")

        return suggestions


if __name__ == "__main__":
    import sys

    agent = LintAgent()

    if len(sys.argv) < 2:
        report = agent.run_health_check()
        agent.suggest_new_questions()
    elif sys.argv[1] == "fix":
        dry_run = "--dry-run" in sys.argv
        agent.run_health_check()
        agent.fix_broken_links(dry_run=dry_run)
    else:
        print("用法:")
        print("  python -m App.agents.lint_agent           - 运行健康检查")
        print("  python -m App.agents.lint_agent fix       - 修复可自动修复的问题")
        print("  python -m App.agents.lint_agent fix --dry-run - 试运行修复")
