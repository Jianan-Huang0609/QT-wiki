import type {
  AgentSummary,
  CandidatePage,
  IndexStatus,
  LintIssue,
  MappingMatrixExport,
  QueryResult,
  ReviewPackage,
  SlidesOutlineExport,
  WikiPage
} from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

export class ApiRequestError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
  }
}

export async function getDashboard(): Promise<{
  agents: AgentSummary[];
  index: IndexStatus;
  pages: WikiPage[];
  issues: LintIssue[];
}> {
  return requestJson<{
    agents: AgentSummary[];
    index: IndexStatus;
    pages: WikiPage[];
    issues: LintIssue[];
  }>("/api/dashboard");
}

export async function getCandidates(): Promise<CandidatePage[]> {
  const payload = await requestJson<{ items: CandidatePage[] }>("/api/ingest/candidates");
  return payload.items;
}

export async function getReviewPackages(): Promise<ReviewPackage[]> {
  const payload = await requestJson<{ items: ReviewPackage[] }>("/api/ingest/review-packages");
  return payload.items;
}

export async function decideReviewPackage(
  packageId: string,
  payload: {
    identity_decision: "confirmed" | "needs_revision";
    confirmed_business_type: string;
    confirmed_effective_level: string;
    confirmed_is_binding: boolean;
    review_notes: string;
    reviewed_by: string;
  }
): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/ingest/review-packages/${packageId}/decision`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload)
  });
}

export async function decideReviewPackageRelations(
  packageId: string,
  payload: {
    relation_decision: "confirmed" | "needs_revision";
    relation_review_notes: string;
    relation_reviewed_by: string;
  }
): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/ingest/review-packages/${packageId}/relations/decision`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify(payload)
  });
}

export async function approveCandidate(candidateId: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/ingest/candidates/${candidateId}/approve`, {
    method: "POST"
  });
}

export async function rejectCandidate(candidateId: string): Promise<{ ok: boolean }> {
  return requestJson<{ ok: boolean }>(`/api/ingest/candidates/${candidateId}/reject`, {
    method: "POST"
  });
}

export async function getWikiPages(): Promise<WikiPage[]> {
  const payload = await requestJson<{ items: WikiPage[] }>("/api/wiki/pages");
  return payload.items;
}

export async function queryWiki(question: string, useLlm: boolean, topKPages: number): Promise<QueryResult> {
  const payload = await requestJson<QueryResult>("/chat/query", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      question,
      use_llm: useLlm,
      top_k_pages: topKPages,
      top_k_citations: 8
    })
  });
  return {
    ...payload,
    trace: payload.trace ?? []
  };
}

export async function getMappingMatrixExport(): Promise<MappingMatrixExport> {
  return requestJson<MappingMatrixExport>("/api/exports/mapping-matrix");
}

export async function getSlidesOutlineExport(): Promise<SlidesOutlineExport> {
  return requestJson<SlidesOutlineExport>("/api/exports/slides-outline");
}

export async function rebuildIndex(): Promise<IndexStatus> {
  return requestJson<IndexStatus>("/chat/reindex", { method: "POST" });
}

export async function runLintScan(): Promise<LintIssue[]> {
  const payload = await requestJson<{ items: LintIssue[] }>("/api/lint/scan", { method: "POST" });
  return payload.items;
}

export async function uploadDocument(
  file: File,
  useLlm: boolean
): Promise<{ run_id: string; pending: number; pending_review_count: number }> {
  const data = new FormData();
  data.append("file", file);
  data.append("use_llm", String(useLlm));
  const payload = await requestJson<{
    run_id: string;
    pending?: number;
    pending_review_count?: number;
  }>("/agent/upload", {
    method: "POST",
    body: data
  });
  const pending = payload.pending ?? payload.pending_review_count ?? 0;
  return {
    run_id: payload.run_id,
    pending,
    pending_review_count: pending
  };
}

async function requestJson<T>(input: RequestInfo | URL, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(input, init);
  } catch {
    throw new ApiRequestError("无法连接后端服务");
  }

  if (!response.ok) {
    throw new ApiRequestError(await responseErrorMessage(response), response.status);
  }

  return (await response.json()) as T;
}

async function responseErrorMessage(response: Response): Promise<string> {
  try {
    const payload = (await response.json()) as { detail?: string };
    if (payload?.detail) {
      return payload.detail;
    }
  } catch {
    // ignore parse failure
  }
  return `${response.status} ${response.statusText}`;
}
