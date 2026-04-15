# App Layer

`App` 现在有三块能力：

- `App.agent`: 自动维护 Wiki
- `App.chat`: 基于 Wiki 页面和证据片段生成结构化回答
- `App.api`: 暴露 FastAPI 接口

## Agent 主入口

```bash
python -m App.agent
```

## Chat API 与前端主入口

```bash
python -m App.api
```

## Chatbot MVP 结构

- 本地检索层：`wiki/index/local.py`
- 问答编排：`App/chat.py`
- FastAPI：`App/api.py`

工作方式：

1. 先检索 `wiki/output/pages/*.json`
2. 再回查 `Tool/output/parsed/*.json` 中的原始片段
3. 输出答案、引用片段、命中页面、置信度

## 聊天接口

### 重建索引

```text
POST /chat/reindex
```

### 提问

```text
POST /chat/query
```

请求体：

```json
{
  "question": "文件控制和电子记录有哪些要求？",
  "use_llm": false,
  "top_k_pages": 5,
  "top_k_citations": 8
}
```

## LLM 行为

默认不调用 LLM。

只有在：
- `python -m App.agent --use-llm`
- `/chat/query` 请求体中传 `"use_llm": true`

时，才会调用 `Tool.llm.client.ask_llm()`。

## 日志

Agent：

```bash
python -m App.agent --log-level INFO
python -m App.agent --use-llm --log-level DEBUG
```

Chat API：

```bash
python -m App.api
```

日志会显示：
- 文档维护过程
- 问题命中的页面与证据片段
- 是否触发 LLM
- LLM 请求开始、完成、失败

## 输出说明

- `App/output/agent_state.json`: Agent 记忆
- `App/output/runs/*.json`: 每次运行摘要
- `wiki/output/pages/*.json`: Wiki 页面
- `wiki/output/proposals/*.json`: 提案
- `wiki/output/obsidian/*.md`: Markdown 页面

## Future API

当前 FastAPI 已经提供 MVP 问答能力，后续可以继续加：
- 多轮会话
- 权限控制
- 重排序
- Embedding 检索

