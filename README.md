# QT Wiki

QT Wiki 是一个面向企业知识沉淀的分层 Wiki 系统。它不是“上传文件后直接生成页面”，而是先把文档拆成可追溯证据、对象和关系，经过人工关口确认后，再发布到 Wiki 并供 Query、映射和 slides 导出复用。

当前实现已经落地以下主线：

- Ingest 审批包工作流
- 双关口发布控制
- Query 基于已批准结构化知识回答
- 映射矩阵与 slides 提纲导出
- Lint 健康检查

## 架构

```text
Schema 层 (AGENTS.md)
    ↓ 定义结构与 Agent 规则
Index 层 (wiki/output/index/*)
    ↓ 召回候选页面
Wiki 层 (Obsidian Markdown + pages/*.json)
    ↓ 引用 fragment/source_refs
Parsed 层 (Tool/output/parsed/*.json)
    ↓ sections / fragments / anchors
Raw 层 (Raw/* 原始文档)
```

- `Raw`：原始 `docx/pdf/pptx/xlsx`
- `Parsed`：规范化 Canonical JSON
- `Wiki`：正式页面 Markdown + JSON 兼容缓存
- `Index`：Query 使用的机器索引
- `Schema`：页面类型、关系、Agent 行为边界

## 当前功能

### 1. IngestAgent

文档摄入已经从“直接生成候选页”升级为“审批包 + 候选页”双产物。

当前能力：

- 读取 Raw 文档并生成 Parsed Canonical JSON
- 识别文档身份：
  - `external_mandatory`
  - `external_reference`
  - `internal_controlled`
  - `runtime_evidence`
  - `feedback`
  - `unknown`
- 生成审批包 `ReviewPackage`
- 抽取最小对象：
  - `requirement`
  - `process_step`
  - `record`
  - `role`
- 抽取最小关系：
  - `requires`
  - `produces`
  - `responsible_for`
- LLM 失败时自动回退到规则抽取
- 同时生成候选 Wiki 页面

审批包会输出到：

- `wiki/output/review_packages/*.json`
- `wiki/output/obsidian/ReviewPackages/*.md`

候选页会输出到：

- `App/candidates/*.json`
- `wiki/output/obsidian/Proposals/*.md`

### 2. 双关口发布

当前发布不是直接批准候选页，而是必须先通过审批包关口。

#### 关口 1：文档身份确认

需要人工确认：

- 这份文档是什么类型
- 它是不是强约束材料
- 它的效力层级和使用边界

接口：

- `POST /api/ingest/review-packages/{package_id}/decision`

#### 关口 2：关键关系确认

如果审批包中存在抽取关系，则需要人工确认关键映射关系是否成立。

接口：

- `POST /api/ingest/review-packages/{package_id}/relations/decision`

#### 发布约束

候选页只有在以下条件满足时才允许发布：

1. `identity_decision == confirmed`
2. 且满足下列之一：
   - `relation_decision == confirmed`
   - `relation_decision == not_applicable`
   - 审批包本身没有抽取关系

候选页发布接口：

- `POST /api/ingest/candidates/{candidate_id}/approve`
- `POST /api/ingest/candidates/{candidate_id}/reject`

### 3. QueryAgent

Query 已经不只依赖 Wiki 摘要页。

当前回答会组合两类上下文：

- Index 召回到的少量 Wiki 页面
- 已批准审批包中的结构化对象和关系

当前能力：

- 只加载少量命中页面，不默认读全量 Wiki
- 读取已批准审批包中的对象/关系
- 对映射类问题优先使用结构化关系
- 返回可追溯 citations
- 返回命中的结构化审批包 `structured_matches`
- 支持问答归档为 `qa` 页面

接口：

- `POST /chat/query`
- `POST /chat/reindex`

### 4. 导出

当前已经落地两类导出，且都只消费“已批准审批包”，不重新回到 Raw 现总结。

#### 映射矩阵

接口：

- `GET /api/exports/mapping-matrix`

输出内容：

- requirement 到 process_step 的映射
- 对应 records
- 对应 roles
- 证据引用

#### Slides 提纲

接口：

- `GET /api/exports/slides-outline`

输出内容：

- 批准知识基线
- 文档身份分布
- 关键要求到流程映射
- 记录与职责覆盖
- 持续复核边界

### 5. LintAgent

当前健康检查能力：

- 矛盾检测
- 过时检测
- 孤儿页检测
- 缺失引用检测
- 断裂链接检测
- 可选 LLM 深度分析建议

接口：

- `POST /api/lint/scan`

## 目录结构

```text
QT-wiki/
├── AGENTS.md
├── CHANGELOG.md
├── Design.md
├── README.md
├── Raw/
├── Tool/
│   ├── document_processor.py
│   ├── contracts/
│   ├── llm/
│   ├── parsers/
│   └── pipelines/
├── wiki/
│   ├── builders/
│   ├── indexing/
│   ├── models/
│   ├── output/
│   │   ├── index/
│   │   ├── obsidian/
│   │   │   ├── Pages/
│   │   │   ├── Proposals/
│   │   │   └── ReviewPackages/
│   │   ├── pages/
│   │   └── review_packages/
│   └── store/
├── App/
│   ├── agents/
│   │   ├── ingest_agent.py
│   │   ├── query_agent.py
│   │   ├── lint_agent.py
│   │   └── structured_knowledge.py
│   ├── api.py
│   ├── candidates/
│   └── web/
└── tests/
```

## 安装

### Python

建议至少安装这些依赖：

```bash
pip install fastapi uvicorn python-multipart pytest pypdf requests openpyxl
```

如果项目里还有其他解析器依赖，按本地实际环境补齐。

### 前端

```bash
cd App/web
npm install
```

## LLM 配置

默认配置文件：

- `config/azure_gpt4o_config.json`

可通过环境变量覆盖：

- `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_ENDPOINT`
- `AZURE_OPENAI_DEPLOYMENT`
- `LLM_PROVIDER`
- `LLM_API_KEY`
- `LLM_BASE_URL`
- `LLM_MODEL`

注意：

- 当前系统要求“有 LLM 更好，没有 LLM 也能走规则回退”
- 对象和关系最小抽取、审批包产出、基础导出不依赖网络可继续工作

## 启动方式

### 启动后端 API

在仓库根目录执行：

```bash
python -m uvicorn App.api:app --host 127.0.0.1 --port 8000
```

健康检查：

```bash
GET http://127.0.0.1:8000/health
```

### 启动前端控制台

```bash
cd App/web
npm run dev
```

默认地址：

- `http://127.0.0.1:5173/`

前端已配置代理到 `127.0.0.1:8000`。

## 使用方法

### 路径 A：通过前端控制台使用

这是当前最完整的使用方式。

#### 1. 上传文档

进入 `Ingest` 页面，上传 `docx/pdf/pptx/xlsx`。

系统会自动：

- 保存 Raw
- 解析为 Parsed
- 生成审批包
- 生成候选页

#### 2. 审核审批包

先看审批包里的：

- 文档身份
- 风险与缺口
- 抽取对象
- 抽取关系

然后依次完成：

1. 文档身份确认
2. 关键关系确认

#### 3. 发布候选页

只有审批包双关口通过后，关联候选页才允许发布到 Wiki。

发布后会写入：

- `wiki/output/pages/*.json`
- `wiki/output/obsidian/Pages/*.md`

同时索引会被重建。

#### 4. 查询

进入 `Query` 页面提问。

适合问：

- 某条要求对应哪些流程步骤
- 某个步骤产出哪些记录
- 某个角色负责哪些步骤
- 某个主题的 Wiki 已有结论和证据是什么

返回会包含：

- answer
- matched_pages
- citations
- structured_matches
- trace

#### 5. 导出

进入 `Settings` 页面，可以直接拉取：

- 映射矩阵
- slides 提纲

这两类导出都基于已批准审批包。

### 路径 B：直接调用 API

#### 上传文档

```bash
POST /agent/upload
form-data:
  file=<binary>
  use_llm=false
```

#### 查看审批包

```bash
GET /api/ingest/review-packages
```

#### 确认文档身份

```bash
POST /api/ingest/review-packages/{package_id}/decision
{
  "identity_decision": "confirmed",
  "confirmed_business_type": "external_mandatory",
  "confirmed_effective_level": "external_mandatory",
  "confirmed_is_binding": true,
  "review_notes": "作为正式要求使用",
  "reviewed_by": "qa.lead"
}
```

#### 确认关键关系

```bash
POST /api/ingest/review-packages/{package_id}/relations/decision
{
  "relation_decision": "confirmed",
  "relation_review_notes": "关键关系成立",
  "relation_reviewed_by": "qa.lead"
}
```

#### 发布候选页

```bash
POST /api/ingest/candidates/{candidate_id}/approve
```

#### 查询

```bash
POST /chat/query
{
  "question": "设计开发要求对应哪些流程步骤？",
  "use_llm": false,
  "top_k_pages": 5,
  "top_k_citations": 8
}
```

#### 导出映射矩阵

```bash
GET /api/exports/mapping-matrix
```

#### 导出 slides 提纲

```bash
GET /api/exports/slides-outline
```

### 路径 C：命令行 Agent

#### IngestAgent

```bash
python -m App.agents.ingest_agent
python -m App.agents.ingest_agent list
python -m App.agents.ingest_agent ingest <document_id>
python -m App.agents.ingest_agent approve <candidate_id>
python -m App.agents.ingest_agent reject <candidate_id> [reason]
```

#### QueryAgent

```bash
python -m App.agents.query_agent
python -m App.agents.query_agent "什么是质量管理体系？"
```

#### LintAgent

```bash
python -m App.agents.lint_agent
python -m App.agents.lint_agent fix
python -m App.agents.lint_agent fix --dry-run
```

## 关键输出目录

- `Raw/`：原始文档
- `Tool/output/parsed/`：Parsed Canonical JSON
- `wiki/output/review_packages/`：审批包 JSON
- `wiki/output/obsidian/ReviewPackages/`：审批包 Markdown
- `App/candidates/`：候选页 JSON
- `wiki/output/obsidian/Proposals/`：候选页 Markdown
- `wiki/output/pages/`：正式 Wiki JSON
- `wiki/output/obsidian/Pages/`：正式 Wiki Markdown
- `wiki/output/index/`：Query 机器索引

## 当前验证

当前和本轮功能直接相关的验证结果：

```bash
pytest -q tests/test_review_package.py tests/test_app_api.py
```

结果：

- `15 passed`

前端检查：

```bash
cd App/web
npx tsc --noEmit
```

结果：

- 通过

## 已知边界

- 结构化关系当前还是“最小闭环”，关系类型主要覆盖 `requires / produces / responsible_for`
- 跨文档高风险对象合并还没有做成完整人工工作台
- slides 目前输出的是结构化提纲，不是 `.pptx`
- Query 已能消费审批包结构化知识，但复杂推理质量仍取决于审批包质量和来源覆盖

## 相关文档

- 架构与行为约束：[`AGENTS.md`](AGENTS.md)
- 设计目标：[`Design.md`](Design.md)
- 变更记录：[`CHANGELOG.md`](CHANGELOG.md)
