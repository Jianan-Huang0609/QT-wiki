# Raw 层说明

`Raw` 只负责接收和留存原始文档，不做知识组织。

## 目录职责

- 保存原始文件
- 保存上传元数据
- 保存版本关系
- 为后续解析提供稳定输入

## 当前样本

- `P020251106552222183224.docx`
- `新版《医疗器械生产质量管理规范》的理解和实施（最新）.pdf`

这两份文件可视为同一主题的两个来源：

- `docx`：法规原文/制度文本
- `pdf`：培训解读/实施说明

## 建议的落库规则

每次上传时生成一条元数据记录，例如：

```json
{
  "document_id": "doc-20260414-0001",
  "file_name": "P020251106552222183224.docx",
  "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
  "source_system": "manual_upload",
  "biz_domain": "medical-device-qms",
  "department": "quality",
  "owner": "qa-team",
  "confidentiality": "internal",
  "version": "v1",
  "checksum": "sha256:...",
  "ingested_at": "2026-04-14T13:05:10+08:00"
}
```

## 后续接口设计建议

上传接口至少接收：

- 文件本体
- 文件元数据
- 来源系统标识
- 业务域标签
- 可选版本号
- 可选父版本 `parent_document_id`

## Raw 层原则

- 文件不可覆盖，只能新增版本
- 原始文件不在此层做清洗
- 不在此层生成用户可见摘要
- 解析失败也要保留原始文件和错误记录
