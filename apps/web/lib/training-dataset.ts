import { promises as fs } from "fs";
import path from "path";

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
  source_text: string;
  prediction_text: string;
  gold_template_text: string;
  gold_text: string;
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
  const sample = await buildSampleSummary(sampleId, samplePath);
  const [metaText, sourceText, predictionText, goldTemplateText, goldText] = await Promise.all([
    readTextOrDefault(path.join(samplePath, "meta.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "source.txt"), ""),
    readTextOrDefault(path.join(samplePath, "prediction.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "gold.template.json"), "{}"),
    readTextOrDefault(path.join(samplePath, "gold.json"), ""),
  ]);

  return {
    sample,
    meta: parseJsonObject(metaText),
    source_text: sourceText,
    prediction_text: predictionText,
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
    label_status: asNullableString(gold.label_status) || (goldExists ? "draft" : "missing"),
    source_text_length: asNumber(meta.source_text_length),
    updated_at: stat.mtime.toISOString(),
  };
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
  return `${JSON.stringify(payload, null, 2)}\n`;
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
