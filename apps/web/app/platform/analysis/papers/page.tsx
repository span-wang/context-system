"use client";

import Link from "next/link";
import { LayoutTemplate, Sigma, Trash2, type LucideIcon } from "lucide-react";
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
  { value: "accurate", label: "高精度", engine: "PP-StructureV3", dpi: "320", icon: LayoutTemplate },
  { value: "formula", label: "公式加强", engine: "PP-StructureV3", dpi: "340", icon: Sigma },
];

const presetDefaultDpi: Record<ParsePreset, string> = {
  auto: "240",
  fast: "150",
  balanced: "220",
  accurate: "320",
  formula: "340",
};

const parseOutputFormatOptions: Array<{ value: ParseOutputFormat; label: string }> = [
  { value: "markdown", label: "Markdown" },
  { value: "text", label: "TXT" },
];

const uploadRegionOptions = [
  "全国",
  "北京",
  "天津",
  "上海",
  "重庆",
  "河北",
  "山西",
  "内蒙古",
  "辽宁",
  "吉林",
  "黑龙江",
  "江苏",
  "浙江",
  "安徽",
  "福建",
  "江西",
  "山东",
  "河南",
  "湖北",
  "湖南",
  "广东",
  "广西",
  "海南",
  "四川",
  "贵州",
  "云南",
  "西藏",
  "陕西",
  "甘肃",
  "青海",
  "宁夏",
  "新疆",
  "香港",
  "澳门",
  "台湾",
] as const;

type PaperWorkspaceTab = "detail" | "upload";

type PaperListFilters = {
  subjectId: string;
  category: string;
  year: string;
};

type PaperSubjectMeta = {
  code: string;
  name: string;
  categories: string[];
};

export default function PapersPage() {
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [subjects, setSubjects] = useState<SubjectConfig[]>([]);
  const [selected, setSelected] = useState<PaperDetailResponse | null>(null);
  const [selectedSubjectId, setSelectedSubjectId] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [filterSubjectId, setFilterSubjectId] = useState("");
  const [filterCategory, setFilterCategory] = useState("");
  const [filterYear, setFilterYear] = useState("");
  const [workspaceTab, setWorkspaceTab] = useState<PaperWorkspaceTab>("detail");
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
  const [parsePreset, setParsePreset] = useState<ParsePreset>("accurate");
  const [outputFormat, setOutputFormat] = useState<ParseOutputFormat>("markdown");
  const [forceOcr, setForceOcr] = useState(false);
  const [renderDpi, setRenderDpi] = useState(presetDefaultDpi.accurate);
  const [pageChunkSize, setPageChunkSize] = useState("4");
  const pageRequestGate = useLatestRequestGate();
  const detailRequestIdRef = useRef(0);
  const activeSubject = subjects.find((subject) => subject.id === selectedSubjectId) || null;
  const visibleParseJob = selected && parseJob && Number(parseJob.scope_config_json?.paper_id || 0) === selected.id ? parseJob : null;
  const listFilters: PaperListFilters = {
    subjectId: filterSubjectId,
    category: filterCategory,
    year: filterYear,
  };
  const subjectLookup = buildPaperSubjectLookup(subjects);
  const filteredPapers = filterPaperList(papers, listFilters, subjectLookup);
  const categoryOptions = buildPaperCategoryOptions(papers, subjects, subjectLookup, filterSubjectId);
  const yearOptions = buildPaperYearOptions(papers);
  const uploadYearOptions = buildUploadYearOptions(yearOptions);
  const filteredPaperCount = filteredPapers.length;
  const parsedPaperCount = papers.filter((paper) => paper.status === "parsed").length;
  const activeFilterCount = Number(Boolean(filterSubjectId)) + Number(Boolean(filterCategory)) + Number(Boolean(filterYear));
  const selectedSubjectMeta = selected?.subject_id != null ? subjectLookup.get(selected.subject_id) || null : null;

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
        const nextSubject = configSubjects.find((item) => item.id === selectedSubjectId) || configSubjects[0];
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
    const intervalMs = 1200;
    const timer = window.setInterval(() => {
      loadParseJob(parseJob.id).catch((err) => setError(toErrorMessage(err, "刷新解析进度失败")));
    }, intervalMs);
    return () => window.clearInterval(timer);
  }, [parseJob?.id, parseJob?.status]);

  useEffect(() => {
    if (loading) return;
    const nextFiltered = filterPaperList(
      papers,
      { subjectId: filterSubjectId, category: filterCategory, year: filterYear },
      buildPaperSubjectLookup(subjects),
    );
    const currentSelectedId = selected?.id || null;
    const currentSelectedVisible = currentSelectedId != null && nextFiltered.some((paper) => paper.id === currentSelectedId);
    if (!nextFiltered.length) {
      if (currentSelectedId != null) {
        setSelected(null);
        setDetailError("");
        clearParseStateForPaper(currentSelectedId);
      }
      return;
    }
    if (!currentSelectedVisible) {
      setParseMessage("");
      void loadPaperDetail(nextFiltered[0].id, "加载试卷详情失败");
    }
  }, [loading, papers, subjects, filterSubjectId, filterCategory, filterYear, selected?.id]);

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
    const job = await apiFetch<AnalysisJobResponse>(`/api/papers/parse-jobs/${jobId}`);
    setParseJob(job);
    if (job.status === "completed") {
      const summary = job.result_summary_json || {};
      const warnings = Array.isArray(summary.warnings) ? summary.warnings.map(String).filter(Boolean) : [];
      const datasetSamplePath = typeof summary.dataset_sample_path === "string" ? summary.dataset_sample_path : "";
      const datasetExportError = typeof summary.dataset_export_error === "string" ? summary.dataset_export_error : "";
      await refreshPapers(selected?.id || null);
      setParsingId(null);
      setParseMessage(
        `解析完成：已生成 ${Number(summary.question_count || 0)} 道题，规则命中 ${Number(summary.tagged_count || 0)} 条候选考点${warnings.length ? `；当前有 ${warnings.length} 条待复核提示` : ""}${datasetSamplePath ? `；样本已自动导入 ${datasetSamplePath}` : ""}${datasetExportError ? `；训练样本自动导入失败：${datasetExportError}` : ""}。`,
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
    setParseMessage("");
    setWorkspaceTab("detail");
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
      const uploadedYear = String(data.get("exam_year") || "").trim();
      await refreshPapers(uploaded.id);
      form.reset();
      setSelectedSubjectId(activeSubject.id);
      setFilterSubjectId(activeSubject.id);
      setFilterCategory(selectedCategory);
      setFilterYear(uploadedYear);
      setWorkspaceTab("detail");
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
      form.append("parse_mode", "rules");
      if (parsePreset === "formula") form.append("enable_formula_recognition", "true");
      const result = await apiFormFetch<PaperParseJobResponse>(`/api/papers/${id}/parse-jobs`, form);
      setParseJob({
        id: result.job_id,
        job_type: "paper_parse",
        scope_type: "paper",
        scope_config_json: { paper_id: id, stage: "queued", parse_mode: "rules" },
        status: result.status,
        progress: result.progress,
        created_at: new Date().toISOString(),
      });
      setParseMessage(`解析任务已启动：#${result.job_id}。当前模式：规则切题。`);
      await loadParseJob(result.job_id);
    } catch (err) {
      setError(toErrorMessage(err, "解析试卷失败"));
      setParsingId(null);
    } finally {
      // Completion is handled by the job poller.
    }
  }

  async function deletePaper(paper: PaperSummary) {
    const confirmed = window.confirm(`确定删除试卷“${paper.paper_name}”？已解析的分区、题目数据和来源链接也会一并删除。`);
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
      setListMessage(
        `已删除：${result.paper_name}；源文件${result.removed_storage_file ? "已删除" : "未删除"}；已清理解析缓存 ${Number(result.removed_parsed_cache_files || 0)} 个；已清理 OCR 缓存目录 ${Number(result.removed_pdf_checkpoint_dirs || 0)} 个${result.cleanup_warnings?.length ? `；清理告警：${result.cleanup_warnings.join("；")}` : ""}`,
      );
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
    <div className="paperCenterPage">
      <section className="paperCenterHero">
        <div className="paperCenterHeroTop">
          <div className="paperCenterHeroTitle">
            <span className="paperCenterEyebrow">Paper Workspace</span>
            <h1>试卷中心</h1>
          </div>
          <div className="paperCenterHeroActions">
            <div className="paperCenterInlineFilters">
              <select
                className="paperCenterFilterSelect"
                aria-label="按学科筛选"
                value={filterSubjectId}
                onChange={(event) => {
                  setFilterSubjectId(event.target.value);
                  setFilterCategory("");
                }}
              >
                <option value="">全部学科</option>
                {subjects.map((subject) => (
                  <option key={subject.id} value={subject.id}>
                    {subject.name}
                  </option>
                ))}
              </select>
              <select
                className="paperCenterFilterSelect"
                aria-label="按类目筛选"
                value={filterCategory}
                onChange={(event) => setFilterCategory(event.target.value)}
              >
                <option value="">全部类目</option>
                {categoryOptions.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
              <select
                className="paperCenterFilterSelect"
                aria-label="按年份筛选"
                value={filterYear}
                onChange={(event) => setFilterYear(event.target.value)}
              >
                <option value="">全部年份</option>
                {yearOptions.map((year) => (
                  <option key={year} value={year}>
                    {year}
                  </option>
                ))}
              </select>
              <button
                className="button small"
                type="button"
                disabled={!activeFilterCount}
                onClick={() => {
                  setFilterSubjectId("");
                  setFilterCategory("");
                  setFilterYear("");
                }}
              >
                重置
              </button>
            </div>
            <div className="paperCenterHeroMetrics">
              <div className="paperCenterHeroMetric">
                <span>已入库</span>
                <strong>{papers.length}</strong>
              </div>
              <div className="paperCenterHeroMetric">
                <span>当前筛选</span>
                <strong>{filteredPaperCount}</strong>
              </div>
              <div className="paperCenterHeroMetric">
                <span>已解析</span>
                <strong>{parsedPaperCount}</strong>
              </div>
            </div>
            <div className="buttonRow">
              <button className="button primary" type="button" onClick={() => setWorkspaceTab("upload")}>
                上传新试卷
              </button>
              <Link className="button" href={selected?.id ? `/analysis/questions?paperId=${selected.id}` : "/analysis/questions"}>
                进入题目解析
              </Link>
            </div>
          </div>
        </div>
      </section>
      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <section className="dashboardGrid twoCol questionWorkspace paperCenterWorkspace">
        <div className="panel questionPanel questionQueuePanel paperCenterListPanel">
          <div className="panelHeader panelHeaderActions">
            <div>
              <h2>试卷列表</h2>
              <p>支持按学科、类目、年份快速收敛范围。</p>
            </div>
            <StatusBadge value={`${filteredPaperCount} / ${papers.length}`} tone="info" />
          </div>
          <div className="panelBody questionQueueBody">
            {listMessage && <p className="muted">{listMessage}</p>}
            <LoadState
              loading={loading}
              error={error}
              empty={!filteredPaperCount}
              emptyLabel={papers.length ? "当前筛选条件下暂无试卷" : "暂无试卷数据"}
            />
            {!!filteredPaperCount && (
              <div className="stackList paperCenterListScroll">
                {filteredPapers.map((paper) => {
                  const subjectMeta = paper.subject_id != null ? subjectLookup.get(paper.subject_id) || null : null;
                  return (
                    <div key={paper.id} className="paperListItem">
                      <button
                        className={`paperPickButton${selected?.id === paper.id ? " active" : ""}`}
                        type="button"
                        onClick={() => pickPaper(paper.id)}
                      >
                        <div className="paperCenterCardMain">
                          <div className="paperCenterCardHeader">
                            <span className="paperCenterCardEyebrow">{subjectMeta?.name || "未绑定学科"}</span>
                            <strong>{paper.paper_name}</strong>
                          </div>
                          <div className="paperCenterCardMeta">
                            <span>{paper.category || "未分类"}</span>
                            <span>{paper.exam_year || "-"} 年</span>
                            <span>{paper.exam_region || "未知地区"}</span>
                            <span>{paper.total_question_count} 题</span>
                          </div>
                        </div>
                        <div className="paperCenterListBadgeStack">
                          <StatusBadge value={paper.review_status} tone={paper.review_status === "approved" ? "good" : "warn"} />
                          <span className="paperCenterInlineStatus">{paperStatusLabel(paper.status)}</span>
                        </div>
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
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="panel questionPanel questionDetailPanel paperCenterWorkspacePanel">
          <div className="panelHeader paperCenterWorkspaceHeader">
            <div>
              <h2>{workspaceTab === "detail" ? "试卷详情" : "上传试卷"}</h2>
              <p>
                {workspaceTab === "detail"
                  ? "查看解析状态、分区结果与 OCR 参数。"
                  : "完成文件入库与元数据补充，不需要离开当前页面。"}
              </p>
            </div>
            <div className="paperCenterTabs" role="tablist" aria-label="试卷工作区">
              <button
                className={`paperCenterTab${workspaceTab === "detail" ? " active" : ""}`}
                type="button"
                aria-selected={workspaceTab === "detail"}
                onClick={() => setWorkspaceTab("detail")}
              >
                详情
              </button>
              <button
                className={`paperCenterTab${workspaceTab === "upload" ? " active" : ""}`}
                type="button"
                aria-selected={workspaceTab === "upload"}
                onClick={() => setWorkspaceTab("upload")}
              >
                上传
              </button>
            </div>
          </div>
          <div className="panelBody questionDetailBody">
            {workspaceTab === "detail" ? (
              <>
                <LoadState
                  loading={loading}
                  error={detailError}
                  empty={!selected}
                  emptyLabel={filteredPaperCount ? "请选择一份试卷" : papers.length ? "当前筛选条件下暂无试卷" : "暂无试卷数据"}
                />
                {selected && (
                  <div className="paperCenterDetailScroll">
                    <section className="paperCenterSelectedHero">
                      <div className="paperCenterSelectedSummary">
                        <h3>{selected.paper_name}</h3>
                        <p>
                          {selected.category || "未分类"} · {selected.exam_year || "-"} 年 · {selected.exam_region || "未知地区"} · {selected.total_question_count} 题
                        </p>
                      </div>
                      <div className="paperCenterSelectedBadges">
                        <div className="paperCenterStatusLights" aria-label="试卷状态摘要">
                          <span
                            className="paperCenterStatusItem"
                            title={`解析状态：${
                              selected.active_parse_stage
                                ? parseStageLabel(selected.active_parse_stage)
                                : parseRuntimeStatusLabel(selected.asset_parse_status)
                            }`}
                            aria-label={`解析状态：${
                              selected.active_parse_stage
                                ? parseStageLabel(selected.active_parse_stage)
                                : parseRuntimeStatusLabel(selected.asset_parse_status)
                            }`}
                          >
                            <span>解析</span>
                            <span
                              className={`paperCenterStatusLight ${statusLightTone(
                                selected.active_parse_stage ? selected.active_parse_stage : selected.asset_parse_status,
                                "parse",
                              )}`}
                            />
                          </span>
                          <span
                            className="paperCenterStatusItem"
                            title={`试卷状态：${
                              selected.active_parse_stage
                                ? parseStageLabel(selected.active_parse_stage)
                                : paperStatusLabel(selected.status)
                            }`}
                            aria-label={`试卷状态：${
                              selected.active_parse_stage
                                ? parseStageLabel(selected.active_parse_stage)
                                : paperStatusLabel(selected.status)
                            }`}
                          >
                            <span>试卷</span>
                            <span
                              className={`paperCenterStatusLight ${statusLightTone(
                                selected.active_parse_stage ? selected.active_parse_stage : selected.status,
                                "paper",
                              )}`}
                            />
                          </span>
                          <span
                            className="paperCenterStatusItem"
                            title={`审核状态：${reviewStatusLabel(selected.review_status)}`}
                            aria-label={`审核状态：${reviewStatusLabel(selected.review_status)}`}
                          >
                            <span>审核</span>
                            <span className={`paperCenterStatusLight ${statusLightTone(selected.review_status, "review")}`} />
                          </span>
                        </div>
                        <span className="paperCenterEyebrow paperCenterSelectedSubjectBadge">
                          {selectedSubjectMeta?.name || selected.subject_name || "未绑定学科"}
                        </span>
                      </div>
                    </section>

                    <div className="buttonRow">
                      <button className="button primary" type="button" disabled={parsingId === selected.id} onClick={() => parsePaper(selected.id)}>
                        {parsingId === selected.id ? "解析中..." : "解析并切题"}
                      </button>
                      <Link className="button" href={`/analysis/papers/preview?file_id=${selected.asset_id}`}>
                        解析预览
                      </Link>
                      <Link className="button" href={`/analysis/questions?paperId=${selected.id}`}>
                        进入题目解析
                      </Link>
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

                    <div className="paperCenterDetailSplit">
                      <div className="calloutBox">
                        <strong>OCR 设备能力</strong>
                        {ocrCapability ? (
                          <>
                            <div className="ocrCapabilityCompact">
                              <div className="ocrCapabilityRow">
                                <span className="ocrCapabilityLabel">设备</span>
                                <strong>{ocrCapability.device_name || "未检测到 GPU"}</strong>
                              </div>
                              <div className="ocrCapabilityRow">
                                <span className="ocrCapabilityLabel">显存</span>
                                <strong>{formatMemory(ocrCapability.gpu_memory_free_mb)}</strong>
                                <span className="muted">空闲</span>
                                <strong>
                                  {formatMemory(ocrCapability.gpu_memory_free_mb)} / {formatMemory(ocrCapability.gpu_memory_total_mb)}
                                </strong>
                              </div>
                              <div className="ocrCapabilityRow">
                                <span className="ocrCapabilityLabel">模型</span>
                                <span className="ocrModelChip active">
                                  {String(ocrCapability.current_settings.text_detection_model_name || "-")}
                                </span>
                                <span className="ocrModelChip active">
                                  {String(ocrCapability.current_settings.text_recognition_model_name || "-")}
                                </span>
                              </div>
                            </div>
                            {!!ocrCapability.warnings.length && <p className="errorText">{ocrCapability.warnings.join(" | ")}</p>}
                          </>
                        ) : (
                          <p className={ocrCapabilityError ? "errorText" : "muted"}>{ocrCapabilityError || "正在检测 OCR 设备能力..."}</p>
                        )}
                        <button className="button small" type="button" onClick={loadOcrCapability}>
                          刷新检测
                        </button>
                      </div>

                      <div className="stackList">
                        <div className="ocrControlPanel">
                          <div className="ocrControlHeader">
                            <strong>解析模式</strong>
                            <span>规则切题</span>
                          </div>
                          <div className="ocrControlHeader" style={{ marginTop: 12 }}>
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
                                max="360"
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
                      </div>
                    </div>

                    <div className="subsection">
                      <div className="paperCenterSectionHeader">
                        <strong>试卷分区</strong>
                        <span className="muted">{selected.sections.length} 个分区</span>
                      </div>
                      {selected.sections.length ? (
                        <div className="tableWrap paperCenterSectionTableWrap">
                          <table className="paperCenterSectionTable">
                            <thead>
                              <tr>
                                <th>分区</th>
                                <th>题型</th>
                                <th>数量</th>
                                <th>题号范围</th>
                                <th>分值</th>
                              </tr>
                            </thead>
                            <tbody>
                              {selected.sections.map((section) => (
                                <tr key={section.id}>
                                  <td>{section.section_name}</td>
                                  <td>{section.question_type || "-"}</td>
                                  <td>{paperSectionQuestionCount(section.start_no, section.end_no)}</td>
                                  <td>{paperSectionRangeLabel(section.start_no, section.end_no)}</td>
                                  <td>{section.score != null ? `${section.score} 分` : "-"}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      ) : (
                        <div className="empty compact">暂无试卷分区</div>
                      )}
                    </div>
                  </div>
                )}
              </>
            ) : (
              <div className="paperCenterUploadBody">
                <div className="calloutBox">
                  <strong>上传建议</strong>
                  <p>支持 PDF、图片、DOCX、Markdown 与 TXT。先入库基础元数据，后续解析任务会自动接管 OCR、切题和考点识别。</p>
                </div>
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
                      <select name="exam_year" defaultValue="" disabled={uploading}>
                        <option value="">未填写</option>
                        {uploadYearOptions.map((year) => (
                          <option key={year} value={year}>
                            {year}
                          </option>
                        ))}
                      </select>
                    </label>
                    <label className="field">
                      <span>月份</span>
                      <input name="exam_month" type="number" min="1" max="12" placeholder="8" disabled={uploading} />
                    </label>
                  </div>
                  <div className="row">
                    <label className="field">
                      <span>地区</span>
                      <input
                        name="exam_region"
                        list="paperUploadRegions"
                        defaultValue="全国"
                        placeholder="搜索或输入地区"
                        autoComplete="off"
                        disabled={uploading}
                      />
                      <datalist id="paperUploadRegions">
                        {uploadRegionOptions.map((region) => (
                          <option key={region} value={region} />
                        ))}
                      </datalist>
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
            )}
          </div>
        </div>
      </section>
    </div>
  );
}

function buildPaperSubjectLookup(subjects: SubjectConfig[]) {
  const lookup = new Map<number, PaperSubjectMeta>();
  subjects.forEach((subject) => {
    if (subject.platform_id == null) return;
    lookup.set(subject.platform_id, {
      code: subject.id,
      name: subject.name,
      categories: subject.categories,
    });
  });
  return lookup;
}

function filterPaperList(
  papers: PaperSummary[],
  filters: PaperListFilters,
  subjectLookup: Map<number, PaperSubjectMeta>,
) {
  return papers.filter((paper) => {
    const subjectMeta = paper.subject_id != null ? subjectLookup.get(paper.subject_id) || null : null;
    const matchesSubject = !filters.subjectId || subjectMeta?.code === filters.subjectId;
    const matchesCategory = !filters.category || String(paper.category || "") === filters.category;
    const matchesYear = !filters.year || String(paper.exam_year || "") === filters.year;
    return matchesSubject && matchesCategory && matchesYear;
  });
}

function buildPaperCategoryOptions(
  papers: PaperSummary[],
  subjects: SubjectConfig[],
  subjectLookup: Map<number, PaperSubjectMeta>,
  subjectId: string,
) {
  const categories = new Set<string>();
  if (subjectId) {
    const subject = subjects.find((item) => item.id === subjectId) || null;
    subject?.categories.forEach((category) => {
      const normalized = String(category || "").trim();
      if (normalized) categories.add(normalized);
    });
    papers.forEach((paper) => {
      const subjectMeta = paper.subject_id != null ? subjectLookup.get(paper.subject_id) || null : null;
      const normalized = String(paper.category || "").trim();
      if (subjectMeta?.code === subjectId && normalized) categories.add(normalized);
    });
  } else {
    papers.forEach((paper) => {
      const normalized = String(paper.category || "").trim();
      if (normalized) categories.add(normalized);
    });
  }
  return Array.from(categories).sort((left, right) => left.localeCompare(right, "zh-CN"));
}

function buildPaperYearOptions(papers: PaperSummary[]) {
  return Array.from(
    new Set(
      papers
        .map((paper) => String(paper.exam_year || "").trim())
        .filter(Boolean),
    ),
  ).sort((left, right) => Number(right) - Number(left));
}

function buildUploadYearOptions(existingYears: string[]) {
  const values = new Set(existingYears.filter(Boolean));
  const currentYear = new Date().getFullYear();
  for (let year = currentYear + 1; year >= 1990; year -= 1) {
    values.add(String(year));
  }
  return Array.from(values).sort((left, right) => Number(right) - Number(left));
}

function paperSectionQuestionCount(startNo?: number | null, endNo?: number | null) {
  if (startNo == null || endNo == null) return "-";
  if (endNo < startNo) return "-";
  return String(endNo - startNo + 1);
}

function paperSectionRangeLabel(startNo?: number | null, endNo?: number | null) {
  if (startNo == null || endNo == null) return "-";
  return `${startNo} - ${endNo}`;
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
    accurate: "PP-StructureV3 高精度版面解析，默认模式",
    formula: "高精度版面解析 + 公式识别，适合公式较多试卷",
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

function reviewStatusLabel(status?: string | null) {
  const labels: Record<string, string> = {
    pending: "待审核",
    approved: "已通过",
    needs_revision: "待修订",
    rejected: "已驳回",
  };
  return labels[status || ""] || status || "-";
}

function statusLightTone(status: string | null | undefined, scope: "parse" | "paper" | "review") {
  const normalized = String(status || "");
  if (scope === "review") {
    if (normalized === "approved") return "good";
    if (normalized === "rejected") return "danger";
    return "warn";
  }
  if (normalized === "parsed" || normalized === "completed") return "good";
  if (normalized === "failed" || normalized === "parse_failed" || normalized === "empty") return "danger";
  return "warn";
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
