# QT Regulation Navigator PRD 与技术架构方案

## 0. 文档信息

| 字段 | 内容 |
| --- | --- |
| 文档状态 | Draft |
| 当前版本 | v0.2 |
| 更新时间 | 2026-04-29 |
| 适用范围 | QT Wiki 项目重构、法规导航型知识平台 MVP |
| 对齐对象 | 产品、研发、算法、质量/法规评审人 |

## 1. 项目重定义

### 1.1 背景

当前仓库的主思路是：

- 解析原始文档
- 生成 wiki page 候选
- 人工审批后写入 wiki
- 查询时优先读取 wiki 页面

这条路径适合“知识沉淀”和“页面化展示”，但不适合当前已经重新明确的主目标：

- 给定一条法规，快速找到相关内部主文档
- 展开内部主文档对应的附件文档
- 继续展开到具体章节和证据片段
- 对用户问题给出带结构化引用的答案

因此，产品主线不再应该是“先生成 wiki 页面”，而应该是“先建立法规到文档、文档到章节、章节到证据的导航关系，再让问答和展示复用这层结构”。

### 1.2 新产品定义

QT Wiki 项目应重定义为：

**以法规为入口、以内部主文档和附件为承接、以章节和证据为检索单元、以人工审批为质量边界的法规导航型知识平台。**

### 1.3 设计结论

- 核心路线选型：`RAG-first + typed document graph + approval workflow`
- 现有系统可保留：多格式解析能力、canonical 文档结构、人工审批思路
- 现有系统应降级：page-first 的 wiki 生成逻辑不再作为主交付物
- 新主交付物：`法规 -> 内部主文档 -> 附件文档 -> 章节 -> 证据片段`
- wiki 页面保留为派生产物，仅用于总结页、HTML 页面、slide 输入或二次发布

### 1.4 非目标

本阶段不追求：

- 一步到位的完整知识图谱平台
- 自动放行所有跨文档映射
- 取代专家对高风险关系的最终判断
- 构建开放式通用聊天机器人

## 2. 产品目标

### 2.1 业务目标

- 让用户能从法规快速导航到内部主文档和附件文档
- 让问答能够稳定返回“法规要求 + 内部落实方式 + 章节证据”
- 让审批聚焦在关键边界判断，而不是低价值的全文审核
- 为后续 HTML 总结页、映射矩阵、slide 输出提供稳定输入

### 2.2 MVP 目标

MVP 只解决一个核心问题：

**针对一条法规，系统能告诉用户有哪些内部文档，能展开对应章节，并能基于章节证据回答问题。**

### 2.3 成功指标

- 查询命中率：针对已纳入范围的法规问题，`>= 85%` 的回答能命中至少 1 个法规章节和 1 个内部文档章节
- 引用完整率：`>= 95%` 的回答包含可回溯证据片段
- 审批聚焦率：人工只处理低置信度候选和高风险关系，自动处理低风险解析项
- 用户路径效率：用户在 3 次点击内从法规页进入内部文档章节
- 输出复用率：审批通过后的结构化结果可直接复用于 HTML 总结或 slide 生成

## 3. 用户与核心场景

### 3.1 目标用户

- 法规/质量负责人：关心法规要求及其内部承接情况
- 流程 owner：关心内部主文档、附件和章节是否覆盖法规要求
- 审批专家：关心关键映射、权威边界和风险关系是否成立
- 项目成员：关心如何快速找到证据和形成对外说明材料

### 3.2 核心场景

#### 场景 A：法规导航

用户打开某条法规，系统展示：

- 法规基本信息
- 法规章节树
- 已关联的内部主文档
- 每个主文档下的附件文档
- 已建立的章节级映射

#### 场景 B：证据问答

用户提问“某条法规在内部由哪些 SOP 承接？”，系统返回：

- 结论
- 涉及的法规章节
- 对应的内部主文档章节
- 对应附件或模板
- 证据片段引用
- 不确定项和建议追问

#### 场景 C：审批放行

评审人进入审批工作台，只处理：

- 文档身份是否正确
- 主文档与附件归属是否正确
- 法规到内部文档映射是否成立
- 低置信度章节关系是否需要人工修正

## 4. 核心信息模型

### 4.1 核心对象

系统核心对象固定为 5 类：

1. 外部法规文档：法规、规范、指南、解释性材料
2. 内部主文档：PEP、SOP、WI、流程主文件
3. 内部附件文档：模板、记录表、附录、表单
4. 章节对象：文档内按章拆分的结构节点
5. 证据片段：可回溯到页码、段落、表格、图的最小引用单元

### 4.2 文档类型约束

MVP 阶段建议将文档身份先约束成三大类：

- 外部法规文档
- 内部主文档
- 内部附件文档

对于“解读材料、培训材料、运行证据、经验反馈”这类对象，先作为扩展属性或次级标签存在，不作为主导航路径的一级对象。

### 4.3 关系类型

建议优先支持以下关系：

- `implements`：内部主文档实现某条法规或法规章节
- `attachment_of`：附件文档从属于某个内部主文档
- `references`：文档或章节引用另一文档或章节
- `interprets`：解释性材料解释某条法规要求
- `covers`：某个内部章节覆盖某个法规章节
- `evidence_for`：证据片段支撑某个关系或回答结论

## 5. 产品范围与阶段规划

### 5.1 Phase 1：可用闭环

目标：建立法规导航与章节级检索的基本闭环。

范围包括：

- 文档类型识别
- 多格式解析
- 按章节切分
- 法规中心页面
- 法规详情页
- 章节级证据展示
- 基础结构化问答

### 5.2 Phase 1.5：问答与审批补齐

范围包括：

- 结构化回答 contract
- 推荐问题
- 审批工作台
- 关键关系人工确认
- 健康检查与缺口提示

### 5.3 Phase 2：Wow Moments

范围包括：

- 法规覆盖矩阵
- 章节对章节映射视图
- 自动生成漂亮的 HTML 摘要页
- 表格、模板、流程图的多模态摘要
- 一键生成法规落地简报或框图

## 6. 功能需求

### 6.1 文档接入与识别

系统需要支持：

- 上传或接入 PDF、DOCX、XLSX、PPTX
- 提取标题、版本、来源、发布日期、语言等元数据
- 判断文档属于外部法规、内部主文档还是内部附件文档
- 对文档身份输出置信度和待审提示

验收标准：

- 新文档进入系统后自动生成文档卡片
- 文档卡片至少包含标题、版本、文档类型、来源文件名
- 对低置信度身份判断自动进入审批队列

### 6.2 解析与章节切分

系统需要支持：

- 将原始文档解析为 canonical 结构
- 识别章节树、页码、段落、表格、图片锚点
- 将文档按章节和片段拆成可检索单元
- 保留 `section_id`、`fragment_id`、`anchors`、`page_range`

验收标准：

- 法规与内部主文档均能按章节展开
- 每个回答引用都能回到至少一个具体 fragment
- 表格类证据可单独定位并引用

### 6.3 法规中心

法规中心是首页，需要支持：

- 法规列表、状态筛选、版本筛选
- 展示每条法规关联了多少内部主文档和附件文档
- 一键进入法规详情页

法规中心首页默认展示：

- 法规标题
- 权威级别
- 适用范围
- 内部主文档数量
- 待审批关系数量

### 6.4 法规详情页

法规详情页是 MVP 最核心页面，需要支持：

- 左侧法规章节树
- 中间内部主文档与附件树
- 右侧证据抽屉
- 顶部 `总览 / 相关文档 / 章节映射 / 问答 / 审批记录` 五个标签

用户在这页应能完成：

- 从法规章节跳转到对应内部章节
- 从内部主文档展开附件文档
- 查看映射所对应的证据片段
- 从当前法规上下文发起问答

### 6.5 智能问答

问答不做纯聊天，而做结构化回答。

回答输出至少包含：

- 结论
- 涉及的法规
- 涉及的内部主文档
- 涉及的附件
- 命中的章节
- 证据片段
- 不确定项
- 建议下一步问题

推荐问题来自两个来源：

- 当前法规和章节上下文
- 当前命中的主文档与附件关系

### 6.6 审批工作台

审批对象改成以下四类：

- 文档身份候选
- 主文档/附件归属关系候选
- 法规到内部文档的关键映射候选
- 低置信度章节关系候选

审批人不需要审全文，只需要看：

- 候选结论
- 证据片段
- 冲突提示
- 放行、驳回、改写意见

### 6.7 派生产物

当审批通过后，系统可以产出：

- HTML 摘要页
- 一对多映射矩阵
- 审批通过的法规落地简报
- 可回溯的结构化导出文件

wiki 页面在新架构下属于派生产物，而非主存储。

## 7. LLM 交互与结构化推理编排

### 7.1 原则

- 不保存模型自由思维文本
- 只保存结构化中间结果
- 所有高风险关系都必须带证据和置信度

### 7.2 五段式编排

1. `Doc Classifier`
   - 判断文档类型、权威边界、主文档/附件属性
2. `Section Resolver`
   - 将问题落到法规章节和内部文档章节
3. `Relation Retriever`
   - 找法规与内部主文档、主文档与附件之间的候选关系
4. `Answer Composer`
   - 生成“法规要求 / 内部落实方式 / 章节证据 / 不确定点”结构化回答
5. `Suggestion Generator`
   - 生成推荐问题、比较视图、HTML 摘要卡片

### 7.3 必须保存的结构化字段

- 用户问题意图
- 识别出的法规对象
- 命中的文档列表
- 命中的章节列表
- 最终引用的证据片段
- 置信度
- 待审批标记

## 8. UI 与信息架构

### 8.1 一级页面

建议将 UI 固定成 4 个主界面：

1. 法规中心
2. 法规详情页
3. 智能问答页
4. 审批工作台

### 8.2 页面设计原则

- 首页不是聊天框，而是法规导航面板
- 用户总能看到“法规 -> 文档 -> 章节 -> 证据”的上下文位置
- 问答结果必须与具体章节和证据联动展示
- 审批页要优先显示证据与差异，而不是长文本摘要

### 8.3 静态前端原型

本次设计附带一个可直接修改的单文件静态原型：

- `Design/regulation-navigator-prototype.html`

该原型覆盖：

- 步骤框架总览
- 法规中心
- 文档接入
- 章节映射
- 智能问答
- 审批工作台
- Phase 2 展望

## 9. 技术架构

### 9.1 设计原则

- 解析层复用，不推倒重来
- 查询层重做，不继续依赖 full-wiki context
- 存储分层，不把所有信息压进 json page
- 低风险自动化，高风险审批化
- 页面展示层与主存储解耦

### 9.2 逻辑架构

```text
Source Files
  -> Parsing Layer
  -> Document Registry
  -> Section Index
  -> Relation Layer
  -> Approval Workflow
  -> Retrieval Layer
  -> Answer Orchestrator
  -> UI / HTML / Slides / Export
```

### 9.3 模块划分

建议系统拆成 6 个明确模块：

- `Parsing Layer`：复用现有 PDF/DOCX/XLSX/PPTX 解析能力
- `Document Registry`：管理文档身份、版本、主文档/附件关系
- `Section Index`：管理章节树、章节 chunk、页码锚点、表格锚点
- `Relation Layer`：管理法规到文档、文档到附件、章节到章节的关系
- `Retrieval Layer`：做混合检索，先 metadata/filter，再 vector，再 rerank
- `Answer Orchestrator`：负责问答、推荐问题、多模态输出、HTML 产物

### 9.4 数据存储建议

MVP 阶段不建议直接上图数据库。建议组合为：

- 原始文件：本地文件系统、SharePoint 或对象存储
- 结构化元数据：`PostgreSQL`
- 向量检索：`pgvector`
- Azure 环境成熟时，可替换为 `Azure AI Search + PostgreSQL`

不建议 MVP 直接使用 Neo4j，原因：

- 运维复杂度高
- 当前主要问题是“稳定检索与审批”，不是复杂图遍历
- 章节级关系数量有限，关系型表足以支撑

### 9.5 核心表结构

- `documents`：文档主表，含 `doc_type`、`authority_level`、`parent_document_id`
- `document_versions`：版本信息
- `sections`：章节树，含 `path`、`level`、`page_start`、`page_end`
- `chunks`：章节内可检索片段
- `tables` / `figures`：表格和图对象
- `document_relations`：`implements`、`attachment_of`、`references`、`interprets`
- `section_relations`：章节到章节映射
- `approvals`：审批记录
- `query_logs`：问答轨迹
- `generated_assets`：HTML、框图、导出内容

### 9.6 检索链路

查询流程建议固定为：

1. 识别问题涉及的法规、内部流程、附件或章节
2. 按文档类型做 metadata 过滤
3. 优先按章节级召回，而不是整篇文档召回
4. 用 reranker 重新排序章节和证据片段
5. 生成结构化回答，并分别列出法规章节、内部文档章节、附件证据

### 9.7 Answer Contract

```json
{
  "summary": "string",
  "regulations": [],
  "internal_master_documents": [],
  "attachments": [],
  "matched_sections": [],
  "evidence_fragments": [],
  "uncertainties": [],
  "suggested_questions": []
}
```

## 10. 基于当前仓库的实施级重构方案

### 10.1 总体判断

当前仓库不是从零开始。它已经具备：

- 多格式解析能力
- canonical 文档契约
- 章节、fragment、anchor 基础字段
- 候选审批思路

真正需要重构的是：

- 查询主线
- 数据主模型
- 候选对象的类型定义
- 展示层信息架构

### 10.2 模块保留

这些模块建议直接保留并继续使用：

- `Tool/parsers/*`
- `Tool/contracts/canonical.py`
- `Tool/normalizers/*`
- `Tool/pipelines/common.py`
- 解析相关测试用例，尤其是 parse pipeline 的章节与 anchor 测试

### 10.3 模块局部改造

这些模块建议保留文件基础，但调整职责：

- `Tool/pipelines/ingest.py`
  - 从“文档入库”扩展为“文档登记 + manifest 规范化”
- `Tool/pipelines/parse.py`
  - 继续负责解析，但输出要对接 `sections/chunks/tables/figures`
- `Tool/document_processor.py`
  - 从“给 LLM 的全文上下文工具”改成“解析结果装配器和导出入口”
- `App/web/*`
  - 视觉调性可部分复用，但信息架构需重写为法规导航型界面

### 10.4 模块重写

这些模块建议重写：

- `App/agents/query_agent.py`
  - 不再走 full wiki context，改成基于章节和关系的结构化检索问答
- `App/agents/ingest_agent.py`
  - 候选对象从 `wiki page candidate` 改成 `document/section/relation candidate`
- `App/agents/lint_agent.py`
  - 从 wiki 健康检查改成关系、引用、覆盖缺口和断裂映射扫描
- `wiki/builders/*`
  - 从主流程降级为派生产物生成器
- `wiki/updaters/*`
  - 从主写入路径降级为 approved artifact 发布器

### 10.5 目录重构建议

建议在不影响现有解析层的前提下，将目录逐步重构为：

```text
QT-wiki/
├── App/
│   ├── api/
│   │   ├── regulations.py
│   │   ├── documents.py
│   │   ├── queries.py
│   │   └── approvals.py
│   ├── web/
│   │   ├── index.html
│   │   └── assets/
│   └── workflows/
│       ├── intake_workflow.py
│       ├── query_workflow.py
│       └── approval_workflow.py
├── Core/
│   ├── documents/
│   │   ├── classifier.py
│   │   ├── registry.py
│   │   └── models.py
│   ├── sections/
│   │   ├── splitter.py
│   │   ├── chunker.py
│   │   └── anchors.py
│   ├── relations/
│   │   ├── extractor.py
│   │   ├── scorer.py
│   │   └── repository.py
│   ├── retrieval/
│   │   ├── filters.py
│   │   ├── vector_index.py
│   │   ├── reranker.py
│   │   └── service.py
│   ├── answering/
│   │   ├── contracts.py
│   │   ├── composer.py
│   │   └── suggestions.py
│   ├── approvals/
│   │   ├── candidates.py
│   │   └── service.py
│   └── health/
│       └── scanners.py
├── Storage/
│   ├── db/
│   │   ├── schema.sql
│   │   └── repositories/
│   ├── vector/
│   │   └── embeddings.py
│   └── files/
│       └── manifests.py
├── Tool/
│   ├── contracts/
│   ├── normalizers/
│   └── parsers/
├── wiki/
│   └── artifacts/
├── Design/
│   ├── Design.md
│   └── regulation-navigator-prototype.html
└── tests/
```

### 10.6 目录重构原则

- `Tool/` 只保留通用解析与规范化能力
- `Core/` 承担新的业务核心模型和检索编排
- `Storage/` 明确承接数据库、向量、文件层
- `wiki/` 保留但降级为 artifact layer
- `App/` 只放对外接口、工作流与前端

### 10.7 API 建议

MVP 至少应提供以下接口：

- `GET /regulations`
- `GET /regulations/{regulation_id}`
- `GET /documents/{document_id}`
- `GET /sections/{section_id}`
- `POST /queries`
- `GET /approvals`
- `POST /approvals/{approval_id}/approve`
- `POST /approvals/{approval_id}/reject`
- `POST /reindex`

### 10.8 迁移路径

#### Step 1：冻结旧 wiki page 主线

- 不再把新增能力设计成 overview/entity/concept page
- 旧 wiki 功能只保留读取和导出

#### Step 2：先立 Document Registry 和 Section Index

- 将解析结果持久化到 `documents / sections / chunks`
- 保证法规和内部主文档都能稳定展开章节

#### Step 3：重写 Query 主线

- 改成 metadata filter + section retrieval + rerank + answer contract
- 彻底移除 full wiki context 依赖

#### Step 4：重写 Ingest Candidate

- 候选从 page 改为关系和章节级对象
- 审批对象收敛到身份、映射和低置信度关系

#### Step 5：补审批工作台与健康检查

- 引入 orphan relation、missing evidence、broken mapping、coverage gap 扫描

#### Step 6：恢复派生产物

- 在审批通过数据上生成 HTML 页面、矩阵和 slide 输入

## 11. 研发分工建议

### 11.1 后端/算法

- 文档分类器
- 章节切分与 chunk 策略
- 关系抽取与置信度评分
- 混合检索与 rerank
- 结构化回答编排

### 11.2 前端

- 法规中心
- 法规详情页
- 问答结果结构化视图
- 审批工作台
- 后续 HTML 摘要页模板

### 11.3 质量/法规专家

- 定义文档类型边界
- 定义高风险关系列表
- 审核法规到内部文档的关键映射
- 审核要求/建议/解释边界

## 12. 风险与控制

### 12.1 主要风险

- 文档身份识别错误，导致后续问答全部偏离
- 章节切分不稳定，导致证据引用体验差
- 内部主文档与附件关系不清晰，影响导航价值
- 模型将“解释”误说成“要求”

### 12.2 控制策略

- 对文档身份和关键关系建立强制审批门
- 保留 page/paragraph/table anchors，保证引用稳定
- 在回答 contract 中强制暴露不确定项
- 对关系类型设置白名单，不允许自由扩张

## 13. 最终判断

这个项目不应该继续沿着“先写 wiki 页面，再让用户搜索”的主线推进。

正确路线是：

- 复用现有解析层
- 重做查询层和数据模型
- 将产品主线改成法规导航、章节证据检索与审批放行
- 将 wiki 页面降级为派生产物

一句话总结：

**这不是一个先生成 wiki 页面、再让人去搜的系统；这是一个以法规为入口、以内部文档和附件为承接、以章节和证据为检索单元、以受控审批为边界的法规导航型知识平台。**