"use client";

import { useEffect, useRef, useState } from "react";
import {
  apiFetch,
  QuestionBatchReviewResponse,
  QuestionDetailResponse,
  QuestionKnowledgeReviewResponse,
  QuestionRetagResponse,
  QuestionSummary,
} from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

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

const pageSummary =
  "当前页面已升级为“原始题复核 + 候选考点审核”的第一版工作台，支持题目批量复核、候选考点确认与主次考点人工收口。";

export default function QuestionsPage() {
  const [questions, setQuestions] = useState<QuestionSummary[]>([]);
  const [selected, setSelected] = useState<QuestionDetailResponse | null>(null);
  const [selectedIds, setSelectedIds] = useState<number[]>([]);
  const [selectedLinkIds, setSelectedLinkIds] = useState<number[]>([]);
  const [primaryLinkId, setPrimaryLinkId] = useState<number | null>(null);
  const [reviewStatusFilter, setReviewStatusFilter] = useState<ReviewStatusFilter>("all");
  const [questionTypeFilter, setQuestionTypeFilter] = useState<QuestionTypeFilter>("all");
  const [reviewNote, setReviewNote] = useState("");
  const [loading, setLoading] = useState(true);
  const [reviewing, setReviewing] = useState(false);
  const [knowledgeReviewing, setKnowledgeReviewing] = useState(false);
  const [retagging, setRetagging] = useState(false);
  const [error, setError] = useState("");
  const [actionMessage, setActionMessage] = useState("");
  const [knowledgeActionMessage, setKnowledgeActionMessage] = useState("");
  const pageRequestGate = useLatestRequestGate();
  const detailRequestIdRef = useRef(0);

  function applySelectedDetail(detail: QuestionDetailResponse | null) {
    setSelected(detail);
    setKnowledgeActionMessage("");
    if (!detail) {
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
    try {
      const next = await loadQuestions(reviewStatusFilter, questionTypeFilter);
      if (!pageRequestGate.isCurrent(requestId)) return;

      setQuestions(next);
      setSelectedIds((current) => current.filter((id) => next.some((item) => item.id === id)));

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
    loadPage();
  }, [reviewStatusFilter, questionTypeFilter]);

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
    if (!questions.length) return;
    const visibleIds = questions.map((item) => item.id);
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
      setActionMessage(`已批量更新 ${result.updated_count} 道题为 ${questionReviewLabel(result.review_status)}`);
      setReviewNote("");
    } catch (err) {
      setError(toErrorMessage(err, "批量复核失败"));
    } finally {
      setReviewing(false);
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
      setKnowledgeActionMessage(`已重新召回候选考点，新增 ${result.created_links} 条，当前共 ${result.total_links} 条。`);
    } catch (err) {
      setError(toErrorMessage(err, "重新召回候选考点失败"));
    } finally {
      setRetagging(false);
    }
  }

  const allVisibleSelected = questions.length > 0 && questions.every((item) => selectedIds.includes(item.id));
  const pendingKnowledgeIds = selected?.links.filter((link) => link.review_status === "pending").map((link) => link.id) || [];
  const allPendingKnowledgeSelected =
    pendingKnowledgeIds.length > 0 && pendingKnowledgeIds.every((id) => selectedLinkIds.includes(id));

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>题目中心</h1>
          <p suppressHydrationWarning>{pageSummary}</p>
        </div>
      </header>

      <section className="dashboardGrid twoCol">
        <div className="panel">
          <div className="panelHeader">
            <h2>原始题复核队列</h2>
            <p>按复核状态和题型筛选，批量推进原始题人工确认。</p>
          </div>
          <div className="panelBody stackList">
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

            <div className="detailRow">
              <span>已选题数</span>
              <strong>{selectedIds.length}</strong>
            </div>

            <label className="field">
              <span>复核备注</span>
              <textarea value={reviewNote} onChange={(event) => setReviewNote(event.target.value)} rows={3} placeholder="可选：记录退回原因、修订要求或通过说明" />
            </label>

            <div className="buttonRow">
              <button className="button" type="button" onClick={toggleAllCurrent} disabled={!questions.length}>
                {allVisibleSelected ? "取消全选当前列表" : "全选当前列表"}
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

            <LoadState loading={loading} error={error} empty={!questions.length} emptyLabel="当前筛选条件下暂无题目" />

            {!!questions.length && (
              <div className="stackList">
                {questions.map((question) => {
                  const checked = selectedIds.includes(question.id);
                  return (
                    <button key={question.id} className="listButton" type="button" onClick={() => pickQuestion(question.id)}>
                      <div style={{ display: "flex", gap: 12, alignItems: "flex-start" }}>
                        <input
                          type="checkbox"
                          checked={checked}
                          onChange={() => toggleQuestion(question.id)}
                          onClick={(event) => event.stopPropagation()}
                        />
                        <div>
                          <strong>
                            {question.question_no}. {question.stem_text}
                          </strong>
                          <span className="muted">
                            {question.question_type} · 难度 {question.difficulty_level || "-"} · {question.score || 0} 分 · {question.parse_status}
                          </span>
                          {question.review_note ? <span className="muted">备注：{question.review_note}</span> : null}
                        </div>
                      </div>
                      <StatusBadge value={questionReviewLabel(question.review_status)} tone={questionTone(question.review_status)} />
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>题目详情与考点审核</h2>
            <p>查看题干、答案、解析和候选考点，并人工指定主考点或退回不合适候选。</p>
          </div>
          <div className="panelBody">
            <LoadState loading={loading} error={error} empty={!selected} emptyLabel="请选择一道题目" />
            {selected && (
              <div className="stackList">
                <div className="detailRow">
                  <span>题目复核</span>
                  <StatusBadge value={questionReviewLabel(selected.review_status)} tone={questionTone(selected.review_status)} />
                </div>
                <div className="detailRow">
                  <span>复核备注</span>
                  <strong>{selected.review_note || "-"}</strong>
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
                  <div className="metaLine">
                    <span>答案：{selected.answer_text || "-"}</span>
                    <span>题型：{selected.question_type}</span>
                  </div>
                  <div className="metaLine">
                    <span>
                      页码：{selected.source_page_from || "-"} - {selected.source_page_to || "-"}
                    </span>
                    <span>质量分：{selected.quality_score || "-"}</span>
                  </div>
                  <p>{selected.analysis_text || "暂无解析"}</p>
                </div>

                <div className="subsection">
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
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}

async function loadQuestions(reviewStatus: ReviewStatusFilter, questionType: QuestionTypeFilter): Promise<QuestionSummary[]> {
  const params = new URLSearchParams();
  if (reviewStatus !== "all") {
    params.set("review_status", reviewStatus);
  }
  if (questionType !== "all") {
    params.set("question_type", questionType);
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
