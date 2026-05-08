"use client";

import { useEffect, useRef, useState } from "react";
import {
  apiFetch,
  QuestionAiCompleteResponse,
  QuestionAiKnowledgeReviewResponse,
  QuestionAiProcessResponse,
  QuestionAiReviewResponse,
  QuestionBatchReviewResponse,
  QuestionDetailResponse,
  QuestionKnowledgeReviewResponse,
  PaperSummary,
  QuestionRetagResponse,
  QuestionSummary,
  SubjectCategoryResponse,
  SubjectResponse,
} from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { allRejected, firstRejectedReason, summarizeRejectedRequests, toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

type ReviewStatusFilter = "all" | "pending" | "approved" | "rejected" | "needs_revision";
type QuestionTypeFilter =
  | "all"
  | "single_choice"
  | "multiple_choice"
  | "judge"
  | "fill_blank"
  | "short_answer"
  | "calculation"
  | "case_analysis"
  | "material_analysis"
  | "composite";
type DetailTab = "content" | "analysis" | "knowledge";

const pageSummary =
  "当前页面已升级为“原始题复核 + 候选考点审核”的第一版工作台，支持题目批量复核、候选考点确认与主次考点人工收口。";

export default function QuestionsPage() {
  const [paperIdFilter, setPaperIdFilter] = useState<number | null>(null);
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [categories, setCategories] = useState<SubjectCategoryResponse[]>([]);
  const [papers, setPapers] = useState<PaperSummary[]>([]);
  const [subjectIdFilter, setSubjectIdFilter] = useState<number | null>(null);
  const [categoryIdFilter, setCategoryIdFilter] = useState<number | null>(null);
  const [yearFilter, setYearFilter] = useState<number | null>(null);
  const [questions, setQuestions] = useState<QuestionSummary[]>([]);
  const [selected, setSelected] = useState<QuestionDetailResponse | null>(null);
  const [detailTab, setDetailTab] = useState<DetailTab>("content");
  const [keyword, setKeyword] = useState("");
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedLinkIds, setSelectedLinkIds] = useState<number[]>([]);
  const [primaryLinkId, setPrimaryLinkId] = useState<number | null>(null);
  const [reviewStatusFilter, setReviewStatusFilter] = useState<ReviewStatusFilter>("all");
  const [questionTypeFilter, setQuestionTypeFilter] = useState<QuestionTypeFilter>("all");
  const [reviewNote, setReviewNote] = useState("");
  const [aiConcurrency, setAiConcurrency] = useState("3");
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(false);
  const [aiCompleting, setAiCompleting] = useState(false);
  const [aiCompletingIds, setAiCompletingIds] = useState<number[]>([]);
  const [aiReviewing, setAiReviewing] = useState(false);
  const [aiReviewingIds, setAiReviewingIds] = useState<number[]>([]);
  const [aiProcessing, setAiProcessing] = useState(false);
  const [aiProcessingIds, setAiProcessingIds] = useState<number[]>([]);
  const [knowledgeReviewing, setKnowledgeReviewing] = useState(false);
  const [aiKnowledgeReviewing, setAiKnowledgeReviewing] = useState(false);
  const [retagging, setRetagging] = useState(false);
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [aiActionMessage, setAiActionMessage] = useState("");
  const [knowledgeActionMessage, setKnowledgeActionMessage] = useState("");
  const pageRequestGate = useLatestRequestGate();
  const detailRequestIdRef = useRef(0);

  function applySelectedDetail(detail: QuestionDetailResponse | null) {
    setSelected(detail);
    setKnowledgeActionMessage("");
    if (!detail) {
      setDetailTab("content");
      setSelectedLinkIds([]);
      setPrimaryLinkId(null);
      return;
    }
    const pendingLinks = detail.links.filter((link) => link.review_status === "pending");
    const approvedPrimary = detail.links.find((link) => link.review_status === "approved" && link.is_primary);
    setSelectedLinkIds(pendingLinks.map((link) => link.id));
    setPrimaryLinkId(approvedPrimary?.id || pendingLinks.find((link) => link.is_primary)?.id || pendingLinks[0]?.id || null);
  }

  async function loadQuestionDetail(questionId: number, fallback: string) {
    const requestId = detailRequestIdRef.current + 1;
    detailRequestIdRef.current = requestId;
    try {
      const detail = await apiFetch<QuestionDetailResponse>(`/api/questions/${questionId}`);
      if (detailRequestIdRef.current !== requestId) return null;
      applySelectedDetail(detail);
      return detail;
    } catch (err) {
      if (detailRequestIdRef.current !== requestId) return null;
      setError(toErrorMessage(err, fallback));
      return null;
    }
  }

  async function loadPage(preferredQuestionId?: number) {
    const requestId = pageRequestGate.begin();
    setLoading(true);
    setError("");
    setLoadWarning("");
    try {
      const [nextQuestions, nextSubjects, nextCategories, nextPapers] = await Promise.allSettled([
        loadQuestions({
          reviewStatus: reviewStatusFilter,
          questionType: questionTypeFilter,
          paperId: paperIdFilter,
          subjectId: subjectIdFilter,
          categoryId: categoryIdFilter,
          year: yearFilter,
        }),
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        apiFetch<PaperSummary[]>("/api/papers"),
      ]);
      if (!pageRequestGate.isCurrent(requestId)) return;
      const results = [nextQuestions, nextSubjects, nextCategories, nextPapers];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No question page requests succeeded.");
      }

      const next = nextQuestions.status === "fulfilled" ? nextQuestions.value : [];
      const nextSubjectList = nextSubjects.status === "fulfilled" ? nextSubjects.value : [];
      const nextCategoryList = nextCategories.status === "fulfilled" ? nextCategories.value : [];
      const nextPaperList = nextPapers.status === "fulfilled" ? nextPapers.value : [];

      setQuestions(next);
      setSubjects(nextSubjectList);
      setCategories(nextCategoryList);
      setPapers(nextPaperList);
      setSelectedIds((current) => current.filter((id) => next.some((item) => item.id === id)));
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "题目列表", result: nextQuestions },
          { label: "学科列表", result: nextSubjects },
          { label: "类目列表", result: nextCategories },
          { label: "试卷列表", result: nextPapers },
        ]),
      );

      const nextId =
        preferredQuestionId && next.some((item) => item.id === preferredQuestionId)
          ? preferredQuestionId
          : selected?.id && next.some((item) => item.id === selected.id)
            ? selected.id
            : next[0]?.id;

      if (!nextId) {
        applySelectedDetail(null);
        return;
      }

      await loadQuestionDetail(nextId, "加载题目详情失败");
    } catch (err) {
      if (!pageRequestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载题目失败"));
    } finally {
      if (pageRequestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    if (typeof window === "undefined") return;
    const nextPaperId = Number(new URLSearchParams(window.location.search).get("paper_id") || 0) || null;
    setPaperIdFilter(nextPaperId);
  }, []);

  useEffect(() => {
    loadPage();
  }, [reviewStatusFilter, questionTypeFilter, paperIdFilter, subjectIdFilter, categoryIdFilter, yearFilter]);

  useEffect(() => {
    if (subjectIdFilter === null) {
      setCategoryIdFilter((current) => {
        if (current === null) return current;
        return categories.some((item) => item.id === current) ? current : null;
      });
      return;
    }
    setCategoryIdFilter((current) => {
      if (current === null) return current;
      return categories.some((item) => item.id === current && item.subject_id === subjectIdFilter) ? current : null;
    });
  }, [subjectIdFilter, categories]);

  useEffect(() => {
    setPaperIdFilter((current) => {
      if (current === null) return current;
      return papers.some((paper) => {
        if (paper.id !== current) return false;
        if (subjectIdFilter !== null && paper.subject_id !== subjectIdFilter) return false;
        if (categoryIdFilter !== null && paper.category_id !== categoryIdFilter) return false;
        if (yearFilter !== null && paper.exam_year !== yearFilter) return false;
        return true;
      })
        ? current
        : null;
    });
  }, [papers, subjectIdFilter, categoryIdFilter, yearFilter]);

  async function refreshQuestions(preferredQuestionId?: number) {
    await loadPage(preferredQuestionId);
  }

  async function pickQuestion(id: number) {
    setError("");
    await loadQuestionDetail(id, "加载题目详情失败");
  }

  function toggleQuestion(id: number) {
    setSelectedIds((current) => (current.includes(id) ? current.filter((item) => item !== id) : [...current, id]));
  }

  function toggleAllCurrent() {
    if (!visibleQuestions.length) return;
    const visibleIds = visibleQuestions.map((item) => item.id);
    const allSelected = visibleIds.every((id) => selectedIds.includes(id));
    setSelectedIds(allSelected ? selectedIds.filter((id) => !visibleIds.includes(id)) : Array.from(new Set([...selectedIds, ...visibleIds])));
  }

  async function batchReview(reviewStatus: Exclude<ReviewStatusFilter, "all">) {
    if (!selectedIds.length) {
      setError("请先选择需要复核的题目");
      return;
    }
    setReviewing(true);
    setError("");
    setActionMessage("");
    try {
      const result = await apiFetch<QuestionBatchReviewResponse>("/api/questions/batch-review", {
        method: "POST",
        body: JSON.stringify({
          question_ids: selectedIds,
          review_status: reviewStatus,
          review_note: reviewNote.trim() || null,
        }),
      });
      await refreshQuestions(selected?.id && result.question_ids.includes(selected.id) ? selected.id : result.question_ids[0]);
      setActionMessage(
        `已批量更新 ${result.updated_count} 道题为 ${questionReviewLabel(result.review_status)}，通过题目会自动同步到题库中心并保留来源标识。`,
      );
      setReviewNote("");
    } catch (err) {
      setError(toErrorMessage(err, "批量复核失败"));
    } finally {
      setReviewing(false);
    }
  }

  async function aiCompleteQuestions(questionIds: number[]) {
    if (!questionIds.length) {
      setError("请先选择需要 AI 补全的题目");
      return;
    }
    setAiCompleting(true);
    setAiCompletingIds(questionIds);
    setError("");
    setAiActionMessage("");
    try {
      const result = await runConcurrentQuestionAction<QuestionAiCompleteResponse>(
        questionIds,
        parseConcurrency(aiConcurrency),
        async (batchIds) =>
          apiFetch<QuestionAiCompleteResponse>("/api/questions/ai-complete", {
            method: "POST",
            body: JSON.stringify({ question_ids: batchIds }),
          }),
      );
      const preferredId =
        selected?.id && questionIds.includes(selected.id)
          ? selected.id
          : questionIds[0];
      await refreshQuestions(preferredId);
      setAiActionMessage(
        `AI补全完成：更新 ${result.updatedCount} 道，未变更 ${result.unchangedCount} 道`
          + (result.failedCount ? `，失败 ${result.failedCount} 道` : ""),
      );
    } catch (err) {
      setError(toErrorMessage(err, "AI补全失败"));
    } finally {
      setAiCompleting(false);
      setAiCompletingIds([]);
    }
  }

  async function aiReviewQuestions(questionIds: number[]) {
    if (!questionIds.length) {
      setError("请先选择需要 AI 复核的题目");
      return;
    }
    setAiReviewing(true);
    setAiReviewingIds(questionIds);
    setError("");
    setActionMessage("");
    try {
      const result = await runConcurrentQuestionAction<QuestionAiReviewResponse>(
        questionIds,
        parseConcurrency(aiConcurrency),
        async (batchIds) =>
          apiFetch<QuestionAiReviewResponse>("/api/questions/ai-review", {
            method: "POST",
            body: JSON.stringify({ question_ids: batchIds }),
          }),
      );
      const preferredId =
        selected?.id && questionIds.includes(selected.id)
          ? selected.id
          : questionIds[0];
      await refreshQuestions(preferredId);
      setActionMessage(
        `AI复核完成：通过 ${result.approvedCount} 道，待修订 ${result.needsRevisionCount} 道，退回 ${result.rejectedCount} 道`
          + (result.failedCount ? `，失败 ${result.failedCount} 道` : ""),
      );
    } catch (err) {
      setError(toErrorMessage(err, "AI复核失败"));
    } finally {
      setAiReviewing(false);
      setAiReviewingIds([]);
    }
  }

  async function aiProcessQuestions(questionIds: number[]) {
    if (!questionIds.length) {
      setError("请先选择需要 AI 综合处理的题目");
      return;
    }
    setAiProcessing(true);
    setAiProcessingIds(questionIds);
    setError("");
    setAiActionMessage("");
    try {
      const result = await runConcurrentQuestionAction<QuestionAiProcessResponse>(
        questionIds,
        parseConcurrency(aiConcurrency),
        async (batchIds) =>
          apiFetch<QuestionAiProcessResponse>("/api/questions/ai-process", {
            method: "POST",
            body: JSON.stringify({ question_ids: batchIds }),
          }),
      );
      const preferredId =
        selected?.id && questionIds.includes(selected.id)
          ? selected.id
          : questionIds[0];
      await refreshQuestions(preferredId);
      setAiActionMessage(
        `AI综合处理完成：补全更新 ${result.updatedCount} 道，确认考点 ${result.taggedQuestionCount} 道，通过 ${result.approvedCount} 道，待修订 ${result.needsRevisionCount} 道，退回 ${result.rejectedCount} 道`
          + (result.failedCount ? `，失败 ${result.failedCount} 道` : ""),
      );
    } catch (err) {
      setError(toErrorMessage(err, "AI综合处理失败"));
    } finally {
      setAiProcessing(false);
      setAiProcessingIds([]);
    }
  }

  function toggleKnowledgeLink(linkId: number) {
    setSelectedLinkIds((current) => {
      if (current.includes(linkId)) {
        const next = current.filter((item) => item !== linkId);
        if (primaryLinkId === linkId) {
          setPrimaryLinkId(next[0] || null);
        }
        return next;
      }
      return [...current, linkId];
    });
  }

  function setPrimaryLink(linkId: number) {
    setPrimaryLinkId(linkId);
    setSelectedLinkIds((current) => (current.includes(linkId) ? current : [...current, linkId]));
  }

  function toggleAllPendingKnowledgeLinks() {
    if (!selected) return;
    const pendingIds = selected.links.filter((link) => link.review_status === "pending").map((link) => link.id);
    if (!pendingIds.length) return;
    const allSelected = pendingIds.every((id) => selectedLinkIds.includes(id));
    if (allSelected) {
      setSelectedLinkIds((current) => current.filter((id) => !pendingIds.includes(id)));
      if (primaryLinkId && pendingIds.includes(primaryLinkId)) {
        setPrimaryLinkId(null);
      }
      return;
    }
    setSelectedLinkIds((current) => Array.from(new Set([...current, ...pendingIds])));
    if (!primaryLinkId) {
      setPrimaryLinkId(pendingIds[0]);
    }
  }

  async function reviewKnowledgeLinks(reviewStatus: "approved" | "rejected") {
    if (!selected) {
      setError("请先选择题目");
      return;
    }
    if (!selectedLinkIds.length) {
      setError("请先选择需要审核的候选考点");
      return;
    }
    if (reviewStatus === "approved" && !primaryLinkId) {
      setError("请先指定一个主考点");
      return;
    }
    setKnowledgeReviewing(true);
    setError("");
    setKnowledgeActionMessage("");
    try {
      const result = await apiFetch<QuestionKnowledgeReviewResponse>(`/api/questions/${selected.id}/knowledge-links/review`, {
        method: "POST",
        body: JSON.stringify({
          link_ids: selectedLinkIds,
          review_status: reviewStatus,
          primary_link_id: reviewStatus === "approved" ? primaryLinkId : null,
        }),
      });
      await refreshQuestions(selected.id);
      setKnowledgeActionMessage(
        reviewStatus === "approved"
          ? `已确认 ${result.updated_count} 条候选考点，并更新主考点。`
          : `已退回 ${result.updated_count} 条候选考点。`,
      );
    } catch (err) {
      setError(toErrorMessage(err, "候选考点审核失败"));
    } finally {
      setKnowledgeReviewing(false);
    }
  }

  async function aiReviewKnowledgeLinks() {
    if (!selected) {
      setError("请先选择题目");
      return;
    }
    if (!selectedLinkIds.length) {
      setError("请先选择需要 AI 审核的候选考点");
      return;
    }
    setAiKnowledgeReviewing(true);
    setError("");
    setKnowledgeActionMessage("");
    try {
      const result = await apiFetch<QuestionAiKnowledgeReviewResponse>(`/api/questions/${selected.id}/knowledge-links/ai-review`, {
        method: "POST",
        body: JSON.stringify({ link_ids: selectedLinkIds }),
      });
      await refreshQuestions(selected.id);
      setKnowledgeActionMessage(result.message);
    } catch (err) {
      setError(toErrorMessage(err, "AI考点审核失败"));
    } finally {
      setAiKnowledgeReviewing(false);
    }
  }

  async function retagSelectedQuestion() {
    if (!selected) return;
    setRetagging(true);
    setError("");
    setKnowledgeActionMessage("");
    try {
      const result = await apiFetch<QuestionRetagResponse>(`/api/questions/${selected.id}/retag`, {
        method: "POST",
      });
      await refreshQuestions(selected.id);
      setKnowledgeActionMessage(
        `已重新召回候选考点，新增 ${result.created_links} 条，其中 AI 候选 ${result.ai_created_links} 条，当前共 ${result.total_links} 条。`,
      );
    } catch (err) {
      setError(toErrorMessage(err, "重新召回候选考点失败"));
    } finally {
      setRetagging(false);
    }
  }

  const pendingKnowledgeIds = selected?.links.filter((link) => link.review_status === "pending").map((link) => link.id) || [];
  const allPendingKnowledgeSelected =
    pendingKnowledgeIds.length > 0 && pendingKnowledgeIds.every((id) => selectedLinkIds.includes(id));
  const availableCategories = subjectIdFilter === null
    ? categories
    : categories.filter((category) => category.subject_id === subjectIdFilter);
  const availableYearPapers = papers.filter((paper) => {
    if (paperIdFilter !== null && paper.id !== paperIdFilter) return false;
    if (subjectIdFilter !== null && paper.subject_id !== subjectIdFilter) return false;
    if (categoryIdFilter !== null && paper.category_id !== categoryIdFilter) return false;
    return true;
  });
  const availablePapers = papers.filter((paper) => {
    if (subjectIdFilter !== null && paper.subject_id !== subjectIdFilter) return false;
    if (categoryIdFilter !== null && paper.category_id !== categoryIdFilter) return false;
    if (yearFilter !== null && paper.exam_year !== yearFilter) return false;
    return true;
  });
  const availableYears = Array.from(
    new Set(availableYearPapers.map((paper) => paper.exam_year).filter((year): year is number => typeof year === "number")),
  ).sort((left, right) => right - left);
  const normalizedKeyword = keyword.trim().toLowerCase();
  const visibleQuestions = normalizedKeyword
    ? questions.filter((question) => {
        const haystack = `${question.question_no} ${question.stem_text} ${question.question_type} ${question.review_note || ""}`.toLowerCase();
        return haystack.includes(normalizedKeyword);
      })
    : questions;
  const allVisibleSelected = visibleQuestions.length > 0 && visibleQuestions.every((item) => selectedIds.includes(item.id));
  const selectedQuestionIndex = selected ? visibleQuestions.findIndex((item) => item.id === selected.id) : -1;
  const previousQuestionId = selectedQuestionIndex > 0 ? visibleQuestions[selectedQuestionIndex - 1]?.id : null;
  const nextQuestionId =
    selectedQuestionIndex >= 0 && selectedQuestionIndex < visibleQuestions.length - 1
      ? visibleQuestions[selectedQuestionIndex + 1]?.id
      : null;

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>题目中心</h1>
          <p suppressHydrationWarning>{pageSummary}</p>
        </div>
      </header>

      <section className="dashboardGrid twoCol questionWorkspace">
        <div className="panel questionPanel questionQueuePanel">
          <div className="panelHeader">
            <h2>原始题复核队列</h2>
            <p>按学科、类目、年份、试卷、复核状态和题型筛选，批量推进原始题人工确认。</p>
          </div>
          <div className="panelBody questionQueueBody">
            {loadWarning ? <div className="calloutBox">{loadWarning}</div> : null}
            <div className="questionQueueControls stackList">
              <div className="row">
                <label className="field">
                  <span>学科</span>
                  <select
                    value={subjectIdFilter === null ? "" : String(subjectIdFilter)}
                    onChange={(event) => {
                      const nextValue = Number(event.target.value || 0) || null;
                      setSubjectIdFilter(nextValue);
                      setCategoryIdFilter(null);
                    }}
                  >
                    <option value="">全部</option>
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
                    value={categoryIdFilter === null ? "" : String(categoryIdFilter)}
                    onChange={(event) => setCategoryIdFilter(Number(event.target.value || 0) || null)}
                  >
                    <option value="">全部</option>
                    {availableCategories.map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>年份</span>
                  <select value={yearFilter === null ? "" : String(yearFilter)} onChange={(event) => setYearFilter(Number(event.target.value || 0) || null)}>
                    <option value="">全部</option>
                    {availableYears.map((year) => (
                      <option key={year} value={year}>
                        {year}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  <span>试卷</span>
                  <select value={paperIdFilter === null ? "" : String(paperIdFilter)} onChange={(event) => setPaperIdFilter(Number(event.target.value || 0) || null)}>
                    <option value="">全部</option>
                    {availablePapers.map((paper) => (
                      <option key={paper.id} value={paper.id}>
                        {paper.paper_name}
                      </option>
                    ))}
                  </select>
                </label>
              </div>

              <div className="row">
                <label className="field">
                  <span>复核状态</span>
                  <select value={reviewStatusFilter} onChange={(event) => setReviewStatusFilter(event.target.value as ReviewStatusFilter)}>
                    <option value="all">全部</option>
                    <option value="pending">待复核</option>
                    <option value="approved">已通过</option>
                    <option value="rejected">已退回</option>
                    <option value="needs_revision">待修订</option>
                  </select>
                </label>
                <label className="field">
                  <span>题型</span>
                  <select value={questionTypeFilter} onChange={(event) => setQuestionTypeFilter(event.target.value as QuestionTypeFilter)}>
                    <option value="all">全部</option>
                    <option value="single_choice">单选题</option>
                    <option value="multiple_choice">多选题</option>
                    <option value="judge">判断题</option>
                    <option value="fill_blank">填空题</option>
                    <option value="short_answer">简答题</option>
                    <option value="calculation">计算题</option>
                    <option value="case_analysis">案例分析题</option>
                    <option value="material_analysis">材料分析题</option>
                    <option value="composite">综合题</option>
                  </select>
                </label>
              </div>

              <div className="questionQueueStats">
                <div className="questionMiniStat">
                  <span>当前结果</span>
                  <strong>{visibleQuestions.length}</strong>
                </div>
                <div className="questionMiniStat">
                  <span>已选题目</span>
                  <strong>{selectedIds.length}</strong>
                </div>
              </div>

              <label className="field">
                <span>题目搜索</span>
                <input
                  type="search"
                  value={keyword}
                  onChange={(event) => setKeyword(event.target.value)}
                  placeholder="搜索题号、题干关键词、题型或备注"
                />
              </label>

              <div className="questionQueueSecondary">
                <label className="field">
                  <span>复核备注</span>
                  <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} rows={3} placeholder="可选：记录退回原因、修订要求或通过说明" />
                </label>
                <label className="field">
                  <span>AI并发数</span>
                  <input
                    type="number"
                    min="1"
                    max="20"
                    value={aiConcurrency}
                    onChange={(event) => setAiConcurrency(event.target.value)}
                    placeholder="默认 3"
                  />
                </label>
              </div>

              <div className="buttonRow">
                <button className="button" type="button" onClick={toggleAllCurrent} disabled={!visibleQuestions.length}>
                  {allVisibleSelected ? "取消全选当前列表" : "全选当前列表"}
                </button>
                <button className="button primary" type="button" onClick={() => aiProcessQuestions(selectedIds)} disabled={aiProcessing || !selectedIds.length}>
                  {aiProcessing ? "AI综合处理中..." : "批量AI综合处理"}
                </button>
                <button className="button" type="button" onClick={() => aiCompleteQuestions(selectedIds)} disabled={aiCompleting || aiProcessing || !selectedIds.length}>
                  {aiCompleting ? "AI补全中..." : "批量AI补全"}
                </button>
                <button className="button" type="button" onClick={() => aiReviewQuestions(selectedIds)} disabled={aiReviewing || aiProcessing || !selectedIds.length}>
                  {aiReviewing ? "AI复核中..." : "批量AI复核"}
                </button>
                <button className="button primary" type="button" onClick={() => batchReview("approved")} disabled={reviewing || !selectedIds.length}>
                  {reviewing ? "处理中..." : "批量通过"}
                </button>
                <button className="button" type="button" onClick={() => batchReview("needs_revision")} disabled={reviewing || !selectedIds.length}>
                  标记待修订
                </button>
                <button className="button" type="button" onClick={() => batchReview("rejected")} disabled={reviewing || !selectedIds.length}>
                  批量退回
                </button>
              </div>

              {actionMessage ? <div className="calloutBox">{actionMessage}</div> : null}
              {aiActionMessage ? <div className="calloutBox">{aiActionMessage}</div> : null}
            </div>

            <div className="questionQueueListHeader">
              <strong>题目列表</strong>
              <span className="muted">{visibleQuestions.length ? `共 ${visibleQuestions.length} 道，点击切换右侧详情` : "当前筛选下暂无题目"}</span>
            </div>

            <div className="questionQueueList">
              <LoadState loading={loading} error={error} empty={!visibleQuestions.length} emptyLabel="当前筛选条件下暂无题目" />

              {!!visibleQuestions.length && (
                <div className="stackList">
                  {visibleQuestions.map((question) => {
                    const checked = selectedIds.includes(question.id);
                    const active = selected?.id === question.id;
                    return (
                      <div key={question.id} className="selectableRow questionSelectableRow">
                        <label className="rowCheck" aria-label={`选择题目 ${question.question_no}`}>
                          <input
                            type="checkbox"
                            checked={checked}
                            onChange={() => toggleQuestion(question.id)}
                          />
                        </label>
                        <button className={`listButton questionListButton${active ? " active" : ""}`} type="button" onClick={() => pickQuestion(question.id)}>
                          <div className="questionListContent">
                            <strong className="questionListTitle">
                              {question.question_no}. {question.stem_text}
                            </strong>
                            <span className="muted questionListMeta">
                              {questionTypeLabel(question.question_type)} · 难度 {question.difficulty_level || "-"} · {question.score || 0} 分 · {question.parse_status}
                            </span>
                            {question.source_label ? <span className="muted questionListNote">来源：{question.source_label}</span> : null}
                            {question.review_note ? <span className="muted questionListNote">备注：{question.review_note}</span> : null}
                          </div>
                          <div className="questionListBadges">
                            <StatusBadge value={questionReviewLabel(question.review_status)} tone={questionTone(question.review_status)} />
                            {checked ? <span className="badge">已选</span> : null}
                          </div>
                        </button>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>

        <div className="panel questionPanel questionDetailPanel">
          <div className="panelHeader">
            <h2>题目详情与考点审核</h2>
            <p>查看题干、答案、解析和候选考点，并人工指定主考点或退回不合适候选。</p>
          </div>
          <div className="panelBody questionDetailBody">
            <LoadState loading={loading} error={error} empty={!selected} emptyLabel="请选择一道题目" />
            {selected && (
              <>
                <div className="questionDetailSticky">
                  <div className="questionDetailSummary">
                    <div>
                      <strong>第 {selected.question_no} 题</strong>
                      <p className="muted questionDetailLead">{selected.stem_text}</p>
                    </div>
                    <div className="questionDetailSummaryBadges">
                      <StatusBadge value={questionReviewLabel(selected.review_status)} tone={questionTone(selected.review_status)} />
                      <StatusBadge value={questionTypeLabel(selected.question_type)} tone="info" />
                    </div>
                  </div>
                  <div className="questionDetailNav">
                    <button className="button" type="button" onClick={() => previousQuestionId && pickQuestion(previousQuestionId)} disabled={!previousQuestionId}>
                      上一题
                    </button>
                    <span className="muted">{visibleQuestions.length ? `${Math.max(selectedQuestionIndex + 1, 1)} / ${visibleQuestions.length}` : "0 / 0"}</span>
                    <button className="button" type="button" onClick={() => nextQuestionId && pickQuestion(nextQuestionId)} disabled={!nextQuestionId}>
                      下一题
                    </button>
                  </div>
                  <div className="buttonRow">
                    <button
                      className="button primary"
                      type="button"
                      onClick={() => aiProcessQuestions([selected.id])}
                      disabled={aiProcessing}
                    >
                      {aiProcessingIds.includes(selected.id) ? "AI综合处理中..." : "对当前题AI综合处理"}
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={() => aiCompleteQuestions([selected.id])}
                      disabled={aiCompleting || aiProcessing}
                    >
                      {aiCompletingIds.includes(selected.id) ? "AI补全中..." : "对当前题AI补全"}
                    </button>
                    <button
                      className="button"
                      type="button"
                      onClick={() => aiReviewQuestions([selected.id])}
                      disabled={aiReviewing || aiProcessing}
                    >
                      {aiReviewing ? "AI复核中..." : "对当前题AI复核"}
                    </button>
                  </div>
                  <div className="tabs questionDetailTabs" role="tablist" aria-label="题目详情标签">
                    <button className={`tab${detailTab === "content" ? " active" : ""}`} type="button" onClick={() => setDetailTab("content")}>
                      题目内容
                    </button>
                    <button className={`tab${detailTab === "analysis" ? " active" : ""}`} type="button" onClick={() => setDetailTab("analysis")}>
                      答案解析
                    </button>
                    <button className={`tab${detailTab === "knowledge" ? " active" : ""}`} type="button" onClick={() => setDetailTab("knowledge")}>
                      考点审核
                    </button>
                  </div>
                </div>

                <div className="questionDetailScroll">
                  {detailTab === "content" ? (
                    <div className="questionDetailSection">
                      <div className="detailRow">
                        <span>复核备注</span>
                        <strong>{selected.review_note || "-"}</strong>
                      </div>
                      <div className="questionMetaGrid">
                        <div className="questionMetaCard">
                          <span>来源标识</span>
                          <strong>{selected.source_label || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>来源试卷</span>
                          <strong>{selected.paper_name || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>年份 / 地区</span>
                          <strong>{selected.source_year || "-"} / {selected.source_region || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>题型</span>
                          <strong>{questionTypeLabel(selected.question_type)}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>分值 / 难度</span>
                          <strong>{selected.score || 0} 分 · 难度 {selected.difficulty_level || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>页码范围</span>
                          <strong>{selected.source_page_from || "-"} - {selected.source_page_to || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>解析状态</span>
                          <strong>{selected.parse_status}</strong>
                        </div>
                      </div>
                      <div className="questionCard">
                        <strong>
                          {selected.question_no}. {selected.stem_text}
                        </strong>
                        {selected.options_json?.length ? (
                          <ul className="plainList">
                            {selected.options_json.map((option, index) => (
                              <li key={`${selected.id}-${index}`}>{option}</li>
                            ))}
                          </ul>
                        ) : null}
                      </div>
                    </div>
                  ) : null}

                  {detailTab === "analysis" ? (
                    <div className="questionDetailSection">
                      <div className="questionMetaGrid">
                        <div className="questionMetaCard">
                          <span>标准答案</span>
                          <strong>{selected.answer_text || "-"}</strong>
                        </div>
                        <div className="questionMetaCard">
                          <span>质量分</span>
                          <strong>{selected.quality_score || "-"}</strong>
                        </div>
                      </div>
                      <div className="questionCard">
                        <strong>答案与解析</strong>
                        <p>{selected.analysis_text || "暂无解析"}</p>
                      </div>
                    </div>
                  ) : null}

                  {detailTab === "knowledge" ? (
                    <div className="questionDetailSection subsection">
                      <div className="panelHeaderActions">
                        <div>
                          <strong>候选考点审核</strong>
                          <p className="muted" style={{ margin: "6px 0 0" }}>
                            当前共 {selected.links.length} 条映射，其中待审核 {pendingKnowledgeIds.length} 条。
                          </p>
                        </div>
                        <button className="button" type="button" onClick={retagSelectedQuestion} disabled={retagging}>
                          {retagging ? "召回中..." : "重新召回候选"}
                        </button>
                      </div>

                      {knowledgeActionMessage ? <div className="calloutBox">{knowledgeActionMessage}</div> : null}

                      {!selected.links.length ? (
                        <div className="calloutBox">当前题目还没有候选考点，可先执行“重新召回候选”生成规则候选，再继续人工审核。</div>
                      ) : (
                        <>
                          <div className="buttonRow">
                            <button className="button" type="button" onClick={toggleAllPendingKnowledgeLinks} disabled={!pendingKnowledgeIds.length}>
                              {allPendingKnowledgeSelected ? "取消全选待审核候选" : "全选待审核候选"}
                            </button>
                            <button
                              className="button"
                              type="button"
                              onClick={aiReviewKnowledgeLinks}
                              disabled={aiKnowledgeReviewing || !selectedLinkIds.length}
                            >
                              {aiKnowledgeReviewing ? "AI审核中..." : "AI审核候选"}
                            </button>
                            <button
                              className="button primary"
                              type="button"
                              onClick={() => reviewKnowledgeLinks("approved")}
                              disabled={knowledgeReviewing || !selectedLinkIds.length}
                            >
                              {knowledgeReviewing ? "处理中..." : "确认候选考点"}
                            </button>
                            <button
                              className="button"
                              type="button"
                              onClick={() => reviewKnowledgeLinks("rejected")}
                              disabled={knowledgeReviewing || !selectedLinkIds.length}
                            >
                              退回候选
                            </button>
                          </div>

                          <div className="metricTable">
                            {selected.links.map((link) => {
                              const checked = selectedLinkIds.includes(link.id);
                              const canSetPrimary = checked && link.review_status !== "rejected";
                              return (
                                <div
                                  key={link.id}
                                  className="metricRow"
                                  style={{
                                    alignItems: "flex-start",
                                    borderColor: checked ? "#9ecbc6" : undefined,
                                    boxShadow: checked ? "0 0 0 3px rgba(15, 118, 110, 0.08)" : undefined,
                                  }}
                                >
                                  <div style={{ display: "grid", gap: 8, flex: "1 1 auto", minWidth: 0 }}>
                                    <div style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
                                      <input type="checkbox" checked={checked} onChange={() => toggleKnowledgeLink(link.id)} />
                                      <div style={{ minWidth: 0 }}>
                                        <strong>{link.knowledge_point_name || `考点 #${link.knowledge_point_id}`}</strong>
                                        <span className="muted">{link.evidence_text || "暂无证据片段"}</span>
                                      </div>
                                    </div>
                                    <div className="metaLine">
                                      <span>类型：{link.link_type}</span>
                                      <span>来源：{link.tag_source || "-"}</span>
                                      <span>置信度：{link.confidence_score ?? "-"}</span>
                                    </div>
                                    <label className="checkLine" style={{ marginTop: 0 }}>
                                      <input
                                        type="radio"
                                        name="primaryKnowledgeLink"
                                        checked={primaryLinkId === link.id}
                                        disabled={!canSetPrimary}
                                        onChange={() => setPrimaryLink(link.id)}
                                      />
                                      <span>设为主考点</span>
                                    </label>
                                  </div>
                                  <div style={{ display: "grid", gap: 8, justifyItems: "end" }}>
                                    <StatusBadge value={knowledgeReviewLabel(link.review_status)} tone={knowledgeTone(link.review_status)} />
                                    <StatusBadge value={link.is_primary ? "主考点" : "次考点"} tone={link.is_primary ? "good" : "info"} />
                                  </div>
                                </div>
                              );
                            })}
                          </div>
                        </>
                      )}
                    </div>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

async function loadQuestions(
  filters: {
    reviewStatus: ReviewStatusFilter;
    questionType: QuestionTypeFilter;
    paperId?: number | null;
    subjectId?: number | null;
    categoryId?: number | null;
    year?: number | null;
  },
): Promise<QuestionSummary[]> {
  const params = new URLSearchParams();
  if (filters.paperId) {
    params.set("paper_id", String(filters.paperId));
  }
  if (filters.subjectId) {
    params.set("subject_id", String(filters.subjectId));
  }
  if (filters.categoryId) {
    params.set("category_id", String(filters.categoryId));
  }
  if (filters.year) {
    params.set("year", String(filters.year));
  }
  if (filters.reviewStatus !== "all") {
    params.set("review_status", filters.reviewStatus);
  }
  if (filters.questionType !== "all") {
    params.set("question_type", filters.questionType);
  }
  const query = params.toString();
  return apiFetch<QuestionSummary[]>(`/api/questions${query ? `?${query}` : ""}`);
}

function questionReviewLabel(reviewStatus: string): string {
  if (reviewStatus === "approved") return "已通过";
  if (reviewStatus === "rejected") return "已退回";
  if (reviewStatus === "needs_revision") return "待修订";
  return "待复核";
}

function questionTone(reviewStatus: string): "good" | "warn" | "danger" | "info" {
  if (reviewStatus === "approved") return "good";
  if (reviewStatus === "rejected") return "danger";
  if (reviewStatus === "needs_revision") return "info";
  return "warn";
}

function knowledgeReviewLabel(reviewStatus: string): string {
  if (reviewStatus === "approved") return "已确认";
  if (reviewStatus === "rejected") return "已退回";
  return "待审核";
}

function knowledgeTone(reviewStatus: string): "good" | "warn" | "danger" {
  if (reviewStatus === "approved") return "good";
  if (reviewStatus === "rejected") return "danger";
  return "warn";
}

function questionTypeLabel(questionType: string): string {
  if (questionType === "single_choice") return "单选题";
  if (questionType === "multiple_choice") return "多选题";
  if (questionType === "judge") return "判断题";
  if (questionType === "fill_blank") return "填空题";
  if (questionType === "short_answer") return "简答题";
  if (questionType === "calculation") return "计算题";
  if (questionType === "case_analysis") return "案例分析题";
  if (questionType === "material_analysis") return "材料分析题";
  if (questionType === "composite") return "综合题";
  return questionType || "未分类";
}

async function runConcurrentQuestionAction<T>(
  ids: number[],
  concurrency: number,
  runBatch: (batchIds: number[]) => Promise<T>,
): Promise<{
  results: T[];
  updatedCount: number;
  completedCount: number;
  unchangedCount: number;
  failedCount: number;
  approvedCount: number;
  needsRevisionCount: number;
  rejectedCount: number;
  taggedQuestionCount: number;
  createdLinkCount: number;
}> {
  const queue = [...ids];
  const results: T[] = [];
  let updatedCount = 0;
  let completedCount = 0;
  let unchangedCount = 0;
  let failedCount = 0;
  let approvedCount = 0;
  let needsRevisionCount = 0;
  let rejectedCount = 0;
  let taggedQuestionCount = 0;
  let createdLinkCount = 0;

  async function worker() {
    while (queue.length) {
      const nextId = queue.shift();
      if (nextId == null) return;
      const result = await runBatch([nextId]);
      results.push(result);
      const payload = result as Record<string, unknown>;
      updatedCount += Number(payload.updated_count || 0);
      completedCount += Number(payload.completed_count || 0);
      unchangedCount += Number(payload.unchanged_count || 0);
      failedCount += Number(payload.failed_count || 0);
      approvedCount += Number(payload.approved_count || 0);
      needsRevisionCount += Number(payload.needs_revision_count || 0);
      rejectedCount += Number(payload.rejected_count || 0);
      taggedQuestionCount += Number(payload.tagged_question_count || 0);
      createdLinkCount += Number(payload.created_link_count || 0);
    }
  }

  await Promise.all(Array.from({ length: Math.min(concurrency, Math.max(1, ids.length)) }, () => worker()));
  return {
    results,
    updatedCount,
    completedCount,
    unchangedCount,
    failedCount,
    approvedCount,
    needsRevisionCount,
    rejectedCount,
    taggedQuestionCount,
    createdLinkCount,
  };
}

function parseConcurrency(value: string): number {
  const numeric = Number(value || 3);
  if (!Number.isFinite(numeric)) return 3;
  return Math.max(1, Math.min(20, Math.floor(numeric)));
}
