"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, FileText, RefreshCw, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, ParseOutputFormat, ParsePreset, PaperDetailResponse, PaperSummary } from "../../../../lib/pro-api";
import { renderDocumentPreviewHtml } from "../../../../lib/document-preview";

const parsePresetOptions: Array<{ value: ParsePreset; label: string }> = [
  { value: "accurate", label: "高精度" },
  { value: "formula", label: "公式增强" },
  { value: "balanced", label: "均衡" },
  { value: "fast", label: "高速" },
  { value: "auto", label: "自动" },
];

const parseOutputFormatOptions: Array<{ value: ParseOutputFormat; label: string }> = [
  { value: "markdown", label: "Markdown" },
  { value: "text", label: "TXT" },
];

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
  const [selectedPaper, setSelectedPaper] = useState<PaperDetailResponse | null>(null);
  const [preview, setPreview] = useState<any>(null);
  const [parsePreset, setParsePreset] = useState<ParsePreset>("accurate");
  const [outputFormat, setOutputFormat] = useState<ParseOutputFormat>("markdown");
  const [forceOcr, setForceOcr] = useState(false);
  const [pageChunkSize, setPageChunkSize] = useState("4");
  const [headerRatio, setHeaderRatio] = useState("0.00");
  const [footerRatio, setFooterRatio] = useState("0.00");
  const rawPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.raw_markdown || preview?.raw_text || preview?.markdown || preview?.text || ""),
    [preview],
  );
  const cleanedPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.content || preview?.markdown || preview?.text || ""),
    [preview],
  );

  const selectedPaperSummary = useMemo(
    () => papers.find((paper) => paper.id === selectedPaperId) || null,
    [papers, selectedPaperId]
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
        setSelectedPaper(null);
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

  function buildParseParams() {
    const params = new URLSearchParams({
      preset: parsePreset,
      output_format: outputFormat,
    });
    if (forceOcr) params.set("force_ocr", "true");
    if (Number(pageChunkSize) > 0) params.set("pdf_page_chunk_size", String(Number(pageChunkSize)));
    if (Number(headerRatio) > 0) params.set("crop_header_ratio", String(Number(headerRatio)));
    if (Number(footerRatio) > 0) params.set("crop_footer_ratio", String(Number(footerRatio)));
    return params;
  }

  async function openPaper(paper: PaperSummary, options?: { replaceUrl?: boolean }) {
    setSelectedPaperId(paper.id);
    setMessage(`正在加载 ${paper.paper_name}...`);
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
      const params = buildParseParams();
      const result = await apiFetch<any>(`/api/papers/${paperId}/preview?${params.toString()}`);
      setPreview(result);
      setSelectedPaper(result);
      setMessage(`已加载 ${result.filename} 的对照预览。`);
    } catch (err) {
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
          <p>左侧试卷，右侧原始 OCR 与清噪结构化结果对照。</p>
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
            <p>搜索试卷后点选一条，右侧会直接显示原文和清洗结果对照。</p>
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
            <p>{preview ? `Token ${preview.token_count.toLocaleString()} · 解析器 ${preview.provider}` : "选择左侧试卷开始查看对照结果。"}</p>
          </div>
          <div className="panelBody">
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
            <div className="buttonRow">
              <button
                className="button primary"
                disabled={!selectedPaperId || loadingPreview}
                type="button"
                onClick={() => selectedPaperId && loadPreview(selectedPaperId)}
              >
                <FileText size={16} />
                {loadingPreview ? "加载中..." : "刷新当前预览"}
              </button>
              {selectedPaperSummary && (
                <span className="muted">
                  {selectedPaperSummary.category || "未分类"} / {selectedPaperSummary.exam_year || "-"} / {selectedPaperSummary.exam_region || "未知地区"}
                </span>
              )}
            </div>
            {preview && (
              <>
                <div className="previewCompareGrid">
                  <div className="previewComparePane">
                    <div className="previewCompareTitle">
                      <strong>原始 OCR</strong>
                      <span>扫描识别结果</span>
                    </div>
                    <div
                      className="markdown comparePre paperPreviewHtml"
                      dangerouslySetInnerHTML={{ __html: rawPreviewHtml }}
                    />
                  </div>
                  <div className="previewComparePane">
                    <div className="previewCompareTitle">
                      <strong>清噪结构化</strong>
                      <span>可切题结果</span>
                    </div>
                    <div
                      className="markdown comparePre paperPreviewHtml"
                      dangerouslySetInnerHTML={{ __html: cleanedPreviewHtml }}
                    />
                  </div>
                </div>
                <div className="previewCleanupMeta">
                  <div className="detailRow">
                    <span>清洗分</span>
                    <strong>{typeof preview.cleanup_score === "number" ? preview.cleanup_score.toFixed(2) : "-"}</strong>
                  </div>
                  <div className="detailRow">
                    <span>清洗摘要</span>
                    <strong>{formatCleanupSummary(preview.cleanup_report)}</strong>
                  </div>
                </div>
                {!!preview.warnings.length && <p className="muted">{preview.warnings.join(" | ")}</p>}
              </>
            )}
            {!preview && !loadingPreview && <div className="empty">先选择一个试卷查看对照结果。</div>}
          </div>
        </div>
      </section>
    </>
  );
}

function formatCleanupSummary(report?: Record<string, unknown> | null): string {
  if (!report) return "无";
  const removed = Number(report.removed_lines || 0);
  const split = Number(report.split_lines || 0);
  const merged = Number(report.merged_lines || 0);
  const repeated = Number(report.repeated_noise_lines || 0);
  return `删 ${removed} · 拆 ${split} · 合 ${merged} · 重复噪音 ${repeated}`;
}
