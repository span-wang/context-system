import { promises as fs } from "fs";
import path from "path";

const CHECKPOINT_NAMESPACE_FILENAME = "cache.namespace";
const JUDGE_OPTION_VALUES = ["正确", "错误"] as const;

export type TrainingSampleSummary = {
  id: string;
  paper_id: number | null;
  paper_name: string;
  subject_name: string | null;
  category_name: string | null;
  predicted_question_count: number;
  stored_needs_review_count: number;
  gold_exists: boolean;
  label_status: string;
  source_text_length: number;
  ai_source_text_length: number;
  updated_at: string | null;
};

export type TrainingDatasetSummary = {
  dataset_root: string;
  sample_count: number;
  gold_count: number;
  prediction_count: number;
  source_count: number;
  public_web_url: string | null;
  public_hostnames: string[];
  api_base: string | null;
  web_url: string | null;
  started_at: string | null;
  samples: TrainingSampleSummary[];
};

export type TrainingSampleDetail = {
  sample: TrainingSampleSummary;
  meta: Record<string, unknown>;
  raw_source_text: string;
  ai_source_text: string;
  ai_prediction_text: string;
  gold_template_text: string;
  gold_text: string;
};

export type TrainingSampleDeleteResult = {
  id: string;
  paper_name: string;
};

export async function listTrainingSamples(): Promise<TrainingDatasetSummary> {
  const datasetRoot = resolveDatasetRoot();
  const runtime = await readRuntimeInfo();
  let sampleCount = 0;
  let goldCount = 0;
  let predictionCount = 0;
  let sourceCount = 0;
  const samples: TrainingSampleSummary[] = [];

  try {
    const sampleDirs = await fs.readdir(datasetRoot, { withFileTypes: true });
    for (const entry of sampleDirs) {
      if (!entry.isDirectory()) {
        continue;
      }
      const samplePath = path.join(datasetRoot, entry.name);
      const sample = await buildSampleSummary(entry.name, samplePath);
      samples.push(sample);
      sampleCount += 1;
      if (sample.gold_exists) goldCount += 1;
      if (await fileExists(path.join(samplePath, "prediction.json"))) predictionCount += 1;
      if (await fileExists(path.join(samplePath, "source.txt"))) sourceCount += 1;
    }
  } catch {
    // Keep empty dataset state when the folder does not exist yet.
  }

  samples.sort((left, right) => {
    const leftUpdated = left.updated_at || "";
    const rightUpdated = right.updated_at || "";
    return rightUpdated.localeCompare(leftUpdated) || left.id.localeCompare(right.id);
  });

  return {
    dataset_root: datasetRoot,
    sample_count: sampleCount,
    gold_count: goldCount,
    prediction_count: predictionCount,
    source_count: sourceCount,
    public_web_url: runtime.public_web_url,
    public_hostnames: runtime.public_hostnames,
    api_base: runtime.api_base,
    web_url: runtime.web_url,
    started_at: runtime.started_at,
    samples,
  };
}

export async function readTrainingSample(sampleId: string): Promise<TrainingSampleDetail> {
  const samplePath = resolveSamplePath(sampleId);
  await ensureGoldFile(samplePath);
  const sample = await buildSampleSummary(sampleId, samplePath);
  let [metaText, rawSourceText, aiSourceText, aiPredictionText, goldTemplateText, goldText] = await Promise.all([
    readTextOrDefault(path.join(samplePath, "meta.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "raw_source.txt"), ""),
    readTextOrDefault(path.join(samplePath, "ai_source.txt"), ""),
    readTextOrDefault(path.join(samplePath, "ai_prediction.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "gold.template.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "gold.json"), ""),
  ]);
  const meta = parseJsonObject(metaText);
  const imageRoots = await resolveTrainingImageRoots(samplePath, meta);
  [rawSourceText, aiSourceText, aiPredictionText, goldTemplateText, goldText] = await Promise.all([
    inlineSampleImages(rawSourceText, imageRoots),
    inlineSampleImages(aiSourceText, imageRoots),
    inlineSampleImages(aiPredictionText, imageRoots),
    inlineSampleImages(goldTemplateText, imageRoots),
    inlineSampleImages(goldText, imageRoots),
  ]);

  return {
    sample,
    meta,
    raw_source_text: rawSourceText,
    ai_source_text: aiSourceText,
    ai_prediction_text: aiPredictionText,
    gold_template_text: goldTemplateText,
    gold_text: goldText || goldTemplateText,
  };
}

export async function saveTrainingSampleGold(sampleId: string, goldText: string): Promise<TrainingSampleDetail> {
  const samplePath = resolveSamplePath(sampleId);
  const normalized = formatJsonText(goldText);
  await fs.writeFile(path.join(samplePath, "gold.json"), normalized, "utf8");
  return readTrainingSample(sampleId);
}

export async function deleteTrainingSample(sampleId: string): Promise<TrainingSampleDeleteResult> {
  const samplePath = resolveSamplePath(sampleId);
  const sample = await buildSampleSummary(sampleId, samplePath);
  await fs.rm(samplePath, { recursive: true, force: false });
  return {
    id: sample.id,
    paper_name: sample.paper_name,
  };
}

function resolveRepoRoot(): string {
  return path.resolve(process.cwd(), "..", "..");
}

function resolveDatasetRoot(): string {
  return path.resolve(resolveRepoRoot(), "data", "paper_parser_dataset");
}

function resolveSamplePath(sampleId: string): string {
  if (!/^[0-9A-Za-z._-]+$/.test(sampleId)) {
    throw new Error("invalid sample id");
  }
  const datasetRoot = resolveDatasetRoot();
  const samplePath = path.resolve(datasetRoot, sampleId);
  const relative = path.relative(datasetRoot, samplePath);
  if (relative.startsWith("..") || path.isAbsolute(relative)) {
    throw new Error("sample path escapes dataset root");
  }
  return samplePath;
}

async function buildSampleSummary(sampleId: string, samplePath: string): Promise<TrainingSampleSummary> {
  await ensureGoldFile(samplePath);
  const meta = parseJsonObject(await readTextOrDefault(path.join(samplePath, "meta.json"), "{}"));
  const goldText = await readTextOrDefault(path.join(samplePath, "gold.json"), "");
  const gold = goldText ? parseJsonObject(goldText) : {};
  const goldExists = Boolean(goldText.trim());
  const stat = await fs.stat(samplePath);
  return {
    id: sampleId,
    paper_id: asNullableNumber(meta.paper_id),
    paper_name: asNullableString(meta.paper_name) || sampleId,
    subject_name: asNullableString(meta.subject_name),
    category_name: asNullableString(meta.category_name),
    predicted_question_count: asNumber(meta.predicted_question_count),
    stored_needs_review_count: asNumber(meta.stored_needs_review_count),
    gold_exists: goldExists,
    label_status: asNullableString(gold.label_status) || "draft",
    source_text_length: asNumber(meta.source_text_length),
    ai_source_text_length: asNumber(meta.ai_source_text_length),
    updated_at: stat.mtime.toISOString(),
  };
}

async function ensureGoldFile(samplePath: string): Promise<void> {
  const goldPath = path.join(samplePath, "gold.json");
  if (await fileExists(goldPath)) {
    return;
  }
  const templateText = await readTextOrDefault(path.join(samplePath, "gold.template.json"), "");
  if (!templateText.trim()) {
    return;
  }
  await fs.writeFile(goldPath, templateText, "utf8");
}

async function readRuntimeInfo(): Promise<{
  public_web_url: string | null;
  public_hostnames: string[];
  api_base: string | null;
  web_url: string | null;
  started_at: string | null;
}> {
  try {
    const portsPath = path.resolve(resolveRepoRoot(), "data", "run", "ports.json");
    const payload = JSON.parse((await fs.readFile(portsPath, "utf8")).replace(/^\uFEFF/, ""));
    return {
      public_web_url: asNullableString(payload.public_web_url),
      public_hostnames: Array.isArray(payload.public_hostnames)
        ? payload.public_hostnames
            .map((item: unknown) => asNullableString(item))
            .filter((item: string | null): item is string => Boolean(item))
        : [],
      api_base: asNullableString(payload.api_base),
      web_url: asNullableString(payload.web_url),
      started_at: asNullableString(payload.started_at),
    };
  } catch {
    return {
      public_web_url: null,
      public_hostnames: [],
      api_base: null,
      web_url: null,
      started_at: null,
    };
  }
}

async function readTextOrDefault(filePath: string, fallback: string): Promise<string> {
  try {
    return await fs.readFile(filePath, "utf8");
  } catch {
    return fallback;
  }
}

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await fs.access(filePath);
    return true;
  } catch {
    return false;
  }
}

function parseJsonObject(text: string): Record<string, unknown> {
  try {
    const payload = JSON.parse(text);
    return payload && typeof payload === "object" ? (payload as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function formatJsonText(text: string): string {
  const payload = JSON.parse(text);
  return `${JSON.stringify(normalizeTrainingDocumentPayload(payload), null, 2)}\n`;
}

function normalizeTrainingDocumentPayload(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return value;
  }
  const record = value as Record<string, unknown>;
  if (!Array.isArray(record.sections)) {
    return record;
  }
  return {
    ...record,
    sections: record.sections.map((section) => normalizeTrainingSectionPayload(section)),
  };
}

function normalizeTrainingSectionPayload(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return value;
  }
  const record = value as Record<string, unknown>;
  if (!Array.isArray(record.questions)) {
    return record;
  }
  return {
    ...record,
    questions: record.questions.map((question) => normalizeTrainingQuestionPayload(question)),
  };
}

function normalizeTrainingQuestionPayload(value: unknown): unknown {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    return value;
  }
  const record = value as Record<string, unknown>;
  if (!isJudgeQuestionType(record.question_type)) {
    return record;
  }
  return {
    ...record,
    options: [...JUDGE_OPTION_VALUES],
  };
}

function isJudgeQuestionType(value: unknown): boolean {
  if (typeof value !== "string") {
    return false;
  }
  const trimmed = value.trim();
  return trimmed.toLowerCase() === "judge" || trimmed === "判断题";
}

function asNullableString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value : null;
}

function asNullableNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function asNumber(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

async function inlineSampleImages(text: string, imageRoots: string[]): Promise<string> {
  if (!text.includes("imgs/")) {
    return text;
  }
  const htmlMatches = Array.from(text.matchAll(/<img([^>]*?)src=["'](imgs\/[^"']+)["']([^>]*?)>/gi));
  const markdownMatches = Array.from(text.matchAll(/!\[([^\]]*)\]\((imgs\/[^)\s]+)\)/g));
  let result = text;

  for (const match of htmlMatches) {
    const original = match[0];
    const before = match[1] || "";
    const imagePath = match[2] || "";
    const after = match[3] || "";
    const dataUrl = await sampleImageToDataUrl(imageRoots, imagePath);
    if (!dataUrl) continue;
    result = result.replace(original, `<img${before}src="${dataUrl}"${after}>`);
  }

  for (const match of markdownMatches) {
    const original = match[0];
    const alt = match[1] || "";
    const imagePath = match[2] || "";
    const dataUrl = await sampleImageToDataUrl(imageRoots, imagePath);
    if (!dataUrl) continue;
    result = result.replace(original, `![${alt}](${dataUrl})`);
  }

  return result;
}

async function sampleImageToDataUrl(imageRoots: string[], relativePath: string): Promise<string> {
  const normalized = relativePath.replace(/\\/g, "/").replace(/^\/+/, "");
  for (const imageRoot of imageRoots) {
    const primary = path.join(imageRoot, normalized);
    const fallback = normalized.startsWith("imgs/") ? path.join(imageRoot, normalized.slice(5)) : primary;
    for (const candidate of primary === fallback ? [primary] : [primary, fallback]) {
      try {
        const raw = await fs.readFile(candidate);
        const mime = imageMimeType(candidate);
        return `data:${mime};base64,${raw.toString("base64")}`;
      } catch {
        // try next
      }
    }
  }
  return "";
}

function imageMimeType(filePath: string): string {
  const suffix = path.extname(filePath).toLowerCase();
  if (suffix === ".png") return "image/png";
  if (suffix === ".webp") return "image/webp";
  if (suffix === ".gif") return "image/gif";
  if (suffix === ".bmp") return "image/bmp";
  if (suffix === ".svg") return "image/svg+xml";
  return "image/jpeg";
}

async function resolveTrainingImageRoots(samplePath: string, meta: Record<string, unknown>): Promise<string[]> {
  const roots: string[] = [];
  const sampleImgs = path.join(samplePath, "imgs");
  if (await fileExists(sampleImgs)) {
    roots.push(samplePath);
  }

  const assetId = asNullableNumber(meta.asset_id);
  if (!assetId) {
    return roots;
  }

  const checkpointRoot = path.resolve(resolveRepoRoot(), "data", "cache", "pdf_ocr_checkpoints", "layout");
  const namespace = `paper_asset_${assetId}`;
  const stack = [checkpointRoot];
  while (stack.length) {
    const current = stack.pop();
    if (!current) continue;
    let entries: import("fs").Dirent[] = [];
    try {
      entries = await fs.readdir(current, { withFileTypes: true });
    } catch {
      continue;
    }
    for (const entry of entries) {
      const fullPath = path.join(current, entry.name);
      if (entry.isDirectory()) {
        stack.push(fullPath);
        continue;
      }
      if (entry.name !== CHECKPOINT_NAMESPACE_FILENAME) {
        continue;
      }
      const text = (await readTextOrDefault(fullPath, "")).trim();
      if (text !== namespace) {
        continue;
      }
      const checkpointDir = path.dirname(fullPath);
      const assetEntries = await fs.readdir(checkpointDir, { withFileTypes: true }).catch(() => []);
      for (const assetEntry of assetEntries) {
        if (assetEntry.isDirectory() && /^page_\d+_assets$/i.test(assetEntry.name)) {
          roots.push(path.join(checkpointDir, assetEntry.name));
        }
      }
    }
  }

  return [...new Set(roots)];
}
