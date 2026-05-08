"use client";

import { Gauge, LayoutTemplate, ScanText, Sigma, Trash2, Zap, type LucideIcon } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { apiFetch as legacyApiFetch } from "../../../../lib/api";
import type { SubjectConfig, SystemConfig } from "../../../../lib/api";
import {
  apiFetch,
  apiFormFetch,
  AnalysisJobResponse,
  OCRCapabilityResponse,
  ParseOutputFormat,
  PaperDeleteResponse,
  PaperDetailResponse,
  PaperParseJobResponse,
  PaperParseResponse,
  PaperSummary,
  PaperUploadResponse,
  ParsePreset,
} from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../../lib/request-guard";

const parsePresetOptions: Array<{
  value: ParsePreset;
  label: string;
  engine: string;
  dpi: string;
  icon: LucideIcon;
}> = [
  { value: "auto", label: "自动", engine: "文本优先", dpi: "240", icon: ScanText },
  { value: "fast", label: "快速 OCR", engine: "PP-OCRv5", dpi: "150", icon: Zap },
  { value: "balanced", label: "均衡 OCR", engine: "PP-OCRv5", dpi: "220", icon: Gauge },
  { value: "accurate", label: "高精度版面", engine: "PP-StructureV3", dpi: "280", icon: LayoutTemplate },
  { value: "formula", label: "公式增强", engine: "PP-StructureV3", dpi: "280", icon: Sigma },
];

const presetDefaultDpi: Record<ParsePreset, string> = {
  auto: "240",
  fast: "150",
  balanced: "220",
  accurate: "280",
  formula: "280",
};

const parseOutputFormatOptions: Array<{ value: ParseOutputFormat; label: string }> = [
  { value: "markdown", label: "Markdown" },
  { value: "text", label: "TXT" },
];

export default function PapersPage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);
  const [selected, setSelected] = useState<PaperDetailResponse | null>(null);
  const [selectedSubjectId, setSelectedSubjectId] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [parsingId, setParsingId] = useState<number | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const [listMessage, setListMessage] = useState("");
  const [uploadMessage, setUploadMessage] = useState("");
  const [uploadError, setUploadError] = useState("");
  const [parseMessage, setParseMessage] = useState("");
  const [parseJob, setParseJob] = useState<AnalysisJobResponse | null>(null);
  const [ocrCapability, setOcrCapability] = useState<OCRCapabilityResponse | null>(null);
  const [ocrCapabilityError, setOcrCapabilityError] = useState("");
  const [parsePreset, setParsePreset] = useState<ParsePreset>("auto");
  const [outputFormat, setOutputFormat] = useState<ParseOutputFormat>("markdown");
  const [forceOcr, setForceOcr] = useState(false);
  const [renderDpi, setRenderDpi] = useState(presetDefaultDpi.auto);
  const [pageChunkSize, setPageChunkSize] = useState("4");
  const [headerRatio, setHeaderRatio] = useState("0.00");
  const [footerRatio, setFooterRatio] = useState("0.00");
  const pageRequestGate = useLatestRequestGate();
  const detailRequestIdRef = useRef(0);
  const activeSubject = subjects.find((subject) => subject.id === selectedSubjectId) || null;
  const visibleParseJob = selected && parseJob && Number(parseJob.scope_config_json?.paper_id || 0) === selected.id ? parseJob : null;

  function clearParseStateForPaper(paperId?: number | null) {
    if (paperId == null) {
      setParseJob(null);
      setParsingId(null);
      return;
    }
    setParseJob((current) => {
      if (!current || Number(current.scope_config_json?.paper_id || 0) !== paperId) return current;
      return null;
    });
    setParsingId((current) => (current === paperId ? null : current));
  }

  async function loadPaperDetail(id: number, fallback: string) {
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    try {
      const detail = await apiFetch<PaperDetailResponse>(`/api/papers/${id}`);
      if (detailRequestIdRef.current !== requestId) return null;
      setSelected(detail);
      if (
        detail.active_parse_job_id &&
        ["pending", "running"].includes(String(detail.active_parse_job_status || "")) &&
        (!parseJob || parseJob.id !== detail.active_parse_job_id || !["pending", "running"].includes(parseJob.status))
      ) {
        setParseJob({
          id: detail.active_parse_job_id,
          job_type: "paper_parse",
          scope_type: "paper",
          scope_config_json: { paper_id: detail.id, stage: detail.active_parse_stage || "queued" },
          status: detail.active_parse_job_status || "running",
          progress: detail.active_parse_progress || 0,
          created_at: new Date().toISOString(),
        });
        setParsingId(detail.id);
      } else {
        clearParseStateForPaper(detail.id);
      }
      setDetailError("");
      return detail;
    } catch (err) {
      if (detailRequestIdRef.current !== requestId) return null;
      setSelected(null);
      setDetailError(toErrorMessage(err, fallback));
      return null;
    }
  }

  async function loadPage(preferredPaperId?: number | null) {
    const requestId = pageRequestGate.begin();
    setLoading(true);
    setError("");
    setDetailError("");
    setLoadWarning("");
    try {
      const [nextPapers, nextSubjects] = await Promise.allSettled([
        apiFetch<PaperSummary[]>("/api/papers"),
        legacyApiFetch<SystemConfig>("/api/system/config"),
      ]);

      if (!pageRequestGate.isCurrent(requestId)) return;

      const results = [nextPapers, nextSubjects];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No paper page requests succeeded.");
      }

      const paperList = nextPapers.status === "fulfilled" ? nextPapers.value : [];
      if (nextPapers.status === "fulfilled") {
        setPapers(paperList);
      } else {
        setPapers([]);
      }
      if (nextSubjects.status === "fulfilled") {
        const configSubjects = nextSubjects.value.subjects;
        const nextSubject =
          configSubjects.find((item) => item.id === selectedSubjectId) || configSubjects[0];
        setSubjects(configSubjects);
        setSelectedSubjectId(nextSubject?.id || "");
        setSelectedCategory((category) => {
          return nextSubject?.categories.includes(category) ? category : nextSubject?.categories[0] || "";
        });
      } else {
        setSubjects([]);
        setSelectedSubjectId("");
        setSelectedCategory("");
      }
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "试卷列表", result: nextPapers },
          { label: "学科配置", result: nextSubjects },
        ]),
      );

      const nextSelectedId = preferredPaperId === null
        ? paperList[0]?.id
        : preferredPaperId || selected?.id || paperList[0]?.id;
      if (!nextSelectedId) {
        setSelected(null);
        clearParseStateForPaper();
        return;
      }
      await loadPaperDetail(nextSelectedId, "加载试卷详情失败");
    } catch (err) {
      if (!pageRequestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载试卷失败"));
    } finally {
      if (pageRequestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadPage();
    loadOcrCapability();
  }, []);

  useEffect(() => {
    if (!parseJob || !["pending", "running"].includes(parseJob.status)) return;
    const timer = window.setInterval(() => {
      loadParseJob(parseJob.id).catch((err) => setError(toErrorMessage(err, "刷新解析进度失败")));
    }, 1200);
    return () => window.clearInterval(timer);
  }, [parseJob?.id, parseJob?.status]);

  async function refreshPapers(selectedId?: number | null) {
    await loadPage(selectedId);
  }

  async function loadOcrCapability() {
    try {
      const result = await apiFetch<OCRCapabilityResponse>("/api/system/ocr-capability");
      setOcrCapability(result);
      setOcrCapabilityError("");
    } catch (err) {
      setOcrCapability(null);
      setOcrCapabilityError(toErrorMessage(err, "设备能力检测失败"));
    }
  }

  async function loadParseJob(jobId: number) {
    const job = await apiFetch<AnalysisJobResponse>(`/api/analysis/jobs/${jobId}`);
    setParseJob(job);
    if (job.status === "completed") {
      const summary = job.result_summary_json || {};
      const parseOptions = (summary.parse_options && typeof summary.parse_options === "object")
        ? (summary.parse_options as Record<string, unknown>)
        : null;
      const warnings = Array.isArray(summary.warnings) ? summary.warnings.map(String).filter(Boolean) : [];
      const datasetSamplePath = typeof summary.dataset_sample_path === "string" ? summary.dataset_sample_path : "";
      await refreshPapers(selected?.id || null);
      setParsingId(null);
      setParseMessage(
        `解析完成：${Number(summary.question_count || 0)} 道题已进入题目中心，规则命中 ${Number(summary.tagged_count || 0)} 条候选考点。后续 AI 补全、AI 标注、AI 复核请到 /platform/analysis/questions?paper_id=${selected?.id || 0} 执行${warnings.length ? `；当前有 ${warnings.length} 条待复核提示` : ""}${datasetSamplePath ? `；样本已自动导入 ${datasetSamplePath}` : ""}。`,
      );
    }
    if (job.status === "failed") {
      setParsingId(null);
      setError(job.error_message || "解析任务失败");
    }
    return job;
  }

  async function pickPaper(id: number) {
    setError("");
    setDetailError("");
    setListMessage("");
    await loadPaperDetail(id, "加载试卷详情失败");
  }

  async function uploadPaper(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = new FormData(form);
    const file = data.get("file");
    const paperName = String(data.get("paper_name") || "").trim();
    if (!(file instanceof File) || !file.size) {
      setUploadError("请选择试卷文件");
      return;
    }
    if (!paperName) {
      setUploadError("请填写试卷名称");
      return;
    }
    if (!activeSubject) {
      setUploadError("请先在学科中心添加学科。");
      return;
    }
    data.set("subject_code", activeSubject.id);
    data.set("subject_name", activeSubject.name);
    if (activeSubject.platform_id != null) {
      data.set("subject_id", String(activeSubject.platform_id));
    }
    if (selectedCategory) {
      data.set("category", selectedCategory);
    }
    for (const key of [
      "subject_id",
      "subject_code",
      "subject_name",
      "category",
      "exam_year",
      "exam_month",
      "exam_region",
      "exam_type",
      "paper_type",
      "paper_code",
    ]) {
      if (!String(data.get(key) || "").trim()) {
        data.delete(key);
      }
    }

    setUploading(true);
    setUploadError("");
    setUploadMessage("");
    setListMessage("");
    try {
      const uploaded = await apiFormFetch<PaperUploadResponse>("/api/papers/upload", data);
      await refreshPapers(uploaded.id);
      form.reset();
      setSelectedSubjectId(activeSubject.id);
      setUploadMessage(`已上传：${uploaded.paper_name}`);
    } catch (err) {
      setUploadError(toErrorMessage(err, "上传试卷失败"));
    } finally {
      setUploading(false);
    }
  }

  async function parsePaper(id: number) {
    setParsingId(id);
    setError("");
    setListMessage("");
    setParseMessage("");
    setParseJob(null);
    try {
      const form = new FormData();
      form.append("preset", parsePreset);
      form.append("output_format", outputFormat);
      if (forceOcr) form.append("force_ocr", "true");
      if (Number(renderDpi) > 0) form.append("render_dpi", String(Number(renderDpi)));
      if (Number(pageChunkSize) > 0) form.append("pdf_page_chunk_size", String(Number(pageChunkSize)));
      if (Number(headerRatio) > 0) form.append("crop_header_ratio", String(Number(headerRatio)));
      if (Number(footerRatio) > 0) form.append("crop_footer_ratio", String(Number(footerRatio)));
      if (parsePreset === "formula") form.append("enable_formula_recognition", "true");
      const result = await apiFormFetch<PaperParseJobResponse>(`/api/papers/${id}/parse-jobs`, form);
      setParseJob({
        id: result.job_id,
        job_type: "paper_parse",
        scope_type: "paper",
        scope_config_json: { paper_id: id, stage: "queued" },
        status: result.status,
        progress: result.progress,
        created_at: new Date().toISOString(),
      });
      setParseMessage(`解析任务已启动：#${result.job_id}。完成后会直接进入题目中心，AI 操作不再自动执行。`);
      await loadParseJob(result.job_id);
    } catch (err) {
      setError(toErrorMessage(err, "解析试卷失败"));
      setParsingId(null);
    } finally {
      // Completion is handled by the job poller.
    }
  }

  async function deletePaper(paper: PaperSummary) {
    const confirmed = window.confirm(`确定删除试卷“${paper.paper_name}”？已解析的分区、原始题和来源链接也会一并删除。`);
    if (!confirmed) return;
    setDeletingId(paper.id);
    setError("");
    setListMessage("");
    setParseMessage("");
    clearParseStateForPaper(paper.id);
    try {
      const result = await apiFetch<PaperDeleteResponse>(`/api/papers/${paper.id}`, { method: "DELETE" });
      const nextSelectedId = selected?.id === paper.id
        ? papers.find((item) => item.id !== paper.id)?.id
        : selected?.id;
      await refreshPapers(nextSelectedId || null);
      setListMessage(`已删除：${result.paper_name}`);
    } catch (err) {
      await refreshPapers(selected?.id || null);
      setError(toErrorMessage(err, "删除试卷失败"));
    } finally {
      setDeletingId(null);
    }
  }

  function chooseParsePreset(nextPreset: ParsePreset) {
    setParsePreset(nextPreset);
    setRenderDpi(presetDefaultDpi[nextPreset]);
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>试卷中心</h1>
          <p>试卷列表、学科和详情加载已做竞态保护，避免旧响应覆盖当前选择。</p>
        </div>
      </header>
      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <section className="dashboardGrid twoCol">
        <div className="panel">
          <div className="panelHeader">
            <h2>试卷列表</h2>
            <p>已接入的真题与试卷资产。</p>
          </div>
          <div className="panelBody">
            <LoadState loading={loading} error={error} empty={!papers.length} emptyLabel="暂无试卷数据" />
            {listMessage && <p className="muted">{listMessage}</p>}
            {!!papers.length && (
              <div className="stackList">
                {papers.map((paper) => (
                  <div key={paper.id} className="paperListItem">
                    <button className="paperPickButton" type="button" onClick={() => pickPaper(paper.id)}>
                      <div>
                        <strong>{paper.paper_name}</strong>
                        <span className="muted">
                          {paper.exam_year || "-"} · {paper.category || "未分类"} · {paper.exam_region || "未知地区"} · {paper.total_question_count} 题 · {paperStatusLabel(paper.status)}
                        </span>
                      </div>
                      <StatusBadge value={paper.review_status} tone={paper.review_status === "approved" ? "good" : "warn"} />
                    </button>
                    <div className="paperListActions">
                      <button
                        className="button danger small iconButton"
                        type="button"
                        title="删除试卷"
                        aria-label={`删除试卷 ${paper.paper_name}`}
                        disabled={deletingId === paper.id}
                        onClick={() => deletePaper(paper)}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                        <span>{deletingId === paper.id ? "删除中" : "删除"}</span>
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>上传试卷</h2>
            <p>先完成文件与试卷元数据入库，后续解析任务会接管 OCR、切题和考点识别。</p>
          </div>
          <div className="panelBody">
            <form className="formGrid" onSubmit={uploadPaper}>
              <label className="field">
                <span>试卷文件</span>
                <input name="file" type="file" accept=".pdf,.png,.jpg,.jpeg,.docx,.md,.txt" disabled={uploading} />
              </label>
              <label className="field">
                <span>试卷名称</span>
                <input name="paper_name" placeholder="例如：2026 注册会计师《会计》真题" disabled={uploading} />
              </label>
              <div className="row">
                <label className="field">
                  <span>学科</span>
                  <select
                    disabled={uploading}
                    value={selectedSubjectId}
                    onChange={(event) => {
                      const subject = subjects.find((item) => item.id === event.target.value) || null;
                      setSelectedSubjectId(subject?.id || "");
                      setSelectedCategory(subject?.categories[0] || "");
                    }}
                  >
                    {!subjects.length && <option value="">请先在学科中心添加学科</option>}
                    {subjects.map((subject) => (
                      <option key={subject.id} value={subject.id}>
                        {subject.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>类目</span>
                  <select
                    disabled={uploading || !activeSubject}
                    value={selectedCategory}
                    onChange={(event) => setSelectedCategory(event.target.value)}
                  >
                    <option value="">未分类</option>
                    {activeSubject?.categories.map((category) => (
                      <option key={category} value={category}>
                        {category}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <div className="row">
                <label className="field">
                  <span>年份</span>
                  <input name="exam_year" type="number" min="1990" max="2100" placeholder="2026" disabled={uploading} />
                </label>
                <label className="field">
                  <span>月份</span>
                  <input name="exam_month" type="number" min="1" max="12" placeholder="8" disabled={uploading} />
                </label>
              </div>
              <div className="row">
                <label className="field">
                  <span>地区</span>
                  <input name="exam_region" placeholder="全国" disabled={uploading} />
                </label>
                <label className="field">
                  <span>考试类型</span>
                  <input name="exam_type" placeholder="资格考试" disabled={uploading} />
                </label>
              </div>
              <div className="row">
                <label className="field">
                  <span>试卷类型</span>
                  <input name="paper_type" placeholder="真题" disabled={uploading} />
                </label>
                <label className="field">
                  <span>试卷编号</span>
                  <input name="paper_code" placeholder="可选，例如 CPA-ACC-2026" disabled={uploading} />
                </label>
              </div>
              <div className="buttonRow">
                <button className="button primary" type="submit" disabled={uploading}>
                  {uploading ? "上传中..." : "上传并入库"}
                </button>
                {uploadMessage && <span className="muted">{uploadMessage}</span>}
                {uploadError && <span className="errorText">{uploadError}</span>}
              </div>
            </form>
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>试卷详情</h2>
            <p>展示已解析资产、分区和当前状态。</p>
          </div>
          <div className="panelBody">
            <LoadState loading={loading} error={detailError} empty={!selected} emptyLabel="请选择一份试卷" />
            {selected && (
              <div className="stackList">
                <div className="detailRow">
                  <span>学科</span>
                  <strong>{selected.subject_name || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>类目</span>
                  <strong>{selected.category || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>素材文件</span>
                  <strong>{selected.asset_filename || "-"}</strong>
                </div>
                <div className="detailRow">
                  <span>解析状态</span>
                  <StatusBadge
                    value={selected.active_parse_stage ? parseStageLabel(selected.active_parse_stage) : parseRuntimeStatusLabel(selected.asset_parse_status)}
                    tone={selected.asset_parse_status === "parsed" ? "good" : selected.asset_parse_status === "failed" ? "danger" : "info"}
                  />
                </div>
                <div className="detailRow">
                  <span>试卷状态</span>
                  <StatusBadge
                    value={selected.active_parse_stage ? parseStageLabel(selected.active_parse_stage) : paperStatusLabel(selected.status)}
                    tone={selected.status === "parsed" ? "good" : selected.status === "parse_failed" ? "danger" : "info"}
                  />
                </div>
                <div className="detailRow">
                  <span>审核状态</span>
                  <StatusBadge value={selected.review_status} tone="good" />
                </div>
                <div className="calloutBox">
                  <strong>OCR 设备能力</strong>
                  {ocrCapability ? (
                    <>
                      <p>
                        {ocrCapability.summary} · {ocrCapability.device_name || "未检测到 GPU"} ·
                        {" "}空闲显存 {formatMemory(ocrCapability.gpu_memory_free_mb)} / {formatMemory(ocrCapability.gpu_memory_total_mb)}
                      </p>
                      <p className="muted">
                        当前模型：{String(ocrCapability.current_settings.text_detection_model_name || "-")} /{" "}
                        {String(ocrCapability.current_settings.text_recognition_model_name || "-")} · CUDA{" "}
                        {ocrCapability.cuda_available ? "可用" : "不可用"} · Paddle {ocrCapability.paddle_version || "-"}
                      </p>
                      <p className="muted">推荐主流程：{ocrCapability.recommended_pipeline}</p>
                      {!!ocrCapability.warnings.length && <p className="errorText">{ocrCapability.warnings.join(" | ")}</p>}
                    </>
                  ) : (
                    <p className={ocrCapabilityError ? "errorText" : "muted"}>{ocrCapabilityError || "正在检测 OCR 设备能力..."}</p>
                  )}
                  <button className="button small" type="button" onClick={loadOcrCapability}>
                    刷新检测
                  </button>
                </div>
                <div className="ocrControlPanel">
                  <div className="ocrControlHeader">
                    <strong>OCR 模式</strong>
                    <span>{parsePresetSummary(parsePreset)}</span>
                  </div>
                  <div className="ocrModeGrid">
                    {parsePresetOptions.map((option) => {
                      const Icon = option.icon;
                      const active = parsePreset === option.value;
                      return (
                        <button
                          key={option.value}
                          className={`ocrModeButton${active ? " active" : ""}`}
                          type="button"
                          aria-pressed={active}
                          onClick={() => chooseParsePreset(option.value)}
                        >
                          <Icon size={17} aria-hidden />
                          <strong>{option.label}</strong>
                          <span>{option.engine} · {option.dpi} DPI</span>
                        </button>
                      );
                    })}
                  </div>
                  <div className="row">
                    <label className="field">
                      <span>渲染 DPI</span>
                      <input
                        min="96"
                        max="300"
                        step="10"
                        type="number"
                        value={renderDpi}
                        onChange={(e) => setRenderDpi(e.target.value)}
                      />
                    </label>
                    <label className="field">
                      <span>每批页数</span>
                      <input
                        min="1"
                        max="50"
                        step="1"
                        type="number"
                        value={pageChunkSize}
                        onChange={(e) => setPageChunkSize(e.target.value)}
                      />
                    </label>
                  </div>
                  <div className="row">
                    <label className="field">
                      <span>强制 OCR</span>
                      <select value={forceOcr ? "true" : "false"} onChange={(e) => setForceOcr(e.target.value === "true")}>
                        <option value="false">否</option>
                        <option value="true">是</option>
                      </select>
                    </label>
                    <label className="field">
                      <span>输出格式</span>
                      <select value={outputFormat} onChange={(e) => setOutputFormat(e.target.value as ParseOutputFormat)}>
                        {parseOutputFormatOptions.map((option) => (
                          <option key={option.value} value={option.value}>
                            {option.label}
                          </option>
                        ))}
                      </select>
                    </label>
                  </div>
                </div>
                <div className="row">
                  <label className="field">
                    <span>页眉裁切</span>
                    <input value={headerRatio} onChange={(e) => setHeaderRatio(e.target.value)} placeholder="0.04" />
                  </label>
                  <label className="field">
                    <span>页脚裁切</span>
                    <input value={footerRatio} onChange={(e) => setFooterRatio(e.target.value)} placeholder="0.05" />
                  </label>
                </div>
                <div className="buttonRow">
                  <button className="button primary" type="button" disabled={parsingId === selected.id} onClick={() => parsePaper(selected.id)}>
                    {parsingId === selected.id ? "解析中..." : "解析并切题"}
                  </button>
                  {parseMessage && <span className="muted">{parseMessage}</span>}
                </div>
                {visibleParseJob && (
                  <div className="calloutBox">
                    <div className="detailRow">
                      <span>解析任务 #{visibleParseJob.id}</span>
                      <strong>{parseStageLabel(visibleParseJob.scope_config_json?.stage)} · {visibleParseJob.progress}%</strong>
                    </div>
                    <div className="progressTrack" aria-label="解析进度">
                      <div className="progressFill" style={{ width: `${Math.max(3, Math.min(100, visibleParseJob.progress))}%` }} />
                    </div>
                    <p className={visibleParseJob.status === "failed" ? "errorText" : "muted"}>
                      {visibleParseJob.status === "failed"
                        ? visibleParseJob.error_message || "解析失败"
                        : parseJobDetailText(visibleParseJob)}
                    </p>
                    {visibleParseJob.status !== "failed" && parseJobChunkDetailText(visibleParseJob) && (
                      <p className="muted">{parseJobChunkDetailText(visibleParseJob)}</p>
                    )}
                    {visibleParseJob.status !== "failed" && parseJobResumeDetailText(visibleParseJob) && (
                      <p className="muted">{parseJobResumeDetailText(visibleParseJob)}</p>
                    )}
                  </div>
                )}
                <div className="subsection">
                  <strong>试卷分区</strong>
                  <div className="metricTable">
                    {selected.sections.map((section) => (
                      <div key={section.id} className="metricRow">
                        <div>
                          <strong>{section.section_name}</strong>
                          <span className="muted">
                            {section.question_type} · {section.start_no} - {section.end_no}
                          </span>
                        </div>
                        <StatusBadge value={`${section.score || 0} 分`} tone="info" />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

function formatMemory(value?: number | null) {
  if (value == null) return "-";
  return `${(value / 1024).toFixed(1)} GB`;
}

function parsePresetSummary(preset: ParsePreset) {
  const summaries: Record<ParsePreset, string> = {
    auto: "可选文本优先，扫描件自动 OCR",
    fast: "速度优先，适合快速预览",
    balanced: "PP-OCRv5 server，速度和精度折中",
    accurate: "PP-StructureV3 版面优先，低质时自动 PP-OCRv5 兜底",
    formula: "版面分析 + 表格/公式识别，适合公式较多试卷",
  };
  return summaries[preset];
}

function paperStatusLabel(status?: string) {
  const labels: Record<string, string> = {
    uploaded: "已上传",
    parsing: "解析中",
    preparing: "准备文件",
    reading_file: "读取文件",
    ocr_running: "OCR 识别中",
    layout_analyzing: "版面分析中",
    ocr_fallback_running: "OCR 兜底中",
    splitting_questions: "切题中",
    building_sections: "生成分区中",
    tagging: "考点标注中",
    saving: "保存结果中",
    parsed: "已解析",
    parse_failed: "解析失败",
  };
  return labels[status || ""] || status || "-";
}

function parseRuntimeStatusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    pending: "待解析",
    preparing: "准备文件",
    reading_file: "读取文件",
    parsing: "解析中",
    ocr_running: "OCR 识别中",
    layout_analyzing: "版面分析中",
    ocr_fallback_running: "OCR 兜底中",
    splitting_questions: "切题中",
    building_sections: "生成分区中",
    tagging: "考点标注中",
    saving: "保存结果中",
    parsed: "已解析",
    failed: "解析失败",
    empty: "解析为空",
  };
  return labels[status || ""] || status || "-";
}

function parseStageLabel(stage?: string) {
  const labels: Record<string, string> = {
    queued: "等待解析",
    device_check: "设备检测",
    prepare: "准备文件",
    read_file: "读取文件",
    ocr: "OCR 切片识别",
    layout_analysis: "版面切片分析",
    split_questions: "切题",
    build_sections: "生成分区",
    tagging: "考点标注",
    saving: "保存结果",
    completed: "完成",
    failed: "失败",
  };
  return labels[stage || ""] || stage || "处理中";
}

function parseJobDetailText(job: AnalysisJobResponse) {
  const detail = job.scope_config_json?.detail || {};
  const stage = String(job.scope_config_json?.stage || "");
  if (stage === "ocr") {
    const done = Number(detail.done_pages || 0);
    const total = Number(detail.total_pages || 0);
    return total ? `正在识别第 ${done} / ${total} 页` : "正在执行 OCR 识别";
  }
  if (stage === "layout_analysis") {
    const done = Number(detail.done_pages || 0);
    const total = Number(detail.total_pages || 0);
    return total ? `PP-StructureV3 正在按切片分析第 ${done} / ${total} 页版面` : "正在进行版面切片与阅读顺序分析";
  }
  if (stage === "ocr_fallback") {
    const done = Number(detail.done_pages || 0);
    const total = Number(detail.total_pages || 0);
    return total ? `版面结果触发兜底，PP-OCRv5 正在按切片复核第 ${done} / ${total} 页` : "正在执行 PP-OCRv5 兜底切片复核";
  }
  if (stage === "device_check") {
    const device = String(detail.device_name || "未知设备");
    const status = String(detail.capability_status || "checking");
    return `设备 ${device}，状态 ${status}`;
  }
  if (stage === "tagging") {
    const done = Number(detail.tagged_questions || 0);
    const total = Number(detail.question_count || 0);
    return total ? `正在生成规则候选第 ${done} / ${total} 题` : "正在生成规则候选";
  }
  if (stage === "build_sections") {
    return String(detail.section_name || "正在生成试卷分区");
  }
  if (stage === "completed") {
    const questionCount = Number(detail.question_count || 0);
    const taggedCount = Number(detail.tagged_count || 0);
    return `解析完成，生成 ${questionCount} 道题，规则命中 ${taggedCount} 条候选考点。`;
  }
  return "后台解析中，页面会自动刷新进度。";
}

function parseJobChunkDetailText(job: AnalysisJobResponse) {
  const detail = job.scope_config_json?.detail || {};
  const chunkCount = Number(detail.chunk_count || 0);
  const completedChunkCount = Number(detail.completed_chunk_count || 0);
  const currentChunkIndex = Number(detail.current_chunk_index || 0);
  const chunkFrom = Number(detail.current_chunk_page_from || 0);
  const chunkTo = Number(detail.current_chunk_page_to || 0);
  const pageBatchSize = Number(detail.page_batch_size || 0);
  if (!chunkCount) return "";
  if (currentChunkIndex && chunkFrom && chunkTo) {
    return `已完成切片 ${Math.min(completedChunkCount, chunkCount)} / ${chunkCount} · 当前切片第 ${currentChunkIndex} 段（第 ${chunkFrom}-${chunkTo} 页）· 每批 ${pageBatchSize || "-"} 页`;
  }
  return `已完成切片 ${Math.min(completedChunkCount, chunkCount)} / ${chunkCount} · 每批 ${pageBatchSize || "-"} 页`;
}

function parseJobResumeDetailText(job: AnalysisJobResponse) {
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
