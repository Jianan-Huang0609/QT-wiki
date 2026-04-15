const state = {
  loading: false,
  uploading: false,
  citations: [],
  matchedPages: [],
  pendingProposals: [],
};

const messagesEl = document.getElementById("messages");
const evidenceListEl = document.getElementById("evidence-list");
const pageListEl = document.getElementById("page-list");
const proposalListEl = document.getElementById("proposal-list");
const formEl = document.getElementById("chat-form");
const questionInputEl = document.getElementById("question-input");
const submitButtonEl = document.getElementById("submit-button");
const healthPillEl = document.getElementById("health-pill");
const healthTextEl = document.getElementById("health-text");
const llmToggleEl = document.getElementById("llm-toggle");
const reindexButtonEl = document.getElementById("reindex-button");
const pagesRangeEl = document.getElementById("pages-range");
const citationsRangeEl = document.getElementById("citations-range");
const pagesRangeValueEl = document.getElementById("pages-range-value");
const citationsRangeValueEl = document.getElementById("citations-range-value");
const metricPagesEl = document.getElementById("metric-pages");
const metricCitationsEl = document.getElementById("metric-citations");
const metricConfidenceEl = document.getElementById("metric-confidence");
const metricLlmEl = document.getElementById("metric-llm");
const citationCountBadgeEl = document.getElementById("citation-count-badge");
const pageCountBadgeEl = document.getElementById("page-count-badge");
const pendingCountBadgeEl = document.getElementById("pending-count-badge");
const pendingRefreshButtonEl = document.getElementById("pending-refresh-button");
const uploadFormEl = document.getElementById("upload-form");
const uploadFileEl = document.getElementById("upload-file");
const uploadUseLlmEl = document.getElementById("upload-use-llm");
const uploadAutoPublishEl = document.getElementById("upload-auto-publish");
const uploadAutoApproveSmallEl = document.getElementById("upload-auto-approve-small");
const uploadButtonEl = document.getElementById("upload-button");
const uploadNoteEl = document.getElementById("upload-note");
const messageTemplate = document.getElementById("message-template");

bootstrap();

function bootstrap() {
  seedWelcome();
  bindEvents();
  refreshHealth();
  refreshPendingProposals({ silent: true });
}

function seedWelcome() {
  addMessage({
    role: "assistant",
    label: "系统前言",
    html: "<p>你可以直接提问制度、职责、流程、风险控制等问题。</p><p>回答会优先引用右侧证据卡片，而不是空泛生成。</p><p>右侧新增的待审核提案面板，会直接展示审核理由和工具轨迹，方便人工复核。</p>",
  });
}

function bindEvents() {
  formEl.addEventListener("submit", onSubmit);
  uploadFormEl.addEventListener("submit", onUploadSubmit);

  questionInputEl.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      formEl.requestSubmit();
    }
  });

  document.querySelectorAll(".prompt-chip").forEach((button) => {
    button.addEventListener("click", () => {
      questionInputEl.value = button.dataset.question || "";
      questionInputEl.focus();
    });
  });

  pagesRangeEl.addEventListener("input", () => {
    pagesRangeValueEl.textContent = pagesRangeEl.value;
  });

  citationsRangeEl.addEventListener("input", () => {
    citationsRangeValueEl.textContent = citationsRangeEl.value;
  });

  reindexButtonEl.addEventListener("click", async () => {
    reindexButtonEl.disabled = true;
    reindexButtonEl.textContent = "索引刷新中";
    try {
      const response = await fetch("/chat/reindex", { method: "POST" });
      if (!response.ok) {
        throw new Error("索引刷新失败");
      }
      const payload = await response.json();
      toast(`索引已刷新：页面 ${payload.pages} / 文档 ${payload.documents} / 片段 ${payload.fragments}`);
      await refreshHealth();
      await refreshPendingProposals({ silent: true });
    } catch (error) {
      toast(error.message || "索引刷新失败");
    } finally {
      reindexButtonEl.disabled = false;
      reindexButtonEl.textContent = "重建索引";
    }
  });

  pendingRefreshButtonEl.addEventListener("click", async () => {
    await refreshPendingProposals();
  });

  document.addEventListener("click", (event) => {
    const citationTarget = event.target.closest(".citation-link");
    if (citationTarget) {
      event.preventDefault();
      highlightCitation(citationTarget.dataset.citationId);
      return;
    }

    const approveButton = event.target.closest(".proposal-approve");
    if (approveButton) {
      event.preventDefault();
      onApproveProposal(approveButton.dataset.proposalId, approveButton);
    }
  });
}

async function refreshHealth() {
  try {
    const response = await fetch("/health");
    if (!response.ok) {
      throw new Error("服务未响应");
    }
    const payload = await response.json();
    if (payload.status === "ok") {
      healthPillEl.classList.add("online");
      healthPillEl.classList.remove("offline");
      healthTextEl.textContent = "服务在线，可直接提问";
      return;
    }
    throw new Error("状态异常");
  } catch (_) {
    healthPillEl.classList.add("offline");
    healthPillEl.classList.remove("online");
    healthTextEl.textContent = "服务离线，请先启动 App.api";
  }
}

async function onUploadSubmit(event) {
  event.preventDefault();
  if (state.uploading) {
    return;
  }

  const selectedFile = uploadFileEl.files && uploadFileEl.files[0];
  if (!selectedFile) {
    toast("请先选择要上传的文档");
    return;
  }

  setUploading(true);

  try {
    const formData = new FormData();
    formData.append("file", selectedFile);
    formData.append("use_llm", String(uploadUseLlmEl.checked));
    formData.append("auto_publish_low_risk", String(uploadAutoPublishEl.checked));
    formData.append("auto_approve_small_changes", String(uploadAutoApproveSmallEl.checked));

    const response = await fetch("/agent/upload", {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(await readError(response));
    }

    const result = await response.json();
    uploadFileEl.value = "";
    uploadNoteEl.textContent = `最近一次运行：${result.run_id}，发布页面 ${result.pages_published} 个，待审核 ${result.pending_review_count} 个`;

    addMessage({
      role: "assistant",
      label: "Agent 维护完成",
      html: [
        `<p>文件 <strong>${escapeHtml(result.file_name)}</strong> 已上传并维护完成。</p>`,
        `<p>run_id: ${escapeHtml(result.run_id)} | 解析文档: ${Number(result.documents_parsed)} | 生成提案: ${Number(result.proposals_created)} | 发布页面: ${Number(result.pages_published)} | 待审核: ${Number(result.pending_review_count)}</p>`,
        `<p>工作流引擎：${escapeHtml(result.workflow_engine)}</p>`,
      ].join(""),
    });
    toast("上传成功，Wiki 已自动维护并刷新检索索引");
    await refreshHealth();
    await refreshPendingProposals({ silent: true });
  } catch (error) {
    toast(error.message || "上传失败");
  } finally {
    setUploading(false);
  }
}

async function onSubmit(event) {
  event.preventDefault();
  if (state.loading) {
    return;
  }

  const question = questionInputEl.value.trim();
  if (!question) {
    questionInputEl.focus();
    return;
  }

  addMessage({ role: "user", label: "你的问题", text: question });
  questionInputEl.value = "";
  setLoading(true);
  const loadingNode = addLoadingMessage();

  try {
    const payload = {
      question,
      use_llm: llmToggleEl.checked,
      top_k_pages: Number(pagesRangeEl.value),
      top_k_citations: Number(citationsRangeEl.value),
    };

    const response = await fetch("/chat/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      throw new Error(await readError(response));
    }

    const result = await response.json();
    state.citations = result.citations || [];
    state.matchedPages = result.matched_pages || [];

    loadingNode.remove();
    addMessage({
      role: "assistant",
      label: buildAssistantLabel(result),
      html: formatAnswer(result.answer, state.citations),
    });
    renderEvidence(state.citations);
    renderMatchedPages(state.matchedPages);
    updateMetrics(result);
  } catch (error) {
    loadingNode.remove();
    addMessage({
      role: "assistant",
      label: "系统提示",
      html: `<p>${escapeHtml(error.message || "请求失败")}</p>`,
    });
  } finally {
    setLoading(false);
  }
}

async function readError(response) {
  try {
    const payload = await response.json();
    if (payload && typeof payload.detail === "string" && payload.detail) {
      return payload.detail;
    }
  } catch (_) {
    // ignore parsing failure
  }
  return `请求失败（HTTP ${response.status}）`;
}

function addMessage({ role, label, text = "", html = "" }) {
  const node = messageTemplate.content.firstElementChild.cloneNode(true);
  node.classList.add(role);
  node.querySelector(".message-meta").textContent = label;
  const body = node.querySelector(".message-body");
  if (html) {
    body.innerHTML = html;
  } else {
    body.innerHTML = formatPlainText(text);
  }
  messagesEl.appendChild(node);
  messagesEl.scrollTop = messagesEl.scrollHeight;
  return node;
}

function addLoadingMessage() {
  return addMessage({
    role: "assistant",
    label: "系统正在组织证据",
    html: '<div class="loading-ribbon"><span></span><span></span><span></span> 正在检索页面与片段</div>',
  });
}

function setLoading(loading) {
  state.loading = loading;
  submitButtonEl.disabled = loading;
  submitButtonEl.textContent = loading ? "处理中" : "发送问题";
}

function setUploading(uploading) {
  state.uploading = uploading;
  uploadButtonEl.disabled = uploading;
  uploadButtonEl.textContent = uploading ? "处理中" : "上传并维护";
  if (uploading) {
    uploadNoteEl.textContent = "正在上传并触发 Agent 自动维护，请稍候...";
  } else if (!uploadNoteEl.textContent.trim()) {
    uploadNoteEl.textContent = "支持文件类型：.docx / .pdf / .pptx / .xlsx";
  }
}

function renderEvidence(citations) {
  evidenceListEl.innerHTML = "";
  citationCountBadgeEl.textContent = String(citations.length);

  if (!citations.length) {
    evidenceListEl.innerHTML = '<div class="empty-state small">这次回答没有返回可引用片段。</div>';
    return;
  }

  citations.forEach((citation) => {
    const card = document.createElement("article");
    card.className = "evidence-card";
    card.id = `citation-${citation.citation_id}`;
    card.innerHTML = `
      <div class="evidence-top">
        <div>
          <div class="citation-tag">${escapeHtml(citation.citation_id)}</div>
          <h4 class="evidence-title">${escapeHtml(citation.page_title)}</h4>
        </div>
        <div class="evidence-meta">${escapeHtml(citation.file_name)}<br />${escapeHtml(citation.anchor_label)}</div>
      </div>
      <p class="evidence-quote">${escapeHtml(citation.quote)}</p>
    `;
    evidenceListEl.appendChild(card);
  });
}

function renderMatchedPages(pages) {
  pageListEl.innerHTML = "";
  pageCountBadgeEl.textContent = String(pages.length);

  if (!pages.length) {
    pageListEl.innerHTML = '<div class="empty-state small">当前问题没有命中任何 Wiki 页面。</div>';
    return;
  }

  pages.forEach((page) => {
    const card = document.createElement("article");
    card.className = "page-card";
    card.innerHTML = `
      <div class="page-top">
        <div>
          <h4 class="page-title">${escapeHtml(page.title)}</h4>
          <div class="page-summary">${escapeHtml(page.summary || "该页面没有摘要")}</div>
        </div>
        <div class="page-type-pill">${escapeHtml(page.page_type)}</div>
      </div>
      <div class="evidence-meta">检索分数：${Number(page.score).toFixed(2)}</div>
    `;
    pageListEl.appendChild(card);
  });
}

async function refreshPendingProposals(options = {}) {
  const { silent = false } = options;
  pendingRefreshButtonEl.disabled = true;
  pendingRefreshButtonEl.textContent = "刷新中";
  try {
    const response = await fetch("/agent/proposals/pending");
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const payload = await response.json();
    state.pendingProposals = payload.items || [];
    renderPendingProposals(state.pendingProposals);
    if (!silent) {
      toast(`待审核提案已刷新：${state.pendingProposals.length} 个`);
    }
  } catch (error) {
    if (!silent) {
      toast(error.message || "待审核提案刷新失败");
    }
  } finally {
    pendingRefreshButtonEl.disabled = false;
    pendingRefreshButtonEl.textContent = "刷新";
  }
}

function renderPendingProposals(proposals) {
  proposalListEl.innerHTML = "";
  pendingCountBadgeEl.textContent = String(proposals.length);

  if (!proposals.length) {
    proposalListEl.innerHTML = '<div class="empty-state small">暂无待审核提案。</div>';
    return;
  }

  proposals.forEach((proposal) => {
    const card = document.createElement("article");
    card.className = "proposal-card";
    card.innerHTML = `
      <div class="proposal-top">
        <div>
          <div class="proposal-id">${escapeHtml(proposal.proposal_id)}</div>
          <h4 class="proposal-title">${escapeHtml(proposal.target_page_id)}</h4>
        </div>
        <div class="proposal-badges">
          <span class="proposal-badge risk-${escapeHtml(proposal.risk_level)}">${escapeHtml(humanizeRisk(proposal.risk_level))}</span>
          <span class="proposal-badge">${escapeHtml(humanizeScope(proposal.change_scope))}</span>
        </div>
      </div>
      <div class="proposal-meta">动作：${escapeHtml(proposal.action)} · 审核方式：${escapeHtml(humanizeReviewMode(proposal.review_mode))}</div>
      <div class="proposal-block">
        <div class="proposal-label">提案原因</div>
        <p>${escapeHtml(proposal.reason || "未提供")}</p>
      </div>
      <div class="proposal-block">
        <div class="proposal-label">审核理由</div>
        <p>${escapeHtml(proposal.review_notes || "未提供")}</p>
      </div>
      <div class="proposal-block">
        <div class="proposal-label">来源文档</div>
        <div class="inline-list">${formatInlineList(proposal.source_document_ids, "暂无")}</div>
      </div>
      <div class="proposal-block">
        <div class="proposal-label">工具轨迹</div>
        <div class="trace-list">${formatTraceList(proposal.tool_trace)}</div>
      </div>
      <details class="proposal-details">
        <summary>查看候选内容</summary>
        <pre>${escapeHtml(truncateText(proposal.candidate_content || "暂无内容", 1200))}</pre>
      </details>
      <button class="primary-button proposal-approve" type="button" data-proposal-id="${escapeHtml(proposal.proposal_id)}">批准发布</button>
    `;
    proposalListEl.appendChild(card);
  });
}

async function onApproveProposal(proposalId, buttonEl) {
  if (!proposalId || !buttonEl) {
    return;
  }
  buttonEl.disabled = true;
  buttonEl.textContent = "发布中";
  try {
    const response = await fetch(`/agent/proposals/${encodeURIComponent(proposalId)}/approve`, {
      method: "POST",
    });
    if (!response.ok) {
      throw new Error(await readError(response));
    }
    const result = await response.json();
    addMessage({
      role: "assistant",
      label: "人工审核完成",
      html: [
        `<p>提案 <strong>${escapeHtml(result.proposal_id)}</strong> 已批准发布。</p>`,
        `<p>目标页面：${escapeHtml(result.target_page_id)} | 审核方式：${escapeHtml(result.review_mode)}</p>`,
        `<p>审核结论：${escapeHtml(result.review_notes || "人工审核通过")}</p>`,
      ].join(""),
    });
    toast(`提案 ${proposalId} 已发布`);
    await refreshPendingProposals({ silent: true });
    await refreshHealth();
  } catch (error) {
    toast(error.message || "批准提案失败");
  } finally {
    buttonEl.disabled = false;
    buttonEl.textContent = "批准发布";
  }
}

function updateMetrics(result) {
  metricPagesEl.textContent = String((result.matched_pages || []).length);
  metricCitationsEl.textContent = String((result.citations || []).length);
  metricConfidenceEl.textContent = humanizeConfidence(result.confidence);
  metricLlmEl.textContent = result.used_llm ? "是" : "否";
}

function buildAssistantLabel(result) {
  return `回答完成 · ${humanizeConfidence(result.confidence)}置信度 · ${result.used_llm ? "LLM 已参与" : "规则式回答"}`;
}

function humanizeConfidence(confidence) {
  if (confidence === "high") return "高";
  if (confidence === "medium") return "中";
  return "低";
}

function humanizeRisk(risk) {
  if (risk === "high") return "高风险";
  if (risk === "medium") return "中风险";
  return "低风险";
}

function humanizeScope(scope) {
  if (scope === "large") return "大改动";
  if (scope === "medium") return "中改动";
  return "小改动";
}

function humanizeReviewMode(mode) {
  if (mode === "manual") return "人工已通过";
  if (mode === "auto") return "自动推进";
  return "人工审核";
}

function formatAnswer(answer, citations) {
  const paragraphs = escapeHtml(answer).split(/\n{2,}|\r\n{2,}/).map((block) => block.trim()).filter(Boolean);
  const citationIds = new Set(citations.map((item) => item.citation_id));
  return paragraphs.map((paragraph) => {
    const withBreaks = paragraph.replace(/\n/g, "<br />");
    return `<p>${withBreaks.replace(/\[(c\d+)\]/g, (match, id) => {
      if (!citationIds.has(id)) {
        return match;
      }
      return `<a href="#citation-${id}" class="citation-link" data-citation-id="${id}">[${id}]</a>`;
    })}</p>`;
  }).join("");
}

function formatPlainText(text) {
  return text
    .split(/\n+/)
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => `<p>${escapeHtml(line)}</p>`)
    .join("");
}

function formatInlineList(values, fallback) {
  if (!Array.isArray(values) || !values.length) {
    return `<span class="empty-inline">${escapeHtml(fallback)}</span>`;
  }
  return values.map((value) => `<span class="inline-chip">${escapeHtml(value)}</span>`).join("");
}

function formatTraceList(values) {
  if (!Array.isArray(values) || !values.length) {
    return '<span class="empty-inline">暂无工具轨迹</span>';
  }
  return values.map((value) => `<span class="trace-chip">${escapeHtml(value)}</span>`).join("");
}

function truncateText(text, maxLength) {
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength)}\n\n...`;
}

function highlightCitation(citationId) {
  const target = document.getElementById(`citation-${citationId}`);
  if (!target) {
    return;
  }
  document.querySelectorAll(".evidence-card.is-highlighted").forEach((card) => card.classList.remove("is-highlighted"));
  target.classList.add("is-highlighted");
  target.scrollIntoView({ behavior: "smooth", block: "center" });
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function toast(message) {
  addMessage({
    role: "assistant",
    label: "系统提示",
    html: `<p>${escapeHtml(message)}</p>`,
  });
}
