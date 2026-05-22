"use client";

import Link from "next/link";
import { Suspense, useEffect, useMemo, useState } from "react";
import { ArrowLeft, FileText, RefreshCw, Search } from "lucide-react";
import { useRouter, useSearchParams } from "next/navigation";
import { apiFetch, LibraryFile, LibraryFilePreview, ParseOutputFormat, ParsePreset } from "../../../lib/api";
import { renderDocumentPreviewHtml } from "../../../lib/document-preview";
import {
  buildParseQueryParams,
  FALLBACK_PARSE_CAPABILITY,
  getParsePresetDefaults,
  getParseOutputFormatOptions,
  getPrimaryParsePresetOptions,
  ParseCapabilityResponse,
} from "../../../lib/parse-presets";

const libraryPreviewChars = 200_000;

const defaultParsePresetSettings = getParsePresetDefaults(
  FALLBACK_PARSE_CAPABILITY.default_preset,
  FALLBACK_PARSE_CAPABILITY
);

export default function LibraryPreviewPage() {
  return (
    <Suspense
      fallback={
        <div className="panel">
          <div className="panelBody">加载中...</div>
        </div>
      }
    >
      <LibraryPreviewPageContent />
    </Suspense>
  );
}

function LibraryPreviewPageContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const requestedFileId = (searchParams.get("file_id") || "").trim();

  const [files, setFiles] = useState<LibraryFile[]>([]);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadingFiles, setLoadingFiles] = useState(false);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [selectedFileId, setSelectedFileId] = useState("");
  const [preview, setPreview] = useState<LibraryFilePreview | null>(null);
  const [parseCapability, setParseCapability] = useState<ParseCapabilityResponse>(FALLBACK_PARSE_CAPABILITY);
  const [parsePreset, setParsePreset] = useState<ParsePreset>(FALLBACK_PARSE_CAPABILITY.default_preset);
  const [outputFormat, setOutputFormat] = useState<ParseOutputFormat>(FALLBACK_PARSE_CAPABILITY.default_output_format);
  const [forceOcr] = useState(true);
  const [rawOcrMode, setRawOcrMode] = useState(false);
  const [preservePdfImageContent, setPreservePdfImageContent] = useState(true);
  const [renderDpi, setRenderDpi] = useState(defaultParsePresetSettings.renderDpi);
  const [pageChunkSize, setPageChunkSize] = useState(String(FALLBACK_PARSE_CAPABILITY.default_page_chunk_size));
  const [headerRatio, setHeaderRatio] = useState("0.00");
  const [footerRatio, setFooterRatio] = useState("0.00");
  const [trimMargins, setTrimMargins] = useState(defaultParsePresetSettings.trimMargins);
  const [removeRepeatedLines, setRemoveRepeatedLines] = useState(defaultParsePresetSettings.removeRepeatedLines);
  const [watermarkDetection, setWatermarkDetection] = useState(defaultParsePresetSettings.watermarkDetection);

  const selectedFileSummary = useMemo(
    () => files.find((file) => file.id === selectedFileId) || null,
    [files, selectedFileId]
  );
  const rawPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.raw_text || preview?.raw_markdown || preview?.text || preview?.markdown || ""),
    [preview]
  );
  const cleanedPreviewHtml = useMemo(
    () => renderDocumentPreviewHtml(preview?.content || preview?.markdown || preview?.text || ""),
    [preview]
  );

  useEffect(() => {
    loadFiles().catch((err) => setError(err instanceof Error ? err.message : "加载素材列表失败"));
    loadParseCapability().catch((err) => setError(err instanceof Error ? err.message : "加载解析能力失败"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadParseCapability() {
    const capability = await apiFetch<ParseCapabilityResponse>("/api/system/parse-capability");
    setParseCapability(capability);
  }

  async function loadFiles() {
    setLoadingFiles(true);
    setError("");
    try {
      const params = new URLSearchParams();
      if (search.trim()) params.set("search", search.trim());
      const data = await apiFetch<LibraryFile[]>(`/api/library/files?${params.toString()}`);
      setFiles(data);
      if (!data.length) {
        setSelectedFileId("");
        setPreview(null);
        return;
      }
      const preferredId =
        (requestedFileId && data.some((file) => file.id === requestedFileId) && requestedFileId) ||
        (selectedFileId && data.some((file) => file.id === selectedFileId) && selectedFileId) ||
        data[0].id;
      if (preferredId && preferredId !== selectedFileId) {
        const next = data.find((file) => file.id === preferredId);
        if (next) {
          await openFile(next, { replaceUrl: !requestedFileId });
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载素材列表失败");
    } finally {
      setLoadingFiles(false);
    }
  }

  function buildParseParams() {
    return buildParseQueryParams(
      {
        preset: parsePreset,
        outputFormat,
        rawOcrMode,
        preservePdfImageContent,
        renderDpi,
        pageChunkSize,
        cropHeaderRatio: headerRatio,
        cropFooterRatio: footerRatio,
        trimMargins,
        removeRepeatedLines,
        watermarkDetection,
      },
      parseCapability,
      { max_chars: String(libraryPreviewChars) }
    );
  }

  function chooseParsePreset(nextPreset: ParsePreset) {
    const defaults = getParsePresetDefaults(nextPreset, parseCapability);
    setParsePreset(nextPreset);
    setRenderDpi(defaults.renderDpi);
    setTrimMargins(defaults.trimMargins);
    setRemoveRepeatedLines(defaults.removeRepeatedLines);
    setWatermarkDetection(defaults.watermarkDetection);
  }

  async function openFile(file: LibraryFile, options?: { replaceUrl?: boolean }) {
    setSelectedFileId(file.id);
    setMessage(`正在加载 ${file.filename}...`);
    setError("");
    if (options?.replaceUrl !== false) {
      router.replace(`/library/preview?file_id=${file.id}`);
    }
    await loadPreview(file.id);
  }

  async function loadPreview(fileId: string) {
    setLoadingPreview(true);
    setError("");
    try {
      const params = buildParseParams();
      const result = await apiFetch<LibraryFilePreview>(`/api/library/files/${fileId}/preview?${params.toString()}`);
      setPreview(result);
      setMessage(`已加载 ${result.filename} 的解析预览。`);
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
          <h1>素材解析预览</h1>
          <p>左侧选择素材文件，右侧对照原始 OCR 与清噪结果。</p>
        </div>
        <div className="buttonRow">
          <Link className="button" href="/library">
            <ArrowLeft size={17} />
            返回素材库
          </Link>
          <button className="button" disabled={loadingFiles} type="button" onClick={() => loadFiles()}>
            <RefreshCw size={17} />
            刷新列表
          </button>
        </div>
      </header>

      <section className="gridTwo libraryPreviewLayout">
        <div className="panel libraryPreviewSidebar">
          <div className="panelHeader">
            <h2>素材列表</h2>
            <p>搜索文件名、来源标题或学科后点选一条，右侧会直接显示解析对照。</p>
          </div>
          <div className="panelBody formGrid">
            <div className="field">
              <label>搜索</label>
              <div className="row">
                <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="文件名、来源标题、学科" />
                <button className="button" type="button" onClick={() => loadFiles()}>
                  <Search size={16} />
                  筛选
                </button>
              </div>
            </div>
            <div className="previewFileList">
              {files.map((file) => (
                <button
                  className={selectedFileId === file.id ? "previewFileButton active" : "previewFileButton"}
                  key={file.id}
                  type="button"
                  onClick={() => openFile(file)}
                >
                  <strong>{file.filename}</strong>
                  <span>
                    {file.subject}
                    {file.category ? ` / ${file.category}` : ""}
                    {file.chapter ? ` / ${file.chapter}` : ""}
                  </span>
                  <span>{file.source_title}</span>
                </button>
              ))}
            </div>
            {!files.length && <div className="empty">没有匹配的素材文件。</div>}
            {!!error && <p className="errorText">{error}</p>}
            {!!message && <p className="muted">{message}</p>}
          </div>
        </div>

        <div className="panel libraryPreviewMain">
          <div className="panelHeader">
            <h2>{preview?.filename || selectedFileSummary?.filename || "未选择素材"}</h2>
            <p>
              {preview
                ? `Token ${preview.token_count.toLocaleString()} · 解析器 ${preview.provider}`
                : "选择左侧素材开始查看对照结果。"}
            </p>
          </div>
          <div className="panelBody">
            <div className="row">
              <div className="field">
                <label>解析预设</label>
                <select value={parsePreset} onChange={(e) => chooseParsePreset(e.target.value as ParsePreset)}>
                  {getPrimaryParsePresetOptions(parseCapability).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="field">
                <label>输出格式</label>
                <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as ParseOutputFormat)}>
                  {getParseOutputFormatOptions(parseCapability).map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>渲染 DPI</label>
                <input
                  min="96"
                  max="360"
                  step="10"
                  type="number"
                  value={renderDpi}
                  onChange={(e) => setRenderDpi(e.target.value)}
                />
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
                <label>强制 OCR</label>
                <select value={forceOcr ? "true" : "false"} disabled>
                  <option value="true">是（固定）</option>
                </select>
              </div>
              <div className="field">
                <label>说明</label>
                <input value="固定开启，确保 PDF 始终走 OCR 解析链路" readOnly />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>页眉裁切</label>
                <input
                  min="0"
                  max="0.2"
                  step="0.01"
                  type="number"
                  value={headerRatio}
                  onChange={(e) => setHeaderRatio(e.target.value)}
                />
              </div>
              <div className="field">
                <label>页脚裁切</label>
                <input
                  min="0"
                  max="0.2"
                  step="0.01"
                  type="number"
                  value={footerRatio}
                  onChange={(e) => setFooterRatio(e.target.value)}
                />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>空白边裁切</label>
                <select value={trimMargins ? "true" : "false"} onChange={(e) => setTrimMargins(e.target.value === "true")}>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              <div className="field">
                <label>重复行清理</label>
                <select value={removeRepeatedLines ? "true" : "false"} onChange={(e) => setRemoveRepeatedLines(e.target.value === "true")}>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>浅色水印弱化</label>
                <select value={watermarkDetection ? "true" : "false"} onChange={(e) => setWatermarkDetection(e.target.value === "true")}>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              <div className="field">
                <label>说明</label>
                <input value="仅适合浅灰水印，深色遮挡仍需外部清理" readOnly />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>原始 OCR 模式</label>
                <select value={rawOcrMode ? "true" : "false"} onChange={(e) => setRawOcrMode(e.target.value === "true")}>
                  <option value="false">关闭</option>
                  <option value="true">开启</option>
                </select>
              </div>
              <div className="field">
                <label>说明</label>
                <input value="仅关闭 OCR 规则清噪，AI 清噪继续执行" readOnly />
              </div>
            </div>
            <div className="row">
              <div className="field">
                <label>保留 PDF 图片内容</label>
                <select value={preservePdfImageContent ? "true" : "false"} onChange={(e) => setPreservePdfImageContent(e.target.value === "true")}>
                  <option value="true">开启</option>
                  <option value="false">关闭</option>
                </select>
              </div>
              <div className="field">
                <label>说明</label>
                <input value="关闭后不保留 PDF 中图片的完整内容与引用" readOnly />
              </div>
            </div>
            <div className="buttonRow">
              <button
                className="button primary"
                disabled={!selectedFileId || loadingPreview}
                type="button"
                onClick={() => selectedFileId && loadPreview(selectedFileId)}
              >
                <FileText size={16} />
                {loadingPreview ? "加载中..." : "刷新当前预览"}
              </button>
              {selectedFileSummary && (
                <span className="muted">
                  {selectedFileSummary.subject}
                  {selectedFileSummary.category ? ` / ${selectedFileSummary.category}` : ""}
                  {selectedFileSummary.chapter ? ` / ${selectedFileSummary.chapter}` : ""}
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
                      <span>可直接使用的内容</span>
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
            {!preview && !loadingPreview && <div className="empty">先选择一个素材查看对照结果。</div>}
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
