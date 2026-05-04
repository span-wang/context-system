export const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000";
export const LAYOUT_API_BASE = process.env.NEXT_PUBLIC_LAYOUT_API_BASE || "http://127.0.0.1:3210";

export type ContentType =
  | "mnemonic"
  | "tri_color"
  | "summary_pages"
  | "formula_dict"
  | "compare_table"
  | "exam_review";

export type ReviewMode = "llm_only" | "document_only" | "hybrid";

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
  text: string;
  truncated: boolean;
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
  unverified_warning?: string | null;
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
    unverified: boolean;
  } | null;
  review?: ReviewReport | null;
  created_at: string;
  error?: string | null;
};

export type LLMEndpointConfig = {
  provider: "local_template" | "local_rules" | "openai_compat" | "deepseek" | "anthropic";
  model: string;
  max_tokens: number;
  base_url?: string | null;
  has_api_key: boolean;
};

export type LLMPresetConfig = LLMEndpointConfig & {
  name: string;
};

export type SubjectConfig = {
  id: string;
  name: string;
  categories: string[];
};

export type SystemConfig = {
  app: {
    name: string;
    context_token_limit: number;
  };
  llm: {
    generator: LLMEndpointConfig;
    reviewer: LLMEndpointConfig;
    presets: LLMPresetConfig[];
  };
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
    throw new Error(text || response.statusText);
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
