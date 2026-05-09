"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { FileText, RefreshCw, RotateCcw, Trash2, UploadCloud, ExternalLink } from "lucide-react";
import {
  apiFetch,
  LibraryFile,
  LibraryParseJobResponse,
  LibraryParseJobStatus,
  LibraryParseMode,
  LibraryReparseResponse,
  ParseOutputFormat,
  ParsePreset,
  SubjectConfig,
} from "../../lib/api";
import {
  apiFetch as platformApiFetch,
  SubjectCategoryResponse,
  SubjectResponse,
} from "../../lib/pro-api";

const libraryPreviewChars = 200_000;

const sourceTypes = [
  ["textbook", "教材"],
  ["standard", "规范"],
  ["regulation", "法规"],
  ["exam", "真题"],
  ["note", "笔记"],
  ["other", "其他"],
];

const parsePresetOptions: Array<{ value: ParsePreset; label: string }> = [
  { value: "auto", label: "自动" },
  { value: "fast", label: "高速" },
  { value: "balanced", label: "均衡" },
  { value: "accurate", label: "高精度" },
  { value: "formula", label: "公式增强" },
];

const parseOutputFormatOptions: Array<{ value: ParseOutputFormat; label: string }> = [
  { value: "markdown", label: "Markdown" },
  { value: "text", label: "TXT" },
];

export default function LibraryPage() {
  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [uploadFiles, setUploadFiles] = useState<FileList | null>(null);
  const [message, setMessage] = useState("");
  const [previewError, setPreviewError] = useState("");
  const [loading, setLoading] = useState(false);
  const [reparsingId, setReparsingId] = useState<string | null>(null);
  const [parsingFileId, setParsingFileId] = useState<string | null>(null);
  const [parseJob, setParseJob] = useState<LibraryParseJobStatus | null>(null);
  const [reparseResult, setReparseResult] = useState<LibraryReparseResponse | null>(null);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);
  const [parsePreset, setParsePreset] = useState<ParsePreset>("auto");
  const [outputFormat, setOutputFormat] = useState<ParseOutputFormat>("markdown");
  const [forceOcr, setForceOcr] = useState(false);
  const [pageChunkSize, setPageChunkSize] = useState("4");
  const [headerRatio, setHeaderRatio] = useState("0.00");
  const [footerRatio, setFooterRatio] = useState("0.00");
  const [meta, setMeta] = useState({
    subject: "",
    category: "",
    chapter: "",
    source_type: "textbook",
    source_authority: "high",
    source_title: "",
    source_publisher: "",
    source_code: "",
    source_version: "",
    year: "",
    tags: "",
  });
  const [filters, setFilters] = useState({ subject: "", search: "" });

  async function loadFiles() {
    const params = new URLSearchParams();
    if (filters.subject) params.set("subject", filters.subject);
    if (filters.search) params.set("search", filters.search);
    const data = await apiFetch<LibraryFile[]>(`/api/library/files?${params.toString()}`);
    setFiles(data);
  }

  async function loadSubjects() {
    const [subjectList, categoryList] = await Promise.all([
      platformApiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
      platformApiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
    ]);
    const nextSubjects = buildSubjectConfigs(subjectList, categoryList);
    setSubjects(nextSubjects);
    setMeta((current) => normalizeMetaSubject(current, nextSubjects));
  }

  useEffect(() => {
    loadFiles().catch((error) => setMessage(error.message));
    loadSubjects().catch((error) => setMessage(error.message));
  }, []);

  useEffect(() => {
    if (!parseJob || !["pending", "running"].includes(parseJob.status)) return;
    const timer = window.setInterval(() => {
      loadParseJob(parseJob.id).catch((error) => setPreviewError(error.message || "刷新解析进度失败"));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [parseJob?.id, parseJob?.status]);

  const totalSize = useMemo(() => files.reduce((sum, file) => sum + file.size, 0), [files]);
  const activeSubject = useMemo(
    () => subjects.find((subject) => subject.name === meta.subject) || null,
    [meta.subject, subjects]
  );

  async function onUpload(event: FormEvent) {
    event.preventDefault();
    if (!uploadFiles?.length) {
      setMessage("请选择要上传的资料。");
      return;
    }
    if (!meta.subject) {
      setMessage("请先在学科中心添加学科。");
      return;
    }
    setLoading(true);
    setMessage("");
    try {
      const form = new FormData();
      Array.from(uploadFiles).forEach((file) => form.append("files", file));
      form.append(
        "batch_meta",
        JSON.stringify({
          ...meta,
          source_title: meta.source_title.trim(),
          year: meta.year ? Number(meta.year) : null,
          tags: meta.tags.split(/[，,\s]+/).filter(Boolean),
        })
      );
      await apiFetch<LibraryFile[]>("/api/library/upload", { method: "POST", body: form });
      setMessage("上传完成。");
      await loadFiles();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "上传失败");
    } finally {
      setLoading(false);
    }
  }

  async function deleteFile(id: string) {
    await apiFetch(`/api/library/files/${id}`, { method: "DELETE" });
    await loadFiles();
  }

  function buildParseParams() {
    const params = new URLSearchParams({
      max_chars: String(libraryPreviewChars),
      preset: parsePreset,
      output_format: outputFormat,
    });
    if (forceOcr) params.set("force_ocr", "true");
    if (Number(pageChunkSize) > 0) params.set("pdf_page_chunk_size", String(Number(pageChunkSize)));
    if (Number(headerRatio) > 0) params.set("crop_header_ratio", String(Number(headerRatio)));
    if (Number(footerRatio) > 0) params.set("crop_footer_ratio", String(Number(footerRatio)));
    return params;
  }

  async function startParseJob(file: LibraryFile, mode: LibraryParseMode) {
    setPreviewError("");
    setMessage("");
    setReparseResult(null);
    setParseJob(null);
    setParsingFileId(file.id);
    setReparsingId(mode === "reparse" ? file.id : null);
    try {
      const params = buildParseParams();
      params.set("mode", mode);
      const data = await apiFetch<LibraryParseJobResponse>(
        `/api/library/files/${file.id}/parse-jobs?${params.toString()}`,
        { method: "POST" }
      );
      setParseJob({
        id: data.job_id,
        job_type: "library_parse",
        scope_type: "library_file",
        scope_config_json: {
          stage: "queued",
          file_id: file.id,
          filename: file.filename,
          mode,
          detail: { file_id: file.id, filename: file.filename, mode },
        },
        status: data.status,
        progress: data.progress,
        created_at: new Date().toISOString(),
      });
      setMessage(`${libraryJobModeLabel(mode)}任务已启动：#${data.job_id}`);
      await loadParseJob(data.job_id);
    } catch (error) {
      setPreviewError(error instanceof Error ? error.message : "启动解析任务失败");
      setParsingFileId(null);
      if (mode === "reparse") setReparsingId(null);
    }
  }

  async function reparseFile(file: LibraryFile) {
    await startParseJob(file, "reparse");
  }

  async function loadParseJob(jobId: number) {
    const job = await apiFetch<LibraryParseJobStatus>(`/api/library/parse-jobs/${jobId}`);
    setParseJob(job);
    if (job.status === "completed") {
      const result = job.result_summary_json;
      if (isLibraryReparseResult(result)) {
        setReparseResult(result);
        setMessage(
          `重新入库完成：第 ${result.stored_sequence_number} 次结果，完整 Token ${result.token_count.toLocaleString()}，保留 ${result.kept_results.length} 条。`
        );
      } else {
        setMessage("解析预览完成。");
      }
      setParsingFileId(null);
      setReparsingId(null);
      await loadFiles();
    }
    if (job.status === "failed") {
      setPreviewError(job.error_message || "解析任务失败");
      setParsingFileId(null);
      setReparsingId(null);
    }
    return job;
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>素材库</h1>
          <p>上传教材、规范、法规、真题和笔记，系统会按 SHA256 去重，并在首次使用时解析缓存。</p>
        </div>
        <div className="buttonRow">
          <span className="badge">{files.length} 个文件</span>
          <span className="badge">{(totalSize / 1024 / 1024).toFixed(2)} MB</span>
        </div>
      </header>

      <section className="gridTwo">
        <form className="panel" onSubmit={onUpload}>
          <div className="panelHeader">
            <h2>批量上传</h2>
            <p>先填写批次元数据，必要时后续可单独编辑文件。</p>
          </div>
          <div className="panelBody formGrid">
            <label className="dropzone">
              <UploadCloud size={28} />
              <strong>{uploadFiles?.length ? `${uploadFiles.length} 个文件已选择` : "选择或拖入资料"}</strong>
              <span>PDF / 图片 / DOCX / Markdown / TXT</span>
              <input
                hidden
                multiple
                type="file"
                accept=".pdf,.doc,.docx,.md,.markdown,.txt,.png,.jpg,.jpeg,.webp,.bmp,.tif,.tiff,application/pdf,image/*"
                onChange={(event) => setUploadFiles(event.target.files)}
              />
            </label>
            <div className="row">
              <div className="field">
                <label>学科</label>
                <select value={meta.subject} onChange={(e) => setMeta(selectMetaSubject(meta, subjects, e.target.value))}>
                  {!subjects.length && <option value="">请先在学科中心添加学科</option>}
                  {subjects.map((subject) => (
                    <option key={subject.id} value={subject.name}>
                      {subject.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>类目</label>
                <select value={meta.category} onChange={(e) => setMeta({ ...meta, category: e.target.value })}>
                  <option value="">未分类</option>
                  {activeSubject?.categories.map((category) => (
                    <option key={category} value={category}>
                      {category}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <label>章节</label>
              <input value={meta.chapter} onChange={(e) => setMeta({ ...meta, chapter: e.target.value })} />
            </div>
            <div className="row">
              <div className="field">
                <label>来源类型</label>
                <select value={meta.source_type} onChange={(e) => setMeta({ ...meta, source_type: e.target.value })}>
                  {sourceTypes.map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>权威等级</label>
                <select
                  value={meta.source_authority}
                  onChange={(e) => setMeta({ ...meta, source_authority: e.target.value })}
                >
                  <option value="high">high</option>
                  <option value="medium">medium</option>
                  <option value="low">low</option>
                </select>
              </div>
            </div>
            <div className="field">
              <label>来源标题</label>
              <input
                value={meta.source_title}
                onChange={(e) => setMeta({ ...meta, source_title: e.target.value })}
                placeholder="例如 2026 CPA 会计教材"
              />
            </div>
            <div className="row">
              <div className="field">
                <label>版本/规范号</label>
                <input
                  value={meta.source_version}
                  onChange={(e) => setMeta({ ...meta, source_version: e.target.value })}
                />
              </div>
              <div className="field">
                <label>年份</label>
                <input value={meta.year} onChange={(e) => setMeta({ ...meta, year: e.target.value })} />
              </div>
            </div>
            <div className="field">
              <label>标签</label>
              <input
                value={meta.tags}
                onChange={(e) => setMeta({ ...meta, tags: e.target.value })}
                placeholder="高频, 易错, 冲刺"
              />
            </div>
            <div className="buttonRow">
              <button className="button primary" disabled={loading} type="submit">
                <UploadCloud size={17} />
                上传入库
              </button>
              <button className="button" type="button" onClick={loadFiles}>
                <RefreshCw size={17} />
                刷新
              </button>
            </div>
            {message && <p className="muted">{message}</p>}
          </div>
        </form>

        <div className="panel">
          <div className="panelHeader">
            <h2>文件列表</h2>
            <p>按学科和关键词筛选。首次预览会解析入库，后续点击只展示已保存结果；如需按新参数重跑，请点重新解析入库。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="row">
              <div className="field">
                <label>解析预设</label>
                <select value={parsePreset} onChange={(e) => setParsePreset(e.target.value as ParsePreset)}>
                  {parsePresetOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                  </select>
              </div>
              <div className="field">
                <label>输出格式</label>
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as ParseOutputFormat)}>
                  {parseOutputFormatOptions.map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>强制 OCR</label>
                <select value={forceOcr ? "true" : "false"} onChange={(e) => setForceOcr(e.target.value === "true")}>
                  <option value="false">否</option>
                  <option value="true">是</option>
                </select>
              </div>
              <div className="field">
                <label>每批页数</label>
                <input
                  min="1"
                  max="50"
                  step="1"
                  type="number"
                  value={pageChunkSize}
                  onChange={(e) => setPageChunkSize(e.target.value)}
                />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>页眉裁切</label>
                <input value={headerRatio} onChange={(e) => setHeaderRatio(e.target.value)} placeholder="0.04" />
              </div>
              <div className="field">
                <label>页脚裁切</label>
                <input value={footerRatio} onChange={(e) => setFooterRatio(e.target.value)} placeholder="0.05" />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>学科筛选</label>
                <select value={filters.subject} onChange={(e) => setFilters({ ...filters, subject: e.target.value })}>
                  <option value="">全部学科</option>
                  {subjects.map((subject) => (
                    <option key={subject.id} value={subject.name}>
                      {subject.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>搜索</label>
                <input value={filters.search} onChange={(e) => setFilters({ ...filters, search: e.target.value })} />
              </div>
            </div>
            <button className="button" type="button" onClick={loadFiles}>
              <RefreshCw size={17} />
              应用筛选
            </button>
            <div className="tableWrap">
              <table>
                <thead>
                  <tr>
                    <th>文件</th>
                    <th>学科/类目</th>
                    <th>来源</th>
                    <th>Token</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {files.map((file) => (
                    <tr key={file.id}>
                      <td>
                        <strong>{file.filename}</strong>
                        <div className="muted">{(file.size / 1024).toFixed(1)} KB</div>
                      </td>
                      <td>
                        {file.subject}
                        <div className="muted">{[file.category, file.chapter].filter(Boolean).join(" / ")}</div>
                      </td>
                      <td>
                        <span className={`badge ${file.source_authority}`}>{file.source_authority}</span>
                        <div className="muted">{file.source_title}</div>
                      </td>
                      <td>{renderTokenStatus(file)}</td>
                      <td>
                        <div className="buttonRow">
                          <Link className="button" href={`/analysis/papers/preview?file_id=${file.id}`} title="解析预览">
                            <ExternalLink size={16} />
                          </Link>
                          <button
                            className="button"
                            type="button"
                            disabled={parsingFileId === file.id || reparsingId === file.id}
                            onClick={() => reparseFile(file)}
                            title="重新解析并入库"
                          >
                            <RotateCcw size={16} />
                          </button>
                          <button className="button danger" type="button" onClick={() => deleteFile(file.id)}>
                            <Trash2 size={16} />
                          </button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!files.length && <div className="empty">素材库还没有文件。</div>}
            {parseJob && (
              <div className="calloutBox">
                <div className="detailRow">
                  <span>解析任务</span>
                  <strong>
                    #{parseJob.id} · {libraryStageLabel(parseJob.scope_config_json?.stage)} · {parseJob.progress}%
                  </strong>
                </div>
                <div className="progressTrack" aria-label="素材解析进度">
                  <div className="progressFill" style={{ width: `${Math.max(3, Math.min(100, parseJob.progress))}%` }} />
                </div>
                <p className={parseJob.status === "failed" ? "errorText" : "muted"}>
                  {parseJob.status === "failed" ? parseJob.error_message || "解析失败" : libraryJobDetailText(parseJob)}
                </p>
                {parseJob.status !== "failed" && libraryJobChunkDetailText(parseJob) && (
                  <p className="muted">{libraryJobChunkDetailText(parseJob)}</p>
                )}
                {parseJob.status !== "failed" && libraryJobResumeDetailText(parseJob) && (
                  <p className="muted">{libraryJobResumeDetailText(parseJob)}</p>
                )}
              </div>
            )}
          </div>
        </div>
      </section>

    </>
  );
}

function renderTokenStatus(file: LibraryFile) {
  if (file.token_count == null) return "未解析";
  if (file.token_count === 0) return "解析为空";
  return file.token_count.toLocaleString();
}

function libraryJobModeLabel(mode?: LibraryParseMode | null) {
  return mode === "reparse" ? "重新解析入库" : "解析预览";
}

function libraryStageLabel(stage?: string) {
  const labels: Record<string, string> = {
    queued: "等待解析",
    prepare: "准备文件",
    read_file: "读取文件",
    cache: "命中缓存",
    ocr: "OCR 切片识别",
    layout_analysis: "版面切片分析",
    ocr_fallback: "OCR 兜底切片",
    completed: "完成",
    failed: "失败",
  };
  return labels[stage || ""] || stage || "处理中";
}

function libraryJobDetailText(job: LibraryParseJobStatus) {
  const detail = job.scope_config_json?.detail || {};
  const stage = String(job.scope_config_json?.stage || "");
  if (stage === "ocr" || stage === "layout_analysis" || stage === "ocr_fallback") {
    const done = Number(detail.done_pages || 0);
    const total = Number(detail.total_pages || 0);
    return total ? `${libraryStageLabel(stage)}：第 ${done} / ${total} 页` : libraryStageLabel(stage);
  }
  if (stage === "cache") {
    return "已命中解析缓存，正在整理预览结果。";
  }
  if (stage === "completed") {
    const provider = String(detail.provider || "-");
    const tokenCount = Number(detail.token_count || 0);
    return `解析完成：${tokenCount.toLocaleString()} Token，解析器 ${provider}`;
  }
  return "后台解析中，页面会自动刷新进度。";
}

function libraryJobChunkDetailText(job: LibraryParseJobStatus) {
  const detail = job.scope_config_json?.detail || {};
  const chunkCount = Number(detail.chunk_count || 0);
  const completedChunkCount = Number(detail.completed_chunk_count || 0);
  const currentChunkIndex = Number(detail.current_chunk_index || 0);
  const chunkFrom = Number(detail.current_chunk_page_from || 0);
  const chunkTo = Number(detail.current_chunk_page_to || 0);
  const pageBatchSize = Number(detail.page_batch_size || 0);
  if (!chunkCount) return "";
  if (currentChunkIndex && chunkFrom && chunkTo) {
    return `切片进度：已完成 ${Math.min(completedChunkCount, chunkCount)} / ${chunkCount} · 当前第 ${currentChunkIndex} 段（第 ${chunkFrom}-${chunkTo} 页）· 每批 ${pageBatchSize || "-"} 页`;
  }
  return `切片进度：已完成 ${Math.min(completedChunkCount, chunkCount)} / ${chunkCount} · 每批 ${pageBatchSize || "-"} 页`;
}

function libraryJobResumeDetailText(job: LibraryParseJobStatus) {
  const detail = job.scope_config_json?.detail || {};
  const resumedPages = Number(detail.resumed_pages || 0);
  const resumedChunks = Number(detail.resumed_chunk_count || 0);
  const resumeStartPage = Number(detail.resume_start_page || 0);
  if (!resumedPages && !resumedChunks) return "";
  if (resumeStartPage > 0) {
    return `断点续跑已复用 ${resumedPages} 页、${resumedChunks} 个切片，从第 ${resumeStartPage} 页继续。`;
  }
  return `断点续跑已复用 ${resumedPages} 页、${resumedChunks} 个切片，当前参数下无需重跑已完成部分。`;
}

function isLibraryReparseResult(value: unknown): value is LibraryReparseResponse {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<LibraryReparseResponse>;
  return (
    typeof item.file_id === "string" &&
    typeof item.filename === "string" &&
    typeof item.token_count === "number" &&
    typeof item.stored_sequence_number === "number" &&
    Array.isArray(item.kept_results)
  );
}


type LibraryMeta = {
  subject: string;
  category: string;
  chapter: string;
  source_type: string;
  source_authority: string;
  source_title: string;
  source_publisher: string;
  source_code: string;
  source_version: string;
  year: string;
  tags: string;
};

function normalizeMetaSubject(meta: LibraryMeta, subjects: SubjectConfig[]): LibraryMeta {
  const subject = findSubject(subjects, meta.subject) || subjects[0];
  if (!subject) return { ...meta, subject: "", category: "" };
  return {
    ...meta,
    subject: subject.name,
    category: subject.categories.includes(meta.category) ? meta.category : subject.categories[0] || "",
  };
}

function selectMetaSubject(meta: LibraryMeta, subjects: SubjectConfig[], name: string): LibraryMeta {
  const subject = findSubject(subjects, name);
  if (!subject) return { ...meta, subject: name, category: "" };
  return {
    ...meta,
    subject: subject.name,
    category: subject.categories.includes(meta.category) ? meta.category : subject.categories[0] || "",
  };
}

function findSubject(subjects: SubjectConfig[], value: string): SubjectConfig | undefined {
  const normalized = value.trim().toLowerCase();
  return subjects.find(
    (subject) =>
      subject.name === value ||
      subject.id.toLowerCase() === normalized ||
      (normalized === "cpa" && subject.id === "cpa")
  );
}

function buildSubjectConfigs(subjects: SubjectResponse[], categories: SubjectCategoryResponse[]): SubjectConfig[] {
  const categoriesBySubjectId = new Map<number, string[]>();
  for (const category of categories) {
    const current = categoriesBySubjectId.get(category.subject_id) || [];
    if (!current.includes(category.name)) current.push(category.name);
    categoriesBySubjectId.set(category.subject_id, current);
  }

  return subjects.map((subject) => ({
    id: subject.code || String(subject.id),
    name: subject.name,
    categories: categoriesBySubjectId.get(subject.id) || [],
    platform_id: subject.id,
  }));
}
