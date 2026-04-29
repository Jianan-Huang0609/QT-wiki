# Changelog

## 2026-04-29

- 新增根目录 `CHANGELOG.md`，用于按日期记录后续变更。
- 为 Wiki 模型层新增最小审批包结构：`DocumentIdentity`、`ReviewObject`、`ReviewRelation`、`ReviewIssue`、`HumanReviewQuestion`、`ReviewPackage`。
- 为存储层新增审批包 JSON 和 Obsidian Markdown 输出目录与读写接口。
- Ingest 流程现在会在生成候选页面的同时生成一个最小审批包，先覆盖文档身份、证据摘要、风险提示和待人工确认问题。
- 新增审批包相关测试，覆盖保存/加载和 Ingest 构建审批包的基础行为。
- 新增 `/api/ingest/review-packages` 接口，后端可返回审批包列表供前端审阅。
- 前端 Ingest 视图改为以审批包为主视图，展示文档身份、人工关口、风险问题和关联候选页。
- 候选页批准/拒绝动作暂时保留原逻辑，审批包先承担“确认关键判断”的工作台角色。
- 为审批包新增关口 1 决策字段：`identity_decision`、确认后的业务类型/效力/强约束、审核备注、审核人、审核时间。
- 新增审批包决策写回能力和 `/api/ingest/review-packages/{package_id}/decision` 接口，文档身份确认不再只是只读展示。
- 前端 Ingest 页面新增文档身份确认表单，支持确认或退回重判，并展示已确认结果。
- 候选页发布新增前置约束：对应审批包的文档身份未确认时，前端禁用发布按钮，后端 API 也会返回 `409` 拒绝发布。
- 为审批包补齐最小对象抽取，当前会规则提取 `requirement`、`process_step`、`record`、`role` 四类对象，并绑定来源片段。
- `/api/ingest/review-packages` 现在会返回 `extracted_objects`，前端 Ingest 页面新增“抽取对象”区块用于审阅。
- 新增对象抽取和 API 兼容性测试，确认最小对象层已进入可审状态。
- 为审批包补齐最小关系抽取，当前会规则生成 `requires`、`produces`、`responsible_for` 三类关系，并绑定来源片段。
- 新增关系决策关口和 `/api/ingest/review-packages/{package_id}/relations/decision` 接口，关键关系现在可以正式确认或退回重判。
- 候选页发布条件升级为“双关口”通过：文档身份已确认，且关键关系已确认或无关系需要确认。
- 前端 Ingest 页面新增“抽取关系”与关系审核区块，支持在发布前完成人工映射确认。
- QueryAgent 现在会直接消费已批准审批包中的结构化对象与关系；`/chat/query` 返回 `structured_matches`，并把审批包证据补进 citations。
- 新增 `App/agents/structured_knowledge.py`，统一承载已批准审批包筛选、关系展开、问题上下文构建、映射矩阵和 slides 提纲生成逻辑。
- 新增导出接口 `/api/exports/mapping-matrix` 与 `/api/exports/slides-outline`，导出源只使用已批准审批包，可直接复用为法规-流程映射和汇报提纲底稿。
- 前端 Ingest 页补齐关口 2：支持关键关系审核、显示关系决策状态，并把候选页发布按钮切换为“文档身份 + 关系确认”双关口控制。
- 前端 Query / Settings 页补齐结构化消费与导出预览：查询结果展示命中的审批包，设置页可直接拉取映射矩阵和 slides 提纲。
- 新增回归测试，覆盖关系关口发布约束、结构化 Query 返回、映射矩阵导出和 slides 提纲导出；当前验证结果为 `15 passed`，`npx tsc --noEmit` 通过。
- 修复前端“看起来没用到 LLM / 反馈不真实”的问题：默认开启 LLM、Ingest 页显式展示 LLM 开关、Query 结果按实际 `used_llm` 显示，不再把请求开关误当成真实执行结果。
- 修复前端静默吞错并回退 mock 的问题：API 失败现在直接返回真实错误信息，控制台会明确提示后端错误而不是假装成功。
- 修复 `dashboard` 被空 JSON / 损坏 JSON 页面文件打崩的问题：`wiki.store.files.load_all_pages()` 与 `list_review_packages()` 现在会跳过无效文件并打印告警。
- 新增回归测试覆盖无效页面 JSON 跳过逻辑；当前验证结果升级为 `16 passed`，`npx tsc --noEmit` 通过。
