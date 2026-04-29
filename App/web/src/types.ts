import type { LucideIcon } from "lucide-react";

export type ViewKey = "dashboard" | "ingest" | "wiki" | "query" | "lint" | "settings";

export type AgentKey = "ingest" | "query" | "lint";

export type AgentStatus = "idle" | "running" | "blocked" | "ready";

export type RiskLevel = "low" | "medium" | "high";

export type ReviewStatus = "pending_review" | "published" | "approved" | "generated";

export interface NavItem {
  key: ViewKey;
  label: string;
  caption: string;
  icon: LucideIcon;
}

export interface AgentSummary {
  key: AgentKey;
  name: string;
  status: AgentStatus;
  headline: string;
  queue: number;
  lastRun: string;
  accent: "teal" | "amber" | "red" | "blue";
}

export interface SourceRef {
  document_id: string;
  fragment_id?: string;
  file_name?: string;
  anchor_label?: string;
  quote?: string;
}

export interface CandidatePage {
  candidate_id: string;
  document_ids: string[];
  page_type: string;
  title: string;
  status: "pending" | "approved" | "rejected";
  confidence: number;
  summary: string;
  keywords: string[];
  related_titles: string[];
  source_refs: SourceRef[];
}

export interface IngestRunSummary {
  run_id: string;
  document_id: string;
  file_name: string;
  review_package_id: string;
  candidate_ids: string[];
  pending_review_count: number;
  proposals_created: number;
  use_llm: boolean;
  created_at: string;
}

export interface ReviewPackageIssue {
  issue_id: string;
  issue_type: string;
  detail: string;
  severity: RiskLevel;
}

export interface ReviewPackageQuestion {
  question_id: string;
  question: string;
  rationale: string;
  target: string;
}

export interface ReviewPackageObject {
  object_id: string;
  object_type: string;
  name: string;
  confidence: number;
  review_risk: RiskLevel;
  evidence_refs: SourceRef[];
}

export interface ReviewPackageRelation {
  relation_id: string;
  relation_type: string;
  from_object_id: string;
  to_object_id: string;
  claim_type: "mandatory" | "recommendation" | "explanation";
  direction: "forward" | "reverse";
  confidence: number;
  human_required: boolean;
  evidence_refs: SourceRef[];
}

export interface ReviewPackage {
  package_id: string;
  document_id: string;
  status: "pending_review" | "identity_confirmed" | "pending_revision" | "ready_to_publish" | "approved" | "rejected";
  identity_decision: "pending" | "confirmed" | "needs_revision";
  title: string;
  business_type: string;
  effective_level: string;
  version: string;
  scope: string;
  is_binding: boolean;
  confidence: number;
  notes: string[];
  confirmed_business_type: string;
  confirmed_effective_level: string;
  confirmed_is_binding: boolean | null;
  review_notes: string;
  reviewed_at: string;
  reviewed_by: string;
  relation_decision: "pending" | "confirmed" | "needs_revision" | "not_applicable";
  relation_review_notes: string;
  relation_reviewed_at: string;
  relation_reviewed_by: string;
  source_refs: SourceRef[];
  issues: ReviewPackageIssue[];
  human_questions: ReviewPackageQuestion[];
  extracted_objects: ReviewPackageObject[];
  extracted_relations: ReviewPackageRelation[];
  candidate_page_titles: string[];
  tool_trace: string[];
}

export interface WikiPage {
  page_id: string;
  title: string;
  page_type: string;
  review_status: ReviewStatus;
  summary: string;
  aliases: string[];
  linked_pages: string[];
  updated_at: string;
  source_refs: SourceRef[];
  markdown: string;
}

export interface MatchedPage {
  page_id: string;
  title: string;
  page_type: string;
  summary: string;
  score: number;
}

export interface Citation {
  citation_id: string;
  page_title: string;
  file_name: string;
  anchor_label: string;
  quote: string;
  document_id?: string;
  fragment_id?: string;
}

export interface QueryResult {
  answer: string;
  confidence: "low" | "medium" | "high";
  used_llm: boolean;
  matched_pages: MatchedPage[];
  citations: Citation[];
  trace: string[];
  structured_matches?: StructuredMatch[];
}

export interface StructuredMatch {
  package_id: string;
  document_id: string;
  title: string;
  business_type: string;
  relation_count: number;
  object_count: number;
  source_refs: SourceRef[];
}

export interface MappingMatrixItem {
  requirement_name: string;
  requirement_type: string;
  source_documents: string[];
  source_packages: string[];
  claim_types: string[];
  mapped_process_steps: { name: string; object_type: string; document_id: string; source_package: string }[];
  mapped_records: { name: string; object_type: string; document_id: string; source_package: string }[];
  mapped_roles: { name: string; object_type: string; document_id: string; source_package: string }[];
  evidence_refs: SourceRef[];
}

export interface MappingMatrixExport {
  generated_at: string;
  package_count: number;
  relation_count: number;
  row_count: number;
  rows: MappingMatrixItem[];
}

export interface SlidesOutlineExport {
  generated_at: string;
  package_count: number;
  slide_count: number;
  slides: { title: string; bullets: string[] }[];
  markdown: string;
}

export interface LintIssue {
  issue_id: string;
  type: "missing_source" | "broken_link" | "stale_page" | "conflict" | "orphan";
  title: string;
  target: string;
  severity: RiskLevel;
  detail: string;
  suggestion: string;
  status: "open" | "proposed" | "resolved";
}

export interface IndexStatus {
  state: "fresh" | "stale" | "missing";
  pages: number;
  terms: number;
  sources: number;
  lastBuilt: string;
}
