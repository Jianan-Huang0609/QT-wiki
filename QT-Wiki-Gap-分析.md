# QT Wiki 实现与 Design.md 的差距分析 (Gap Analysis)

## 概述

本文档对比 Design.md 的设计要求与当前代码实现，识别已完成功能和待完善功能。

---

## 1. 核心流程对比

### 1.1 首次上传 6 步骤实现状态

| 步骤 | Design.md 要求 | 当前实现状态 | Gap 说明 |
|------|----------------|--------------|----------|
| **步骤1** | 识别文档类型（5类）+ 提取关键信息 | ⚠️ **部分实现** | 业务类型分类已实现，但缺少"发布时间"提取，权威级别判断较简单 |
| **步骤2** | 切成可回溯的证据片段 | ✅ **已实现** | CanonicalDocument 包含 fragments、sections、anchors |
| **步骤3** | 拆出六类关键对象 | ⚠️ **部分实现** | 实现了 process_step、role、record、requirement，但缺少 regulation_clause、pep_node、concept 的明确区分 |
| **步骤4** | 建立对象间关系 | ⚠️ **部分实现** | 实现了 requires/produces/responsible_for，但缺少 implements、references、constrains 的完整支持 |
| **步骤5** | AI 生成审批包 | ✅ **已实现** | ReviewPackage 包含完整结构 |
| **步骤6** | 人工放行后发布 | ✅ **已实现** | 双关口审批机制已实现 |

---

## 2. 详细 Gap 分析

### 2.1 文档类型识别 (步骤1)

#### Design.md 要求
```
五类文档：
- 外部强制文件（法规、规范、条例、强制标准）
- 外部解释与参考文件（指南、专家解读、培训讲义）
- 内部受控文件（PEP、WI、SOP、流程文件、模板、QR空白表）
- 运行证据文件（已填写的记录、评审纪要、验证报告、DHF产物、放行记录）
- 经验反馈文件（Finding、Audit、CAPA、偏差、投诉、经验复盘）

关键信息：标题、版本、适用范围、权威级别、发布时间、是否可以作为强约束
```

#### 当前实现
```python
# App/agents/ingest_agent.py: _classify_business_type()
def _classify_business_type(self, doc: "ProcessedDocument") -> str:
    title = f"{doc.title} {doc.file_name}".lower()
    if any(token in title for token in ("sop", "pep", "wi", "程序", "规程", "流程", "模板")):
        return "internal_controlled"
    if any(token in title for token in ("capa", "偏差", "投诉", "audit", "finding", "复盘")):
        return "feedback"
    # ... 其他规则
```

#### Gap 详情

| 要求项 | 实现状态 | 优先级 | 说明 |
|--------|----------|--------|------|
| 五类文档分类 | ⚠️ 基本实现 | 中 | 分类逻辑基于文件名关键词，不够 robust |
| 标题提取 | ✅ 已实现 | - | 从文档元数据获取 |
| 版本提取 | ⚠️ 部分实现 | 低 | 仅从 metadata 获取，未从内容解析 |
| 适用范围 | ❌ **未实现** | 中 | 未从文档中提取适用范围信息 |
| 权威级别 | ⚠️ 简化实现 | 中 | 仅基于 business_type 推断，未深度分析 |
| 发布时间 | ❌ **未实现** | 低 | 未提取文档发布时间 |
| 强制/解释性判断 | ⚠️ 简化实现 | 高 | 仅基于关键词（应当/必须/不得）判断 |

#### 建议改进
1. 使用 LLM 分析文档内容，提取适用范围、发布时间等信息
2. 增强强制/解释性判断逻辑，结合文档类型和内容语境

---

### 2.2 六类对象抽取 (步骤3)

#### Design.md 要求
```
- 流程节点 (process_step)
- 角色 (role)
- 交付物或记录 (deliverable/record)
- 法规条款 (regulation_clause)
- 内部 PEP 节点 (pep_node)
- 核心概念 (concept)
```

#### 当前实现
```python
# App/agents/ingest_agent.py: _objects_from_fragment_text()
def _objects_from_fragment_text(self, text: str) -> list[tuple[str, str, float, str]]:
    objects: list[tuple[str, str, float, str]] = []
    # 1. requirement - 基于关键词判断
    if any(token in compact for token in ("应当", "必须", "不得")):
        objects.append(("requirement", requirement_name, 0.86, "high"))
    
    # 2. process_step - 预定义步骤列表
    for step in self._extract_process_steps(compact):
        objects.append(("process_step", step, 0.72, "medium"))
    
    # 3. record - 正则匹配
    for record_name in self._extract_records(text):
        objects.append(("record", record_name, 0.7, "medium"))
    
    # 4. role - 正则匹配
    for role_name in self._extract_roles(text):
        objects.append(("role", role_name, 0.68, "medium"))
```

#### Gap 详情

| 对象类型 | 实现状态 | 优先级 | Gap 说明 |
|----------|----------|--------|----------|
| process_step | ⚠️ 简化实现 | 中 | 使用预定义关键词列表，未使用 LLM 深度抽取 |
| role | ⚠️ 简化实现 | 中 | 正则匹配，覆盖面有限 |
| record | ⚠️ 简化实现 | 中 | 正则匹配，可能遗漏 |
| **regulation_clause** | ❌ **未实现** | **高** | 未区分法规条款和普通要求 |
| **pep_node** | ❌ **未实现** | **高** | 未识别 PEP 流程节点 |
| **concept** | ❌ **未实现** | **高** | 未抽取核心概念 |

#### 建议改进
1. 使用 LLM 进行对象抽取，提高准确率和覆盖率
2. 在 LLM prompt 中明确六类对象的定义和示例
3. 建立对象类型识别的验证机制

---

### 2.3 关系建立 (步骤4)

#### Design.md 要求
```
- 法规条款 requires 流程步骤
- 流程步骤 produces 记录
- 角色 responsible_for 步骤
- 内部 PEP implements 法规要求
- 解读材料 references 法规要求
- 风险管理 constrains 设计开发活动
```

#### 当前实现
```python
# App/agents/ingest_agent.py: _extract_relations_rule_based()
# 已实现的关系：
- requires: requirement → process_step
- produces: process_step → record
- responsible_for: role → process_step

# 未实现的关系：
- implements (PEP → regulation)
- references (interpretation → regulation)
- constrains (risk → activity)
```

#### Gap 详情

| 关系类型 | 实现状态 | 优先级 | Gap 说明 |
|----------|----------|--------|----------|
| requires | ✅ 已实现 | - | requirement → process_step |
| produces | ✅ 已实现 | - | process_step → record |
| responsible_for | ✅ 已实现 | - | role → process_step |
| **implements** | ❌ **未实现** | **高** | 需要识别 PEP 节点与法规要求的实现关系 |
| **references** | ❌ **未实现** | **中** | 需要识别解读材料与法规的引用关系 |
| **constrains** | ❌ **未实现** | **中** | 需要识别风险管理与其他活动的约束关系 |

#### 建议改进
1. 在 LLM 关系抽取 prompt 中增加未实现的关系类型
2. 建立跨文档关系识别机制（需要加载多个文档）

---

### 2.4 审批包内容 (步骤5)

#### Design.md 要求
```
审批包应包含：
- 文档被识别成什么类型
- 拆出了哪些关键对象
- 建立了哪些关键关系
- 每个关键判断对应的证据片段
- 哪些地方有冲突
- 哪些地方存在缺口
- 哪些问题需要人工确认
```

#### 当前实现
```python
# wiki/models/page.py: ReviewPackage
@dataclass(slots=True)
class ReviewPackage:
    package_id: str
    document_id: str
    status: str
    document_identity: DocumentIdentity
    identity_decision: str = "pending"
    # ... 身份审批字段
    relation_decision: str = "pending"
    # ... 关系审批字段
    evidence_refs: list[dict[str, Any]] = field(default_factory=list)
    extracted_objects: list[ReviewObject] = field(default_factory=list)
    extracted_relations: list[ReviewRelation] = field(default_factory=list)
    issues: list[ReviewIssue] = field(default_factory=list)
    human_questions: list[HumanReviewQuestion] = field(default_factory=list)
```

#### Gap 详情

| 要求项 | 实现状态 | 说明 |
|--------|----------|------|
| 文档类型 | ✅ 已实现 | document_identity.business_type |
| 关键对象 | ✅ 已实现 | extracted_objects |
| 关键关系 | ✅ 已实现 | extracted_relations |
| 证据片段 | ✅ 已实现 | evidence_refs + object.evidence_refs |
| **冲突检测** | ⚠️ **简化实现** | 仅检测边界风险，未实现深度冲突分析 |
| **缺口分析** | ⚠️ **简化实现** | 有 LLM 缺口分析，但效果待验证 |
| 人工问题 | ✅ 已实现 | human_questions |

#### 建议改进
1. 增强冲突检测：检测同一要求在不同文档中的描述差异
2. 完善缺口分析：识别法规要求未在内部流程中实现的情况

---

### 2.5 人工审批关口 (步骤6)

#### Design.md 要求
```
人工关口 1：确认文档身份和权威边界
- 文件类型、标题、版本、效力层级、适用范围、是否强制

人工关口 2：确认关键映射和高风险关系
- 法规要求是否对应内部流程
- 关系方向是否正确
- 结论是要求、解释还是建议
```

#### 当前实现
```python
# App/api.py
@app.post("/api/ingest/review-packages/{package_id}/decision")
def decide_review_package(package_id: str, payload: ReviewPackageDecisionRequest):
    # 人工关口 1：身份审批
    
@app.post("/api/ingest/review-packages/{package_id}/relations/decision")
def decide_review_package_relations(package_id: str, payload: ReviewPackageRelationDecisionRequest):
    # 人工关口 2：关系审批
```

#### Gap 详情

| 要求项 | 实现状态 | 说明 |
|--------|----------|------|
| 双关口机制 | ✅ 已实现 | 身份审批和关系审批分开 |
| 身份审批字段 | ✅ 已实现 | business_type/effective_level/is_binding |
| 关系审批字段 | ✅ 已实现 | relation_decision |
| **审批界面信息展示** | ⚠️ **需优化** | 前端已展示基本信息，但缺少证据片段的直接展示 |
| **高风险关系标记** | ⚠️ **部分实现** | ReviewRelation.human_required 字段存在，但前端未突出显示 |

#### 建议改进
1. 前端审批界面增加证据片段的直接引用展示
2. 高风险关系在前端用特殊标记突出显示
3. 增加审批历史记录

---

## 3. 人机协作边界

### 3.1 AI 自动处理的内容

| 内容 | Design.md 要求 | 当前实现 | Gap |
|------|----------------|----------|-----|
| 章节切分 | AI 自动 | ✅ 已实现 | - |
| 页码和 fragment 锚点 | AI 自动 | ✅ 已实现 | - |
| 流程名称抽取 | AI 自动 | ⚠️ 规则实现 | 建议改用 LLM |
| 角色名称抽取 | AI 自动 | ⚠️ 规则实现 | 建议改用 LLM |
| 记录名称抽取 | AI 自动 | ⚠️ 规则实现 | 建议改用 LLM |
| 初步相关链接 | AI 自动 | ✅ 已实现 | - |
| 别名建议 | AI 自动 | ✅ 已实现 | - |
| 缺口提醒 | AI 自动 | ⚠️ 简化实现 | 需增强 |

### 3.2 AI 生成候选 + 人工抽审

| 内容 | Design.md 要求 | 当前实现 | Gap |
|------|----------------|----------|-----|
| 流程节点拆分 | AI 生成 + 人工抽审 | ⚠️ 规则实现 | 未实现抽审机制 |
| 交付物识别 | AI 生成 + 人工抽审 | ⚠️ 规则实现 | 未实现抽审机制 |
| 核心概念提取 | AI 生成 + 人工抽审 | ❌ 未实现 | 需补充 |

### 3.3 必须人工确认

| 内容 | Design.md 要求 | 当前实现 | Gap |
|------|----------------|----------|-----|
| 跨文档映射 | 必须人工 | ⚠️ 部分实现 | 单文档关系已支持，跨文档需增强 |
| 语义等价判断 | 必须人工 | ❌ 未实现 | 需补充对象合并审批 |
| 关键关系方向 | 必须人工 | ✅ 已实现 | 关系审批关口 |
| 要求和建议边界 | 必须人工 | ⚠️ 简化实现 | claim_type 字段存在，但前端未突出展示 |

---

## 4. 溯源规则

### 4.1 引用要求实现状态

| 要求 | Design.md 要求 | 当前实现 | Gap |
|------|----------------|----------|-----|
| 每个事实必须追溯 | 至少一个 source_ref | ✅ 已实现 | - |
| source_ref 必填 | document_id | ✅ 已实现 | - |
| 正式页面要求 | fragment_id/file_name/anchor_label/quote | ✅ 已实现 | - |
| 脚注给人阅读 | 页面正文脚注 | ❌ **未实现** | Wiki 页面未生成脚注 |
| source_refs 给程序 | frontmatter/section | ✅ 已实现 | - |

---

## 5. 功能模块对比

### 5.1 IngestAgent

| 功能 | Design.md 要求 | 当前实现 | 完成度 |
|------|----------------|----------|--------|
| 文档识别 | 5类文档 + 关键信息 | 基本实现 | 70% |
| 片段切分 | 章节/页码/fragment/锚点 | 完整实现 | 100% |
| 对象抽取 | 6类对象 | 4类实现 | 60% |
| 关系建立 | 6种关系 | 3种实现 | 50% |
| 审批包生成 | 完整审批包结构 | 完整实现 | 100% |
| 冲突检测 | 检测冲突 | 简化实现 | 40% |
| 缺口分析 | 识别缺口 | 简化实现 | 50% |

### 5.2 QueryAgent

| 功能 | Design.md 要求 | 当前实现 | 完成度 |
|------|----------------|----------|--------|
| 索引召回 | 基于 pages.jsonl | 完整实现 | 100% |
| 受控上下文 | 只加载候选页面 | 完整实现 | 100% |
| 结构化关系引用 | 优先引用关系 | 完整实现 | 100% |
| 溯源支持 | 返回 citations | 完整实现 | 100% |
| 归档功能 | 问答归档为 Wiki | 完整实现 | 100% |

### 5.3 LintAgent

| 功能 | Design.md 要求 | 当前实现 | 完成度 |
|------|----------------|----------|--------|
| 矛盾检测 | 实体描述冲突 | 基本实现 | 70% |
| 过时检测 | 基于更新日期 | 完整实现 | 100% |
| 孤儿页检测 | 无入链页面 | 完整实现 | 100% |
| 缺失引用检测 | 无 source_refs | 完整实现 | 100% |
| 断裂链接检测 | 指向不存在页面 | 完整实现 | 100% |
| LLM 深度分析 | 重复/合并/缺失建议 | 简化实现 | 60% |
| 交互式修复 | 人工确认后修复 | 完整实现 | 100% |

---

## 6. UI/前端 Gap

### 6.1 审批界面

| Design.md 要求 | 当前实现 | Gap |
|----------------|----------|-----|
| 展示文档是什么 | ✅ 已实现 | - |
| 展示拆出的关键对象 | ⚠️ 部分实现 | 对象列表展示较简单 |
| 展示关键映射和关系 | ⚠️ 部分实现 | 关系展示缺少可视化 |
| 展示无法自动确认的问题 | ⚠️ 部分实现 | human_questions 已展示 |
| **证据片段直接展示** | ❌ **未实现** | 需增加原文片段引用 |
| **高风险标记突出显示** | ❌ **未实现** | 需增加视觉区分 |

### 6.2 其他界面

| 界面 | 实现状态 | 说明 |
|------|----------|------|
| Dashboard | ✅ 已实现 | 总览、Agent 状态、指标 |
| 摄入审核 | ✅ 已实现 | 审批包列表、审批操作 |
| Wiki 浏览 | ✅ 已实现 | 页面列表、详情 |
| 知识问答 | ✅ 已实现 | 提问、回答、引用 |
| 健康中心 | ✅ 已实现 | 问题列表、扫描 |
| 设置/导出 | ✅ 已实现 | 映射矩阵、Slides 大纲 |

---

## 7. 优先级排序的改进建议

### 🔴 P0 - 关键 Gap（影响核心流程）

1. **六类对象完整实现**
   - 补充 regulation_clause、pep_node、concept 的抽取
   - 使用 LLM 替代规则抽取

2. **完整关系类型实现**
   - 补充 implements、references、constrains 关系
   - 支持跨文档关系识别

3. **审批界面增强**
   - 证据片段直接展示
   - 高风险关系突出标记

### 🟡 P1 - 重要 Gap（影响使用体验）

4. **冲突检测增强**
   - 检测同一要求在不同文档中的描述差异
   - 检测对象定义冲突

5. **缺口分析增强**
   - 识别法规要求未在内部流程中实现的情况
   - 识别缺失的交付物

6. **溯源脚注生成**
   - Wiki 页面正文生成人读脚注

### 🟢 P2 - 优化项（提升质量）

7. **文档信息提取完善**
   - 提取发布时间、适用范围
   - 增强权威级别判断

8. **LLM 深度分析增强**
   - 重复页面检测
   - 合并建议生成

9. **对象合并审批**
   - 语义等价判断界面
   - 高风险对象合并确认

---

## 8. 总结

### 整体完成度评估

| 模块 | 完成度 | 状态 |
|------|--------|------|
| 核心架构 | 95% | ✅ 成熟 |
| 文档摄入流程 | 75% | ⚠️ 可用，需增强对象和关系抽取 |
| 审批机制 | 85% | ✅ 基本成熟，界面需优化 |
| 问答系统 | 90% | ✅ 成熟 |
| 健康检查 | 85% | ✅ 基本成熟 |
| 前端界面 | 80% | ⚠️ 功能完整，体验需优化 |

### 关键结论

1. **核心流程已跑通**：从文档上传到审批发布的完整链路已实现
2. **对象和关系抽取是主要 Gap**：当前规则-based 实现需升级为 LLM-based
3. **审批界面需增强**：证据展示和高风险标记是优先改进点
4. **跨文档能力待加强**：implements/references 等关系需要跨文档支持

### 下一步建议

1. 短期（1-2周）：优化审批界面，增加证据片段展示
2. 中期（1个月）：升级对象抽取为 LLM-based，完整支持六类对象
3. 长期（2个月）：实现跨文档关系识别，增强冲突和缺口检测
