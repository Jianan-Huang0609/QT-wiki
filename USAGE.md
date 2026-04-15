# QT Wiki 使用说明

## 推荐入口

维护 Wiki：

```bash
python -m App.agent
```

启动聊天 API 与前端：

```bash
python -m App.api
```

## Agent 工作流

用户把文件上传到 `Raw/`，然后运行 Agent。Agent 会自动完成：

1. 文档入库
2. 文档解析
3. 生成 Wiki 页面候选变更
4. 审核闸门判断：大改动默认人工审核，小改动可自动推进
5. 冲突扫描
6. 页面发布
7. 导出 Markdown 到 `wiki/output/obsidian/`

## 人工审核闭环

待审核提案会写入 `wiki/output/proposals/`。你可以：

1. 先查看待审提案
2. 人工确认后批准发布
3. 再让 Chatbot 重新索引

命令行批准：

```bash
python -m wiki.updaters.review_publish --proposal-id <proposal_id>
```

API 查看和批准：

```bash
curl http://127.0.0.1:8000/agent/proposals/pending
curl -X POST http://127.0.0.1:8000/agent/proposals/<proposal_id>/approve
```

## Chatbot MVP 工作流

Chatbot 的数据源不是 Markdown，而是：
- `wiki/output/pages/*.json`
- `Tool/output/parsed/*.json`

处理链路：

1. 先检索相关 Wiki 页面
2. 再根据页面里的 `source_refs` 回查原始片段
3. 返回结构化回答，并附带引用片段

## 是否使用大语言模型

项目已经接入大语言模型，但默认不开启。

当前 LLM 的主要用途：
- 在首次建库时为页面生成摘要
- 在聊天接口中生成最终回答

默认情况下：
- `python -m App.agent` 不调用 LLM
- `/chat/query` 里如果 `use_llm=false`，也不调用 LLM

只有显式开启：

```bash
python -m App.agent --use-llm
```

或请求中传：

```json
{ "use_llm": true }
```

才会调用模型。

## 如何查看调用过程

### Agent 日志

```bash
python -m App.agent --log-level INFO
python -m App.agent --use-llm --log-level DEBUG
python -m App.agent --workflow-engine langgraph
python -m App.agent --no-auto-approve-small-changes
```

### Chat API 日志

```bash
python -m App.api
```

日志会展示：
- 文档是否被解析
- 文档是否进入增量维护
- 是否执行 bootstrap
- 问题命中的页面和片段数量
- 是否调用 LLM
- LLM 请求开始、结束、失败

## 快速开始

### 1. 安装依赖

```bash
pip install pytest pypdf requests openpyxl fastapi uvicorn
```

### 2. 配置 LLM

编辑 `config/azure_gpt4o_config.json`。

### 3. 上传文件并维护 Wiki

```bash
python -m App.agent
```

或通过 API 上传并自动触发 Agent：

```bash
curl -X POST http://127.0.0.1:8000/agent/upload \
  -F "file=@./Raw/你的文档.docx" \
  -F "use_llm=false" \
  -F "auto_publish_low_risk=true" \
  -F "auto_approve_small_changes=true" \
  -F "workflow_engine=langgraph"
```

### 4. 启动 Chat API

```bash
python -m App.api
```

### 5. 发起聊天请求

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

## 常用命令

维护 Wiki：

```bash
python -m App.agent
python -m App.agent --use-llm
python -m App.agent --log-level DEBUG
python -m App.agent --force-reparse --force-reconcile
python -m App.agent --workflow-engine langgraph
python -m App.agent --no-auto-approve-small-changes
```

启动 API：

```bash
python -m App.api
```

手动重建聊天索引：

```bash
curl -X POST http://127.0.0.1:8000/chat/reindex
```

上传文件并自动维护：

```bash
curl -X POST http://127.0.0.1:8000/agent/upload \
  -F "file=@./sample.pdf" \
  -F "use_llm=false" \
  -F "auto_publish_low_risk=true" \
  -F "auto_approve_small_changes=true" \
  -F "workflow_engine=auto"
```

查看待审核提案：

```bash
curl http://127.0.0.1:8000/agent/proposals/pending
```

批准提案：

```bash
curl -X POST http://127.0.0.1:8000/agent/proposals/<proposal_id>/approve
```

## 聊天接口返回字段

- `answer`: 最终回答
- `citations`: 引用片段列表
- `matched_pages`: 命中的页面
- `confidence`: 置信度
- `used_llm`: 是否真的调用了 LLM
- `question`: 原问题

## 上传维护接口返回字段

- `status`: 执行状态
- `file_name`: 实际落盘文件名（位于 `Raw/`）
- `stored_path`: 仓库相对路径
- `run_id`: Agent 运行编号
- `manifests_seen`: 本次入库文档数
- `documents_parsed`: 本次解析文档数
- `proposals_created`: 产生提案数
- `pages_published`: 自动发布页面数
- `pending_review_count`: 待人工审核提案数
- `workflow_engine`: 实际使用的工作流引擎

## 输出目录

- `App/output/agent_state.json`: 记录文档是否已经被维护过
- `App/output/runs/*.json`: 每次运行的结果摘要
- `Tool/output/parsed/`: 解析结果
- `wiki/output/pages/`: 页面结果
- `wiki/output/proposals/`: 提案结果
- `wiki/output/obsidian/`: 最终 Markdown 页面

## 模块级命令

```bash
python -m Tool.pipelines.ingest --input Raw/
python -m Tool.pipelines.parse --document-id <id>
python -m wiki.builders.bootstrap --use-llm
python -m wiki.updaters.incremental --document-id <id>
python -m wiki.updaters.conflict_scan
python -m wiki.updaters.review_publish --proposal-id <id>
python -m wiki.exporters.obsidian
python -m App.agent
python -m App.api
```

