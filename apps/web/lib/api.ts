import { resolvePublicBase } from "./public-base";

export const API_BASE = resolvePublicBase(process.env.NEXT_PUBLIC_API_BASE, "");
export const LAYOUT_API_BASE = resolvePublicBase(process.env.NEXT_PUBLIC_LAYOUT_API_BASE, "/layout");
export const LAYOUT_PUBLIC_URL = process.env.NEXT_PUBLIC_LAYOUT_PUBLIC_URL || "http://127.0.0.1:3210";

export type ContentType =
  | "mnemonic"
  | "tri_color"
  | "summary_pages"
  | "formula_dict"
  | "compare_table"
  | "exam_review";

export type ReviewMode = "llm_only" | "document_only" | "hybrid";
export type ReviewItemStatus = "pending" | "confirmed" | "replaced" | "skipped";
export type ParsePreset = "vl15" | "v3";
export type ParseOutputFormat = "markdown" | "text";
export type WorkflowTopicStatus =
  | "idea"
  | "planned"
  | "drafting"
  | "generated"
  | "reviewing"
  | "needs_changes"
  | "awaiting_confirm"
  | "approved"
  | "exported"
  | "published"
  | "archived";
export type WorkflowReviewStatus = "not_started" | "reviewing" | "passed" | "needs_changes" | "waived";
export type WorkflowPriority = "low" | "medium" | "high" | "urgent";

export type LibraryFile = {
  id: string;
  sha256: string;
  filename: string;
  size: number;
  mime: string;
  storage_path: string;
  subject: string;
  category?: string | null;
  chapter?: string | null;
  source_type: string;
  source_authority: "high" | "medium" | "low";
  source_title: string;
  source_publisher?: string | null;
  source_code?: string | null;
  source_version?: string | null;
  year?: number | null;
  tags: string[];
  token_count?: number | null;
  created_at: string;
  last_used_at?: string | null;
};

export type LibraryFilePreview = {
  file_id: string;
  filename: string;
  token_count: number;
  provider: string;
  raw_text: string;
  raw_markdown: string;
  text: string;
  markdown: string;
  content: string;
  output_format: ParseOutputFormat;
  table_count: number;
  warning_count: number;
  warnings: string[];
  truncated: boolean;
  parse_options: Record<string, unknown>;
  cleanup_report: Record<string, unknown>;
  cleanup_score?: number | null;
};

export type LibraryParseResultSummary = {
  id: string;
  file_id: string;
  sequence_number: number;
  provider: string;
  token_count: number;
  created_at: string;
};

export type LibraryReparseResponse = LibraryFilePreview & {
  stored_result_id: string;
  stored_sequence_number: number;
  kept_results: LibraryParseResultSummary[];
};

export type LibraryParseMode = "preview" | "reparse";

export type LibraryParseJobResponse = {
  job_id: number;
  file_id: string;
  mode: LibraryParseMode;
  status: string;
  progress: number;
};

export type LibraryParseJobStatus = {
  id: number;
  job_type: string;
  scope_type: string;
  scope_config_json?: {
    stage?: string;
    detail?: Record<string, unknown>;
    file_id?: string;
    filename?: string;
    mode?: LibraryParseMode;
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

export type LayoutMode = {
  id: string;
  name: string;
  title: string;
  summary: string;
  highlights: string[];
  sort: number;
  enabled: boolean;
  renderMode: string;
  templateVersion: string;
  updatedAt: string;
  templateUrl: string;
  templateAbsoluteUrl?: string;
};

export type LayoutTemplatePlaceholder = {
  key: string;
  label: string;
  required: boolean;
};

export type LayoutTemplatePayload = {
  modeId: string;
  modeName: string;
  modeTitle: string;
  renderMode: string;
  templateVersion: string;
  syntaxVersion: string;
  updatedAt: string;
  syntax: string;
  modeTemplate: string;
  template: string;
  placeholders: LayoutTemplatePlaceholder[];
};

export type LayoutMarkdownDocument = {
  id: string;
  title: string;
  modeId: string;
  modeName: string;
  markdown: string;
  stats: {
    characters: number;
    lines: number;
  };
  source: string;
  metadata: Record<string, unknown>;
  createdAt: string;
};

export type ReviewReport = {
  pass_overall: boolean;
  strict_mode: boolean;
  mode: ReviewMode;
  evidence_policy: "model_only" | "documents_only" | "model_and_documents";
  llm_used: boolean;
  evidence_source_count: number;
  citation_check: Record<string, unknown>;
  nli_results: Array<Record<string, unknown>>;
  version_conflicts: Array<Record<string, unknown>>;
  numeric_checks: Array<Record<string, unknown>>;
  issues: string[];
  suggestions: string[];
  items: ReviewItem[];
  unverified_warning?: string | null;
};

export type ReviewItem = {
  id: string;
  issue: string;
  suggestion?: string | null;
  original_text?: string | null;
  replacement_text?: string | null;
  status: ReviewItemStatus;
  replace_count: number;
};

export type XiaohongshuPublishPackage = {
  title_options: string[];
  body: string;
  cover_text: string;
  carousel_pages: string[];
  tags: string[];
  comment_guides: string[];
};

export type GenerationJob = {
  id: string;
  context: {
    mode: "ragflow" | "direct";
    subject: string;
    category?: string | null;
    chapter?: string | null;
    content_type: ContentType;
    options: Record<string, unknown>;
    sources: Array<Record<string, unknown>>;
    user_notes?: string | null;
    has_authoritative_source: boolean;
  };
  status: "pending" | "retrieving" | "generating" | "reviewing" | "done" | "failed";
  result?: {
    content_type: string;
    title: string;
    sections: Array<Record<string, unknown>>;
    claims: Array<Record<string, unknown>>;
    raw_markdown: string;
    publish_package?: XiaohongshuPublishPackage | null;
    unverified: boolean;
  } | null;
  review?: ReviewReport | null;
  created_at: string;
  error?: string | null;
};

export type WorkflowTopic = {
  id: string;
  title: string;
  brief?: string | null;
  subject: string;
  category?: string | null;
  chapter?: string | null;
  content_type: ContentType;
  owner?: string | null;
  status: WorkflowTopicStatus;
  review_status: WorkflowReviewStatus;
  priority: WorkflowPriority;
  scheduled_date?: string | null;
  due_date?: string | null;
  publish_channel: string;
  content_goal?: string | null;
  audience?: string | null;
  material_file_ids: string[];
  ragflow_dataset_ids: string[];
  generation_job_id?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  published_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowTopicCreate = {
  title: string;
  brief?: string | null;
  subject: string;
  category?: string | null;
  chapter?: string | null;
  content_type: ContentType;
  owner?: string | null;
  status?: WorkflowTopicStatus;
  review_status?: WorkflowReviewStatus;
  priority?: WorkflowPriority;
  scheduled_date?: string | null;
  due_date?: string | null;
  publish_channel?: string;
  content_goal?: string | null;
  audience?: string | null;
  material_file_ids?: string[];
  ragflow_dataset_ids?: string[];
};

export type WorkflowTopicPatch = Partial<WorkflowTopicCreate> & {
  generation_job_id?: string | null;
  confirmed_by?: string | null;
  confirmed_at?: string | null;
  published_at?: string | null;
  actor?: string | null;
  note?: string | null;
};

export type WorkflowEvent = {
  id: string;
  topic_id: string;
  version: number;
  event_type: string;
  note?: string | null;
  actor?: string | null;
  snapshot: Record<string, unknown>;
  created_at: string;
};

export type WorkflowGenerateResponse = {
  topic: WorkflowTopic;
  job_id: string;
};

export type LLMEndpointConfig = {
  provider: "local_template" | "local_rules" | "openai_compat" | "deepseek" | "anthropic";
  model: string;
  max_tokens: number;
  base_url?: string | null;
  has_api_key: boolean;
  model_id?: string | null;
  model_name?: string | null;
};

export type LLMModelConfig = Omit<LLMEndpointConfig, "model_id" | "model_name"> & {
  id: string;
  name: string;
};

export type LLMPresetConfig = LLMModelConfig;

export type PaperAICleanupConfig = LLMEndpointConfig & {
  enabled: boolean;
  disable_thinking: boolean;
  system_prompt: string;
};

export type AIFeatureEndpointConfig = LLMEndpointConfig & {
  enabled: boolean;
  disable_thinking: boolean;
};

export type SubjectConfig = {
  id: string;
  name: string;
  categories: string[];
  platform_id?: number | null;
};

export type RAGFlowDataset = {
  id: string;
  name: string;
  description?: string | null;
  document_count?: number | null;
  chunk_count?: number | null;
  token_num?: number | null;
  status?: string | null;
  permission?: string | null;
  embedding_model?: string | null;
  chunk_method?: string | null;
  unstart_count?: number | null;
  running_count?: number | null;
  cancel_count?: number | null;
  done_count?: number | null;
  fail_count?: number | null;
};

export type RAGFlowDatasetList = {
  datasets: RAGFlowDataset[];
  total: number;
};

export type SystemConfig = {
  app: {
    name: string;
    context_token_limit: number;
  };
  llm: {
    generator: LLMEndpointConfig;
    reviewer: LLMEndpointConfig;
    models: LLMModelConfig[];
    presets: LLMModelConfig[];
  };
  paper_ai_cleanup: PaperAICleanupConfig;
  question_ai_standardizer: AIFeatureEndpointConfig;
  question_auto_tagger: AIFeatureEndpointConfig;
  storage: {
    type: string;
  };
  ragflow: {
    enabled: boolean;
    base_url: string;
    has_api_key: boolean;
  };
  subjects: SubjectConfig[];
};

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json", ...(init?.headers || {}) },
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(errorMessageFromResponse(text, response.statusText));
  }
  return response.json() as Promise<T>;
}

export async function layoutFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${LAYOUT_API_BASE}${path}`, {
    ...init,
    headers: init?.body instanceof FormData
      ? init.headers
      : { "Content-Type": "application/json; charset=utf-8", ...(init?.headers || {}) },
  });
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};
  if (!response.ok || payload?.success === false) {
    const message = payload?.error?.message || payload?.error || response.statusText;
    throw new Error(message);
  }
  return (payload?.data ?? payload) as T;
}

function errorMessageFromResponse(text: string, fallback: string) {
  if (!text) return fallback;
  try {
    const payload = JSON.parse(text);
    const detail = payload?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) return detail.map((item) => item?.msg || JSON.stringify(item)).join("\n");
    if (payload?.message) return String(payload.message);
    if (payload?.error) return String(payload.error);
  } catch {
    // Plain text errors are already readable.
  }
  return text;
}

export const contentTypeLabels: Record<ContentType, string> = {
  mnemonic: "口诀",
  tri_color: "三色笔记",
  summary_pages: "考前 N 页纸",
  formula_dict: "公式/分录大全",
  compare_table: "易错对比",
  exam_review: "真题串讲",
};

export const reviewModeLabels: Record<ReviewMode, string> = {
  llm_only: "纯大模型",
  document_only: "仅依据文档",
  hybrid: "混合审查",
};

export const workflowStatusLabels: Record<WorkflowTopicStatus, string> = {
  idea: "选题池",
  planned: "已排期",
  drafting: "生成中",
  generated: "待审查",
  reviewing: "审查中",
  needs_changes: "需修改",
  awaiting_confirm: "待确认",
  approved: "已确认",
  exported: "已导出",
  published: "已发布",
  archived: "已归档",
};

export const workflowReviewStatusLabels: Record<WorkflowReviewStatus, string> = {
  not_started: "未审查",
  reviewing: "审查中",
  passed: "已通过",
  needs_changes: "需修改",
  waived: "跳过审查",
};

export const workflowPriorityLabels: Record<WorkflowPriority, string> = {
  low: "低",
  medium: "中",
  high: "高",
  urgent: "紧急",
};
