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

export type ParsePreset = "auto" | "fast" | "balanced" | "accurate" | "formula";
export type ParseOutputFormat = "markdown" | "text";
export type ParseMode = "rules";

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
  parse_mode: ParseMode;
  output_format: ParseOutputFormat;
  warnings: string[];
  parse_options: Record<string, unknown>;
  dataset_sample_path?: string | null;
  dataset_auto_exported?: boolean;
  dataset_export_error?: string | null;
};

export type PaperParseJobResponse = {
  job_id: number;
  paper_id: number;
  status: string;
  progress: number;
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
  question_uid: string;
  content_fingerprint: string;
  sort_order: number;
  question_no: string;
  question_type: string;
  source_section_name: string;
  source_raw_text: string;
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
};

export type PaperReviewWorkspaceResponse = {
  paper: PaperReviewPaperResponse;
  sections: PaperSectionResponse[];
  summary: PaperReviewSummaryResponse;
  questions: PaperReviewQuestionResponse[];
};

export type PaperReviewQuestionUpdateRequest = {
  question_type?: string | null;
  stem_text?: string | null;
  options_json?: string[] | null;
  answer_text?: string | null;
  analysis_text?: string | null;
  review_status?: "pending" | "approved" | "needs_revision" | "rejected" | null;
  review_note?: string | null;
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

export type PaperReviewAIActionResponse = {
  message: string;
  changed: boolean;
  used_ai: boolean;
  question: PaperReviewQuestionResponse;
};

export type AnalysisJobResponse = {
  id: number;
  job_type: string;
  subject_id?: number | null;
  scope_type: string;
  scope_config_json?: {
    stage?: string;
    detail?: Record<string, unknown>;
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
  papers: "试卷中心",
  paper_review: "题目解析",
  knowledge: "学科中心",
};
