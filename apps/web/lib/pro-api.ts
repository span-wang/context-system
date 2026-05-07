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
    return "请先在 /platform/settings 登录后再执行该操作。";
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

export type ParsePreset = "auto" | "fast" | "balanced" | "accurate" | "formula";

export type SubjectCategoryResponse = {
  id: number;
  subject_id: number;
  name: string;
  sort_order: number;
};

export type ChapterResponse = {
  id: number;
  subject_id: number;
  parent_id?: number | null;
  name: string;
  level: number;
  path: string;
  sort_order: number;
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

export type PaperSummary = {
  id: number;
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
  warnings: string[];
  parse_options: Record<string, unknown>;
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
  removed_question_count: number;
  removed_source_link_count: number;
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
  subject_name?: string | null;
  category?: string | null;
  asset_filename?: string | null;
  asset_parse_status?: string | null;
  sections: PaperSectionResponse[];
};

export type QuestionSummary = {
  id: number;
  paper_id: number;
  subject_id: number;
  section_id?: number | null;
  question_no: string;
  question_uid: string;
  question_type: string;
  stem_text: string;
  answer_text?: string | null;
  score?: number | null;
  difficulty_level?: number | null;
  parse_status: string;
  review_status: string;
  review_note?: string | null;
};

export type QuestionKnowledgeLinkResponse = {
  id: number;
  knowledge_point_id: number;
  question_layer: string;
  link_type: string;
  confidence_score?: number | null;
  evidence_text?: string | null;
  tag_source?: string | null;
  is_primary: boolean;
  review_status: string;
  reviewed_at?: string | null;
  knowledge_point_name?: string | null;
};

export type QuestionDetailResponse = QuestionSummary & {
  options_json?: string[] | null;
  analysis_text?: string | null;
  source_page_from?: number | null;
  source_page_to?: number | null;
  quality_score?: number | null;
  links: QuestionKnowledgeLinkResponse[];
};

export type QuestionBatchReviewResponse = {
  updated_count: number;
  review_status: string;
  question_ids: number[];
};

export type QuestionKnowledgeReviewResponse = {
  question_id: number;
  updated_count: number;
  review_status: string;
  link_ids: number[];
  primary_link_id?: number | null;
};

export type QuestionRetagResponse = {
  question_id: number;
  created_links: number;
  total_links: number;
};

export type DashboardMetric = {
  key: string;
  label: string;
  value: string;
  trend?: string | null;
};

export type DashboardFocusItem = {
  knowledge_point_id: number;
  knowledge_point_name: string;
  frequency: number;
  paper_coverage: number;
  hot_score: number;
};

export type DashboardResponse = {
  metrics: DashboardMetric[];
  focus_points: DashboardFocusItem[];
  pending_reviews: number;
  latest_report_name?: string | null;
};

export type FrequencyResponse = {
  knowledge_point_id: number;
  knowledge_point_name: string;
  question_count: number;
  paper_count: number;
  hot_score: number;
};

export type TrendResponse = {
  label: string;
  year?: number | null;
  question_count: number;
};

export type ReportResponse = {
  id: number;
  subject_id?: number | null;
  report_type: string;
  report_name: string;
  snapshot_date?: string | null;
  version_no: number;
  status: string;
  report_json?: Record<string, unknown> | null;
  created_at: string;
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

export type StandardizeQuestionsResponse = {
  created: number;
  linked: number;
  skipped: number;
};

export type QuestionBankItemResponse = {
  id: number;
  subject_id: number;
  canonical_stem: string;
  canonical_options_json?: string[] | null;
  canonical_answer?: string | null;
  canonical_analysis?: string | null;
  question_type: string;
  difficulty_level?: number | null;
  quality_score?: number | null;
  source_count: number;
  status: string;
};

export type PracticeSetResponse = {
  id: number;
  subject_id: number;
  set_type: string;
  title: string;
  description?: string | null;
  source_report_id?: number | null;
  difficulty_policy?: string | null;
  question_count: number;
  status: string;
};

export type MockExamResponse = {
  id: number;
  subject_id: number;
  title: string;
  exam_mode: string;
  duration_minutes?: number | null;
  total_score?: number | null;
  status: string;
};

export type LearningHomeResponse = {
  learner_name?: string | null;
  target_exam?: string | null;
  active_subject?: string | null;
  total_sessions: number;
  wrong_book_count: number;
  favorite_count: number;
  weakest_points: string[];
};

export type PracticeSessionResponse = {
  id: number;
  learner_id: number;
  session_type: string;
  subject_id?: number | null;
  practice_set_id?: number | null;
  mock_exam_id?: number | null;
  status: string;
  started_at?: string | null;
  submitted_at?: string | null;
  score?: number | null;
  accuracy_rate?: number | null;
  duration_seconds?: number | null;
};

export type WrongBookResponse = {
  id: number;
  learner_id: number;
  bank_question_id: number;
  source_session_id?: number | null;
  wrong_count: number;
  mastered: boolean;
};

export type MasteryResponse = {
  id: number;
  learner_id: number;
  subject_id: number;
  knowledge_point_id: number;
  mastery_score: number;
  answered_count: number;
  correct_count: number;
  snapshot_date: string;
  knowledge_point_name?: string | null;
};

export type ReviewTaskResponse = {
  id: number;
  task_type: string;
  target_type: string;
  target_id: string;
  status: string;
  assigned_to?: number | null;
  priority: string;
  review_note?: string | null;
  created_at: string;
};

export type WorkflowTopicResponse = {
  title: string;
  source_report: string;
  task_type: string;
  priority: string;
  status: string;
};

export const moduleLabelMap: Record<string, string> = {
  auth: "认证与权限",
  papers: "试卷中心",
  questions: "题目中心",
  knowledge: "学科中心",
  analysis: "分析中心",
  question_bank: "题库中心",
  learning: "学习中心",
  workflow: "工作流联动",
};
