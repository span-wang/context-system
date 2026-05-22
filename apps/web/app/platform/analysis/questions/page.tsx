"use client";

import Link from "next/link";
import { Bot, BrainCircuit, Orbit, ShieldCheck, Sparkles, Wand2 } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type TextareaHTMLAttributes } from "react";

import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { renderDocumentPreviewHtml } from "../../../../lib/document-preview";
import {
  apiFetch,
  KnowledgePointResponse,
  PaperReviewAIActionResponse,
  PaperReviewAIBatchActionResponse,
  PaperReviewAutoTagJobResponse,
  PaperReviewAutoTagResponse,
  PaperReviewBatchReviewResponse,
  PaperReviewQuestionKnowledgePointUpdateRequest,
  PaperReviewQuestionResponse,
  PaperReviewQuestionUpdateRequest,
  PaperReviewSummaryResponse,
  PaperReviewWorkspaceResponse,
  PaperSummary,
  SubjectResponse,
} from "../../../../lib/pro-api";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

type DraftState = {
  nodeRole: "standalone" | "group" | "subquestion";
  questionType: string;
  groupStem: string;
  materialText: string;
  stemText: string;
  options: string[];
  answerText: string;
  analysisText: string;
  reviewStatus: "pending" | "approved" | "needs_revision" | "rejected";
  reviewNote: string;
  suggestedKnowledgePointIds: number[];
  primaryKnowledgePointId: number | null;
};

type BulkReviewState = {
  reviewStatus: "pending" | "approved" | "needs_revision" | "rejected";
  reviewNote: string;
};

const emptyDraft: DraftState = {
  nodeRole: "standalone",
  questionType: "",
  groupStem: "",
  materialText: "",
  stemText: "",
  options: [],
  answerText: "",
  analysisText: "",
  reviewStatus: "pending",
  reviewNote: "",
  suggestedKnowledgePointIds: [],
  primaryKnowledgePointId: null,
};

const emptyBulkReview: BulkReviewState = {
  reviewStatus: "approved",
  reviewNote: "",
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

const JUDGE_OPTION_VALUES = ["正确", "错误"] as const;
const AI_OPTION_PLACEHOLDER = "（待补全选项）";

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
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [workspace, setWorkspace] = useState<PaperReviewWorkspaceResponse | null>(null);
  const [knowledgePoints, setKnowledgePoints] = useState<KnowledgePointResponse[]>([]);
  const [selectedPaperId, setSelectedPaperId] = useState<number | null>(null);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [selectedSubquestionId, setSelectedSubquestionId] = useState<number | null>(null);
  const [selectedQuestionIds, setSelectedQuestionIds] = useState<number[]>([]);
  const [draft, setDraft] = useState<DraftState>(emptyDraft);
  const [bulkReview, setBulkReview] = useState<BulkReviewState>(emptyBulkReview);
  const [loadingPapers, setLoadingPapers] = useState(true);
  const [loadingWorkspace, setLoadingWorkspace] = useState(false);
  const [saving, setSaving] = useState(false);
  const [batchSaving, setBatchSaving] = useState(false);
  const [savingKnowledgePoints, setSavingKnowledgePoints] = useState(false);
  const [autoTagging, setAutoTagging] = useState(false);
  const [autoTaggingQuestionId, setAutoTaggingQuestionId] = useState<number | null>(null);
  const [autoTagProgress, setAutoTagProgress] = useState<PaperReviewAutoTagResponse | null>(null);
  const [standardizingIds, setStandardizingIds] = useState<number[]>([]);
  const [reviewingIds, setReviewingIds] = useState<number[]>([]);
  const [error, setError] = useState("");
  const [workspaceError, setWorkspaceError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [search, setSearch] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("all");
  const [categoryFilter, setCategoryFilter] = useState("all");
  const [reviewFilter, setReviewFilter] = useState<(typeof reviewStatusOptions)[number]["value"]>("all");
  const [aiFilter, setAiFilter] = useState<(typeof aiStatusOptions)[number]["value"]>("all");
  const [sectionFilter, setSectionFilter] = useState("all");

  const subjectNameMap = useMemo(
    () => new Map(subjects.map((subject) => [subject.id, subject.name])),
    [subjects],
  );
  const subjectOptions = useMemo(() => {
    const seen = new Set<number>();
    return papers
      .filter((paper) => {
        if (!paper.subject_id || seen.has(paper.subject_id)) return false;
        seen.add(paper.subject_id);
        return true;
      })
      .map((paper) => ({
        value: String(paper.subject_id),
        label: subjectNameMap.get(paper.subject_id || 0) || `学科 ${paper.subject_id}`,
      }))
      .sort((left, right) => left.label.localeCompare(right.label, "zh-CN"));
  }, [papers, subjectNameMap]);
  const categoryOptions = useMemo(() => {
    const seen = new Set<string>();
    return papers
      .filter((paper) => subjectFilter === "all" || String(paper.subject_id || "") === subjectFilter)
      .map((paper) => (paper.category || "").trim())
      .filter((category) => {
        if (!category || seen.has(category)) return false;
        seen.add(category);
        return true;
      })
      .sort((left, right) => left.localeCompare(right, "zh-CN"));
  }, [papers, subjectFilter]);
  const filteredPapers = useMemo(
    () => papers.filter((paper) => {
      if (subjectFilter !== "all" && String(paper.subject_id || "") !== subjectFilter) return false;
      if (categoryFilter !== "all" && (paper.category || "").trim() !== categoryFilter) return false;
      return true;
    }),
    [categoryFilter, papers, subjectFilter],
  );

  useEffect(() => {
    loadPapers();
  }, []);

  useEffect(() => {
    if (categoryFilter !== "all" && !categoryOptions.includes(categoryFilter)) {
      setCategoryFilter("all");
    }
  }, [categoryFilter, categoryOptions]);

  useEffect(() => {
    if (!filteredPapers.length) {
      if (selectedPaperId !== null) {
        setSelectedPaperId(null);
      }
      return;
    }
    if (selectedPaperId && filteredPapers.some((paper) => paper.id === selectedPaperId)) return;
    const fallbackPaperId = preferredPaperId && filteredPapers.some((paper) => paper.id === preferredPaperId)
      ? preferredPaperId
      : filteredPapers[0]?.id || null;
    setSelectedPaperId(fallbackPaperId);
  }, [filteredPapers, preferredPaperId, selectedPaperId]);

  useEffect(() => {
    if (!selectedPaperId) {
      setWorkspace(null);
      setSelectedQuestionId(null);
      setSelectedSubquestionId(null);
      setSelectedQuestionIds([]);
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
      const aiStatuses = [question.ai_review_status, ...question.subquestions.map((item) => item.ai_review_status)].filter(Boolean);
      if (aiFilter === "pending") {
        if (aiStatuses.length > 0) return false;
      } else if (aiFilter !== "all" && !aiStatuses.includes(aiFilter)) {
        return false;
      }
      if (sectionFilter !== "all" && String(question.section_id || "") !== sectionFilter) return false;
      if (!keyword) return true;
      return [
        question.question_no,
        question.source_section_name,
        question.group_stem || "",
        question.material_text || "",
        question.stem_text,
        question.answer_text || "",
        question.analysis_text || "",
        ...question.subquestions.flatMap((subquestion) => [
          subquestion.question_no,
          subquestion.stem_text,
          subquestion.answer_text || "",
          subquestion.analysis_text || "",
        ]),
      ]
        .join("\n")
        .toLowerCase()
        .includes(keyword);
    });
  }, [aiFilter, reviewFilter, search, sectionFilter, workspace]);

  const activeRootQuestion = useMemo(
    () => workspace?.questions.find((question) => question.id === selectedQuestionId) || null,
    [selectedQuestionId, workspace],
  );
  const activeQuestion = useMemo(() => {
    if (!activeRootQuestion) return null;
    if (!selectedSubquestionId) return activeRootQuestion;
    return activeRootQuestion.subquestions.find((question) => question.id === selectedSubquestionId) || activeRootQuestion;
  }, [activeRootQuestion, selectedSubquestionId]);
  const selectedQuestionIdSet = useMemo(() => new Set(selectedQuestionIds), [selectedQuestionIds]);
  const filteredQuestionIds = useMemo(() => filteredQuestions.map((question) => question.id), [filteredQuestions]);
  const allFilteredSelected = filteredQuestionIds.length > 0
    && filteredQuestionIds.every((questionId) => selectedQuestionIdSet.has(questionId));
  const selectedVisibleCount = filteredQuestionIds.reduce(
    (count, questionId) => count + (selectedQuestionIdSet.has(questionId) ? 1 : 0),
    0,
  );
  const aiBatchBusy = batchSaving || standardizingIds.length > 0 || reviewingIds.length > 0;
  const draftJudgeQuestion = isJudgeQuestionType(draft.questionType);
  const draftOptions = draftJudgeQuestion ? getFixedJudgeOptions() : draft.options;

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
  const scopedKnowledgePointMap = useMemo(
    () => new Map(scopedKnowledgePoints.map((point) => [point.id, point])),
    [scopedKnowledgePoints],
  );
  const draftCandidateKnowledgePointId = useMemo(
    () => draft.suggestedKnowledgePointIds.find((id) => id !== draft.primaryKnowledgePointId) || null,
    [draft.primaryKnowledgePointId, draft.suggestedKnowledgePointIds],
  );
  const draftPrimaryKnowledgePoint = draft.primaryKnowledgePointId
    ? scopedKnowledgePointMap.get(draft.primaryKnowledgePointId) || null
    : null;
  const draftCandidateKnowledgePoint = draftCandidateKnowledgePointId
    ? scopedKnowledgePointMap.get(draftCandidateKnowledgePointId) || null
    : null;
  const currentPrimaryKnowledgePoint = activeQuestion && draft.primaryKnowledgePointId
    ? findQuestionKnowledgePoint(activeQuestion, draft.primaryKnowledgePointId)
    : null;
  const currentCandidateKnowledgePoint = activeQuestion && draftCandidateKnowledgePointId
    ? findQuestionKnowledgePoint(activeQuestion, draftCandidateKnowledgePointId)
    : null;

  useEffect(() => {
    if (!activeQuestion) {
      setDraft(emptyDraft);
      return;
    }
    setDraft(buildDraft(activeQuestion));
  }, [activeQuestion]);

  useEffect(() => {
    if (!activeRootQuestion) {
      setSelectedSubquestionId(null);
      return;
    }
    if (!selectedSubquestionId) return;
    if (!activeRootQuestion.subquestions.some((question) => question.id === selectedSubquestionId)) {
      setSelectedSubquestionId(null);
    }
  }, [activeRootQuestion, selectedSubquestionId]);

  useEffect(() => {
    setSelectedQuestionIds((current) => {
      if (!workspace) {
        return current.length ? [] : current;
      }
      const allowedIds = new Set(workspace.questions.map((question) => question.id));
      const next = current.filter((questionId) => allowedIds.has(questionId));
      return next.length === current.length ? current : next;
    });
  }, [workspace]);

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
      const [nextPapers, nextKnowledgePoints, nextSubjects] = await Promise.all([
        apiFetch<PaperSummary[]>("/api/papers"),
        apiFetch<KnowledgePointResponse[]>("/api/knowledge/points"),
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
      ]);
      if (!paperGate.isCurrent(requestId)) return;
      setPapers(nextPapers);
      setKnowledgePoints(nextKnowledgePoints);
      setSubjects(nextSubjects);
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
      const normalizedWorkspace = normalizeWorkspace(nextWorkspace);
      const nextSelectedQuestion = (
        preferredQuestionId && normalizedWorkspace.questions.some((question) => question.id === preferredQuestionId)
          ? normalizedWorkspace.questions.find((question) => question.id === preferredQuestionId)
          : selectedQuestionId && normalizedWorkspace.questions.some((question) => question.id === selectedQuestionId)
            ? normalizedWorkspace.questions.find((question) => question.id === selectedQuestionId)
            : normalizedWorkspace.questions[0]
      ) || null;
      setWorkspace(normalizedWorkspace);
      setSelectedQuestionId(nextSelectedQuestion?.id || null);
      setSelectedSubquestionId(defaultSubquestionId(nextSelectedQuestion));
      if (sectionFilter !== "all" && !normalizedWorkspace.sections.some((section) => String(section.id) === sectionFilter)) {
        setSectionFilter("all");
      }
    } catch (err) {
      if (!workspaceGate.isCurrent(requestId)) return;
      setWorkspace(null);
      setSelectedQuestionId(null);
      setWorkspaceError(toErrorMessage(err, "加载审核工作台失败"));
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
      await persistActiveQuestionDraft("manual");
      setActionMessage("人工审核已保存。");
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "保存题目失败"));
    } finally {
      setSaving(false);
    }
  }

  async function saveKnowledgePoints() {
    if (!activeQuestion) return;
    if (activeQuestion.node_role === "group") return;
    setSavingKnowledgePoints(true);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const candidateKnowledgePointId = draft.suggestedKnowledgePointIds.find((id) => id !== draft.primaryKnowledgePointId) || null;
      const currentSuggestedPoint = candidateKnowledgePointId
        ? activeQuestion.suggested_knowledge_points.find((point) => point.knowledge_point_id === candidateKnowledgePointId) || null
        : null;
      const payload: PaperReviewQuestionKnowledgePointUpdateRequest = {
        suggested: candidateKnowledgePointId ? [
          {
            knowledge_point_id: candidateKnowledgePointId,
            relation_type: "secondary",
            source: currentSuggestedPoint?.source || "manual",
            confidence: currentSuggestedPoint?.confidence ?? undefined,
            reason: currentSuggestedPoint?.reason || undefined,
            rank: 1,
          },
        ] : [],
        confirmed: draft.primaryKnowledgePointId ? [
          {
            knowledge_point_id: draft.primaryKnowledgePointId,
            relation_type: "primary",
            source: "manual",
            reason: "人工标注",
            rank: 1,
          },
        ] : [],
      };
      const nextQuestion = await apiFetch<PaperReviewQuestionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/knowledge-points`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      replaceQuestion(normalizeReviewQuestion(nextQuestion));
      setActionMessage("考点标注已保存。");
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "保存考点标注失败"));
    } finally {
      setSavingKnowledgePoints(false);
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
    setStandardizingIds([activeQuestion.id]);
    setActionMessage("");
    setWorkspaceError("");
    try {
      await persistActiveQuestionDraft("ai_standardize");
      const result = await apiFetch<PaperReviewAIActionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/ai-standardize`, {
        method: "POST",
      });
      replaceQuestion(normalizeReviewQuestion(result.question));
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 标准化失败"));
    } finally {
      setStandardizingIds([]);
    }
  }

  async function runAiReview() {
    if (!activeQuestion) return;
    setReviewingIds([activeQuestion.id]);
    setActionMessage("");
    setWorkspaceError("");
    try {
      await persistActiveQuestionDraft("ai_review");
      const result = await apiFetch<PaperReviewAIActionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}/ai-review`, {
        method: "POST",
      });
      replaceQuestion(normalizeReviewQuestion(result.question));
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 审核失败"));
    } finally {
      setReviewingIds([]);
    }
  }

  async function runSelectedAiStandardize() {
    const targetIds = uniqueQuestionIds(selectedQuestionIds);
    if (!targetIds.length) return;
    setStandardizingIds(targetIds);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<PaperReviewAIBatchActionResponse>(`${paperReviewApiBase}/questions/ai-standardize`, {
        method: "POST",
        body: JSON.stringify({ question_ids: targetIds }),
      });
      replaceQuestions(result.questions.map((question) => normalizeReviewQuestion(question)), activeQuestion?.id || targetIds[0] || null);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 批量标准化失败"));
    } finally {
      setStandardizingIds([]);
    }
  }

  async function runSelectedAiReview() {
    const targetIds = uniqueQuestionIds(selectedQuestionIds);
    if (!targetIds.length) return;
    setReviewingIds(targetIds);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<PaperReviewAIBatchActionResponse>(`${paperReviewApiBase}/questions/ai-review`, {
        method: "POST",
        body: JSON.stringify({ question_ids: targetIds }),
      });
      replaceQuestions(result.questions.map((question) => normalizeReviewQuestion(question)), activeQuestion?.id || targetIds[0] || null);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "AI 批量审核失败"));
    } finally {
      setReviewingIds([]);
    }
  }

  async function saveSelectedReviewStatus() {
    const targetIds = uniqueQuestionIds(selectedQuestionIds);
    if (!targetIds.length) return;
    setBatchSaving(true);
    setActionMessage("");
    setWorkspaceError("");
    try {
      const result = await apiFetch<PaperReviewBatchReviewResponse>(`${paperReviewApiBase}/questions/batch-review`, {
        method: "POST",
        body: JSON.stringify({
          question_ids: targetIds,
          review_status: bulkReview.reviewStatus,
          review_note: bulkReview.reviewNote.trim() || null,
        }),
      });
      replaceQuestions(result.questions.map((question) => normalizeReviewQuestion(question)), activeRootQuestion?.id || targetIds[0] || null);
      setActionMessage(result.message);
    } catch (err) {
      setWorkspaceError(toErrorMessage(err, "批量保存人工审核失败"));
    } finally {
      setBatchSaving(false);
    }
  }

  async function persistActiveQuestionDraft(mode: "manual" | "ai_standardize" | "ai_review") {
    if (!activeQuestion) {
      throw new Error("请选择一道题目");
    }
    const payload = buildQuestionUpdatePayload(draft, mode);
    const nextQuestion = await apiFetch<PaperReviewQuestionResponse>(`${paperReviewApiBase}/questions/${activeQuestion.id}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    const normalizedQuestion = normalizeReviewQuestion(nextQuestion);
    replaceQuestion(normalizedQuestion);
    return normalizedQuestion;
  }

  function replaceQuestion(nextQuestion: PaperReviewQuestionResponse) {
    replaceQuestions([nextQuestion], nextQuestion.id);
  }

  function replaceQuestions(nextQuestions: PaperReviewQuestionResponse[], preferredQuestionId?: number | null) {
    if (!nextQuestions.length) return;
    const nextQuestionMap = new Map(nextQuestions.map((question) => [question.id, question]));
    const nextQuestionIdSet = new Set(nextQuestionMap.keys());
    setWorkspace((current) => {
      if (!current) return current;
      const mergedQuestions = current.questions.map((question) => mergeNestedQuestion(question, nextQuestionMap));
      return {
        ...current,
        paper: {
          ...current.paper,
          question_review_count: mergedQuestions.length,
        },
        summary: summarizeQuestions(mergedQuestions),
        questions: mergedQuestions,
      };
    });
    setSelectedQuestionId((current) => {
      if (current != null) {
        return current;
      }
      return nextQuestions[0]?.id || null;
    });
    setSelectedSubquestionId((current) => {
      if (current && nextQuestionIdSet.has(current)) {
        return current;
      }
      return current;
    });
  }

  function toggleQuestionSelection(questionId: number) {
    setSelectedQuestionIds((current) => (
      current.includes(questionId)
        ? current.filter((item) => item !== questionId)
        : [...current, questionId]
    ));
  }

  function selectFilteredQuestions() {
    if (!filteredQuestionIds.length) return;
    setSelectedQuestionIds((current) => uniqueQuestionIds([...current, ...filteredQuestionIds]));
  }

  function clearQuestionSelection() {
    setSelectedQuestionIds([]);
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
            <h1 className="paperReviewHeroTitle">题目审核工作台</h1>
            <p className="paperReviewHeroCaption">
              {workspace?.paper
                ? `${workspace.paper.paper_name} · ${workspace.paper.question_review_count} 个父题/题组 · ${workspace.paper.leaf_question_count} 个小问 · ${workspace.summary.pending_count} 个待审父题/题组`
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
            <label className="field">
              <span>学科</span>
              <select
                value={subjectFilter}
                onChange={(event) => {
                  setSubjectFilter(event.target.value);
                  setCategoryFilter("all");
                  setActionMessage("");
                }}
                disabled={loadingPapers || !subjectOptions.length}
              >
                <option value="all">全部学科</option>
                {subjectOptions.map((subject) => (
                  <option key={subject.value} value={subject.value}>
                    {subject.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>类目</span>
              <select
                value={categoryFilter}
                onChange={(event) => {
                  setCategoryFilter(event.target.value);
                  setActionMessage("");
                }}
                disabled={loadingPapers || !categoryOptions.length}
              >
                <option value="all">全部类目</option>
                {categoryOptions.map((category) => (
                  <option key={category} value={category}>
                    {category}
                  </option>
                ))}
              </select>
            </label>
            <label className="field questionPaperField">
              <span>试卷</span>
              <select
                value={selectedPaperId ? String(selectedPaperId) : ""}
                onChange={(event) => {
                  setSelectedPaperId(Number(event.target.value) || null);
                  setActionMessage("");
                }}
                disabled={loadingPapers || !filteredPapers.length}
              >
                {!filteredPapers.length && <option value="">当前筛选下暂无试卷</option>}
                {filteredPapers.map((paper) => (
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
                {workspace ? <span className="muted">{`已选 ${selectedQuestionIds.length} 题`}</span> : null}
                <button
                  className="button small"
                  type="button"
                  onClick={selectFilteredQuestions}
                  disabled={!filteredQuestionIds.length || allFilteredSelected || aiBatchBusy}
                >
                  全选当前筛选
                </button>
                <button
                  className="button small"
                  type="button"
                  onClick={clearQuestionSelection}
                  disabled={!selectedQuestionIds.length || aiBatchBusy}
                >
                  清空已选
                </button>
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
                <span>待审父题/题组</span>
                <strong>{workspace?.summary.pending_count || 0}</strong>
              </div>
              <div className="questionMiniStat">
                <span>AI 标记风险</span>
                <strong>{workspace?.summary.ai_flagged_count || 0}</strong>
              </div>
                <div className="questionMiniStat">
                <span>缺答案/解析小问</span>
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
                  const active = question.id === activeRootQuestion?.id;
                  const selected = selectedQuestionIdSet.has(question.id);
                  return (
                    <div key={question.id} className="selectableRow questionSelectableRow">
                      <label className="rowCheck" aria-label={`选择第 ${question.question_no || question.sort_order} 题`}>
                        <input
                          type="checkbox"
                          checked={selected}
                          onChange={() => toggleQuestionSelection(question.id)}
                          disabled={aiBatchBusy}
                        />
                      </label>
                      <button
                        className={active ? "listButton questionListButton active paperReviewQueueCard" : "listButton questionListButton paperReviewQueueCard"}
                        type="button"
                        onClick={() => {
                          setSelectedQuestionId(question.id);
                          setSelectedSubquestionId(defaultSubquestionId(question));
                        }}
                      >
                        <div className="questionListContent">
                          <div className="paperReviewQueueTop">
                            <strong className="questionListTitle">
                              {question.node_role === "group"
                                ? `第 ${question.question_no || question.sort_order} 题组`
                                : `第 ${question.question_no || question.sort_order} 题`}
                            </strong>
                            <div className="paperReviewQueueMetaLine">
                              <span className="paperReviewQuestionLabel">{questionTypeLabel(question.question_type)}</span>
                              {question.subquestions.length ? (
                                <StatusBadge value={`${question.subquestions.length} 个小问`} tone="info" />
                              ) : null}
                              <StatusBadge value={reviewStatusLabel(question.review_status)} tone={reviewTone(question.review_status)} />
                              {question.ai_review_status ? (
                                <StatusBadge value={`AI ${reviewStatusLabel(question.ai_review_status)}`} tone={aiTone(question.ai_review_status)} />
                              ) : (
                                <StatusBadge value="AI 未审" tone="info" />
                              )}
                              <StatusBadge value={`质检 ${formatScore(question.quality_score)}`} tone="info" />
                              <StatusBadge
                                value={hasKnowledgePointTag(question) ? "AI 已标记" : "AI 未标记"}
                                tone={hasKnowledgePointTag(question) ? "good" : "warn"}
                              />
                            </div>
                          </div>
                          <span
                            className="questionListNote paperPreviewHtml"
                            dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(questionPreviewText(question)) }}
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
                  {activeRootQuestion && (
                    <p className="questionDetailLead">
                      {`${activeRootQuestion.source_section_name} · 第 ${activeRootQuestion.question_no} ${activeRootQuestion.node_role === "group" ? "题组" : "题"} · ${questionTypeLabel(activeQuestion?.question_type || activeRootQuestion.question_type)}`}
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
                      disabled={savingKnowledgePoints || activeQuestion.node_role === "group"}
                    >
                      <Sparkles size={16} aria-hidden />
                      <span>{activeQuestion.node_role === "group" ? "题组不直接标注考点" : savingKnowledgePoints ? "保存中..." : "保存考点标注"}</span>
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
                      disabled={aiBatchBusy}
                    >
                      <Wand2 size={16} aria-hidden />
                      <span>{standardizingIds.includes(activeQuestion.id) ? "AI 处理中..." : "AI 补全与标准化"}</span>
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={runAiReview}
                      disabled={aiBatchBusy}
                    >
                      <Bot size={16} aria-hidden />
                      <span>{reviewingIds.includes(activeQuestion.id) ? "AI 审核中..." : "AI 答案审核"}</span>
                    </button>
                  </div>
                </div>

                <div className="questionDetailScroll">
                  <div className="questionDetailSection paperReviewDetailGrid">
                    <section className="paperReviewEditorStack">
                      {activeRootQuestion?.node_role === "group" ? (
                        <div className="infoCard">
                          <div className="infoCardTop">
                            <strong>题组材料</strong>
                            <BrainCircuit size={18} aria-hidden />
                          </div>
                          <div className="paperReviewComposeMain">
                            <ReadonlyHtml label="题组导语" value={activeRootQuestion.group_stem || "-"} />
                            <ReadonlyHtml label="共用材料" value={activeRootQuestion.material_text || "-"} />
                            <div className="tagList">
                              <span>{`题组状态：${reviewStatusLabel(activeRootQuestion.review_status)}`}</span>
                              <span>{`小问数：${activeRootQuestion.subquestions.length}`}</span>
                              {selectedSubquestionId ? (
                                <span>{`当前编辑：第 ${activeQuestion.question_no} 题`}</span>
                              ) : (
                                <span>当前编辑：题组父题</span>
                              )}
                            </div>
                            <p className="muted">
                              题组父题主要维护导语和共用材料；题干、选项、答案、解析请切换到下面的小问编辑。
                            </p>
                            <div className="buttonRow">
                              <button className={selectedSubquestionId == null ? "button primary" : "button"} type="button" onClick={() => setSelectedSubquestionId(null)}>
                                编辑题组
                              </button>
                              {activeRootQuestion.subquestions.map((question) => (
                                <button
                                  key={question.id}
                                  className={selectedSubquestionId === question.id ? "button primary" : "button"}
                                  type="button"
                                  onClick={() => setSelectedSubquestionId(question.id)}
                                >
                                  {`第 ${question.question_no} 题`}
                                </button>
                              ))}
                            </div>
                          </div>
                        </div>
                      ) : null}
                      <div className="infoCard">
                        <div className="infoCardTop">
                          <strong>{activeQuestion.node_role === "group" ? "题组信息" : "题干与作答信息"}</strong>
                          <BrainCircuit size={18} aria-hidden />
                        </div>
                        <div className="paperReviewComposeBoard">
                          <div className="paperReviewMetaBar" aria-label="题目元信息">
                            <label className="field paperReviewInlineField">
                              <span>题型</span>
                              <select
                                value={draft.questionType}
                                onChange={(event) => {
                                  const nextQuestionType = event.target.value;
                                  setDraft((current) => ({
                                    ...current,
                                    questionType: nextQuestionType,
                                    options: isJudgeQuestionType(nextQuestionType)
                                      ? getFixedJudgeOptions()
                                      : current.options,
                                  }));
                                }}
                              >
                                {questionTypeOptions.map((option) => (
                                  <option key={option} value={option}>
                                    {questionTypeLabel(option)}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {activeQuestion.node_role !== "group" ? (
                              <label className="field paperReviewInlineField">
                                <span>答案</span>
                                <input
                                  value={draft.answerText}
                                  onChange={(event) => setDraft((current) => ({ ...current, answerText: event.target.value }))}
                                  placeholder="A / AC / 正确"
                                />
                              </label>
                            ) : null}
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
                            {activeQuestion.node_role === "group" ? (
                              <>
                                <label className="field">
                                  <span>题组导语</span>
                                  <AutoResizeTextarea
                                    className="paperReviewAdaptiveTextarea"
                                    minRows={3}
                                    value={draft.groupStem}
                                    onChange={(event) => setDraft((current) => ({ ...current, groupStem: event.target.value }))}
                                  />
                                </label>
                                <label className="field">
                                  <span>共用材料</span>
                                  <AutoResizeTextarea
                                    className="paperReviewAdaptiveTextarea paperReviewStemTextarea"
                                    minRows={8}
                                    value={draft.materialText}
                                    onChange={(event) => setDraft((current) => ({ ...current, materialText: event.target.value }))}
                                  />
                                </label>
                              </>
                            ) : (
                              <>
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
                                    {!draftJudgeQuestion ? (
                                      <button
                                        className="button small"
                                        type="button"
                                        onClick={() => setDraft((current) => ({ ...current, options: [...current.options, ""] }))}
                                      >
                                        新增选项
                                      </button>
                                    ) : null}
                                  </div>
                                  {(draftOptions.length ? draftOptions : [""]).map((option, index) => (
                                    <div key={`option-${index}`} className="paperReviewOptionRow">
                                      <span>{String.fromCharCode(65 + index)}</span>
                                      <input
                                        value={option}
                                        onChange={(event) => {
                                          if (draftJudgeQuestion) return;
                                          const nextOptions = [...draft.options];
                                          nextOptions[index] = event.target.value;
                                          setDraft((current) => ({ ...current, options: nextOptions }));
                                        }}
                                        placeholder={`选项 ${String.fromCharCode(65 + index)}`}
                                        readOnly={draftJudgeQuestion}
                                        disabled={draftJudgeQuestion}
                                      />
                                      {!draftJudgeQuestion ? (
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
                                      ) : null}
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
                              </>
                            )}
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
                          </div>
                        </div>
                      </div>
                    </section>

                    <aside className="paperReviewAside">
                      {activeRootQuestion?.node_role === "group" && activeQuestion.node_role !== "group" ? (
                        <div className="paperReviewInsightCard">
                          <div className="paperReviewInsightTop">
                            <strong>当前子问共用材料</strong>
                            <Bot size={16} aria-hidden />
                          </div>
                          <div className="paperReviewRawBlock paperPreviewHtml" dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(activeRootQuestion.material_text || "-") }} />
                        </div>
                      ) : null}
                      {activeQuestion.node_role !== "group" ? (
                        <div className="paperReviewInsightCard">
                          <div className="paperReviewInsightTop">
                            <strong>考点标注</strong>
                            <Sparkles size={16} aria-hidden />
                          </div>
                          <div className="paperReviewComposeMain">
                            <label className="field">
                              <span>主考点</span>
                              <select
                                value={draft.primaryKnowledgePointId ? String(draft.primaryKnowledgePointId) : ""}
                                onChange={(event) => {
                                  const nextPrimaryId = Number(event.target.value) || null;
                                  setDraft((current) => ({
                                    ...current,
                                    primaryKnowledgePointId: nextPrimaryId,
                                    suggestedKnowledgePointIds: current.suggestedKnowledgePointIds.filter((id) => id !== nextPrimaryId),
                                  }));
                                }}
                              >
                                <option value="">请选择主考点</option>
                                {scopedKnowledgePoints.map((point) => (
                                  <option key={point.id} value={point.id}>
                                    {point.name}
                                  </option>
                                ))}
                              </select>
                            </label>
                            {draftPrimaryKnowledgePoint ? (
                              <div className="paperReviewKnowledgeBadgeRow">
                                <StatusBadge value={draftPrimaryKnowledgePoint.name} tone="good" />
                                <StatusBadge
                                  value={knowledgePointSourceLabel(currentPrimaryKnowledgePoint?.source || "manual")}
                                  tone={knowledgePointSourceTone(currentPrimaryKnowledgePoint?.source || "manual")}
                                />
                                {currentPrimaryKnowledgePoint?.reason ? (
                                  <StatusBadge value={currentPrimaryKnowledgePoint.reason} tone="default" />
                                ) : null}
                              </div>
                            ) : (
                              <p className="muted">当前还没有主考点，可直接从下拉中选择。</p>
                            )}
                            <div className="field">
                              <span>候选考点</span>
                              {draftCandidateKnowledgePoint ? (
                                <div className="paperReviewKnowledgeBadgeRow">
                                  <StatusBadge value={draftCandidateKnowledgePoint.name} tone="info" />
                                  <StatusBadge
                                    value={knowledgePointSourceLabel(currentCandidateKnowledgePoint?.source)}
                                    tone={knowledgePointSourceTone(currentCandidateKnowledgePoint?.source)}
                                  />
                                  {currentCandidateKnowledgePoint?.reason ? (
                                    <StatusBadge value={currentCandidateKnowledgePoint.reason} tone="default" />
                                  ) : null}
                                </div>
                              ) : (
                                <p className="muted">暂无候选考点。</p>
                              )}
                            </div>
                          </div>
                        </div>
                      ) : null}
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

      {!!selectedQuestionIds.length && (
        <div className="questionBulkDock">
          <div className="questionBulkDockMain">
            <div className="questionBulkDockInfo">
              <strong>{`已选 ${selectedQuestionIds.length} 道题`}</strong>
              <span className="muted">
                {selectedVisibleCount === selectedQuestionIds.length
                  ? "可直接批量改人工审核状态，也可继续批量执行 AI 补全与标准化、AI 答案审核。"
                  : `当前筛选结果里可见 ${selectedVisibleCount} 道，其余已选题也会一并执行。`}
              </span>
            </div>
            <div className="questionBulkReviewPanel">
              <label className="field paperReviewInlineField">
                <span>批量状态</span>
                <select
                  value={bulkReview.reviewStatus}
                  onChange={(event) => setBulkReview((current) => ({ ...current, reviewStatus: event.target.value as BulkReviewState["reviewStatus"] }))}
                  disabled={aiBatchBusy}
                >
                  {reviewStatusOptions.filter((option) => option.value !== "all").map((option) => (
                    <option key={option.value} value={option.value}>
                      {option.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field questionBulkReviewNoteField">
                <span>批量备注</span>
                <AutoResizeTextarea
                  className="paperReviewAdaptiveTextarea"
                  minRows={2}
                  value={bulkReview.reviewNote}
                  onChange={(event) => setBulkReview((current) => ({ ...current, reviewNote: event.target.value }))}
                  placeholder="统一写入本次多选审核备注，可留空"
                  disabled={aiBatchBusy}
                />
              </label>
              <button className="button primary" type="button" onClick={saveSelectedReviewStatus} disabled={aiBatchBusy}>
                <ShieldCheck size={16} aria-hidden />
                <span>{batchSaving ? `批量保存中（${selectedQuestionIds.length}题）` : `批量保存人工审核（${selectedQuestionIds.length}题）`}</span>
              </button>
            </div>
          </div>
          <div className="buttonRow questionBulkDockActions">
            <button className="button" type="button" onClick={clearQuestionSelection} disabled={aiBatchBusy}>
              清空选择
            </button>
            <button className="button" type="button" onClick={runSelectedAiStandardize} disabled={aiBatchBusy}>
              <Wand2 size={16} aria-hidden />
              <span>{standardizingIds.length ? `AI 标准化中（${standardizingIds.length}题）` : `AI 补全与标准化（${selectedQuestionIds.length}题）`}</span>
            </button>
            <button className="button primary" type="button" onClick={runSelectedAiReview} disabled={aiBatchBusy}>
              <Bot size={16} aria-hidden />
              <span>{reviewingIds.length ? `AI 审核中（${reviewingIds.length}题）` : `AI 答案审核（${selectedQuestionIds.length}题）`}</span>
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function ReadonlyHtml({ label, value }: { label: string; value: string }) {
  return (
    <div className="field">
      <span>{label}</span>
      <div
        className="paperReviewRawBlock paperPreviewHtml"
        dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(value || "-") }}
      />
    </div>
  );
}

function normalizeReviewQuestion(question: PaperReviewQuestionResponse): PaperReviewQuestionResponse {
  const subquestions = Array.isArray(question.subquestions)
    ? question.subquestions.map((item) => normalizeReviewQuestion(item))
    : [];
  const options = normalizeQuestionOptions(
    question.question_type,
    Array.isArray(question.options_json) ? question.options_json : [],
  );
  return {
    ...question,
    node_role: question.node_role || (subquestions.length ? "group" : "standalone"),
    group_stem: question.group_stem || "",
    material_text: question.material_text || "",
    subquestions,
    suggested_knowledge_points: Array.isArray(question.suggested_knowledge_points) ? question.suggested_knowledge_points : [],
    confirmed_knowledge_points: Array.isArray(question.confirmed_knowledge_points) ? question.confirmed_knowledge_points : [],
    quality_issues_json: Array.isArray(question.quality_issues_json) ? question.quality_issues_json : [],
    options_json: options,
    subquestion_count: typeof question.subquestion_count === "number" ? question.subquestion_count : subquestions.length,
  };
}

function normalizeWorkspace(workspace: PaperReviewWorkspaceResponse): PaperReviewWorkspaceResponse {
  const questions = Array.isArray(workspace.questions)
    ? workspace.questions.map((question) => normalizeReviewQuestion(question))
    : [];
  const summary = summarizeQuestions(questions);
  return {
    ...workspace,
    paper: {
      ...workspace.paper,
      leaf_question_count: typeof workspace.paper.leaf_question_count === "number" ? workspace.paper.leaf_question_count : summary.leaf_question_count,
      group_question_count: typeof workspace.paper.group_question_count === "number" ? workspace.paper.group_question_count : summary.group_question_count,
      question_review_count: typeof workspace.paper.question_review_count === "number" ? workspace.paper.question_review_count : questions.length,
    },
    summary: {
      ...summary,
      ...workspace.summary,
      leaf_question_count: typeof workspace.summary.leaf_question_count === "number" ? workspace.summary.leaf_question_count : summary.leaf_question_count,
      group_question_count: typeof workspace.summary.group_question_count === "number" ? workspace.summary.group_question_count : summary.group_question_count,
    },
    questions,
  };
}

function buildDraft(question: PaperReviewQuestionResponse): DraftState {
  const confirmedPrimaryKnowledgePointId =
    question.confirmed_knowledge_points.find((point) => point.relation_type === "primary")?.knowledge_point_id
    || question.confirmed_knowledge_points[0]?.knowledge_point_id
    || null;
  const suggestedPrimaryKnowledgePointId =
    question.suggested_knowledge_points.find((point) => point.relation_type === "primary")?.knowledge_point_id
    || question.suggested_knowledge_points[0]?.knowledge_point_id
    || null;
  const primaryKnowledgePointId = confirmedPrimaryKnowledgePointId || suggestedPrimaryKnowledgePointId || null;
  return {
    nodeRole: question.node_role,
    questionType: question.question_type,
    groupStem: question.group_stem || "",
    materialText: question.material_text || "",
    stemText: question.stem_text,
    options: normalizeQuestionOptions(question.question_type, [...(question.options_json || [])]),
    answerText: question.answer_text || "",
    analysisText: question.analysis_text || "",
    reviewStatus: (question.review_status as DraftState["reviewStatus"]) || "pending",
    reviewNote: question.review_note || "",
    suggestedKnowledgePointIds: question.suggested_knowledge_points
      .map((point) => point.knowledge_point_id)
      .filter((knowledgePointId) => knowledgePointId !== primaryKnowledgePointId),
    primaryKnowledgePointId,
  };
}

function summarizeQuestions(questions: PaperReviewQuestionResponse[]): PaperReviewSummaryResponse {
  const leafQuestions = questions.flatMap((question) => flattenLeafQuestions(question));
  return questions.reduce<PaperReviewSummaryResponse>(
    (summary, question) => {
      summary.total_questions += 1;
      if (question.node_role === "group") summary.group_question_count += 1;
      if (question.review_status === "approved") summary.approved_count += 1;
      else if (question.review_status === "needs_revision") summary.needs_revision_count += 1;
      else if (question.review_status === "rejected") summary.rejected_count += 1;
      else summary.pending_count += 1;

      if (
        question.ai_review_status === "needs_revision"
        || question.ai_review_status === "rejected"
        || question.subquestions.some((item) => item.ai_review_status === "needs_revision" || item.ai_review_status === "rejected")
      ) {
        summary.ai_flagged_count += 1;
      }
      if (question.last_ai_reviewed_at || question.subquestions.some((item) => item.last_ai_reviewed_at)) summary.ai_reviewed_count += 1;
      return summary;
    },
    {
      total_questions: 0,
      leaf_question_count: leafQuestions.length,
      group_question_count: 0,
      pending_count: 0,
      approved_count: 0,
      needs_revision_count: 0,
      rejected_count: 0,
      ai_flagged_count: 0,
      ai_reviewed_count: 0,
      missing_solution_count: leafQuestions.filter((question) => !question.answer_text || !question.analysis_text).length,
    },
  );
}

function flattenLeafQuestions(question: PaperReviewQuestionResponse): PaperReviewQuestionResponse[] {
  if (!question.subquestions.length) return [question];
  return question.subquestions.flatMap((item) => flattenLeafQuestions(item));
}

function mergeNestedQuestion(
  current: PaperReviewQuestionResponse,
  nextQuestionMap: Map<number, PaperReviewQuestionResponse>,
): PaperReviewQuestionResponse {
  const directReplacement = nextQuestionMap.get(current.id);
  if (directReplacement) {
    return directReplacement;
  }
  if (!current.subquestions.length) {
    return current;
  }
  return {
    ...current,
    subquestions: current.subquestions.map((question) => mergeNestedQuestion(question, nextQuestionMap)),
  };
}

function questionPreviewText(question: PaperReviewQuestionResponse) {
  if (question.node_role === "group") {
    return [question.group_stem || question.stem_text, question.material_text || "", ...question.subquestions.map((item) => `${item.question_no}. ${item.stem_text}`)]
      .filter(Boolean)
      .join("\n");
  }
  return question.stem_text;
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

function isJudgeQuestionType(questionType?: string | null) {
  const trimmed = (questionType || "").trim();
  return trimmed.toLowerCase() === "judge" || trimmed === "判断题";
}

function getFixedJudgeOptions(): string[] {
  return [...JUDGE_OPTION_VALUES];
}

function buildQuestionUpdatePayload(
  draft: DraftState,
  mode: "manual" | "ai_standardize" | "ai_review",
): PaperReviewQuestionUpdateRequest {
  return {
    question_type: draft.questionType.trim(),
    group_stem: draft.nodeRole === "group" ? draft.groupStem : undefined,
    material_text: draft.nodeRole === "group" ? draft.materialText : undefined,
    stem_text: draft.nodeRole === "group" ? undefined : draft.stemText,
    options_json: draft.nodeRole === "group"
      ? undefined
      : mode === "ai_standardize"
        ? prepareQuestionOptionsForAiStandardize(draft.questionType, draft.options)
        : normalizeQuestionOptions(draft.questionType, draft.options),
    answer_text: draft.nodeRole === "group" ? undefined : draft.answerText,
    analysis_text: draft.nodeRole === "group" ? undefined : draft.analysisText,
    review_status: draft.reviewStatus,
    review_note: draft.reviewNote,
  };
}

function defaultSubquestionId(question?: PaperReviewQuestionResponse | null): number | null {
  if (!question || question.node_role !== "group") return null;
  return question.subquestions[0]?.id || null;
}

function prepareQuestionOptionsForAiStandardize(questionType: string | null | undefined, options: string[]): string[] {
  if (isJudgeQuestionType(questionType)) {
    return getFixedJudgeOptions();
  }
  return options.map((option) => {
    const normalizedOption = stripOptionLabel(option);
    return normalizedOption.trim() ? normalizedOption : AI_OPTION_PLACEHOLDER;
  });
}

function normalizeQuestionOptions(questionType: string | null | undefined, options: string[]): string[] {
  if (isJudgeQuestionType(questionType)) {
    return getFixedJudgeOptions();
  }
  return options.map(stripOptionLabel).filter((option) => option.trim());
}

function stripOptionLabel(value: string): string {
  return value.replace(/^\s*[A-Ha-h](?:[.、．)]\s*|\s+(?=[^A-Za-z]))/u, "").trim();
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

function isAiKnowledgePointSource(source?: string | null) {
  return (source || "").trim().toLowerCase().startsWith("ai");
}

function knowledgePointSourceLabel(source?: string | null) {
  const normalized = (source || "").trim().toLowerCase();
  if (!normalized) return "待人工标注";
  if (normalized.startsWith("manual")) return "人工标注";
  if (normalized.startsWith("ai")) return "AI标注";
  if (normalized.startsWith("rule")) return "规则召回";
  return source || "未知来源";
}

function knowledgePointSourceTone(source?: string | null) {
  const normalized = (source || "").trim().toLowerCase();
  if (normalized.startsWith("manual")) return "good" as const;
  if (normalized.startsWith("rule")) return "warn" as const;
  return "info" as const;
}

function findQuestionKnowledgePoint(question: PaperReviewQuestionResponse, knowledgePointId: number) {
  return [...question.confirmed_knowledge_points, ...question.suggested_knowledge_points]
    .find((point) => point.knowledge_point_id === knowledgePointId) || null;
}

function hasKnowledgePointTag(question: PaperReviewQuestionResponse): boolean {
  return (
    [...question.confirmed_knowledge_points, ...question.suggested_knowledge_points]
      .some((point) => isAiKnowledgePointSource(point.source))
    || question.subquestions.some((item) => hasKnowledgePointTag(item))
  );
}

function uniqueQuestionIds(questionIds: number[]) {
  return Array.from(new Set(questionIds.filter((questionId) => Number.isFinite(questionId) && questionId > 0)));
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
