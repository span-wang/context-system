import { resolvePublicBase } from "./public-base";

export const PLATFORM_PREFIX = "/platform";
export const API_BASE = resolvePublicBase(process.env.NEXT_PUBLIC_PLATFORM_API_BASE, PLATFORM_PREFIX);
export const PLATFORM_TOKEN_KEY = "pro_platform_access_token";
export const PLATFORM_REFRESH_TOKEN_KEY = "pro_platform_refresh_token";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await platformFetch(path, init);

  if (response.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/refresh") {
    const refreshed = await refreshPlatformToken();
    if (refreshed) {
      const retry = await platformFetch(path, init);
      if (!retry.ok) {
        const text = await retry.text();
        throw new Error(formatApiError(retry.status, text || retry.statusText));
      }
      return (await retry.json()) as T;
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatApiError(response.status, text || response.statusText));
  }

  return (await response.json()) as T;
}

export async function apiTextFetch(path: string, init?: RequestInit): Promise<string> {
  const response = await platformFetch(path, init);

  if (response.status === 401 && path !== "/api/auth/login" && path !== "/api/auth/refresh") {
    const refreshed = await refreshPlatformToken();
    if (refreshed) {
      const retry = await platformFetch(path, init);
      if (!retry.ok) {
        const text = await retry.text();
        throw new Error(formatApiError(retry.status, text || retry.statusText));
      }
      return await retry.text();
    }
  }

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatApiError(response.status, text || response.statusText));
  }

  return await response.text();
}

async function platformFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = getPlatformToken();
  return fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });
}

export async function apiFormFetch<T>(path: string, body: FormData): Promise<T> {
  const token = getPlatformToken();
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    body,
    headers: {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: "no-store",
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(formatApiError(response.status, text || response.statusText));
  }

  return (await response.json()) as T;
}

export function getPlatformToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(PLATFORM_TOKEN_KEY) || "";
}

export function setPlatformToken(token: string): void {
  if (typeof window === "undefined") return;
  if (token) {
    window.localStorage.setItem(PLATFORM_TOKEN_KEY, token);
  } else {
    window.localStorage.removeItem(PLATFORM_TOKEN_KEY);
  }
}

export function getPlatformRefreshToken(): string {
  if (typeof window === "undefined") return "";
  return window.localStorage.getItem(PLATFORM_REFRESH_TOKEN_KEY) || "";
}

export function setPlatformTokens(accessToken: string, refreshToken?: string): void {
  setPlatformToken(accessToken);
  if (typeof window === "undefined") return;
  if (refreshToken) {
    window.localStorage.setItem(PLATFORM_REFRESH_TOKEN_KEY, refreshToken);
  }
}

export function clearPlatformTokens(): void {
  setPlatformToken("");
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(PLATFORM_REFRESH_TOKEN_KEY);
}

async function refreshPlatformToken(): Promise<boolean> {
  const refreshToken = getPlatformRefreshToken();
  if (!refreshToken) return false;
  const response = await fetch(`${API_BASE}/api/auth/refresh`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh_token: refreshToken }),
    cache: "no-store",
  });
  if (!response.ok) {
    clearPlatformTokens();
    return false;
  }
  const payload = (await response.json()) as RefreshResponse;
  setPlatformToken(payload.access_token);
  return true;
}

function formatApiError(status: number, text: string): string {
  if (status === 401) {
    return "请求未授权。";
  }
  if (status === 403) {
    return "当前账号没有执行该操作的权限。";
  }
  try {
    const payload = JSON.parse(text) as { detail?: unknown };
    if (typeof payload.detail === "string") {
      return payload.detail;
    }
    if (payload.detail && typeof payload.detail === "object") {
      const detail = payload.detail as { message?: unknown; reasons?: unknown };
      const message = typeof detail.message === "string" ? detail.message : "";
      const reasons = Array.isArray(detail.reasons) ? detail.reasons.map(String).join("；") : "";
      if (message || reasons) {
        return [message, reasons].filter(Boolean).join("：");
      }
    }
  } catch {
    // Keep the original response text when it is not JSON.
  }
  return text;
}

export type HealthResponse = {
  ok: boolean;
  name: string;
  version: string;
  environment: string;
};

export type PlatformSummary = {
  current_phase: string;
  database_url: string;
  storage_type: string;
  mysql_ready: boolean;
  module_status: Record<string, string>;
};

export type SystemStatusResponse = {
  health: HealthResponse;
  summary: PlatformSummary;
};

export type OCRCapabilityResponse = {
  status: "ok" | "warn" | "fail";
  summary: string;
  device_name?: string | null;
  gpu_memory_total_mb?: number | null;
  gpu_memory_free_mb?: number | null;
  cuda_available: boolean;
  paddle_version?: string | null;
  paddle_cuda_device_count?: number | null;
  recommended_pipeline: string;
  current_settings: Record<string, unknown>;
  warnings: string[];
  checks: Record<string, unknown>;
};

export type RuntimePortsResponse = {
  found: boolean;
  source_path: string;
  api_base?: string | null;
  api_port?: number | null;
  web_url?: string | null;
  web_port?: number | null;
  public_web_url?: string | null;
  public_hostnames?: string[];
  use_local_mysql?: boolean | null;
  mysql_port?: number | null;
  mysql_db_url?: string | null;
  started_at?: string | null;
  probes?: {
    api: {
      configured: boolean;
      online: boolean;
      status_code?: number | null;
    };
    web: {
      configured: boolean;
      online: boolean;
      status_code?: number | null;
    };
    mysql: {
      port?: number | null;
      configured: boolean;
      online: boolean;
    };
  };
};

export type AuditLogResponse = {
  id: number;
  user_id?: number | null;
  module: string;
  action: string;
  target_type?: string | null;
  target_id?: string | null;
  payload_json?: Record<string, unknown> | null;
  created_at: string;
  username?: string | null;
};

export type RoleSummary = {
  id: number;
  role_code: string;
  role_name: string;
};

export type CurrentUserResponse = {
  id: number;
  username: string;
  display_name: string;
  email?: string | null;
  mobile?: string | null;
  user_type: string;
  status: string;
  last_login_at?: string | null;
  roles: RoleSummary[];
};

export type LoginResponse = {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  user: CurrentUserResponse;
};

export type RefreshResponse = {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: CurrentUserResponse;
};

export type SubjectResponse = {
  id: number;
  code: string;
  name: string;
  status: string;
};

export type SubjectDeleteResponse = {
  id: number;
  name: string;
  deleted: boolean;
};

export type SubjectDeleteSkippedItem = {
  id: number;
  name?: string | null;
  reason: string;
};

export type SubjectBatchDeleteResponse = {
  requested_count: number;
  deleted_count: number;
  skipped_count: number;
  deleted: SubjectDeleteResponse[];
  skipped: SubjectDeleteSkippedItem[];
  message: string;
};

export type ParsePreset = "vl15" | "v3";
export type ParseOutputFormat = "markdown" | "text";
export type PaperParseExecutionMode = "ocr_only" | "ai_cleanup_split" | "full_chain";

export type SubjectCategoryResponse = {
  id: number;
  subject_id: number;
  name: string;
  sort_order: number;
};

export type ChapterResponse = {
  id: number;
  subject_id: number;
  category_id?: number | null;
  parent_id?: number | null;
  name: string;
  level: number;
  path: string;
  sort_order: number;
};

export type ChapterDeleteResponse = {
  id: number;
  name: string;
  deleted: boolean;
  removed_chapter_count: number;
  unbound_point_count: number;
};

export type ChapterBatchDeleteResponse = {
  requested_count: number;
  removed_chapter_count: number;
  unbound_point_count: number;
  missing_count: number;
  message: string;
};

export type ChapterMarkdownImportResponse = {
  subject_id: number;
  chapter_created: number;
  chapter_skipped: number;
  chapters: ChapterResponse[];
  message: string;
};

export type KnowledgePointResponse = {
  id: number;
  subject_id: number;
  category_id?: number | null;
  chapter_id?: number | null;
  parent_id?: number | null;
  name: string;
  level: number;
  path: string;
  description?: string | null;
  keywords_json?: string[] | null;
  status: string;
  sort_order: number;
};

export type KnowledgePointMarkdownImportResponse = {
  subject_id: number;
  point_created: number;
  point_skipped: number;
  points: KnowledgePointResponse[];
  message: string;
};

export type TextbookResponse = {
  id: number;
  subject_id?: number | null;
  category_id?: number | null;
  source_title: string;
  filename: string;
  year?: number | null;
  region?: string | null;
  source_version?: string | null;
  tags_json?: string[] | null;
  parse_status: string;
  ocr_status: string;
  token_count?: number | null;
  file_size: number;
};

export type TextbookAutoBuildResponse = {
  textbook_id: number;
  subject_id: number;
  source: string;
  chapter_created: number;
  chapter_skipped: number;
  point_created: number;
  point_skipped: number;
  review_task_created: number;
  chapters: ChapterResponse[];
  points: KnowledgePointResponse[];
  message: string;
};

export type PaperSummary = {
  id: number;
  subject_id?: number | null;
  paper_name: string;
  paper_code?: string | null;
  category?: string | null;
  category_id?: number | null;
  exam_year?: number | null;
  exam_month?: number | null;
  exam_region?: string | null;
  exam_type?: string | null;
  paper_type?: string | null;
  status: string;
  review_status: string;
  total_question_count: number;
  total_score?: number | null;
};

export type PaperParseResponse = {
  paper_id: number;
  asset_id: number;
  parse_status: string;
  paper_status: string;
  question_count: number;
  section_count: number;
  tagged_count: number;
  preview?: string | null;
  provider?: string | null;
  output_format: ParseOutputFormat;
  warnings: string[];
  parse_options: Record<string, unknown>;
  parse_runtime: Record<string, unknown>;
  execution_mode: PaperParseExecutionMode;
  token_count?: number | null;
  dataset_sample_path?: string | null;
  dataset_auto_exported?: boolean;
  dataset_export_error?: string | null;
  ai_standardize_job_count?: number;
  ai_standardize_requested_count?: number;
  ai_standardize_job_ids?: number[];
};

export type PaperParseJobResponse = {
  job_id: number;
  paper_id: number;
  status: string;
  progress: number;
  execution_mode: PaperParseExecutionMode;
};

export type PaperUploadResponse = {
  id: number;
  asset_id: number;
  paper_name: string;
  filename: string;
  sha256: string;
  status: string;
  review_status: string;
  asset_parse_status: string;
};

export type PaperDeleteResponse = {
  id: number;
  paper_name: string;
  deleted: boolean;
  removed_asset?: boolean;
  removed_storage_file?: boolean;
  removed_dataset_dir?: boolean;
  removed_parsed_cache_files?: number;
  removed_pdf_checkpoint_dirs?: number;
  cleanup_warnings?: string[];
};

export type PaperSectionResponse = {
  id: number;
  section_name: string;
  question_type: string;
  start_no?: number | null;
  end_no?: number | null;
  score?: number | null;
  sort_order: number;
};

export type PaperDetailResponse = PaperSummary & {
  asset_id: number;
  subject_name?: string | null;
  category?: string | null;
  asset_filename?: string | null;
  asset_parse_status?: string | null;
  active_parse_job_id?: number | null;
  active_parse_job_status?: string | null;
  active_parse_stage?: string | null;
  active_parse_progress?: number | null;
  sections: PaperSectionResponse[];
};

export type PaperReviewQuestionResponse = {
  id: number;
  paper_id: number;
  section_id?: number | null;
  parent_question_id?: number | null;
  question_uid: string;
  content_fingerprint: string;
  sort_order: number;
  question_no: string;
  node_role: "standalone" | "group" | "subquestion";
  question_type: string;
  source_section_name: string;
  source_raw_text: string;
  group_stem?: string | null;
  material_text?: string | null;
  stem_text: string;
  options_json?: string[] | null;
  answer_text?: string | null;
  analysis_text?: string | null;
  difficulty_level?: number | null;
  quality_score?: number | null;
  subquestion_count: number;
  quality_issues_json?: string[] | null;
  parse_status: string;
  review_status: string;
  review_note?: string | null;
  ai_review_status?: string | null;
  ai_review_note?: string | null;
  ai_standardization_note?: string | null;
  last_ai_standardized_at?: string | null;
  last_ai_reviewed_at?: string | null;
  reviewed_by?: number | null;
  reviewed_at?: string | null;
  created_at: string;
  updated_at: string;
  suggested_knowledge_points: PaperReviewQuestionKnowledgePointResponse[];
  confirmed_knowledge_points: PaperReviewQuestionKnowledgePointResponse[];
  subquestions: PaperReviewQuestionResponse[];
};

export type PaperReviewQuestionKnowledgePointResponse = {
  id: number;
  question_id: number;
  knowledge_point_id: number;
  name: string;
  path: string;
  chapter_id?: number | null;
  category_id?: number | null;
  status: "suggested" | "confirmed" | "rejected";
  relation_type: "primary" | "secondary";
  source: string;
  confidence?: number | null;
  reason?: string | null;
  rank: number;
};

export type PaperReviewSummaryResponse = {
  total_questions: number;
  leaf_question_count: number;
  group_question_count: number;
  pending_count: number;
  approved_count: number;
  needs_revision_count: number;
  rejected_count: number;
  ai_flagged_count: number;
  ai_reviewed_count: number;
  missing_solution_count: number;
};

export type PaperReviewPaperResponse = {
  id: number;
  paper_name: string;
  subject_name?: string | null;
  category?: string | null;
  status: string;
  review_status: string;
  total_question_count: number;
  question_review_count: number;
  leaf_question_count: number;
  group_question_count: number;
};

export type PaperReviewWorkspaceResponse = {
  paper: PaperReviewPaperResponse;
  sections: PaperSectionResponse[];
  summary: PaperReviewSummaryResponse;
  questions: PaperReviewQuestionResponse[];
};

export type PaperReviewQuestionUpdateRequest = {
  question_type?: string | null;
  group_stem?: string | null;
  material_text?: string | null;
  stem_text?: string | null;
  options_json?: string[] | null;
  answer_text?: string | null;
  analysis_text?: string | null;
  review_status?: "pending" | "approved" | "needs_revision" | "rejected" | null;
  review_note?: string | null;
  subquestions?: {
    id: number;
    question_type?: string | null;
    stem_text?: string | null;
    options_json?: string[] | null;
    answer_text?: string | null;
    analysis_text?: string | null;
    review_status?: "pending" | "approved" | "needs_revision" | "rejected" | null;
    review_note?: string | null;
  }[];
};

export type PaperReviewQuestionKnowledgePointUpsertItem = {
  knowledge_point_id: number;
  relation_type: "primary" | "secondary";
  source: string;
  confidence?: number | null;
  reason?: string | null;
  rank: number;
};

export type PaperReviewQuestionKnowledgePointUpdateRequest = {
  suggested: PaperReviewQuestionKnowledgePointUpsertItem[];
  confirmed: PaperReviewQuestionKnowledgePointUpsertItem[];
};

export type PaperReviewRebuildResponse = {
  paper_id: number;
  imported_count: number;
  replaced_count: number;
  section_count: number;
  message: string;
};

export type PaperReviewAutoTagResponse = {
  paper_id: number;
  status: string;
  progress: number;
  requested_count: number;
  updated_count: number;
  failed_count: number;
  skipped_count: number;
  message: string;
};

export type PaperReviewAutoTagJobResponse = {
  job_id: number;
  paper_id: number;
  status: string;
  progress: number;
};

export type PaperReviewAIStandardizeJobItemResponse = {
  job_id: number;
  paper_id: number;
  status: string;
  progress: number;
  requested_count: number;
  batch_index: number;
  batch_count: number;
  question_ids: number[];
};

export type PaperReviewAIStandardizeJobSubmitResponse = {
  paper_id: number;
  requested_count: number;
  job_count: number;
  jobs: PaperReviewAIStandardizeJobItemResponse[];
  message: string;
};

export type PaperReviewAIStandardizeJobResponse = {
  job_id: number;
  paper_id: number;
  status: string;
  progress: number;
  requested_count: number;
  success_count: number;
  failed_count: number;
  changed_count: number;
  used_ai_count: number;
  batch_index: number;
  batch_count: number;
  question_ids: number[];
  message: string;
};

export type PaperReviewAIActionResponse = {
  message: string;
  changed: boolean;
  used_ai: boolean;
  question: PaperReviewQuestionResponse;
};

export type PaperReviewAIBatchActionRequest = {
  question_ids: number[];
};

export type PaperReviewBatchReviewRequest = {
  question_ids: number[];
  review_status: "pending" | "approved" | "needs_revision" | "rejected";
  review_note?: string | null;
};

export type PaperReviewAIBatchFailureResponse = {
  question_id: number;
  message: string;
};

export type PaperReviewBatchReviewResponse = {
  message: string;
  requested_count: number;
  success_count: number;
  failed_count: number;
  questions: PaperReviewQuestionResponse[];
  failures: PaperReviewAIBatchFailureResponse[];
};

export type PaperReviewAIBatchActionResponse = {
  message: string;
  requested_count: number;
  success_count: number;
  failed_count: number;
  changed_count: number;
  used_ai_count: number;
  questions: PaperReviewQuestionResponse[];
  failures: PaperReviewAIBatchFailureResponse[];
};

export type QuestionBankKnowledgePointResponse = {
  id: number;
  name: string;
  path: string;
  relation_type: string;
  status: string;
};

export type QuestionBankItemResponse = {
  id: number;
  subject_id?: number | null;
  subject_name?: string | null;
  category_id?: number | null;
  category_name?: string | null;
  parent_question_id?: number | null;
  question_no?: string | null;
  question_uid: string;
  content_fingerprint: string;
  node_role: "standalone" | "group" | "subquestion";
  question_type: string;
  group_stem?: string | null;
  material_text?: string | null;
  stem_text: string;
  options_json?: string[] | null;
  answer_text?: string | null;
  analysis_text?: string | null;
  difficulty_level?: number | null;
  quality_score?: number | null;
  subquestion_count: number;
  status: string;
  source_count: number;
  first_source_question_id?: number | null;
  first_source_paper_name?: string | null;
  created_at: string;
  updated_at: string;
  knowledge_points: QuestionBankKnowledgePointResponse[];
  subquestions: QuestionBankItemResponse[];
};

export type QuestionBankListResponse = {
  total: number;
  items: QuestionBankItemResponse[];
  status_counts: Record<string, number>;
};

export type QuestionBankExportSolutionMode = "inline" | "appendix";

export type QuestionBankExportPaperOptionResponse = {
  paper_id: number;
  paper_name: string;
  subject_name?: string | null;
  category_name?: string | null;
  question_count: number;
};

export type QuestionBankPaperExportRequest = {
  paper_id: number;
  solution_mode: QuestionBankExportSolutionMode;
  subject_id?: number | null;
  category_id?: number | null;
  status?: "draft" | "active" | "inactive" | "archived" | null;
  question_type?: string | null;
  keyword?: string | null;
};

export type QuestionBankSourceResponse = {
  id: number;
  source_type: string;
  source_question_id: number;
  paper_id?: number | null;
  paper_name?: string | null;
  section_id?: number | null;
  question_no?: string | null;
  status: string;
  created_at: string;
};

export type QuestionBankDeleteResponse = {
  id: number;
  question_uid: string;
  deleted: boolean;
  removed_source_link_count: number;
  message: string;
};

export type QuestionBankAnalysisSummaryResponse = {
  paper_count: number;
  bank_question_count: number;
  source_question_count: number;
  tagged_source_question_count: number;
  point_count: number;
  chapter_count: number;
  year_count: number;
  primary_coverage_rate: number;
  top_point_concentration_rate: number;
};

export type QuestionBankAnalysisYearOverviewResponse = {
  year: number;
  paper_count: number;
  source_question_count: number;
  tagged_source_question_count: number;
};

export type QuestionBankAnalysisDistributionItemResponse = {
  key: string;
  name: string;
  path?: string | null;
  total_frequency: number;
  paper_count: number;
  yearly_frequency: number[];
  share: number;
  last_frequency: number;
  recent_average: number;
  slope: number;
  trend_label: string;
  prediction_frequency: number;
  confidence: number;
  appearance_year_count: number;
};

export type QuestionBankAnalysisPointItemResponse = QuestionBankAnalysisDistributionItemResponse & {
  knowledge_point_id?: number | null;
  chapter_name?: string | null;
};

export type QuestionBankAnalysisChapterItemResponse = QuestionBankAnalysisDistributionItemResponse & {
  chapter_key: string;
};

export type QuestionBankAnalysisPredictionItemResponse = {
  key: string;
  name: string;
  prediction_frequency: number;
  confidence: number;
  trend_label: string;
  evidence: string;
};

export type QuestionBankAnalysisReportResponse = {
  overview: string;
  point_insight: string;
  chapter_insight: string;
  forecast: string;
  disclaimer: string;
};

export type QuestionBankKnowledgeAnalysisResponse = {
  data_scope: string;
  subject_id?: number | null;
  subject_name?: string | null;
  category_id?: number | null;
  category_name?: string | null;
  start_year?: number | null;
  end_year?: number | null;
  years: number[];
  prediction_year?: number | null;
  summary: QuestionBankAnalysisSummaryResponse;
  yearly_overview: QuestionBankAnalysisYearOverviewResponse[];
  point_distribution: QuestionBankAnalysisPointItemResponse[];
  chapter_distribution: QuestionBankAnalysisChapterItemResponse[];
  top_predicted_points: QuestionBankAnalysisPredictionItemResponse[];
  top_predicted_chapters: QuestionBankAnalysisPredictionItemResponse[];
  report: QuestionBankAnalysisReportResponse;
};

export type PracticeSessionType = "chapter" | "random" | "paper" | "wrong_book";
export type PracticeAnswerMode = "memorize" | "exam";

export type PracticeQuestionKnowledgePointResponse = {
  id: number;
  name: string;
  path: string;
  relation_type: string;
  status: string;
};

export type PracticeQuestionSnapshotResponse = {
  bank_question_id?: number | null;
  question_uid: string;
  node_role: string;
  question_type: string;
  group_stem?: string | null;
  material_text?: string | null;
  stem_text: string;
  options_json?: string[] | null;
  difficulty_level?: number | null;
  source_paper_name?: string | null;
  source_question_no?: string | null;
  knowledge_points: PracticeQuestionKnowledgePointResponse[];
  answer_text?: string | null;
  analysis_text?: string | null;
};

export type PracticeSessionItemResponse = {
  id: number;
  sort_order: number;
  score: number;
  question: PracticeQuestionSnapshotResponse;
  user_answer?: string | null;
  is_answered: boolean;
  is_correct?: boolean | null;
  marked: boolean;
  spent_seconds?: number | null;
  show_result: boolean;
};

export type PracticeSessionSummaryResponse = {
  id: number;
  title: string;
  session_type: PracticeSessionType;
  answer_mode: PracticeAnswerMode;
  status: string;
  total_count: number;
  answered_count: number;
  correct_count: number;
  accuracy_rate?: number | null;
  created_at: string;
  started_at?: string | null;
  submitted_at?: string | null;
};

export type PracticeSessionDetailResponse = PracticeSessionSummaryResponse & {
  subject_id?: number | null;
  category_id?: number | null;
  chapter_id?: number | null;
  paper_id?: number | null;
  duration_seconds?: number | null;
  can_show_solutions: boolean;
  can_submit: boolean;
  incomplete_count: number;
  today_review_count: number;
  retry_wrong_count: number;
  similar_practice_available: boolean;
  weak_points: MasterySnapshotResponse[];
  items: PracticeSessionItemResponse[];
};

export type PracticeSessionCreateRequest = {
  session_type: PracticeSessionType;
  answer_mode: PracticeAnswerMode;
  subject_id?: number | null;
  category_id?: number | null;
  chapter_id?: number | null;
  paper_id?: number | null;
  question_type?: string | null;
  question_count: number;
};

export type PracticeAnswerSubmitRequest = {
  item_id: number;
  answer?: string | null;
  spent_seconds?: number | null;
  marked?: boolean;
};

export type PracticeAnswerReflectionRequest = {
  item_id: number;
  wrong_reason_tags: Array<
    "concept_unclear" | "memory_unstable" | "misread_question" | "calculation_error" | "careless" | "method_unfamiliar"
  >;
  reflection_note?: string | null;
};

export type PracticeDerivedSessionRequest = {
  answer_mode: PracticeAnswerMode;
  question_count: number;
};

export type MasterySnapshotResponse = {
  knowledge_point_id: number;
  name: string;
  path: string;
  chapter_id?: number | null;
  mastery_score: number;
  answered_count: number;
  correct_count: number;
  snapshot_date?: string | null;
  last_practiced_at?: string | null;
};

export type ReviewDueItemResponse = {
  id: number;
  bank_question_id?: number | null;
  question_type: string;
  stem_text: string;
  source_paper_name?: string | null;
  knowledge_points: PracticeQuestionKnowledgePointResponse[];
  wrong_count: number;
  correct_streak: number;
  due_at: string;
  due_reason: string;
};

export type PracticeWrongReasonCountResponse = {
  reason_code: "concept_unclear" | "memory_unstable" | "misread_question" | "calculation_error" | "careless" | "method_unfamiliar";
  reason_label: string;
  count: number;
};

export type PracticeResultItemResponse = {
  id: number;
  sort_order: number;
  score: number;
  question: PracticeQuestionSnapshotResponse;
  user_answer?: string | null;
  is_correct?: boolean | null;
  marked: boolean;
  spent_seconds?: number | null;
  wrong_reason_tags: Array<
    "concept_unclear" | "memory_unstable" | "misread_question" | "calculation_error" | "careless" | "method_unfamiliar"
  >;
  reflection_note?: string | null;
};

export type PracticeResultResponse = {
  id: number;
  title: string;
  session_type: PracticeSessionType;
  answer_mode: PracticeAnswerMode;
  total_count: number;
  correct_count: number;
  wrong_count: number;
  accuracy_rate?: number | null;
  duration_seconds?: number | null;
  submitted_at?: string | null;
  today_review_count: number;
  retry_wrong_count: number;
  similar_practice_available: boolean;
  weak_points: MasterySnapshotResponse[];
  wrong_reason_counts: PracticeWrongReasonCountResponse[];
  review_suggestions: string[];
  items: PracticeResultItemResponse[];
};

export type DailyPlanTaskResponse = {
  task_id: string;
  task_type: string;
  title: string;
  description: string;
  priority: string;
  question_count: number;
  action_type?: string | null;
  session_create_payload?: PracticeSessionCreateRequest | null;
  derived_session_payload?: PracticeDerivedSessionRequest | null;
};

export type DailyPlanResponse = {
  headline: string;
  summary: string;
  review_today_count: number;
  weak_points: MasterySnapshotResponse[];
  tasks: DailyPlanTaskResponse[];
};

export type WrongBookItemResponse = {
  id: number;
  bank_question_id?: number | null;
  question_type: string;
  stem_text: string;
  source_paper_name?: string | null;
  knowledge_points: PracticeQuestionKnowledgePointResponse[];
  wrong_count: number;
  correct_streak: number;
  mastered: boolean;
  last_wrong_at?: string | null;
  last_practiced_at?: string | null;
  due_at?: string | null;
  due_reason?: string | null;
};

export type AnalysisJobResponse = {
  id: number;
  job_type: string;
  subject_id?: number | null;
  scope_type: string;
  scope_config_json?: {
    stage?: string;
    detail?: Record<string, unknown>;
    execution_mode?: string;
    [key: string]: unknown;
  } | null;
  status: string;
  progress: number;
  result_summary_json?: Record<string, unknown> | null;
  error_message?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  created_at: string;
};

export const moduleLabelMap: Record<string, string> = {
  auth: "认证与权限",
  learning: "刷题练习",
  papers: "试卷中心",
  paper_review: "审核工作台",
  knowledge: "学科中心",
};
