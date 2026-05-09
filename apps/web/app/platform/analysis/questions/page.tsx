"use client";

import Link from "next/link";
import { Bot, BrainCircuit, Orbit, RefreshCw, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type TextareaHTMLAttributes } from "react";

import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { renderDocumentPreviewHtml } from "../../../../lib/document-preview";
import {
  apiFetch,
  KnowledgePointResponse,
  PaperReviewAIActionResponse,
  PaperReviewAutoTagJobResponse,
  PaperReviewAutoTagResponse,
  PaperReviewQuestionKnowledgePointUpdateRequest,
  PaperReviewQuestionResponse,
  PaperReviewQuestionUpdateRequest,
  PaperReviewSummaryResponse,
  PaperReviewWorkspaceResponse,
  PaperSummary,
} from "../../../../lib/pro-api";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

type DraftState = {
  questionType: string;
  stemText: string;
  options: string[];
  answerText: string;
  analysisText: string;
  reviewStatus: "pending" | "approved" | "needs_revision" | "rejected";
  reviewNote: string;
  suggestedKnowledgePointIds: number[];
  confirmedKnowledgePointIds: number[];
  primaryKnowledgePointId: number | null;
};

const emptyDraft: DraftState = {
  questionType: "",
  stemText: "",
  options: [],
  answerText: "",
  analysisText: "",
  reviewStatus: "pending",
  reviewNote: "",
  suggestedKnowledgePointIds: [],
  confirmedKnowledgePointIds: [],
  primaryKnowledgePointId: null,
};

const reviewStatusOptions = [
  { value: "all", label: "全部人工状态" },
  { value: "pending", label: "待人工审核" },
  { value: "approved", label: "人工通过" },
  { value: "needs_revision", label: "待修订" },
  { value: "rejected", label: "已驳回" },
] as const;

const aiStatusOptions = [
  { value: "all", label: "全部 AI 状态" },
  { value: "pending", label: "未做 AI 审核" },
  { value: "approved", label: "AI 通过" },
  { value: "needs_revision", label: "AI 提醒修订" },
  { value: "rejected", label: "AI 判定异常" },
] as const;

const questionTypeOptions = [
  "single_choice",
  "multiple_choice",
  "judge",
  "fill_blank",
  "short_answer",
  "calculation",
  "case_analysis",
  "material_analysis",
  "composite",
  "mixed",
];

export default function PaperReviewPage() {
  return (
    <Suspense fallback={<div className="panel"><div className="panelBody">加载中...</div></div>}>
      <PaperReviewPageContent />
    </Suspense>
  );
}

function PaperReviewPageContent() {
  const paperReviewApiBase = "/api/paper-review";
  const searchParams = useSearchParams();
  const preferredPaperId = Number(searchParams.get("paperId") || "") || null;
  const paperGate = useLatestRequestGate();
  const workspaceGate = useLatestRequestGate();

  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [workspace, setWorkspace] = useState<PaperReviewWorkspaceResponse | null>(null);
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePointResponse[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [draft, setDraft] = useState<DraftState>(emptyDraft);
  const [loadingPapers, setLoadingPapers] = useState(true);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [saving, setSaving] = useState(false);
  const [savingKnowledgePoints, setSavingKnowledgePoints] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const [autoTagging, setAutoTagging] = useState(false);
  const [autoTaggingQuestionId, setAutoTaggingQuestionId] = useState<number | null>(null);
  const [autoTagProgress, setAutoTagProgress] = useState<PaperReviewAutoTagResponse | null>(null);
  const [standardizingId, setStandardizingId] = useState<number | null>(null);
  const [reviewingId, setReviewingId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [search, setSearch] = useState("");
  const [reviewFilter, setReviewFilter] = useState<(typeof reviewStatusOptions)[number]["value"]>("all");
  const [aiFilter, setAiFilter] = useState<(typeof aiStatusOptions)[number]["value"]>("all");
  const [sectionFilter, setSectionFilter] = useState("all");

  useEffect(() => {
    loadPapers();
  }, []);

  useEffect(() => {
    if (!papers.length) return;
    if (selectedPaperId && papers.some((paper) => paper.id === selectedPaperId)) return;
    const fallbackPaperId = preferredPaperId && papers.some((paper) => paper.id === preferredPaperId)
      ? preferredPaperId
      : papers[0]?.id || null;
    setSelectedPaperId(fallbackPaperId);
  }, [papers, preferredPaperId, selectedPaperId]);

  useEffect(() => {
    if (!selectedPaperId) {
      setWorkspace(null);
      setSelectedQuestionId(null);
      return;
    }
    void loadWorkspace(selectedPaperId);
    syncPaperQuery(selectedPaperId);
  }, [selectedPaperId]);

  const filteredQuestions = useMemo(() => {
    if (!workspace) return [] as PaperReviewQuestionResponse[];
    const keyword = search.trim().toLowerCase();
    return workspace.questions.filter((question) => {
      if (reviewFilter !== "all" && question.review_status !== reviewFilter) return false;
      if (aiFilter === "pending") {
        if (question.ai_review_status) return false;
      } else if (aiFilter !== "all" && question.ai_review_status !== aiFilter) {
        return false;
      }
      if (sectionFilter !== "all" && String(question.section_id || "") !== sectionFilter) return false;
      if (!keyword) return true;
      return [
        question.question_no,
        question.source_section_name,
        question.stem_text,
        question.answer_text || "",
        question.analysis_text || "",
      ]
        .join("\n")
        .toLowerCase()
        .includes(keyword);
    });
  }, [aiFilter, reviewFilter, search, sectionFilter, workspace]);

  const activeQuestion = useMemo(
    () => workspace?.questions.find((question) => question.id === selectedQuestionId) || null,
    [selectedQuestionId, workspace],
  );

  const scopedKnowledgePoints = useMemo(() => {
    if (!workspace?.paper.subject_name) return knowledgePoints;
    const categoryId = papers.find((paper) => paper.id === selectedPaperId)?.category_id || null;
    return knowledgePoints.filter((point) => {
      if (workspace.paper && papers.find((paper) => paper.id === selectedPaperId)?.subject_id && point.subject_id !== papers.find((paper) => paper.id === selectedPaperId)?.subject_id) {
        return false;
      }
      if (categoryId && point.category_id && point.category_id !== categoryId) {
        return false;
      }
      return true;
    });
  }, [knowledgePoints, papers, selectedPaperId, workspace]);

  useEffect(() => {
    if (!activeQuestion) {
      setDraft(emptyDraft);
      return;
    }
    setDraft(buildDraft(activeQuestion));
  }, [activeQuestion]);

  useEffect(() => {
    if (!autoTagging && autoTaggingQuestionId == null) return;
    if (!autoTagProgress) return;
    if (!selectedPaperId) return;
    const jobId = (window as typeof window & { __paperReviewAutoTagJobId?: number }).__paperReviewAutoTagJobId;
    if (!jobId) return;

    const timer = window.setInterval(async () => {
      try {
        const progress = await apiFetch<PaperReviewAutoTagResponse>(`${paperReviewApiBase}/auto-tag-jobs/${jobId}`);
        setAutoTagProgress(progress);
        const done = progress.status === "completed" || progress.status === "failed";
        if (done) {
          window.clearInterval(timer);
          (window as typeof window & { __paperReviewAutoTagJobId?: number }).__paperReviewAutoTagJobId = undefined;
          setAutoTagging(false);
          setAutoTaggingQuestionId(null);
          await loadWorkspace(selectedPaperId, activeQuestion?.id || null);
          setActionMessage(progress.message);
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 1200);

    return () => window.clearInterval(timer);
  }, [activeQuestion?.id, autoTagProgress, autoTagging, autoTaggingQuestionId, paperReviewApiBase, selectedPaperId]);

  async function loadPapers() {
    const requestId = paperGate.begin();
    setLoadingPapers(true);
    setError("");
    try {
      const nextPapers = await apiFetch<PaperSummary[]>("/api/papers");
      const nextKnowledgePoints = await apiFetch<KnowledgePointResponse[]>("/api/knowledge/points");
      if (!paperGate.isCurrent(requestId)) return;
      setPapers(nextPapers);
      setKnowledgePoints(nextKnowledgePoints);
    } catch (err) {
      if (!paperGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载试卷列表失败"));
    } finally {
      if (paperGate.isCurrent(requestId)) setLoadingPapers(false);
    }
  }

  async function loadWorkspace(paperId: number, preferredQuestionId?: number | null) {
    const requestId = workspaceGate.begin();
    setLoadingWorkspace(true);
    setWorkspaceError("");
    try {
      const nextWorkspace = await apiFetch<PaperReviewWorkspaceResponse>(`${paperReviewApiBase}/papers/${paperId}`);
      if (!workspaceGate.isCurrent(requestId)) return;
      setWorkspace(nextWorkspace);
      setSelectedQuestionId((current) => {
        if (preferredQuestionId && nextWorkspace.questions.some((question) => question.id === preferredQuestionId)) {
          return preferredQuestionId;
        }
        if (current && nextWorkspace.questions.some((question) => question.id === current)) {
          return current;
        }
        return nextWorkspace.questions[0]?.id || null;
      });
      if (sectionFilter !== "all" && !nextWorkspace.sections.some((section) => String(section.id) === sectionFilter)) {
        setSectionFilter("all");
      }
    } catch (err) {
      if (!workspaceGate.isCurrent(requestId)) return;
      setWorkspace(null);
      setSelectedQuestionId(null);
      setWorkspaceError(toErrorMessage(err, "加载题目解析工作台失败"));
    } finally {
      if (workspaceGate.isCurrent(requestId)) setLoadingWorkspace(false);
    }
  }

  async function saveQuestion() {
    if (!activeQuestion) return;
    setSaving(true);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const payload: PaperReviewQuestionUpdateRequest = {
        question_type: draft.questionType.trim(),
        stem_text: draft.stemText,
        options_json: draft.options,
        answer_text: draft.answerText,
        analysis_text: draft.analysisText,
        review_status: draft.reviewStatus,
        review_note: draft.reviewNote,
      };
      const nextQuestion = await apiFetch<PaperReviewQuestionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}`, {
        method: "PATCH",
        body: JSON.stringify(payload),
      });
      replaceQuestion(nextQuestion);
      setActionMessage("人工审核已保存。");
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "保存题目失败"));
    } finally {
      setSaving(false);
    }
  }

  async function saveKnowledgePoints() {
    if (!activeQuestion) return;
    setSavingKnowledgePoints(true);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const payload: PaperReviewQuestionKnowledgePointUpdateRequest = {
        suggested: draft.suggestedKnowledgePointIds
          .filter((id) => !draft.confirmedKnowledgePointIds.includes(id))
          .map((knowledgePointId, index) => ({
            knowledge_point_id: knowledgePointId,
            relation_type: "secondary",
            source: "manual",
            rank: index + 1,
          })),
        confirmed: draft.confirmedKnowledgePointIds.map((knowledgePointId, index) => ({
          knowledge_point_id: knowledgePointId,
          relation_type: draft.primaryKnowledgePointId === knowledgePointId ? "primary" : "secondary",
          source: "manual",
          rank: index + 1,
        })),
      };
      const nextQuestion = await apiFetch<PaperReviewQuestionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/knowledge-points`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      replaceQuestion(nextQuestion);
      setActionMessage("考点标注已保存。");
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "保存考点标注失败"));
    } finally {
      setSavingKnowledgePoints(false);
    }
  }

  async function rebuildQuestions() {
    if (!selectedPaperId) return;
    setRebuilding(true);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<{ message: string }>(`${paperReviewApiBase}/papers/${selectedPaperId}/rebuild`, {
        method: "POST",
      });
      await loadWorkspace(selectedPaperId);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "重建题目失败"));
    } finally {
      setRebuilding(false);
    }
  }

  async function autoTagQuestions() {
    if (!selectedPaperId) return;
    setAutoTagging(true);
    setActionMessage("");
    setWorkspaceError("");
    setAutoTagProgress(null);
    try {
      const result = await apiFetch<PaperReviewAutoTagJobResponse>(`${paperReviewApiBase}/papers/${selectedPaperId}/auto-tag`, {
        method: "POST",
      });
      (window as typeof window & { __paperReviewAutoTagJobId?: number }).__paperReviewAutoTagJobId = result.job_id;
      setAutoTagProgress({
        paper_id: result.paper_id,
        status: result.status,
        progress: result.progress,
        requested_count: 0,
        updated_count: 0,
        failed_count: 0,
        skipped_count: 0,
        message: "自动标注任务已启动。",
      });
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "自动考点标注失败"));
      setAutoTagging(false);
    } finally {
      // Keep polling until job completion.
    }
  }

  async function autoTagCurrentQuestion() {
    if (!activeQuestion || !selectedPaperId) return;
    setAutoTaggingQuestionId(activeQuestion.id);
    setActionMessage("");
    setWorkspaceError("");
    setAutoTagProgress(null);
    try {
      const result = await apiFetch<PaperReviewAutoTagJobResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/auto-tag`, {
        method: "POST",
      });
      (window as typeof window & { __paperReviewAutoTagJobId?: number }).__paperReviewAutoTagJobId = result.job_id;
      setAutoTagProgress({
        paper_id: result.paper_id,
        status: result.status,
        progress: result.progress,
        requested_count: 0,
        updated_count: 0,
        failed_count: 0,
        skipped_count: 0,
        message: "当前题自动标注任务已启动。",
      });
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "当前题自动考点标注失败"));
      setAutoTaggingQuestionId(null);
    } finally {
      // Keep polling until job completion.
    }
  }

  async function runAiStandardize() {
    if (!activeQuestion) return;
    setStandardizingId(activeQuestion.id);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<PaperReviewAIActionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/ai-standardize`, {
        method: "POST",
      });
      replaceQuestion(result.question);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 标准化失败"));
    } finally {
      setStandardizingId(null);
    }
  }

  async function runAiReview() {
    if (!activeQuestion) return;
    setReviewingId(activeQuestion.id);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<PaperReviewAIActionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/ai-review`, {
        method: "POST",
      });
      replaceQuestion(result.question);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 审核失败"));
    } finally {
      setReviewingId(null);
    }
  }

  function replaceQuestion(nextQuestion: PaperReviewQuestionResponse) {
    setWorkspace((current) => {
      if (!current) return current;
      const nextQuestions = current.questions.map((question) => (question.id === nextQuestion.id ? nextQuestion : question));
      return {
        ...current,
        paper: {
          ...current.paper,
          total_question_count: nextQuestions.length,
          question_review_count: nextQuestions.length,
        },
        summary: summarizeQuestions(nextQuestions),
        questions: nextQuestions,
      };
    });
    setSelectedQuestionId(nextQuestion.id);
  }

  function syncPaperQuery(paperId: number | null) {
    if (typeof window === "undefined") return;
    const url = new URL(window.location.href);
    if (paperId) {
      url.searchParams.set("paperId", String(paperId));
    } else {
      url.searchParams.delete("paperId");
    }
    window.history.replaceState({}, "", url.toString());
  }

  return (
    <div className="questionPageShell paperReviewPageRoot">
      <section className="paperReviewHeroCompact">
        <div className="paperReviewHeroMain">
          <span className="analysisEyebrow">Question Intelligence Desk</span>
          <div>
            <h1 className="paperReviewHeroTitle">题目解析与审核工作台</h1>
            <p className="paperReviewHeroCaption">
              {workspace?.paper
                ? `${workspace.paper.paper_name} · ${workspace.summary.pending_count} 道待审 · ${workspace.summary.ai_flagged_count} 道 AI 风险提示`
                : "逐题审核、AI 补全与标准化、答案解析复核"}
            </p>
          </div>
        </div>
        <div className="paperReviewHeroActions">
          {workspace && (
            <div className="paperReviewHeroBadges">
              <StatusBadge value={`待审 ${workspace.summary.pending_count}`} tone="warn" />
              <StatusBadge value={`缺答案/解析 ${workspace.summary.missing_solution_count}`} tone="info" />
            </div>
          )}
          <div className="buttonRow">
            <Link className="button" href="/analysis/papers">
              返回试卷中心
            </Link>
            {selectedPaperId && (
              <button className="button primary" type="button" onClick={rebuildQuestions} disabled={rebuilding}>
                <RefreshCw size={16} aria-hidden />
                <span>{rebuilding ? "重建中..." : "重新切分同步"}</span>
              </button>
            )}
            {selectedPaperId && (
              <button className="button" type="button" onClick={autoTagQuestions} disabled={autoTagging}>
                <Sparkles size={16} aria-hidden />
                <span>{autoTagging ? "标注中..." : "自动标注未标注题"}</span>
              </button>
            )}
          </div>
        </div>
      </section>

      <section className="panel questionWorkbenchPanel">
        <div className="panelHeader">
          <div className="questionWorkbenchHeader">
            <div>
              <h2>
                <Orbit size={18} aria-hidden />
                审核编排
              </h2>
            </div>
            <div className="questionWorkbenchHeaderMeta">
              {workspace && (
                <>
                  <StatusBadge value={`${workspace.paper.question_review_count} 道题`} tone="info" />
                  <StatusBadge value={`人工通过 ${workspace.summary.approved_count}`} tone="good" />
                  <StatusBadge value={`待修订 ${workspace.summary.needs_revision_count}`} tone="warn" />
                </>
              )}
            </div>
          </div>
        </div>
        <div className="panelBody questionWorkbenchBody">
          <div className="questionWorkbenchPrimary">
            <label className="field questionPaperField">
              <span>试卷</span>
              <select
                value={selectedPaperId ? String(selectedPaperId) : ""}
                onChange={(event) => {
                  setSelectedPaperId(Number(event.target.value) || null);
                  setActionMessage("");
                }}
                disabled={loadingPapers || !papers.length}
              >
                {!papers.length && <option value="">暂无试卷</option>}
                {papers.map((paper) => (
                  <option key={paper.id} value={paper.id}>
                    {paper.paper_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field questionSearchField">
              <span>关键词搜索</span>
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="题干、答案、解析、题号" />
            </label>
            <label className="field">
              <span>人工审核</span>
              <select value={reviewFilter} onChange={(event) => setReviewFilter(event.target.value as typeof reviewFilter)}>
                {reviewStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>AI 审核</span>
              <select value={aiFilter} onChange={(event) => setAiFilter(event.target.value as typeof aiFilter)}>
                {aiStatusOptions.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>分区</span>
              <select value={sectionFilter} onChange={(event) => setSectionFilter(event.target.value)}>
                <option value="all">全部分区</option>
                {(workspace?.sections || []).map((section) => (
                  <option key={section.id} value={section.id}>
                    {section.section_name}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {autoTagProgress && (
            <div className="calloutBox">
              {autoTagProgress.message}
              {` 进度 ${autoTagProgress.progress}% · 共 ${autoTagProgress.requested_count} 题，已完成 ${autoTagProgress.updated_count + autoTagProgress.failed_count}，成功 ${autoTagProgress.updated_count}，失败 ${autoTagProgress.failed_count}，跳过 ${autoTagProgress.skipped_count}。`}
            </div>
          )}
          {actionMessage && <div className="calloutBox">{actionMessage}</div>}
          {workspaceError && <div className="errorPanel">{workspaceError}</div>}
        </div>
      </section>

      <section className="dashboardGrid twoCol questionWorkspace">
        <article className="panel questionPanel questionQueuePanel">
          <div className="panelHeader">
            <div className="questionQueueListHeader">
              <div className="questionQueueListLead">
                <h2>题目队列</h2>
                {workspace && <p>{`${filteredQuestions.length} / ${workspace.questions.length} 道题`}</p>}
              </div>
              <div className="questionQueueListHeaderActions">
                {workspace?.paper.id ? (
                  <Link className="button small" href={`/analysis/papers?paperId=${workspace.paper.id}`}>
                    试卷详情
                  </Link>
                ) : null}
              </div>
            </div>
          </div>
          <div className="panelBody questionQueueBody">
            <div className="questionQueueStats">
              <div className="questionMiniStat">
                <span>待人工审核</span>
                <strong>{workspace?.summary.pending_count || 0}</strong>
              </div>
              <div className="questionMiniStat">
                <span>AI 标记风险</span>
                <strong>{workspace?.summary.ai_flagged_count || 0}</strong>
              </div>
              <div className="questionMiniStat">
                <span>缺答案/解析</span>
                <strong>{workspace?.summary.missing_solution_count || 0}</strong>
              </div>
              <div className="questionMiniStat">
                <span>人工通过率</span>
                <strong>{formatRate(workspace?.summary)}</strong>
              </div>
            </div>
            <LoadState
              loading={loadingPapers || loadingWorkspace}
              error={error}
              empty={!loadingPapers && !loadingWorkspace && !papers.length}
              emptyLabel="暂无试卷，请先到试卷中心上传并切题"
            />
            {!error && (
              <div className="questionQueueList">
                {filteredQuestions.map((question) => {
                  const active = question.id === activeQuestion?.id;
                  return (
                    <div key={question.id} className="selectableRow questionSelectableRow">
                      <button
                        className={active ? "listButton questionListButton active paperReviewQueueCard" : "listButton questionListButton paperReviewQueueCard"}
                        type="button"
                        onClick={() => setSelectedQuestionId(question.id)}
                      >
                        <div className="questionListContent">
                          <div className="paperReviewQueueTop">
                            <strong className="questionListTitle">第 {question.question_no || question.sort_order} 题</strong>
                            <div className="paperReviewQueueMetaLine">
                              <span className="paperReviewQuestionLabel">{questionTypeLabel(question.question_type)}</span>
                              <StatusBadge value={reviewStatusLabel(question.review_status)} tone={reviewTone(question.review_status)} />
                              {question.ai_review_status ? (
                                <StatusBadge value={`AI ${reviewStatusLabel(question.ai_review_status)}`} tone={aiTone(question.ai_review_status)} />
                              ) : (
                                <StatusBadge value="AI 未审" tone="info" />
                              )}
                              <StatusBadge value={`质检 ${formatScore(question.quality_score)}`} tone="info" />
                            </div>
                          </div>
                          <span
                            className="questionListNote paperPreviewHtml"
                            dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(question.stem_text) }}
                          />
                        </div>
                      </button>
                    </div>
                  );
                })}
                {!loadingWorkspace && !!papers.length && !filteredQuestions.length && (
                  <div className="empty compact">当前筛选下没有题目</div>
                )}
              </div>
            )}
          </div>
        </article>

        <article className="panel questionPanel questionDetailPanel">
          <div className="panelHeader">
              <div className="questionDetailSummary">
                <div>
                  <h2>题目详情</h2>
                  {activeQuestion && (
                    <p className="questionDetailLead">
                      {`${activeQuestion.source_section_name} · 第 ${activeQuestion.question_no} 题 · ${questionTypeLabel(activeQuestion.question_type)}`}
                    </p>
                  )}
                </div>
              <div className="questionDetailSummaryBadges">
                {activeQuestion && (
                  <>
                    <StatusBadge value={reviewStatusLabel(activeQuestion.review_status)} tone={reviewTone(activeQuestion.review_status)} />
                    <StatusBadge
                      value={activeQuestion.ai_review_status ? `AI ${reviewStatusLabel(activeQuestion.ai_review_status)}` : "AI 未审"}
                      tone={activeQuestion.ai_review_status ? aiTone(activeQuestion.ai_review_status) : "info"}
                    />
                  </>
                )}
              </div>
            </div>
          </div>
          <div className="panelBody questionDetailBody">
            <LoadState
              loading={loadingWorkspace}
              error={workspaceError}
              empty={!loadingWorkspace && !activeQuestion}
              emptyLabel="请选择一道题目"
            />
            {activeQuestion && (
              <div className="questionDetailWorkspace">
                <div className="questionDetailSticky">
                  <div className="questionDetailNav">
                    <button className="button primary" type="button" onClick={saveQuestion} disabled={saving}>
                      <ShieldCheck size={16} aria-hidden />
                      <span>{saving ? "保存中..." : "保存人工审核"}</span>
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={saveKnowledgePoints}
                      disabled={savingKnowledgePoints}
                    >
                      <Sparkles size={16} aria-hidden />
                      <span>{savingKnowledgePoints ? "保存中..." : "保存考点标注"}</span>
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={autoTagCurrentQuestion}
                      disabled={autoTaggingQuestionId === activeQuestion.id}
                    >
                      <Sparkles size={16} aria-hidden />
                      <span>{autoTaggingQuestionId === activeQuestion.id ? "标注中..." : "自动标注当前题"}</span>
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={runAiStandardize}
                      disabled={standardizingId === activeQuestion.id}
                    >
                      <Wand2 size={16} aria-hidden />
                      <span>{standardizingId === activeQuestion.id ? "AI 处理中..." : "AI 补全与标准化"}</span>
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={runAiReview}
                      disabled={reviewingId === activeQuestion.id}
                    >
                      <Bot size={16} aria-hidden />
                      <span>{reviewingId === activeQuestion.id ? "AI 审核中..." : "AI 答案审核"}</span>
                    </button>
                  </div>
                </div>

                <div className="questionDetailScroll">
                  <div className="questionDetailSection paperReviewDetailGrid">
                    <section className="paperReviewEditorStack">
                      <div className="infoCard">
                        <div className="infoCardTop">
                          <strong>题干与作答信息</strong>
                          <BrainCircuit size={18} aria-hidden />
                        </div>
                        <div className="paperReviewComposeBoard">
                          <div className="paperReviewMetaBar" aria-label="题目元信息">
                            <label className="field paperReviewInlineField">
                              <span>题型</span>
                              <select
                                value={draft.questionType}
                                onChange={(event) => setDraft((current) => ({ ...current, questionType: event.target.value }))}
                              >
                                {questionTypeOptions.map((option) => (
                                  <option key={option} value={option}>
                                    {questionTypeLabel(option)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="field paperReviewInlineField">
                              <span>答案</span>
                              <input
                                value={draft.answerText}
                                onChange={(event) => setDraft((current) => ({ ...current, answerText: event.target.value }))}
                                placeholder="A / AC / 正确"
                              />
                            </label>
                            <label className="field paperReviewInlineField">
                              <span>审核状态</span>
                              <select
                                value={draft.reviewStatus}
                                onChange={(event) => setDraft((current) => ({ ...current, reviewStatus: event.target.value as DraftState["reviewStatus"] }))}
                              >
                                {reviewStatusOptions.filter((option) => option.value !== "all").map((option) => (
                                  <option key={option.value} value={option.value}>
                                    {option.label}
                                  </option>
                                ))}
                              </select>
                            </label>
                            <label className="field paperReviewInlineField">
                              <span>结构质量</span>
                              <input className="paperReviewReadonlyInput" value={formatScore(activeQuestion.quality_score)} readOnly />
                            </label>
                            <label className="field paperReviewInlineField">
                              <span>子问数量</span>
                              <input className="paperReviewReadonlyInput" value={String(activeQuestion.subquestion_count || 0)} readOnly />
                            </label>
                          </div>
                          <div className="paperReviewComposeMain">
                            <label className="field">
                              <span>题干</span>
                              <AutoResizeTextarea
                                className="paperReviewAdaptiveTextarea paperReviewStemTextarea"
                                minRows={4}
                                value={draft.stemText}
                                onChange={(event) => setDraft((current) => ({ ...current, stemText: event.target.value }))}
                              />
                            </label>
                            <div className="paperReviewOptionList">
                              <div className="paperReviewOptionHeader">
                                <strong>选项</strong>
                                <button
                                  className="button small"
                                  type="button"
                                  onClick={() => setDraft((current) => ({ ...current, options: [...current.options, ""] }))}
                                >
                                  新增选项
                                </button>
                              </div>
                              {(draft.options.length ? draft.options : [""]).map((option, index) => (
                                <div key={`option-${index}`} className="paperReviewOptionRow">
                                  <span>{String.fromCharCode(65 + index)}</span>
                                  <input
                                    value={option}
                                    onChange={(event) => {
                                      const nextOptions = [...draft.options];
                                      nextOptions[index] = event.target.value;
                                      setDraft((current) => ({ ...current, options: nextOptions }));
                                    }}
                                    placeholder={`选项 ${String.fromCharCode(65 + index)}`}
                                  />
                                  <button
                                    className="button small danger"
                                    type="button"
                                    onClick={() => {
                                      const nextOptions = draft.options.filter((_, optionIndex) => optionIndex !== index);
                                      setDraft((current) => ({ ...current, options: nextOptions }));
                                    }}
                                    disabled={draft.options.length <= 1}
                                  >
                                    删除
                                  </button>
                                </div>
                              ))}
                            </div>
                            <label className="field">
                              <span>解析</span>
                              <AutoResizeTextarea
                                className="paperReviewAdaptiveTextarea"
                                minRows={4}
                                value={draft.analysisText}
                                onChange={(event) => setDraft((current) => ({ ...current, analysisText: event.target.value }))}
                              />
                            </label>
                            <label className="field">
                              <span>人工审核备注</span>
                              <AutoResizeTextarea
                                className="paperReviewAdaptiveTextarea"
                                minRows={2}
                                value={draft.reviewNote}
                                onChange={(event) => setDraft((current) => ({ ...current, reviewNote: event.target.value }))}
                                placeholder="记录人工判断、待补材料或入库说明"
                              />
                            </label>
                            <div className="infoCard">
                              <div className="infoCardTop">
                                <strong>考点标注</strong>
                                <Sparkles size={18} aria-hidden />
                              </div>
                              <div className="paperReviewComposeMain">
                                <label className="field">
                                  <span>已确认考点</span>
                                  <select
                                    multiple
                                    value={draft.confirmedKnowledgePointIds.map(String)}
                                    onChange={(event) => {
                                      const values = Array.from(event.target.selectedOptions).map((option) => Number(option.value));
                                      setDraft((current) => ({
                                        ...current,
                                        confirmedKnowledgePointIds: values,
                                        suggestedKnowledgePointIds: current.suggestedKnowledgePointIds.filter((id) => !values.includes(id)),
                                        primaryKnowledgePointId: values.includes(current.primaryKnowledgePointId || -1)
                                          ? current.primaryKnowledgePointId
                                          : values[0] || null,
                                      }));
                                    }}
                                  >
                                    {scopedKnowledgePoints.map((point) => (
                                        <option key={point.id} value={point.id}>
                                          {point.name}
                                        </option>
                                      ))}
                                  </select>
                                </label>
                                <label className="field">
                                  <span>主考点</span>
                                  <select
                                    value={draft.primaryKnowledgePointId ? String(draft.primaryKnowledgePointId) : ""}
                                    onChange={(event) => setDraft((current) => ({ ...current, primaryKnowledgePointId: Number(event.target.value) || null }))}
                                  >
                                    <option value="">未设置</option>
                                    {draft.confirmedKnowledgePointIds.map((id) => {
                                      const point = scopedKnowledgePoints.find((item) => item.id === id);
                                      return point ? (
                                        <option key={point.id} value={point.id}>
                                          {point.name}
                                        </option>
                                      ) : null;
                                    })}
                                  </select>
                                </label>
                                <label className="field">
                                  <span>候选考点</span>
                                  <select
                                    multiple
                                    value={draft.suggestedKnowledgePointIds.map(String)}
                                    onChange={(event) => {
                                      const values = Array.from(event.target.selectedOptions).map((option) => Number(option.value));
                                      setDraft((current) => ({
                                        ...current,
                                        suggestedKnowledgePointIds: values.filter((id) => !current.confirmedKnowledgePointIds.includes(id)),
                                      }));
                                    }}
                                  >
                                    {scopedKnowledgePoints.map((point) => (
                                      <option key={point.id} value={point.id}>
                                        {point.name}
                                      </option>
                                    ))}
                                  </select>
                                </label>
                                <div className="tagList">
                                  {activeQuestion.confirmed_knowledge_points.map((point) => (
                                    <span key={`confirmed-${point.knowledge_point_id}`}>
                                      已确认: {point.name}{point.relation_type === "primary" ? " · 主考点" : ""}
                                    </span>
                                  ))}
                                  {activeQuestion.suggested_knowledge_points.map((point) => (
                                    <span key={`suggested-${point.knowledge_point_id}`}>
                                      候选: {point.name}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </section>

                    <aside className="paperReviewAside">
                      <div className="paperReviewInsightCard">
                        <div className="paperReviewInsightTop">
                          <strong>质量线索</strong>
                          <Sparkles size={16} aria-hidden />
                        </div>
                        {!!activeQuestion.quality_issues_json?.length ? (
                          <div className="tagList">
                            {activeQuestion.quality_issues_json.map((issue, index) => (
                              <span key={`${issue}-${index}`}>{issue}</span>
                            ))}
                          </div>
                        ) : (
                          <p className="muted">暂无明显结构化风险。</p>
                        )}
                      </div>

                      <div className="paperReviewInsightCard">
                        <div className="paperReviewInsightTop">
                          <strong>AI 补全与标准化</strong>
                          <Wand2 size={16} aria-hidden />
                        </div>
                        <p>{activeQuestion.ai_standardization_note || "尚未执行 AI 标准化。"}</p>
                        <small className="muted">{formatTime(activeQuestion.last_ai_standardized_at)}</small>
                      </div>

                      <div className="paperReviewInsightCard">
                        <div className="paperReviewInsightTop">
                          <strong>答案解析审核</strong>
                          <ShieldCheck size={16} aria-hidden />
                        </div>
                        <p>{activeQuestion.ai_review_note || "尚未执行 AI 审核。"}</p>
                        <small className="muted">{formatTime(activeQuestion.last_ai_reviewed_at)}</small>
                      </div>

                      <div className="paperReviewInsightCard">
                        <div className="paperReviewInsightTop">
                          <strong>切题原文</strong>
                          <Bot size={16} aria-hidden />
                        </div>
                        <div
                          className="paperReviewRawBlock paperPreviewHtml"
                          dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(activeQuestion.source_raw_text) }}
                        />
                      </div>
                    </aside>
                  </div>
                </div>
              </div>
            )}
          </div>
        </article>
      </section>
    </div>
  );
}

function buildDraft(question: PaperReviewQuestionResponse): DraftState {
  const confirmedKnowledgePointIds = question.confirmed_knowledge_points.map((point) => point.knowledge_point_id);
  return {
    questionType: question.question_type,
    stemText: question.stem_text,
    options: [...(question.options_json || [])],
    answerText: question.answer_text || "",
    analysisText: question.analysis_text || "",
    reviewStatus: (question.review_status as DraftState["reviewStatus"]) || "pending",
    reviewNote: question.review_note || "",
    suggestedKnowledgePointIds: question.suggested_knowledge_points.map((point) => point.knowledge_point_id),
    confirmedKnowledgePointIds,
    primaryKnowledgePointId:
      question.confirmed_knowledge_points.find((point) => point.relation_type === "primary")?.knowledge_point_id
      || confirmedKnowledgePointIds[0]
      || null,
  };
}

function summarizeQuestions(questions: PaperReviewQuestionResponse[]): PaperReviewSummaryResponse {
  return questions.reduce<PaperReviewSummaryResponse>(
    (summary, question) => {
      summary.total_questions += 1;
      if (question.review_status === "approved") summary.approved_count += 1;
      else if (question.review_status === "needs_revision") summary.needs_revision_count += 1;
      else if (question.review_status === "rejected") summary.rejected_count += 1;
      else summary.pending_count += 1;

      if (question.ai_review_status === "needs_revision" || question.ai_review_status === "rejected") {
        summary.ai_flagged_count += 1;
      }
      if (question.last_ai_reviewed_at) summary.ai_reviewed_count += 1;
      if (!question.answer_text || !question.analysis_text) summary.missing_solution_count += 1;
      return summary;
    },
    {
      total_questions: 0,
      pending_count: 0,
      approved_count: 0,
      needs_revision_count: 0,
      rejected_count: 0,
      ai_flagged_count: 0,
      ai_reviewed_count: 0,
      missing_solution_count: 0,
    },
  );
}

function reviewStatusLabel(status?: string | null) {
  if (status === "approved") return "人工通过";
  if (status === "needs_revision") return "待修订";
  if (status === "rejected") return "已驳回";
  return "待审核";
}

function reviewTone(status?: string | null) {
  if (status === "approved") return "good" as const;
  if (status === "needs_revision") return "warn" as const;
  if (status === "rejected") return "danger" as const;
  return "info" as const;
}

function aiTone(status?: string | null) {
  if (status === "approved") return "good" as const;
  if (status === "needs_revision") return "warn" as const;
  if (status === "rejected") return "danger" as const;
  return "info" as const;
}

function questionTypeLabel(questionType?: string | null) {
  const labels: Record<string, string> = {
    single_choice: "单选题",
    multiple_choice: "多选题",
    judge: "判断题",
    fill_blank: "填空题",
    short_answer: "简答题",
    calculation: "计算题",
    case_analysis: "案例分析题",
    material_analysis: "材料分析题",
    composite: "综合题",
    mixed: "混合题型",
  };
  return labels[questionType || ""] || questionType || "未识别题型";
}

function formatScore(score?: number | null) {
  if (score == null || Number.isNaN(score)) return "-";
  return Number(score).toFixed(2);
}

function formatRate(summary?: PaperReviewSummaryResponse | null) {
  if (!summary?.total_questions) return "0%";
  return `${Math.round((summary.approved_count / summary.total_questions) * 100)}%`;
}

function formatTime(value?: string | null) {
  if (!value) return "尚无时间记录";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function AutoResizeTextarea({
  minRows = 3,
  value,
  ...props
}: { minRows?: number; value: string } & TextareaHTMLAttributes<HTMLTextAreaElement>) {
  const ref = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    element.style.height = "auto";
    element.style.height = `${element.scrollHeight}px`;
  }, [minRows, value]);

  return <textarea {...props} ref={ref} rows={minRows} value={value} />;
}
