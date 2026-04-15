# Tool 层说明

`Tool` 层把 `Raw` 文档解析为统一中间格式，供 `Wiki` 层自动维护知识页。

## 目标

不同来源、不同格式的文件，最后都统一输出成一个 `Canonical Document JSON`。

## 解析链路

### 1. 文档识别

- 判断文件类型
- 识别编码、语言、页数、章节特征
- 识别扫描件还是可抽取文本

### 2. 内容提取

- `docx`：标题层级、正文、表格、批注
- `pdf`：页码、段落、表格、图像、页眉页脚
- `pptx`：页面标题、要点、备注、图表
- `xlsx`：sheet、表头、单元格区域、公式文本
- 图片：OCR、版面分析、图注提取

### 3. 结构重建

把原始内容重建成：

- `sections`
- `paragraphs`
- `tables`
- `figures`
- `fragments`

### 4. 语义补充

对结构化文本再做轻量抽取：

- 术语候选
- 实体候选
- 章节摘要
- 时间、角色、制度动作词

## Canonical Document 建议结构

```json
{
  "document": {
    "document_id": "doc-20260414-0001",
    "title": "医疗器械生产质量管理规范",
    "doc_type": "policy",
    "source_type": "docx",
    "language": "zh-CN"
  },
  "sections": [
    {
      "section_id": "sec-1",
      "title": "第一章 总则",
      "level": 1,
      "page_range": [1, 3]
    }
  ],
  "fragments": [
    {
      "fragment_id": "frag-1",
      "section_id": "sec-1",
      "fragment_type": "paragraph",
      "text": "企业应当将风险管理理念贯穿于质量管理体系运行全过程。",
      "anchors": {
        "page": 1,
        "paragraph_index": 4
      }
    }
  ],
  "tables": [],
  "entities": [],
  "terms": []
}
```

## 对 Wiki 层的关键输出

Tool 层输出不能只有纯文本，还必须保留：

- 页码
- 章节
- 来源锚点
- 结构边界
- 原始顺序

否则 `Wiki` 层无法做高质量引用回溯和差异更新。

## 当前样本的处理建议

### `docx`

适合作为规范型来源，重点抽：

- 章节树
- 条款编号
- 义务表达
- 岗位职责

### `pdf`

适合作为解释型来源，重点抽：

- 目录页
- 培训主题
- 专家解释段
- 法规与实践映射关系

## 建议的子模块

- `Tool/parsers/`
- `Tool/normalizers/`
- `Tool/ocr/`
- `Tool/contracts/`
- `Tool/jobs/`

## 错误处理

每次解析都应输出状态：

- `parsed`
- `partially_parsed`
- `failed`

并记录：

- 失败阶段
- 异常信息
- 可恢复与否
- 是否允许进入人工补录
