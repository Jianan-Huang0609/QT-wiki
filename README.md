# QT Wiki

一个面向企业制度/质量体系文档的 Wiki 自动维护项目。当前仓库有两条主线能力：

1. `Agent`：把上传到 `Raw/` 的文档自动入库、解析、建库/增量更新、审核、发布、导出
2. `Chatbot`：基于已发布 Wiki 页面和原始证据片段做检索问答，并返回引用来源

## 现在这个项目怎么工作

项目的核心不是“把文档直接丢给大模型问答”，而是先把文档沉淀成可维护的 Wiki，再让问答建立在 Wiki 和原始证据之上。

完整链路：

1. 用户上传文件到 `Raw/`
2. `App.agent` 调用 `Tool/` 下的入库与解析工具
3. 解析结果写入 `Tool/output/parsed/`
4. `App.agent_graph` 编排建库或增量更新流程
5. `wiki.review` 判断哪些变更可以自动推进，哪些必须人工审核
6. 已发布页面写入 `wiki/output/pages/`，待审核提案写入 `wiki/output/proposals/`
7. 已发布页面导出到 `wiki/output/obsidian/`
8. `App.chat` / `App.api` 基于已发布页面和原始片段做检索问答

## 目录结构

### 根目录

- `App/`: 应用入口。包含 Agent、Chatbot、API、前端页面
- `Tool/`: 文档工具层。包含入库、解析、标准化、LLM 客户端
- `wiki/`: Wiki 领域层。包含页面模型、建库器、更新器、审核器、导出器、索引器
- `Raw/`: 原始上传文件目录，也是 Agent 默认扫描入口
- `config/`: 大模型配置文件
- `tests/`: 测试
- `.obsidian/`: 本地 Obsidian 配置

### App/

- `App/agent.py`: Agent 主入口。负责入库、解析、调度、状态持久化
- `App/agent_graph.py`: Agent 工作流编排。优先用 `LangGraph`，否则回退内置顺序流程
- `App/api.py`: FastAPI 服务。提供聊天、上传、待审提案、批准提案接口
- `App/chat.py`: Chatbot 编排层。负责本地检索、拼装引用、可选调用 LLM 生成最终回答
- `App/web/`: 前端页面与静态资源
- `App/output/agent_state.json`: Agent 文档维护状态
- `App/output/runs/`: 每次 Agent 运行摘要

### Tool/

- `Tool/pipelines/ingest.py`: 扫描 `Raw/` 并生成 manifest
- `Tool/pipelines/parse.py`: 根据文档类型调用解析器
- `Tool/parsers/`: 各文件类型解析器，当前支持 `docx/pdf/pptx/xlsx`
- `Tool/contracts/canonical.py`: 统一解析结果结构
- `Tool/llm/client.py`: 大模型调用客户端
- `Tool/output/parsed/`: 规范化后的解析结果

### wiki/

- `wiki/models/page.py`: `WikiPage`、`UpdateProposal` 等核心模型
- `wiki/builders/bootstrap.py`: 首次建库候选页面生成
- `wiki/updaters/incremental.py`: 增量候选变更生成
- `wiki/review.py`: 审核闸门。决定自动发布还是人工审核
- `wiki/updaters/conflict_scan.py`: 冲突扫描
- `wiki/updaters/review_publish.py`: 人工批准提案并发布
- `wiki/store/files.py`: 页面、提案、输出文件读写
- `wiki/exporters/obsidian.py`: 导出 Obsidian Markdown
- `wiki/index/local.py`: 本地检索索引
- `wiki/output/pages/`: 已落盘页面 JSON
- `wiki/output/proposals/`: 待审核或已发布提案 JSON
- `wiki/output/obsidian/`: 导出的 Markdown 页面

## Agent 用法

### 最常用命令

默认扫描 `Raw/` 并执行一次完整维护：

```bash
python -m App.agent
```

启用 LLM 参与摘要和审核：

```bash
python -m App.agent --use-llm
```

强制重跑解析和维护：

```bash
python -m App.agent --force-reparse --force-reconcile
```

清空输出后干净重建：

```bash
python -m App.agent --clean-rebuild
```

强制所有小改动也进入人工审核：

```bash
python -m App.agent --no-auto-approve-small-changes
```

指定使用 LangGraph：

```bash
python -m App.agent --workflow-engine langgraph
```

打开详细日志：

```bash
python -m App.agent --log-level DEBUG
```

### Agent 参数说明

- `--input`: 输入文件或目录，默认是 `Raw/`
- `--use-llm`: 启用大模型参与摘要生成和审核判断
- `--force-reparse`: 即使已有解析结果，也重新解析
- `--force-reconcile`: 即使文档 checksum 未变化，也重新执行 Wiki 维护
- `--clean-rebuild`: 清空页面和提案输出后重建
- `--no-auto-publish-low-risk`: 低风险变更不自动发布
- `--no-auto-approve-small-changes`: 小范围低风险变更也必须人工审核
- `--workflow-engine auto|langgraph|builtin`: 指定工作流引擎
- `--skip-conflict-scan`: 跳过冲突扫描
- `--skip-sync`: 跳过 Obsidian 导出
- `--state-path`: 指定 Agent 状态文件路径
- `--log-level`: 日志级别

### Agent 默认行为

`App.agent` 每次运行会做这些事：

1. 清理 Office 临时文件残留
2. 扫描 `Raw/` 并生成/更新 manifest
3. 解析尚未解析的文档
4. 如果还没有 Wiki 页面，则执行首次建库
5. 如果已有 Wiki 页面，则对变更文档执行增量维护
6. 进入审核闸门
7. 自动发布可以放行的页面
8. 生成待人工审核提案
9. 执行冲突扫描
10. 导出 Markdown 到 `wiki/output/obsidian/`
11. 记录运行摘要到 `App/output/runs/`

## Agent 审核机制

当前 Agent 不是直接改 Wiki，而是先生成候选变更，再审核：

1. 候选页面或候选增量变更生成
2. `wiki.review` 做规则审核
3. 如果开启 `--use-llm`，再叠加 LLM 审核意见
4. 两边结果保守合并
5. 自动通过的变更直接发布
6. 其余变更写入 proposal，等待人工审核

### 默认会进入人工审核的情况

- 首次建库页面
- `policy` / 制度类文档带来的变更
- 明显规范性内容，如“应当 / 必须 / 不得 / 禁止”
- 证据较多、文本较长、范围较大的改动

### 人工审核怎么做

命令行：

```bash
python -m wiki.updaters.review_publish --proposal-id <proposal_id>
python -m wiki.updaters.review_publish --approve-all
```

API：

```bash
curl http://127.0.0.1:8000/agent/proposals/pending
curl -X POST http://127.0.0.1:8000/agent/proposals/<proposal_id>/approve
curl -X POST http://127.0.0.1:8000/agent/proposals/approve-all
```

前端页面右侧也有“待审核提案”面板，可以直接查看：

- 提案原因
- 审核理由
- 来源文档
- `tool_trace`
- 候选内容
- 一键批准发布

## 是否使用大语言模型

用了，但默认不启用。

当前 LLM 主要参与两个地方：

1. Wiki 建库/更新时生成摘要和辅助审核
2. Chatbot 在已检索到页面与证据后生成最终回答

默认情况下：

- `python -m App.agent` 不会调用 LLM
- `/chat/query` 里如果 `use_llm=false`，也不会调用 LLM

只有显式开启后，系统才会读取 `config/azure_gpt4o_config.json` 发起模型调用。

## API 用法

启动 API 与前端：

```bash
python -m App.api
```

启动后访问：

- 前端首页：`http://127.0.0.1:8000/`
- 健康检查：`http://127.0.0.1:8000/health`

### 1. 聊天接口

```bash
curl -X POST http://127.0.0.1:8000/chat/query \
  -H "Content-Type: application/json" \
  -d '{
    "question": "文件控制和电子记录有哪些要求？",
    "use_llm": false,
    "top_k_pages": 5,
    "top_k_citations": 8
  }'
```

返回字段：

- `answer`
- `citations`
- `matched_pages`
- `confidence`
- `used_llm`
- `question`

### 2. 上传并自动维护 Wiki

```bash
curl -X POST http://127.0.0.1:8000/agent/upload \
  -F "file=@./sample.pdf" \
  -F "use_llm=false" \
  -F "auto_publish_low_risk=true" \
  -F "auto_approve_small_changes=true" \
  -F "workflow_engine=langgraph"
```

返回字段：

- `status`
- `file_name`
- `stored_path`
- `run_id`
- `manifests_seen`
- `documents_parsed`
- `proposals_created`
- `pages_published`
- `pending_review_count`
- `workflow_engine`

### 3. 待审核提案列表

```bash
curl http://127.0.0.1:8000/agent/proposals/pending
```

### 4. 批准提案

```bash
curl -X POST http://127.0.0.1:8000/agent/proposals/<proposal_id>/approve
```

### 5. 批量批准全部待审核提案

```bash
curl -X POST http://127.0.0.1:8000/agent/proposals/approve-all
```

### 6. 重建聊天索引

```bash
curl -X POST http://127.0.0.1:8000/chat/reindex
```

## Chatbot 是怎么回答的

Chatbot 不直接对 Markdown 做全文问答，而是：

1. 检索 `wiki/output/pages/*.json`
2. 找到关联的 `source_refs`
3. 回查 `Tool/output/parsed/*.json` 中的原始片段
4. 组织带引用的回答
5. 如果 `use_llm=true`，再让 LLM 基于检索结果生成更自然的答案

这意味着：

- 问答结果可追溯
- 引用片段可展示
- 页面发布状态会直接影响检索结果
- 待审核页面默认不会进入问答索引

## 输出目录说明

### 输入与中间结果

- `Raw/`: 原始文档
- `Raw/manifests/`: 文档 manifest
- `Tool/output/parsed/`: 解析后的规范化文档

### Agent 运行结果

- `App/output/agent_state.json`: 文档维护状态
- `App/output/runs/*.json`: 每次运行摘要

### Wiki 结果

- `wiki/output/pages/`: 页面 JSON，供导出和检索使用
- `wiki/output/proposals/`: 待审核/已发布提案 JSON
- `wiki/output/obsidian/`: Obsidian Markdown 导出

## 开发与验证

运行测试：

```bash
python -m pytest -q
```

当前仓库测试覆盖了：

- Agent 工作流
- 上传接口
- Chatbot MVP
- 增量更新
- Obsidian 导出
- 文档解析流水线

## 模块级入口

```bash
python -m Tool.pipelines.ingest --input Raw/
python -m Tool.pipelines.parse --document-id <id>
python -m wiki.builders.bootstrap --use-llm
python -m wiki.updaters.incremental --document-id <id>
python -m wiki.updaters.conflict_scan
python -m wiki.updaters.review_publish --proposal-id <id>
python -m wiki.updaters.review_publish --approve-all
python -m wiki.exporters.obsidian
python -m App.agent
python -m App.api
```
