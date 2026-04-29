import type {
  AgentSummary,
  CandidatePage,
  Citation,
  IndexStatus,
  LintIssue,
  MatchedPage,
  QueryResult,
  ReviewPackage,
  WikiPage
} from "./types";

export const mockAgents: AgentSummary[] = [
  {
    key: "ingest",
    name: "IngestAgent",
    status: "ready",
    headline: "2 个候选页等待审核",
    queue: 2,
    lastRun: "2026-04-27 15:20",
    accent: "teal"
  },
  {
    key: "query",
    name: "QueryAgent",
    status: "ready",
    headline: "索引召回已启用",
    queue: 0,
    lastRun: "2026-04-27 15:31",
    accent: "blue"
  },
  {
    key: "lint",
    name: "LintAgent",
    status: "blocked",
    headline: "3 个健康问题待处理",
    queue: 3,
    lastRun: "2026-04-27 14:56",
    accent: "amber"
  }
];

export const mockIndexStatus: IndexStatus = {
  state: "fresh",
  pages: 38,
  terms: 216,
  sources: 492,
  lastBuilt: "2026-04-27 15:30"
};

export const mockCandidates: CandidatePage[] = [
  {
    candidate_id: "candidate-9fa583e5",
    document_ids: ["doc-20260421103742-c60d5225"],
    page_type: "process",
    title: "文件和数据管理",
    status: "pending",
    confidence: 0.91,
    summary: "文件和数据管理页面沉淀文件控制、记录保存、电子记录和数据完整性的要求。",
    keywords: ["文件控制", "电子记录", "数据完整性"],
    related_titles: ["质量管理体系", "风险管理"],
    source_refs: [
      {
        document_id: "doc-20260421103742-c60d5225",
        fragment_id: "frag-44",
        file_name: "新版生产质量管理规范.pdf",
        anchor_label: "p.44",
        quote: "企业应当建立文件控制程序，并保存与产品质量相关的记录。"
      }
    ]
  },
  {
    candidate_id: "candidate-a55a15a8",
    document_ids: ["doc-20260421103743-e6664545"],
    page_type: "role",
    title: "放行审核人职责",
    status: "pending",
    confidence: 0.84,
    summary: "放行审核人负责确认检验记录、偏差处置和放行条件是否满足要求。",
    keywords: ["放行审核", "检验记录", "偏差处置"],
    related_titles: ["产品放行", "质量控制"],
    source_refs: [
      {
        document_id: "doc-20260421103743-e6664545",
        fragment_id: "frag-18",
        file_name: "P020251106552222183224.docx",
        anchor_label: "para.18",
        quote: "放行审核人应当确认检验记录和偏差处置结果。"
      }
    ]
  }
];

export const mockReviewPackages: ReviewPackage[] = [
  {
    package_id: "review-doc-20260421103742-c60d5225",
    document_id: "doc-20260421103742-c60d5225",
    status: "pending_review",
    identity_decision: "pending",
    title: "新版生产质量管理规范",
    business_type: "external_mandatory",
    effective_level: "external_mandatory",
    version: "2025",
    scope: "文件控制 / 数据完整性",
    is_binding: true,
    confidence: 0.92,
    notes: [],
    confirmed_business_type: "",
    confirmed_effective_level: "",
    confirmed_is_binding: null,
    review_notes: "",
    reviewed_at: "",
    reviewed_by: "",
    relation_decision: "pending",
    relation_review_notes: "",
    relation_reviewed_at: "",
    relation_reviewed_by: "",
    source_refs: [
      {
        document_id: "doc-20260421103742-c60d5225",
        fragment_id: "frag-44",
        file_name: "新版生产质量管理规范.pdf",
        anchor_label: "p.44",
        quote: "企业应当建立文件控制程序，并保存与产品质量相关的记录。"
      }
    ],
    issues: [],
    human_questions: [
      {
        question_id: "q-doc-identity",
        question: "这份文档的身份是否正确，属于法规、解读、内部受控文件、运行证据还是经验反馈？",
        rationale: "文档身份会直接决定后续结论能否作为要求使用。",
        target: "doc-20260421103742-c60d5225"
      }
    ],
    extracted_objects: [
      {
        object_id: "obj-1",
        object_type: "regulation_clause",
        name: "第三十六条",
        confidence: 0.92,
        review_risk: "high",
        evidence_refs: [
          {
            document_id: "doc-20260421103742-c60d5225",
            fragment_id: "frag-44",
            file_name: "新版生产质量管理规范.pdf",
            anchor_label: "p.44",
            quote: "企业应当建立文件控制程序，并保存与产品质量相关的记录。"
          }
        ]
      },
      {
        object_id: "obj-2",
        object_type: "process_step",
        name: "文件控制",
        confidence: 0.88,
        review_risk: "medium",
        evidence_refs: []
      },
      {
        object_id: "obj-3",
        object_type: "role",
        name: "质量负责人",
        confidence: 0.85,
        review_risk: "medium",
        evidence_refs: []
      },
      {
        object_id: "obj-4",
        object_type: "deliverable",
        name: "文件控制程序",
        confidence: 0.82,
        review_risk: "low",
        evidence_refs: []
      },
      {
        object_id: "obj-5",
        object_type: "concept",
        name: "数据完整性",
        confidence: 0.79,
        review_risk: "medium",
        evidence_refs: []
      }
    ],
    extracted_relations: [
      {
        relation_id: "rel-1",
        relation_type: "requires",
        from_object_id: "第三十六条",
        to_object_id: "文件控制",
        claim_type: "mandatory",
        direction: "forward",
        confidence: 0.91,
        human_required: true,
        evidence_refs: [
          {
            document_id: "doc-20260421103742-c60d5225",
            fragment_id: "frag-44",
            file_name: "新版生产质量管理规范.pdf",
            anchor_label: "p.44",
            quote: "企业应当建立文件控制程序，并保存与产品质量相关的记录。"
          }
        ]
      },
      {
        relation_id: "rel-2",
        relation_type: "responsible_for",
        from_object_id: "质量负责人",
        to_object_id: "文件控制",
        claim_type: "mandatory",
        direction: "forward",
        confidence: 0.78,
        human_required: false,
        evidence_refs: []
      },
      {
        relation_id: "rel-3",
        relation_type: "produces",
        from_object_id: "文件控制",
        to_object_id: "文件控制程序",
        claim_type: "mandatory",
        direction: "forward",
        confidence: 0.85,
        human_required: false,
        evidence_refs: []
      }
    ],
    candidate_page_titles: ["文件和数据管理"],
    tool_trace: ["App.agents.ingest_agent._build_review_package"]
  },
  {
    package_id: "review-doc-20260421103743-e6664545",
    document_id: "doc-20260421103743-e6664545",
    status: "pending_review",
    identity_decision: "pending",
    title: "质量管理体系培训讲义",
    business_type: "external_reference",
    effective_level: "reference_only",
    version: "",
    scope: "产品放行 / 放行审核",
    is_binding: false,
    confidence: 0.81,
    notes: ["当前文档更像解释性材料，不能直接等同于法规正文。"],
    confirmed_business_type: "",
    confirmed_effective_level: "",
    confirmed_is_binding: null,
    review_notes: "",
    reviewed_at: "",
    reviewed_by: "",
    relation_decision: "pending",
    relation_review_notes: "",
    relation_reviewed_at: "",
    relation_reviewed_by: "",
    source_refs: [
      {
        document_id: "doc-20260421103743-e6664545",
        fragment_id: "frag-18",
        file_name: "P020251106552222183224.docx",
        anchor_label: "para.18",
        quote: "放行审核人应当确认检验记录和偏差处置结果。"
      }
    ],
    issues: [
      {
        issue_id: "issue-guidance-boundary",
        issue_type: "boundary_risk",
        detail: "当前文档更像解读或培训材料，后续不得直接作为强制要求发布。",
        severity: "high"
      }
    ],
    human_questions: [
      {
        question_id: "q-authority-boundary",
        question: "这份文档中的结论哪些可以视为要求，哪些只能视为解释或建议？",
        rationale: "需要先定权威边界，才能继续做跨文档映射。",
        target: "external_reference"
      }
    ],
    extracted_objects: [
      {
        object_id: "obj-1",
        object_type: "role",
        name: "放行审核人",
        confidence: 0.88,
        review_risk: "medium",
        evidence_refs: [
          {
            document_id: "doc-20260421103743-e6664545",
            fragment_id: "frag-18",
            file_name: "P020251106552222183224.docx",
            anchor_label: "para.18",
            quote: "放行审核人应当确认检验记录和偏差处置结果。"
          }
        ]
      },
      {
        object_id: "obj-2",
        object_type: "process_step",
        name: "放行",
        confidence: 0.86,
        review_risk: "medium",
        evidence_refs: []
      },
      {
        object_id: "obj-3",
        object_type: "deliverable",
        name: "检验记录",
        confidence: 0.84,
        review_risk: "low",
        evidence_refs: []
      }
    ],
    extracted_relations: [
      {
        relation_id: "rel-1",
        relation_type: "responsible_for",
        from_object_id: "放行审核人",
        to_object_id: "放行",
        claim_type: "mandatory",
        direction: "forward",
        confidence: 0.87,
        human_required: false,
        evidence_refs: []
      }
    ],
    candidate_page_titles: ["放行审核人职责"],
    tool_trace: ["App.agents.ingest_agent._build_review_package"]
  }
];

export const mockWikiPages: WikiPage[] = [
  {
    page_id: "质量管理体系",
    title: "质量管理体系",
    page_type: "concept",
    review_status: "published",
    summary: "质量管理体系覆盖医疗器械生产全过程，是组织职责、文件数据、设备、采购、生产、放行和改进活动的总框架。",
    aliases: ["QMS"],
    linked_pages: ["风险管理", "文件和数据管理", "产品放行"],
    updated_at: "2026-04-27T15:18:00",
    source_refs: [
      {
        document_id: "doc-20260421103742-c60d5225",
        fragment_id: "frag-1",
        file_name: "新版生产质量管理规范.pdf",
        anchor_label: "p.8",
        quote: "企业应当建立质量管理体系并保持其有效性。"
      }
    ],
    markdown:
      "# 质量管理体系\n\n## 摘要\n\n质量管理体系覆盖医疗器械生产全过程，是组织职责、文件数据、设备、采购、生产、放行和改进活动的总框架。\n\n## 核心依据\n\n- 企业应当建立质量管理体系并保持其有效性。[^src-1]\n\n## 关联页面\n\n- [[风险管理]]\n- [[文件和数据管理]]\n- [[产品放行]]\n\n## 引用来源\n\n[^src-1]: `doc-20260421103742-c60d5225 / frag-1 / p.8 / 新版生产质量管理规范.pdf`"
  },
  {
    page_id: "风险管理",
    title: "风险管理",
    page_type: "concept",
    review_status: "published",
    summary: "风险管理应贯穿产品全生命周期，并与质量管理体系的分析、改进和变更活动联动。",
    aliases: ["质量风险管理"],
    linked_pages: ["质量管理体系"],
    updated_at: "2026-04-27T15:12:00",
    source_refs: [
      {
        document_id: "doc-20260421103742-c60d5225",
        fragment_id: "frag-2",
        file_name: "新版生产质量管理规范.pdf",
        anchor_label: "p.11",
        quote: "风险管理应当贯穿产品全生命周期。"
      }
    ],
    markdown:
      "# 风险管理\n\n## 摘要\n\n风险管理应贯穿产品全生命周期，并与质量管理体系的分析、改进和变更活动联动。\n\n## 核心依据\n\n- 风险管理应当贯穿产品全生命周期。[^src-1]\n\n## 引用来源\n\n[^src-1]: `doc-20260421103742-c60d5225 / frag-2 / p.11 / 新版生产质量管理规范.pdf`"
  },
  {
    page_id: "产品放行",
    title: "产品放行",
    page_type: "process",
    review_status: "published",
    summary: "产品放行要求审核检验记录、偏差处置、批生产记录和放行条件。",
    aliases: ["放行审核"],
    linked_pages: ["放行审核人职责", "质量管理体系"],
    updated_at: "2026-04-27T14:44:00",
    source_refs: [
      {
        document_id: "doc-20260421103743-e6664545",
        fragment_id: "frag-18",
        file_name: "P020251106552222183224.docx",
        anchor_label: "para.18",
        quote: "放行审核人应当确认检验记录和偏差处置结果。"
      }
    ],
    markdown:
      "# 产品放行\n\n## 摘要\n\n产品放行要求审核检验记录、偏差处置、批生产记录和放行条件。\n\n## 放行依据\n\n- 放行审核人应当确认检验记录和偏差处置结果。[^src-1]\n\n## 引用来源\n\n[^src-1]: `doc-20260421103743-e6664545 / frag-18 / para.18 / P020251106552222183224.docx`"
  }
];

export const mockMatchedPages: MatchedPage[] = [
  {
    page_id: "质量管理体系",
    title: "质量管理体系",
    page_type: "concept",
    summary: mockWikiPages[0].summary,
    score: 15.5
  },
  {
    page_id: "风险管理",
    title: "风险管理",
    page_type: "concept",
    summary: mockWikiPages[1].summary,
    score: 9.5
  }
];

export const mockCitations: Citation[] = [
  {
    citation_id: "c1",
    page_title: "质量管理体系",
    file_name: "新版生产质量管理规范.pdf",
    anchor_label: "p.8",
    quote: "企业应当建立质量管理体系并保持其有效性。",
    document_id: "doc-20260421103742-c60d5225",
    fragment_id: "frag-1"
  },
  {
    citation_id: "c2",
    page_title: "风险管理",
    file_name: "新版生产质量管理规范.pdf",
    anchor_label: "p.11",
    quote: "风险管理应当贯穿产品全生命周期。",
    document_id: "doc-20260421103742-c60d5225",
    fragment_id: "frag-2"
  }
];

export const mockQueryResult: QueryResult = {
  answer:
    "根据当前 Wiki，质量管理体系是医疗器械生产全过程的总框架，企业需要建立并持续保持其有效性。[c1]\n\n风险管理不是孤立活动，它应贯穿产品全生命周期，并与质量管理体系中的分析、改进和变更活动联动。[c2]",
  confidence: "high",
  used_llm: false,
  matched_pages: mockMatchedPages,
  citations: mockCitations,
  trace: ["load pages.jsonl", "rank top 5 pages", "load WikiPage JSON", "attach source_refs"],
  structured_matches: [
    {
      package_id: "review-doc-20260421103742-c60d5225",
      document_id: "doc-20260421103742-c60d5225",
      title: "新版生产质量管理规范",
      business_type: "external_mandatory",
      relation_count: 3,
      object_count: 5,
      source_refs: mockReviewPackages[0].source_refs
    }
  ]
};

export const mockIssues: LintIssue[] = [
  {
    issue_id: "lint-001",
    type: "missing_source",
    title: "页面缺少 fragment_id",
    target: "文件和数据管理",
    severity: "high",
    detail: "页面有 document_id，但缺少可定位到原文段落的 fragment_id。",
    suggestion: "回查 Parsed 层并补齐 source_refs.fragment_id。",
    status: "open"
  },
  {
    issue_id: "lint-002",
    type: "broken_link",
    title: "关联页面不存在",
    target: "放行审核人职责 -> 质量控制",
    severity: "medium",
    detail: "linked_pages 指向了尚未发布的页面。",
    suggestion: "创建对应页面，或将链接改为现有页面。",
    status: "proposed"
  },
  {
    issue_id: "lint-003",
    type: "stale_page",
    title: "页面可能过期",
    target: "采购与原材料管理",
    severity: "medium",
    detail: "引用的 Raw 文档晚于页面更新时间。",
    suggestion: "运行增量更新并生成修订提案。",
    status: "open"
  }
];
