# Wiki 层说明

`wiki` 层负责将解析后的文档自动维护成企业知识页。

这里不是简单做检索，而是维护“页面”。

## 核心对象

### Wiki Page

```json
{
  "page_id": "风险管理",
  "title": "风险管理",
  "page_type": "concept",
  "summary": "风险管理贯穿医疗器械质量管理体系全过程。",
  "sections": [],
  "aliases": ["质量风险管理"],
  "source_refs": [],
  "linked_entities": [],
  "review_status": "approved",
  "page_version": 3
}
```

### Update Proposal

这是大模型生成的“修订提案”，不是直接发布结果。

```json
{
  "proposal_id": "proposal-20260414-001",
  "target_page_id": "风险管理",
  "action": "update_section",
  "reason": "新文档补充了风险管理回顾要求",
  "evidence": ["frag-1", "frag-22"],
  "risk_level": "medium",
  "status": "pending_review"
}
```

## 自动维护流程

### 1. 主题识别

从 `Tool` 输出中识别：

- 这份文档在讲什么
- 命中了哪些已有页面
- 是否需要新建页面

### 2. 页面匹配

优先匹配现有页面：

- 标题匹配
- 别名匹配
- 术语匹配
- 实体匹配
- 向量召回辅助

### 3. 修订提案生成

对命中的页面生成结构化改动，而不是整页重写：

- 新增 section
- 补充解释
- 更新定义
- 标记冲突
- 合并重复页面

### 4. 校验

校验规则至少包括：

- 每个新增结论是否有引用
- 引用是否能回到 `fragment`
- 是否与现有内容冲突
- 是否是推断过度

### 5. 发布

按页面风险级别决定：

- 自动发布
- 人工审核后发布

## 页面分类建议

- `concept`
- `policy`
- `process`
- `role`
- `faq`
- `domain`

## 页面结构建议

每个页面建议统一结构：

1. 页面摘要
2. 核心结论
3. 详细说明
4. 关联页面
5. 引用来源
6. 版本记录

## 当前样本的页面映射示例

### 页面：`质量管理体系`

可融合来源：

- `docx` 中关于质量目标、质量保证系统、持续改进的条款
- `pdf` 中关于 QMS 基础知识、法规关系、实施步骤的解读

### 页面：`机构与人员职责`

可沉淀内容：

- 法定代表人职责
- 管理者代表职责
- 质量负责人职责
- 生产负责人职责
- 放行审核人职责

### 页面：`文件和数据管理`

可拆成两个 section：

- 文件控制
- 电子记录和数据管理

## 后台任务建议

- `bootstrap_page_build`
- `incremental_page_update`
- `conflict_scan`
- `stale_page_scan`
- `citation_repair`

## 质量底线

- 页面必须可追溯
- 模型输出必须受来源约束
- 所有更新必须版本化
- 冲突信息不能被静默覆盖

