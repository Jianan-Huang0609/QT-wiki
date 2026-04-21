# QT Wiki Agents Schema

## 架构概述

本文件定义 QT Wiki 的知识结构和智能体行为规则，由开发者和 LLM 共同演化维护。

## 三层架构

```
Schema 层 (本文件)
    ↓ 定义结构
Wiki 层 (摘要/实体/概念/比较/Index)
    ↓ 引用来源
Raw 层 (原文档)
```

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
  2. 提取关键信息（实体、概念、摘要）
  3. 生成候选页面（摘要页、实体页、概念页）
  4. **暂停，等待人工讨论和确认**
  5. 根据确认结果写入 Wiki
  6. 更新 Index

### QueryAgent
- **职责**: 回答用户问题
- **工作流**:
  1. 理解用户问题
  2. 搜索 Wiki 和 Raw
  3. 综合信息生成回答
  4. 提供引用来源
  5. **询问用户是否将好答案归档为 Wiki 页面**

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

## 变更日志

- 2026-04-14: 初始 Schema 定义，定义 5 种页面类型和 3 个 Agent
