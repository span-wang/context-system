"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, FileText, RefreshCw, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, PaperSummary } from "../../../../lib/pro-api";
import { renderDocumentPreviewHtml } from "../../../../lib/document-preview";

type PaperPreviewPayload = {
  paper_id: number;
  asset_id: number;
  filename: string;
  provider: string;
  raw_text: string;
  raw_markdown: string;
  text: string;
  markdown: string;
  content: string;
  token_count: number;
  cleanup_report: Record<string, unknown>;
  cleanup_score: number | null;
  parse_options: Record<string, unknown>;
  parse_runtime: Record<string, unknown>;
  execution_mode: string;
  cached_at?: string | null;
  warnings: string[];
};

export default function PaperPreviewPage() {
  return (
    <Suspense fallback={<div className="panel"><div className="panelBody">加载中...</div></div>}>
      <PaperPreviewPageContent />
    </Suspense>
  );
}

function PaperPreviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedPaperId = Number(searchParams.get("paper_id") || 0) || 0;

  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [selectedPaperId, setSelectedPaperId] = useState(0);
  const [preview, setPreview] = useState<PaperPreviewPayload | null>(null);

  const rawPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.raw_text || preview?.raw_markdown || preview?.text || preview?.markdown || ""),
    [preview],
  );
  const cleanedPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.content || preview?.markdown || preview?.text || ""),
    [preview],
  );
  const selectedPaperSummary = useMemo(
    () => papers.find((paper) => paper.id === selectedPaperId) || null,
    [papers, selectedPaperId],
  );
  const parseRuntime = useMemo(
    () => readPreviewObject(preview?.parse_runtime) || {},
    [preview],
  );
  const resolvedOptions = useMemo(
    () => readPreviewObject(parseRuntime["options"]) || readPreviewObject(preview?.parse_options) || {},
    [parseRuntime, preview],
  );
  const modelSettings = useMemo(
    () => readPreviewObject(parseRuntime["model_settings"]) || {},
    [parseRuntime],
  );

  useEffect(() => {
    loadPapers().catch((err) => setError(err instanceof Error ? err.message : "加载试卷列表失败"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadPapers() {
    setLoadingFiles(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      const data = await apiFetch<PaperSummary[]>(`/api/papers?${params.toString()}`);
      setPapers(data);
      if (!data.length) {
        setSelectedPaperId(0);
        setPreview(null);
        return;
      }
      const preferredId =
        (requestedPaperId && data.some((paper) => paper.id === requestedPaperId) && requestedPaperId) ||
        (selectedPaperId && data.some((paper) => paper.id === selectedPaperId) && selectedPaperId) ||
        data[0].id;
      if (preferredId && preferredId !== selectedPaperId) {
        const next = data.find((paper) => paper.id === preferredId);
        if (next) {
          await openPaper(next, { replaceUrl: !requestedPaperId });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载试卷列表失败");
    } finally {
      setLoadingFiles(false);
    }
  }

  async function openPaper(paper: PaperSummary, options?: { replaceUrl?: boolean }) {
    setSelectedPaperId(paper.id);
    setMessage(`正在读取 ${paper.paper_name} 的正式解析缓存...`);
    setError("");
    if (options?.replaceUrl !== false) {
      router.replace(`/analysis/papers/preview?paper_id=${paper.id}`);
    }
    await loadPreview(paper.id);
  }

  async function loadPreview(paperId: number) {
    setLoadingPreview(true);
    setError("");
    try {
      const result = await apiFetch<PaperPreviewPayload>(`/api/papers/${paperId}/preview`);
      setPreview(result);
      setMessage(`已加载 ${result.filename} 的正式解析缓存。`);
    } catch (err) {
      setPreview(null);
      setError(err instanceof Error ? err.message : "加载解析预览失败");
    } finally {
      setLoadingPreview(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>解析预览</h1>
          <p>这里只展示最近一次正式解析缓存；如需换参数，请回试卷中心重新正式解析。</p>
        </div>
        <div className="buttonRow">
          <Link className="button" href="/analysis/papers">
            <ArrowLeft size={17} />
            返回试卷中心
          </Link>
          <button className="button" disabled={loadingFiles} type="button" onClick={() => loadPapers()}>
            <RefreshCw size={17} />
            刷新列表
          </button>
        </div>
      </header>

      <section className="gridTwo libraryPreviewLayout">
        <div className="panel libraryPreviewSidebar">
          <div className="panelHeader">
            <h2>试卷列表</h2>
            <p>搜索试卷后点选一条，右侧直接读取最近一次正式解析缓存。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="field">
              <label>搜索</label>
              <div className="row">
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="试卷名、学科、区域" />
                <button className="button" type="button" onClick={() => loadPapers()}>
                  <Search size={16} />
                  筛选
                </button>
              </div>
            </div>
            <div className="previewFileList">
              {papers.map((paper) => (
                <button
                  className={selectedPaperId === paper.id ? "previewFileButton active" : "previewFileButton"}
                  key={paper.id}
                  type="button"
                  onClick={() => openPaper(paper)}
                >
                  <strong>{paper.paper_name}</strong>
                  <span>
                    {paper.category || "未分类"} / {paper.exam_year || "-"} / {paper.exam_region || "未知地区"} / {paper.total_question_count} 题
                  </span>
                </button>
              ))}
            </div>
            {!papers.length && <div className="empty">没有匹配的试卷。</div>}
            {!!error && <p className="errorText">{error}</p>}
            {!!message && <p className="muted">{message}</p>}
          </div>
        </div>

        <div className="panel libraryPreviewMain">
          <div className="panelHeader">
            <h2>{preview?.filename || selectedPaperSummary?.paper_name || "未选择试卷"}</h2>
            <p>
              {preview
                ? `Token ${preview.token_count.toLocaleString()} · 解析器 ${preview.provider}`
                : "选择左侧试卷开始查看正式解析缓存。"}
            </p>
          </div>
          <div className="panelBody">
            <div className="buttonRow">
              <button
                className="button primary"
                disabled={!selectedPaperId || loadingPreview}
                type="button"
                onClick={() => selectedPaperId && loadPreview(selectedPaperId)}
              >
                <FileText size={16} />
                {loadingPreview ? "加载中..." : "刷新缓存预览"}
              </button>
              {selectedPaperSummary && (
                <span className="muted">
                  {selectedPaperSummary.category || "未分类"} / {selectedPaperSummary.exam_year || "-"} / {selectedPaperSummary.exam_region || "未知地区"}
                </span>
              )}
            </div>

            {preview && (
              <>
                <div className="previewCleanupMeta">
                  <div className="detailRow">
                    <span>缓存时间</span>
                    <strong>{formatCachedAt(preview.cached_at)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>执行模式</span>
                    <strong>{parseExecutionModeLabel(preview.execution_mode)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>解析预设</span>
                    <strong>{parsePresetLabel(stringValue(resolvedOptions["preset"]))}</strong>
                  </div>
                  <div className="detailRow">
                    <span>输出格式</span>
                    <strong>{stringValue(resolvedOptions["output_format"], "-").toUpperCase()}</strong>
                  </div>
                  <div className="detailRow">
                    <span>渲染 DPI</span>
                    <strong>{stringValue(resolvedOptions["render_dpi"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>每批页数</span>
                    <strong>{stringValue(resolvedOptions["page_chunk_size"] ?? resolvedOptions["pdf_page_chunk_size"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>强制 OCR</span>
                    <strong>{boolLabel(resolvedOptions["force_ocr"], "是", "否")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>原始 OCR 模式</span>
                    <strong>{boolLabel(resolvedOptions["raw_ocr_mode"], "开启", "关闭")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>保留 PDF 图片</span>
                    <strong>{boolLabel(resolvedOptions["preserve_pdf_image_content"], "开启", "关闭", true)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>页眉裁切</span>
                    <strong>{stringValue(resolvedOptions["crop_header_ratio"], "0")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>页脚裁切</span>
                    <strong>{stringValue(resolvedOptions["crop_footer_ratio"], "0")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>空白边裁切</span>
                    <strong>{boolLabel(resolvedOptions["trim_margins"], "开启", "关闭", true)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>重复行清理</span>
                    <strong>{boolLabel(resolvedOptions["remove_repeated_lines"], "开启", "关闭", true)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>浅色水印弱化</span>
                    <strong>{boolLabel(resolvedOptions["watermark_detection"], "开启", "关闭", true)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>公式识别</span>
                    <strong>{boolLabel(resolvedOptions["enable_formula_recognition"], "开启", "关闭", true)}</strong>
                  </div>
                  <div className="detailRow">
                    <span>OCR 引擎</span>
                    <strong>{stringValue(modelSettings["engine"], preview.provider || "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>设备</span>
                    <strong>{stringValue(modelSettings["device"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>OCR 版本</span>
                    <strong>{stringValue(modelSettings["ocr_version"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>检测模型</span>
                    <strong>{stringValue(modelSettings["text_detection_model_name"] || modelSettings["text_detection_model_dir"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>识别模型</span>
                    <strong>{stringValue(modelSettings["text_recognition_model_name"] || modelSettings["text_recognition_model_dir"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>VL1.5 模型源</span>
                    <strong>{stringValue(modelSettings["model_source"], "-")}</strong>
                  </div>
                  <div className="detailRow">
                    <span>清洗分</span>
                    <strong>{typeof preview.cleanup_score === "number" ? preview.cleanup_score.toFixed(2) : "-"}</strong>
                  </div>
                  <div className="detailRow">
                    <span>清洗摘要</span>
                    <strong>{formatCleanupSummary(preview.cleanup_report)}</strong>
                  </div>
                </div>

                <div className="previewCompareGrid">
                  <div className="previewComparePane">
                    <div className="previewCompareTitle">
                      <strong>原始 OCR</strong>
                      <span>正式解析时保存的原始识别结果</span>
                    </div>
                    <div
                      className="markdown comparePre paperPreviewHtml"
                      dangerouslySetInnerHTML={{ __html: rawPreviewHtml }}
                    />
                  </div>
                  <div className="previewComparePane">
                    <div className="previewCompareTitle">
                      <strong>清噪结构化</strong>
                      <span>正式解析时保存的可切题结果</span>
                    </div>
                    <div
                      className="markdown comparePre paperPreviewHtml"
                      dangerouslySetInnerHTML={{ __html: cleanedPreviewHtml }}
                    />
                  </div>
                </div>
                {!!preview.warnings.length && <p className="muted">{preview.warnings.join(" | ")}</p>}
              </>
            )}

            {!preview && !loadingPreview && <div className="empty">先选择一个试卷查看正式解析缓存。</div>}
          </div>
        </div>
      </section>
    </>
  );
}

function readPreviewObject(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function stringValue(value: unknown, fallback = ""): string {
  if (typeof value === "string") {
    return value.trim() || fallback;
  }
  if (typeof value === "number" || typeof value === "boolean") {
    return String(value);
  }
  return fallback;
}

function boolLabel(value: unknown, yes: string, no: string, defaultTrue = false): string {
  if (typeof value === "boolean") {
    return value ? yes : no;
  }
  return defaultTrue ? yes : no;
}

function parsePresetLabel(value: string): string {
  const labels: Record<string, string> = {
    vl15: "VL1.5",
    v3: "V3",
    accurate: "V3",
    formula: "V3",
    v5: "V3",
    balanced: "V3",
    fast: "V3",
    auto: "V3",
  };
  return labels[value] || value || "-";
}

function parseExecutionModeLabel(value: string): string {
  const labels: Record<string, string> = {
    ocr_only: "仅 OCR",
    ai_cleanup_split: "AI 清洗切题",
    full_chain: "完整链路",
  };
  return labels[value] || value || "-";
}

function formatCachedAt(value?: string | null): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN");
}

function formatCleanupSummary(report?: Record<string, unknown> | null): string {
  if (!report) return "无";
  const removed = Number(report.removed_lines || 0);
  const split = Number(report.split_lines || 0);
  const merged = Number(report.merged_lines || 0);
  const repeated = Number(report.repeated_noise_lines || 0);
  return `删 ${removed} · 拆 ${split} · 合 ${merged} · 重复噪音 ${repeated}`;
}
