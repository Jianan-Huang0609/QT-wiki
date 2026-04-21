# QT Wiki 使用文档

## 项目简介

QT Wiki 是一个基于 LLM Wiki 范式的企业知识库系统，采用三层架构：

- **Raw 层**：原文档（文章/论文/数据）
- **Wiki 层**：结构化知识（摘要页/实体页/概念页/比较页/索引）
- **Schema 层**：知识结构和智能体行为定义（`Agents.md`）

**核心操作**：`Ingest 摄入` → `Query 查询` → `Lint 维护`

---

## 架构设计

```
Schema 层 (Agents.md)
    ↓ 定义结构
Wiki 层 (摘要/实体/概念/比较/Index)
    ↓ 引用来源
Raw 层 (原文档)
```

### 页面类型

| 类型 | 用途 | 示例 |
|------|------|------|
| **摘要页** (overview) | 对主题或文档的综合概述 | "医疗器械 GMP 规范 - 摘要" |
| **实体页** (entity) | 具体的人、组织、产品、法规 | "GMP 法规 2024版" |
| **概念页** (concept) | 抽象概念、方法论、原则 | "风险管理", "CAPA" |
| **比较页** (comparison) | 对比两个或多个实体/概念 | "GMP vs ISO 13485" |
| **索引页** (index) | 某类页面的目录和导航 | "所有法规实体索引" |
| **问答页** (qa) | 优质问答的归档 | "Q: 什么是 CAPA?" |

---

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install pytest pypdf requests
```

### 2. 配置 LLM

编辑 `config/azure_gpt4o_config.json`：

```json
{
  "provider": "azure_openai",
  "azure_api_key": "your-api-key",
  "azure_endpoint": "https://your-endpoint.com",
  "azure_deployment": "gpt-4o",
  "model": "gpt-4o"
}
```

---

## 三大核心操作

### 一、Ingest 摄入

将原文档转换为 Wiki 页面，**包含人工讨论环节**。

```bash
# 1. 文档入库（解析原文档）
python -m Tool.pipelines.ingest --input Raw/
python -m Tool.pipelines.parse --document-id doc-xxx

# 2. IngestAgent 分析文档，生成候选页面
python -m App.agents.ingest_agent ingest doc-xxx

# 3. 查看候选页面（人工讨论）
python -m App.agents.ingest_agent list

# 4. 人工确认候选
python -m App.agents.ingest_agent approve <candidate_id>

# 5. 或拒绝候选
python -m App.agents.ingest_agent reject <candidate_id> "原因说明"
```

**工作流**：
1. LLM 读取原文档
2. 提取关键信息（实体、概念、摘要）
3. 生成候选页面保存到 `App/candidates/`
4. **暂停，等待人工讨论和确认**
5. 根据确认结果写入 Wiki

---

### 二、Query 查询

向 Wiki 提问，获取综合回答，**可归档优质回答**。

```bash
# 交互式查询模式
python -m App.agents.query_agent

# 或单次查询
python -m App.agents.query_agent "什么是 CAPA?"
```

**交互模式命令**：
- 输入问题 → 获取回答
- 输入 `archive <标题>` → 将最后回答归档为 Wiki 页面
- 输入 `quit` → 退出

**工作流**：
1. 理解用户问题
2. 搜索 Wiki 和 Raw
3. 综合信息生成回答（带引用来源）
4. **询问用户是否将好答案归档为 Wiki 页面**

---

### 三、Lint 维护

定期健康检查，**生成报告并建议修复**。

```bash
# 运行完整健康检查
python -m App.agents.lint_agent

# 修复可自动修复的问题
python -m App.agents.lint_agent fix

# 试运行修复（不实际修改）
python -m App.agents.lint_agent fix --dry-run
```

**检查项**：
- **矛盾检测**：同一实体在不同页面的描述冲突
- **过时检测**：页面超过 90 天未更新
- **孤儿页**：没有入链的页面
- **缺失引用**：页面没有 source_refs
- **断裂链接**：指向不存在的页面

**工作流**：
1. 定期扫描全部页面
2. 生成健康报告
3. LLM 提出修复建议和新问题
4. **等待人工确认后执行修复**

---

## 完整流程示例

### 首次构建知识库

```bash
# 1. 准备原文档
# 将 .docx / .pdf 文件放入 Raw/ 目录

# 2. 文档入库和解析
python -m Tool.pipelines.ingest --input Raw/
python -m Tool.pipelines.parse --document-id doc-xxx

# 3. IngestAgent 分析（生成候选）
python -m App.agents.ingest_agent ingest doc-xxx

# 4. 人工确认候选页面
python -m App.agents.ingest_agent list
python -m App.agents.ingest_agent approve candidate-xxxxx

# 5. 同步到 Obsidian 查看
python scripts/json_to_obsidian.py
# 在 Obsidian 中打开 ObsidianVault 文件夹
```

### 日常查询和归档

```bash
# 启动交互式查询
python -m App.agents.query_agent

# [Q] 什么是风险管理?
# [A] (置信度: 0.85)
#     基于 Wiki 中的 3 个页面和 2 个原文档...
# [提示] 输入 'archive <标题>' 将此回答归档为 Wiki 页面

# [Q] archive 风险管理概述
# [QueryAgent] 已归档为 Wiki 页面: risk-management-overview

# [Q] quit
```

### 定期维护

```bash
# 运行健康检查
python -m App.agents.lint_agent

# 查看报告后，修复断裂链接
python -m App.agents.lint_agent fix

# 根据 LLM 建议，创建缺失的索引页
python -m App.agents.query_agent
# [Q] 请总结所有实体页面
# [Q] archive 实体索引
```

---

## 目录结构

```
QT-wiki/
├── Agents.md                     # Schema 层：知识结构和智能体定义
├── USAGE.md                      # 本文档
│
├── Raw/                          # Raw 层：原文档
│   ├── manifests/                # 文档元数据
│   └── *.docx, *.pdf            # 原始文件
│
├── Tool/                         # Tool 层：LLM 可调用的工具集
│   ├── llm/                      # LLM 调用
│   ├── parsers/                  # 文档解析器
│   ├── normalizers/              # 文本清洗
│   ├── contracts/                # 数据契约
│   └── pipelines/                # 处理流程
│
├── wiki/                         # Wiki 层：知识页面
│   ├── models/                   # 数据模型
│   ├── builders/                 # 页面构建
│   ├── updaters/                 # 增量更新
│   ├── store/                    # 存储管理
│   └── output/                   # 页面输出
│       ├── pages/               # Wiki 页面
│       └── proposals/           # 更新提案
│
├── App/                          # App 层：智能体
│   ├── agents/                   # 三大智能体
│   │   ├── ingest_agent.py      # IngestAgent
│   │   ├── query_agent.py       # QueryAgent
│   │   └── lint_agent.py        # LintAgent
│   └── candidates/              # 候选页面（人工确认前）
│
├── ObsidianVault/                # Obsidian 仓库
│   └── Wiki/                    # Markdown 页面
│
├── scripts/                      # 工具脚本
│   └── json_to_obsidian.py      # 同步到 Obsidian
│
├── tests/                        # 测试套件
└── config/                       # 配置文件
```

---

## 命令速查表

### Ingest 操作

| 命令 | 功能 |
|------|------|
| `python -m Tool.pipelines.ingest --input Raw/` | 文档入库 |
| `python -m Tool.pipelines.parse --document-id <id>` | 文档解析 |
| `python -m App.agents.ingest_agent ingest <doc_id>` | 生成候选页面 |
| `python -m App.agents.ingest_agent list` | 列出候选 |
| `python -m App.agents.ingest_agent approve <id>` | 批准候选 |
| `python -m App.agents.ingest_agent reject <id>` | 拒绝候选 |

### Query 操作

| 命令 | 功能 |
|------|------|
| `python -m App.agents.query_agent` | 交互式查询 |
| `python -m App.agents.query_agent "问题"` | 单次查询 |

### Lint 操作

| 命令 | 功能 |
|------|------|
| `python -m App.agents.lint_agent` | 健康检查 |
| `python -m App.agents.lint_agent fix` | 修复问题 |
| `python -m App.agents.lint_agent fix --dry-run` | 试运行修复 |

### 同步操作

| 命令 | 功能 |
|------|------|
| `python scripts/json_to_obsidian.py` | 同步到 Obsidian |

---

## 关键设计原则

1. **人机协作**：Ingest 和 Lint 的关键操作需要人工确认
2. **渐进构建**：通过 Query 将优质回答归档，不断丰富 Wiki
3. **Schema 演化**：`Agents.md` 由开发者和 LLM 共同维护
4. **可追溯性**：所有 Wiki 页面必须引用 Raw 来源
5. **持续维护**：定期运行 Lint 保持 Wiki 健康

---

## 测试验证

```bash
# 运行全部测试
python -m pytest tests/ -v
```

---

## 更多信息

- Schema 定义: [Agents.md](Agents.md)
- 架构说明: [README.md](README.md)
- App 层设计: [App/README.md](App/README.md)
