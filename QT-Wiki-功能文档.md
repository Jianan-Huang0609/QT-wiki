# QT Wiki 功能文档

## 1. 项目概述

QT Wiki 是一个企业级知识库系统，专注于质量管理体系（QMS）领域的知识管理和智能问答。系统采用**AI 辅助 + 人工审批**的工作模式，确保知识的准确性和可追溯性。

### 1.1 核心设计理念

- **知识建模与审批流程**：AI 负责知识拆分和初步分析，人工只审核关键判断
- **分层架构**：Raw → Parsed → Wiki → Index → Schema 五层架构
- **溯源优先**：每个事实性结论必须能追溯到原始文档的具体位置
- **一对多映射**：支持法规要求到内部流程、模板、记录的多维度映射

### 1.2 文档类型分类

系统支持五类文档：

| 类型 | 说明 | 示例 |
|------|------|------|
| 外部强制文件 | 法规、规范、条例、强制标准 | GMP 法规 |
| 外部解释与参考文件 | 指南、专家解读、培训讲义 | 法规解读 |
| 内部受控文件 | PEP、WI、SOP、流程文件 | 设计控制程序 |
| 运行证据文件 | 已填写的记录、验证报告 | 验证报告 |
| 经验反馈文件 | Finding、Audit、CAPA、偏差 | 偏差记录 |

---

## 2. 系统架构

### 2.1 五层架构

```
Schema 层 (AGENTS.md)
    ↓ 定义结构
Index 层 (机器索引: pages.jsonl / terms.json / links.json / sources.jsonl)
    ↓ 定位页面和来源
Wiki 层 (Obsidian Markdown 页面 + JSON 兼容缓存)
    ↓ 引用 fragment
Parsed 层 (Canonical JSON: sections / fragments / anchors)
    ↓ 来自解析
Raw 层 (原文档和 manifest)
```

### 2.2 模块结构

```
QT-wiki/
├── App/                          # 应用层 - API 和智能体
│   ├── api.py                    # FastAPI REST API
│   ├── schemas.py                # Pydantic 数据模型
│   ├── validators.py             # 数据验证
│   └── agents/                   # 智能体
│       ├── ingest_agent.py       # 文档摄入智能体
│       ├── query_agent.py        # 问答智能体
│       ├── lint_agent.py         # 维护智能体
│       └── structured_knowledge.py # 结构化知识处理
├── Tool/                         # 工具层 - 文档处理
│   ├── document_processor.py     # 文档处理器
│   ├── llm/                      # LLM 客户端和提示词
│   ├── parsers/                  # 文档解析器 (PDF/DOCX/PPTX/XLSX)
│   ├── pipelines/                # 处理管道
│   ├── contracts/                # 数据契约
│   └── normalizers/              # 文本规范化
├── wiki/                         # Wiki 层
│   ├── models/                   # 数据模型
│   ├── store/                    # 存储层
│   ├── indexing/                 # 索引构建
│   ├── builders/                 # 页面构建
│   └── updaters/                 # 更新器
└── tests/                        # 测试
```

---

## 3. 核心功能模块

### 3.1 文档摄入流程 (IngestAgent)

#### 3.1.1 功能概述

IngestAgent 负责处理新文档入库，将 Raw 文档转换为结构化的 Wiki 知识页面。

#### 3.1.2 工作流程

**第一步：文档识别**
- 识别文档类型（法规/解读/内部流程/运行证据/经验反馈）
- 提取关键信息：标题、版本、适用范围、权威级别、发布时间
- 判断是否为强制性约束

**第二步：文档切分**
- 将文档切分为可回溯的证据片段
- 保留章节、页码、片段编号和顺序
- 生成 fragment 锚点

**第三步：对象抽取**
- 从文档中抽取六类关键对象：
  - 流程节点 (process_step)
  - 角色 (role)
  - 交付物/记录 (deliverable/record)
  - 法规条款 (regulation_clause)
  - 内部 PEP 节点 (pep_node)
  - 核心概念 (concept)

**第四步：关系建立**
- 建立对象之间的关系：
  - `requires`: 法规要求某个流程步骤
  - `produces`: 流程步骤产出某类记录
  - `responsible_for`: 角色负责某个步骤
  - `implements`: 内部流程实现法规要求
  - `references`: 解读材料解释法规要求
  - `constrains`: 风险管理约束设计开发活动

**第五步：生成审批包**
- 生成包含以下内容的审批包：
  - 文档身份识别结果
  - 抽取的关键对象
  - 建立的关键关系
  - 证据片段引用
  - 冲突检测
  - 需要人工确认的问题

**第六步：人工审批**
- 人工关口 1：确认文档身份和权威边界
- 人工关口 2：确认关键映射和高风险关系
- 审批通过后发布到 Wiki

#### 3.1.3 核心数据结构

```python
# 审批包 (ReviewPackage)
{
    "package_id": "review-doc-xxx",
    "document_id": "doc-xxx",
    "status": "pending_review",
    "document_identity": {
        "business_type": "regulation",
        "title": "GMP 法规 2024版",
        "version": "2024",
        "effective_level": "binding",
        "is_binding": True
    },
    "extracted_objects": [...],
    "extracted_relations": [...],
    "issues": [...],
    "human_questions": [...]
}
```

#### 3.1.4 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/agent/upload` | POST | 上传文档并触发摄入流程 |
| `/api/ingest/candidates` | GET | 获取候选页面列表 |
| `/api/ingest/review-packages` | GET | 获取审批包列表 |
| `/api/ingest/review-packages/{id}/decision` | POST | 提交身份审批决策 |
| `/api/ingest/review-packages/{id}/relations/decision` | POST | 提交关系审批决策 |
| `/api/ingest/candidates/{id}/approve` | POST | 批准候选页面 |
| `/api/ingest/candidates/{id}/reject` | POST | 拒绝候选页面 |

---

### 3.2 智能问答 (QueryAgent)

#### 3.2.1 功能概述

QueryAgent 基于索引召回的 Wiki 问答智能体，优先使用已批准的结构化知识回答用户问题。

#### 3.2.2 工作流程

1. **加载机器索引**：从 pages.jsonl 加载页面索引
2. **召回候选页面**：基于问题相关性召回 top-k 页面
3. **加载结构化关系**：从已批准的审批包中加载关系数据
4. **生成回答**：
   - 使用 LLM 基于召回内容生成回答
   - 或基于索引摘要生成确定性回答
5. **返回引用**：提供可追溯的来源引用

#### 3.2.3 核心特性

- **受控上下文**：只加载候选页面和必要来源片段，不加载全部 Wiki
- **结构化关系引用**：涉及映射关系的问题优先引用结构化关系
- **溯源支持**：回答包含可追溯的页面和 fragment 引用
- **归档功能**：支持将优质问答归档为 Wiki 页面

#### 3.2.4 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat/query` | POST | 提交问题获取回答 |
| `/chat/reindex` | POST | 重建索引 |

---

### 3.3 健康检查 (LintAgent)

#### 3.3.1 功能概述

LintAgent 负责维护 Wiki 健康，定期扫描并检测潜在问题。

#### 3.3.2 检查项

| 检查类型 | 说明 | 严重程度 |
|----------|------|----------|
| 矛盾检测 | 同一实体在不同页面的描述冲突 | High |
| 过时检测 | 基于更新日期检查页面新鲜度 | Medium |
| 孤儿页检测 | 没有入链的页面 | Low |
| 缺失引用检测 | 页面没有 source_refs | Medium |
| 断裂链接检测 | 指向不存在的页面 | Medium |

#### 3.3.3 工作流程

1. 加载所有 Wiki 页面
2. 执行各项检查
3. 可选：LLM 深度分析
4. 生成健康报告
5. 交互式修复（需人工确认）

#### 3.3.4 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/lint/scan` | POST | 运行健康检查 |

---

### 3.4 结构化知识处理

#### 3.4.1 映射矩阵生成

构建法规要求到内部流程的映射矩阵：

```python
{
    "requirement_name": "设计输入要求",
    "requirement_type": "regulation_clause",
    "mapped_process_steps": [...],
    "mapped_records": [...],
    "mapped_roles": [...],
    "evidence_refs": [...]
}
```

#### 3.4.2 Slides 大纲生成

基于已批准的知识生成演示文稿大纲：

1. 批准知识基线
2. 文档身份分布
3. 关键要求到流程映射
4. 记录与职责覆盖
5. 持续复核边界

#### 3.4.3 API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/exports/mapping-matrix` | GET | 导出映射矩阵 |
| `/api/exports/slides-outline` | GET | 导出 Slides 大纲 |

---

### 3.5 文档处理管道

#### 3.5.1 解析流程

```
Raw 文档 → 解析 → Canonical JSON → 存储
```

支持的格式：
- PDF
- DOCX
- PPTX
- XLSX

#### 3.5.2 Canonical Document 结构

```python
{
    "document": {
        "document_id": "...",
        "title": "...",
        "source_path": "...",
        "file_name": "...",
        "doc_type": "..."
    },
    "sections": [...],      # 章节结构
    "fragments": [...],     # 文本片段
    "tables": [...],        # 表格数据
    "figures": [...],       # 图片数据
    "terms": [...],         # 术语列表
    "entities": [...]       # 实体列表
}
```

---

## 4. Wiki 页面模型

### 4.1 页面类型

| 类型 | 用途 | 字段 |
|------|------|------|
| Overview | 主题或文档的综合概述 | title, summary, source_refs |
| Entity | 具体的人、组织、产品、法规 | name, entity_type, description |
| Concept | 抽象概念、方法论、原则 | term, definition, examples |
| Comparison | 对比两个或多个实体/概念 | subjects, dimensions, table |
| Index | 某类页面的目录和导航 | category, items |

### 4.2 页面结构

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

# 标题

## 摘要

## 业务章节

## 关联页面

## 引用来源
```

---

## 5. API 完整列表

### 5.1 系统接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/dashboard` | GET | 仪表板数据 |

### 5.2 摄入接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/agent/upload` | POST | 上传文档 |
| `/api/ingest/candidates` | GET | 候选页面列表 |
| `/api/ingest/review-packages` | GET | 审批包列表 |
| `/api/ingest/review-packages/{id}/decision` | POST | 身份审批 |
| `/api/ingest/review-packages/{id}/relations/decision` | POST | 关系审批 |
| `/api/ingest/candidates/{id}/approve` | POST | 批准候选 |
| `/api/ingest/candidates/{id}/reject` | POST | 拒绝候选 |

### 5.3 Wiki 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/wiki/pages` | GET | 页面列表 |

### 5.4 查询接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/chat/query` | POST | 智能问答 |
| `/chat/reindex` | POST | 重建索引 |

### 5.5 导出接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/exports/mapping-matrix` | GET | 映射矩阵 |
| `/api/exports/slides-outline` | GET | Slides 大纲 |

### 5.6 维护接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/lint/scan` | POST | 健康检查 |

---

## 6. 数据模型

### 6.1 SourceRef (来源引用)

```python
{
    "document_id": str,      # 文档ID（必填）
    "fragment_id": str,      # 片段ID
    "file_name": str,        # 文件名
    "anchor_label": str,     # 锚点标签
    "quote": str             # 引用内容
}
```

### 6.2 WikiPage (Wiki 页面)

```python
{
    "page_id": str,          # 页面ID
    "title": str,            # 标题
    "page_type": str,        # 页面类型
    "summary": str,          # 摘要
    "sections": [...],       # 章节列表
    "aliases": [...],        # 别名
    "source_refs": [...],    # 来源引用
    "linked_pages": [...],   # 关联页面
    "review_status": str,    # 审核状态
    "page_version": int,     # 版本号
    "updated_at": str        # 更新时间
}
```

### 6.3 ReviewPackage (审批包)

```python
{
    "package_id": str,                    # 审批包ID
    "document_id": str,                   # 文档ID
    "status": str,                        # 状态
    "document_identity": {...},           # 文档身份
    "identity_decision": str,             # 身份审批决策
    "confirmed_business_type": str,       # 确认的业务类型
    "confirmed_effective_level": str,     # 确认的效力级别
    "confirmed_is_binding": bool,         # 是否强制
    "review_notes": str,                  # 审批备注
    "reviewed_by": str,                   # 审批人
    "relation_decision": str,             # 关系审批决策
    "extracted_objects": [...],           # 抽取的对象
    "extracted_relations": [...],         # 抽取的关系
    "issues": [...],                      # 问题列表
    "human_questions": [...]              # 人工问题
}
```

### 6.4 ReviewObject (审查对象)

```python
{
    "object_id": str,         # 对象ID
    "object_type": str,       # 对象类型
    "name": str,              # 名称
    "evidence_refs": [...],   # 证据引用
    "confidence": float,      # 置信度
    "review_risk": str        # 审查风险
}
```

### 6.5 ReviewRelation (审查关系)

```python
{
    "relation_id": str,       # 关系ID
    "relation_type": str,     # 关系类型
    "from_object_id": str,    # 源对象ID
    "to_object_id": str,      # 目标对象ID
    "claim_type": str,        # 声明类型
    "direction": str,         # 方向
    "evidence_refs": [...],   # 证据引用
    "confidence": float,      # 置信度
    "human_required": bool    # 是否需要人工确认
}
```

---

## 7. 人机协作模式

### 7.1 AI 自动处理的内容

- 章节切分
- 页码和 fragment 锚点生成
- 明显的流程/角色/记录名称抽取
- 初步相关链接
- 别名建议
- 缺口提醒

### 7.2 AI 生成候选 + 人工抽审

- 流程节点拆分
- 交付物识别
- 核心概念提取

### 7.3 必须人工确认的内容

- 文档身份和权威边界
- 法规与内部文档之间的多对多映射
- 高风险对象合并
- 高风险关系和结论边界

---

## 8. 溯源规则

### 8.1 引用要求

- 每个事实性结论必须能追溯到至少一个 `source_ref`
- `source_ref` 至少包含 `document_id`
- 正式页面应优先包含 `fragment_id`、`file_name`、`anchor_label` 和短摘录 `quote`

### 8.2 引用格式

页面正文可以使用脚注给人阅读，frontmatter 和 section `source_refs` 给程序读取。

---

## 9. 运行方式

### 9.1 启动 API 服务

```bash
uvicorn App.api:app --reload
```

### 9.2 运行智能体

```bash
# IngestAgent 交互模式
python -m App.agents.ingest_agent

# QueryAgent 交互模式
python -m App.agents.query_agent

# LintAgent 健康检查
python -m App.agents.lint_agent

# LintAgent 修复
python -m App.agents.lint_agent fix
```

### 9.3 处理管道

```bash
# 摄入文档
python -m Tool.pipelines.ingest --input <path>

# 解析文档
python -m Tool.pipelines.parse --document-id <id>
```

---

## 10. 与 Design.md 的对应关系

| Design.md 要求 | 实现功能 |
|----------------|----------|
| 6 步首次上传流程 | IngestAgent 完整实现 |
| 文档身份识别 | DocumentIdentity + 人工审批关口 |
| 证据片段切分 | CanonicalDocument.fragments |
| 六类对象抽取 | ReviewObject (process_step/role/deliverable/regulation_clause/pep_node/concept) |
| 关系建立 | ReviewRelation (requires/produces/responsible_for/implements/references/constrains) |
| 审批包机制 | ReviewPackage + 双关口审批 |
| 人工关口 1 | `/api/ingest/review-packages/{id}/decision` |
| 人工关口 2 | `/api/ingest/review-packages/{id}/relations/decision` |
| 问答溯源 | QueryAgent 返回 citations |
| 映射矩阵 | `/api/exports/mapping-matrix` |
| Slides 生成 | `/api/exports/slides-outline` |
| 健康检查 | LintAgent 5 项检查 |
