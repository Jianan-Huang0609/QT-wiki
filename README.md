# QT Wiki

QT Wiki 是一个基于 LLM Wiki 范式的企业知识库系统，采用三层架构（Raw/Wiki/Schema），通过三个核心 Agent（Ingest/Query/Lint）实现文档摄入、知识查询和系统维护。

## 架构概述

```
Schema 层 (AGENTS.md)
    ↓ 定义结构
Wiki 层 (pages/*.json)
    ↓ 引用来源
Raw 层 (原始文档)
```

- **Raw 层**：原始文档（docx/pdf/pptx/xlsx）和 manifest
- **Wiki 层**：结构化知识页面（overview/entity/concept/comparison/index/qa）
- **Schema 层**：知识结构和智能体行为定义（`AGENTS.md`）

## 当前真实功能

### 1. 文档处理工具
- `Tool.document_processor`：统一的文档处理接口，将 Raw 文档解析为 LLM 可用的结构化内容

### 2. 三大核心 Agent

#### IngestAgent - 文档摄入
- **交互式工作流**：自动发现待处理文档，批量处理，交互式审批
- **智能页面生成**：使用 LLM 分析文档内容，自动生成候选 Wiki 页面
- **人工确认机制**：候选页面需人工批准后才写入 Wiki
- **自动索引更新**：批准页面后自动更新对应类型的索引

#### QueryAgent - 知识查询
- **全量 Wiki 检索**：将整个 Wiki 传给 LLM，由 LLM 自主决定检索内容
- **智能回答生成**：基于完整 Wiki 内容生成准确回答
- **自动归档**：优质问答可归档为新的 Wiki 页面

#### LintAgent - 系统维护
- **健康检查**：检测矛盾、过时页面、孤儿页、缺失引用、断裂链接
- **LLM 深度分析**：使用 LLM 发现潜在问题并提出建议
- **交互式修复**：人工确认后执行修复操作

### 3. 底层工具（保留但非主线）
- `Tool.pipelines.ingest`：文档入库
- `Tool.pipelines.parse`：文档解析
- `wiki.builders.bootstrap`：首次建库
- `wiki.updaters.incremental`：增量更新
- `wiki.updaters.conflict_scan`：冲突扫描
- `wiki.updaters.publish`：页面发布

## 数据流

```text
Raw/ 原始文件
  -> Tool.document_processor 解析
  -> IngestAgent 分析生成候选
  -> 人工审批
  -> wiki/output/pages/*.json
  -> QueryAgent 全量检索回答
```

## 目录结构

```text
QT-wiki/
├── AGENTS.md              # Schema 层定义
├── README.md              # 本文件
├── USAGE.md               # 使用文档
├── Raw/                   # 原始文档
│   ├── manifests/         # 文档清单
│   └── *.docx / *.pdf / *.pptx / *.xlsx
├── Tool/                  # 工具层
│   ├── document_processor.py  # 统一文档处理
│   ├── contracts/         # 数据契约
│   ├── llm/              # LLM 客户端
│   ├── parsers/          # 文档解析器
│   └── pipelines/        # 处理管道
├── wiki/                  # Wiki 层
│   ├── builders/         # 页面构建
│   ├── models/           # 数据模型
│   ├── output/pages/     # Wiki 页面
│   ├── store/            # 存储接口
│   └── updaters/         # 更新器
├── App/                   # Agent 层
│   └── agents/           # 三大智能体
│       ├── ingest_agent.py
│       ├── query_agent.py
│       └── lint_agent.py
└── tests/                 # 测试
```

## 安装

```bash
pip install pytest pypdf requests openpyxl
```

## LLM 配置

默认配置文件：`config/azure_gpt4o_config.json`

可通过环境变量覆盖：
- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `LLM_PROVIDER`, `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL`

## 快速开始

### 1. 文档摄入（交互式）

```bash
python -m App.agents.ingest_agent
```

流程：
1. 自动发现 `Raw/` 目录下的待处理文档
2. 选择要处理的文档（支持批量）
3. LLM 分析生成候选页面
4. 交互式审批候选（批准/拒绝/跳过）

### 2. 知识查询（交互式）

```bash
python -m App.agents.query_agent
```

流程：
1. 加载整个 Wiki 知识库
2. 输入问题
3. LLM 基于完整 Wiki 内容回答
4. 优质回答可归档为新的 Wiki 页面

### 3. 系统维护

```bash
python -m App.agents.lint_agent
```

## 命令参考

### IngestAgent

```bash
# 交互式工作流（推荐）
python -m App.agents.ingest_agent

# 非交互式（指定文档）
python -m App.agents.ingest_agent ingest <document_id>
python -m App.agents.ingest_agent list
python -m App.agents.ingest_agent approve <candidate_id>
python -m App.agents.ingent_agent reject <candidate_id> [原因]
```

### QueryAgent

```bash
# 交互式查询
python -m App.agents.query_agent

# 单次查询
python -m App.agents.query_agent "什么是质量管理体系？"
```

### LintAgent

```bash
# 运行健康检查
python -m App.agents.lint_agent

# 修复问题
python -m App.agents.lint_agent fix
python -m App.agents.lint_agent fix --dry-run
```

## 核心特性

### IngestAgent
- ✅ 自动发现待处理文档
- ✅ 交互式文档选择
- ✅ LLM 智能分析生成候选
- ✅ 人工确认机制
- ✅ 自动更新索引

### QueryAgent
- ✅ 全量 Wiki 加载
- ✅ LLM 自主检索
- ✅ 语义理解（非字面匹配）
- ✅ 回答归档功能

### LintAgent
- ✅ 矛盾检测
- ✅ 过时检测
- ✅ 孤儿页检测
- ✅ 缺失引用检测
- ✅ 断裂链接检测
- ✅ LLM 深度分析建议

## 页面类型

- **overview**：摘要页，对主题的综合概述
- **entity**：实体页，具体的人、组织、产品、法规等
- **concept**：概念页，抽象概念、方法论、原则
- **comparison**：比较页，对比两个或多个实体/概念
- **index**：索引页，某类页面的目录和导航
- **qa**：问答页，归档的优质问答

## 输出目录

- `Raw/manifests/`：文档 manifest
- `Tool/output/parsed/`：规范化解析结果
- `wiki/output/pages/`：Wiki 页面 JSON
- `App/candidates/`：候选页面（待审批）

## 验证

```bash
python -m pytest -q
```

当前测试：53 passed

## 相关文档

- 架构定义：[`AGENTS.md`](AGENTS.md)
- 使用说明：[`USAGE.md`](USAGE.md)
