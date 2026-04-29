# QT Wiki Agents Schema

## 架构概述

本文件定义 QT Wiki 的知识结构和智能体行为规则，由开发者和 LLM 共同演化维护。

## 分层架构

```
Schema 层 (本文件)
    ↓ 定义结构
Index 层 (机器索引: pages.jsonl / terms.json / links.json / sources.jsonl)
    ↓ 定位页面和来源
Wiki 层 (Obsidian Markdown 页面 + JSON 兼容缓存)
    ↓ 引用 fragment
Parsed 层 (Canonical JSON: sections / fragments / anchors)
    ↓ 来自解析
Raw 层 (原文档和 manifest)
```

## 存储职责

- **Raw 层**: 保存原始 docx/pdf/pptx/xlsx 和 manifest，不直接参与问答生成。
- **Parsed 层**: 保存规范化 Canonical JSON，是 fragment、section、anchor、checksum 的事实来源。
- **Wiki 层**: 正式知识页以 Markdown 为主，必须可在 Obsidian 浏览；JSON 仅作为兼容缓存和程序接口。
- **Index 层**: 自动生成，供 QueryAgent 召回使用，禁止人工编辑。
- **Schema 层**: 定义页面类型、关系、Agent 工作流和质量底线。

## 页面类型定义

### 1. 摘要页 (Overview)
- **用途**: 对某个主题或文档的综合概述
- **字段**: title, summary, source_refs, related_entities, related_concepts
- **生成方式**: LLM 读取 Raw 后生成，需人工确认

### 2. 实体页 (Entity)
- **用途**: 具体的人、组织、产品、法规等
- **字段**: name, entity_type, description, attributes, relationships, appearances
- **示例**: "GMP 法规 2024版", "质量负责人", "灭菌设备"

### 3. 概念页 (Concept)
- **用途**: 抽象概念、方法论、原则
- **字段**: term, definition, related_concepts, examples, source_refs
- **示例**: "风险管理", "变更控制", "CAPA"

### 4. 比较页 (Comparison)
- **用途**: 对比两个或多个实体/概念
- **字段**: subjects, dimensions, comparison_table, conclusion
- **生成方式**: Query 或人工发起

### 5. 索引页 (Index)
- **用途**: 某类页面的目录和导航
- **字段**: category, items, last_updated
- **示例**: "所有法规实体索引", "概念索引"

## Markdown 页面契约

Wiki 页面必须使用 `YAML frontmatter + Markdown 正文`:

```yaml
---
page_id: "质量管理体系"
title: "质量管理体系"
page_type: "concept"
review_status: "published"
page_version: 1
updated_at: "2026-04-27T10:00:00"
aliases:
  - "QMS"
linked_pages:
  - "风险管理"
source_refs:
  - document_id: "doc-xxx"
    fragment_id: "frag-12"
    file_name: "规范.pdf"
    anchor_label: "p.8"
---
```

正文至少包含：

1. `# 标题`
2. `## 摘要`
3. 一个或多个业务章节
4. `## 关联页面`
5. `## 引用来源`

## 溯源规则

- 每个事实性结论必须能追溯到至少一个 `source_ref`。
- `source_ref` 至少包含 `document_id`；正式页面应优先包含 `fragment_id`、`file_name`、`anchor_label` 和短摘录 `quote`。
- 页面正文可以使用脚注给人阅读，frontmatter 和 section `source_refs` 给程序读取。
- LLM 不得把没有来源的推断写成事实；来源不足时必须标记为待确认。

## 关系定义

```yaml
relations:
  - name: defines
    from: Concept
    to: Entity
    meaning: 概念定义了实体的属性

  - name: implements
    from: Entity
    to: Concept
    meaning: 实体实现了某个概念

  - name: references
    from: WikiPage
    to: RawDocument
    meaning: 页面引用了原文档

  - name: related_to
    from: WikiPage
    to: WikiPage
    meaning: 页面间相关

  - name: compares
    from: Comparison
    to: [Entity, Concept]
    meaning: 比较页对比的目标
```

## 智能体行为定义

### IngestAgent
- **职责**: 处理新文档入库
- **工作流**:
  1. 读取 Raw 文档
  2. 解析为 Canonical JSON，保留 fragments、sections、anchors
  3. 提取关键信息（实体、概念、摘要）
  4. 生成候选 Markdown 页面到 `wiki/output/obsidian/Proposals/`
  5. **暂停，等待人工讨论和确认**
  6. 根据确认结果发布到 `wiki/output/obsidian/Pages/`，并保留 JSON 兼容缓存
  7. 更新机器 Index

### QueryAgent
- **职责**: 回答用户问题
- **工作流**:
  1. 理解用户问题
  2. 搜索 Index 层，召回少量候选 Wiki 页面
  3. 只加载候选页面及必要来源片段
  4. 综合信息生成回答
  5. 提供 Wiki 页面和 Raw fragment 引用来源
  6. **询问用户是否将好答案归档为 Wiki 页面**

### LintAgent
- **职责**: 维护 Wiki 健康
- **检查项**:
  - 矛盾检测：同一实体在不同页面的描述冲突
  - 过时检测：基于 Raw 更新日期检查页面 freshness
  - 孤儿页：没有入链的页面
  - 缺失引用：页面没有 source_refs
  - 断裂链接：指向不存在的页面
- **工作流**:
  1. 定期扫描全部页面
  2. 生成健康报告
  3. 提出修复建议
  4. **等待人工确认后执行修复**

## 演化规则

1. **Schema 变更**: 当发现新的页面类型或关系时，更新本文件
2. **页面创建**: 必须通过 Agent 创建，禁止直接写入
3. **人工确认**: Ingest 和 Lint 的关键操作需要人工确认
4. **版本记录**: 每次 Schema 变更记录变更日志
5. **索引生成**: Index 层只能由程序从 Wiki 层生成，不能人工修改
6. **查询边界**: QueryAgent 不允许默认把整个 Wiki 正文传入 LLM

## 变更日志

- 2026-04-27: 架构升级为 Raw / Parsed / Wiki / Index / Schema 五层；规定 Markdown Wiki、机器索引和事实溯源规则。
- 2026-04-14: 初始 Schema 定义，定义 5 种页面类型和 3 个 Agent
