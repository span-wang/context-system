"use client";

import Link from "next/link";
import { CheckCircle2, Download, EyeOff, LibraryBig, RefreshCw, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import { renderDocumentPreviewHtml } from "../../../lib/document-preview";
import {
  apiFetch,
  QuestionBankDeleteResponse,
  apiTextFetch,
  QuestionBankExportPaperOptionResponse,
  QuestionBankExportSolutionMode,
  QuestionBankItemResponse,
  QuestionBankListResponse,
  QuestionBankPaperExportRequest,
  QuestionBankSourceResponse,
  SubjectCategoryResponse,
  SubjectResponse,
} from "../../../lib/pro-api";
import { toErrorMessage, useLatestRequestGate } from "../../../lib/request-guard";

const statusOptions = [
  { value: "", label: "全部状态" },
  { value: "active", label: "已上架" },
  { value: "inactive", label: "已下架" },
  { value: "draft", label: "待完善" },
  { value: "archived", label: "已归档" },
];

const questionTypeOptions = [
  { value: "", label: "全部题型" },
  { value: "single_choice", label: "单选题" },
  { value: "multiple_choice", label: "多选题" },
  { value: "judge", label: "判断题" },
  { value: "fill_blank", label: "填空题" },
  { value: "short_answer", label: "简答题" },
  { value: "calculation", label: "计算题" },
  { value: "case_analysis", label: "案例分析题" },
  { value: "material_analysis", label: "材料分析题" },
  { value: "composite", label: "综合题" },
  { value: "mixed", label: "混合题型" },
];

const exportModeOptions: Array<{ value: QuestionBankExportSolutionMode; label: string }> = [
  { value: "inline", label: "题后紧跟答案解析" },
  { value: "appendix", label: "文末统一答案解析" },
];

export default function QuestionBankPage() {
  const gate = useLatestRequestGate();
  const [questions, setQuestions] = useState<QuestionBankItemResponse[]>([]);
  const [subjects, setSubjects] = useState<SubjectResponse[]>([]);
  const [categories, setCategories] = useState<SubjectCategoryResponse[]>([]);
  const [sources, setSources] = useState<QuestionBankSourceResponse[]>([]);
  const [exportPapers, setExportPapers] = useState<QuestionBankExportPaperOptionResponse[]>([]);
  const [selectedQuestionId, setSelectedQuestionId] = useState<number | null>(null);
  const [selectedExportPaperId, setSelectedExportPaperId] = useState<number | null>(null);
  const [statusCounts, setStatusCounts] = useState<Record<string, number>>({});
  const [total, setTotal] = useState(0);
  const [keyword, setKeyword] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [questionTypeFilter, setQuestionTypeFilter] = useState("");
  const [subjectFilter, setSubjectFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [exportSolutionMode, setExportSolutionMode] = useState<QuestionBankExportSolutionMode>("inline");
  const [loading, setLoading] = useState(true);
  const [loadingSources, setLoadingSources] = useState(false);
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [deletingQuestionId, setDeletingQuestionId] = useState<number | null>(null);
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");
  const [detailError, setDetailError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    void loadInitialData();
  }, []);

  useEffect(() => {
    if (loading && !questions.length && !error) return;
    const timer = window.setTimeout(() => {
      void loadQuestions();
    }, 180);
    return () => window.clearTimeout(timer);
  }, [categoryFilter, keyword, questionTypeFilter, statusFilter, subjectFilter]);

  useEffect(() => {
    if (!selectedQuestionId) {
      setSources([]);
      return;
    }
    void loadSources(selectedQuestionId);
  }, [selectedQuestionId]);

  const activeQuestion = useMemo(
    () => questions.find((question) => question.id === selectedQuestionId) || null,
    [questions, selectedQuestionId],
  );

  const scopedCategories = useMemo(() => {
    if (!subjectFilter) return categories;
    return categories.filter((category) => category.subject_id === Number(subjectFilter));
  }, [categories, subjectFilter]);

  async function loadInitialData() {
    const requestId = gate.begin();
    setLoading(true);
    setError("");
    try {
      const [questionPayload, subjectPayload, categoryPayload, exportPaperPayload] = await Promise.all([
        fetchQuestions(),
        apiFetch<SubjectResponse[]>("/api/knowledge/subjects"),
        apiFetch<SubjectCategoryResponse[]>("/api/knowledge/categories"),
        fetchExportPapers(),
      ]);
      if (!gate.isCurrent(requestId)) return;
      applyQuestionPayload(questionPayload);
      applyExportPaperPayload(exportPaperPayload);
      setSubjects(subjectPayload);
      setCategories(categoryPayload);
    } catch (err) {
      if (!gate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载正式题库失败"));
    } finally {
      if (gate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function loadQuestions() {
    const requestId = gate.begin();
    setLoading(true);
    setError("");
    try {
      const [payload, exportPaperPayload] = await Promise.all([fetchQuestions(), fetchExportPapers()]);
      if (!gate.isCurrent(requestId)) return;
      applyQuestionPayload(payload);
      applyExportPaperPayload(exportPaperPayload);
    } catch (err) {
      if (!gate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载正式题库失败"));
    } finally {
      if (gate.isCurrent(requestId)) setLoading(false);
    }
  }

  async function fetchQuestions() {
    const params = buildQuestionBankFilterParams({
      keyword,
      statusFilter,
      questionTypeFilter,
      subjectFilter,
      categoryFilter,
    });
    params.set("limit", "200");
    return apiFetch<QuestionBankListResponse>(`/api/question-bank/questions?${params.toString()}`);
  }

  async function fetchExportPapers() {
    const params = buildQuestionBankFilterParams({
      keyword,
      statusFilter,
      questionTypeFilter,
      subjectFilter,
      categoryFilter,
    });
    const suffix = params.toString() ? `?${params.toString()}` : "";
    return apiFetch<QuestionBankExportPaperOptionResponse[]>(`/api/question-bank/export/papers${suffix}`);
  }

  function applyQuestionPayload(payload: QuestionBankListResponse) {
    const normalizedItems = (payload.items || []).map((question) => normalizeBankQuestion(question));
    setQuestions(normalizedItems);
    setTotal(payload.total);
    setStatusCounts(payload.status_counts || {});
    setSelectedQuestionId((current) => {
      if (current && normalizedItems.some((question) => question.id === current)) {
        return current;
      }
      return normalizedItems[0]?.id || null;
    });
  }

  function applyExportPaperPayload(payload: QuestionBankExportPaperOptionResponse[]) {
    setExportPapers(payload);
    setSelectedExportPaperId((current) => {
      if (current && payload.some((paper) => paper.paper_id === current)) {
        return current;
      }
      return payload[0]?.paper_id || null;
    });
  }

  async function loadSources(questionId: number) {
    setLoadingSources(true);
    setDetailError("");
    try {
      const payload = await apiFetch<QuestionBankSourceResponse[]>(`/api/question-bank/questions/${questionId}/sources`);
      setSources(payload);
    } catch (err) {
      setDetailError(toErrorMessage(err, "加载来源记录失败"));
    } finally {
      setLoadingSources(false);
    }
  }

  async function updateQuestionStatus(nextStatus: "active" | "inactive") {
    if (!activeQuestion) return;
    setUpdatingStatus(true);
    setMessage("");
    setDetailError("");
    try {
      const nextQuestion = await apiFetch<QuestionBankItemResponse>(
        `/api/question-bank/questions/${activeQuestion.id}/${nextStatus === "active" ? "activate" : "deactivate"}`,
        { method: "POST" },
      );
      const normalizedQuestion = normalizeBankQuestion(nextQuestion);
      setQuestions((current) => current.map((question) => (question.id === normalizedQuestion.id ? normalizedQuestion : question)));
      setMessage(nextStatus === "active" ? "题目已上架。" : "题目已下架。");
      await loadQuestions();
    } catch (err) {
      setDetailError(toErrorMessage(err, "更新题目状态失败"));
    } finally {
      setUpdatingStatus(false);
    }
  }

  async function deleteQuestion() {
    if (!activeQuestion) return;
    const confirmed = window.confirm(
      `确定删除正式题“${stripText(activeQuestion.stem_text) || `正式题 ${activeQuestion.id}`}”吗？会删除该正式题及其来源关联，但不会删除原始审核题。`,
    );
    if (!confirmed) return;

    const deletingId = activeQuestion.id;
    setDeletingQuestionId(deletingId);
    setMessage("");
    setDetailError("");
    setError("");
    try {
      const result = await apiFetch<QuestionBankDeleteResponse>(`/api/question-bank/questions/${deletingId}`, { method: "DELETE" });
      setSources([]);
      await loadQuestions();
      setMessage(`已删除正式题：${result.question_uid}，清理来源关联 ${result.removed_source_link_count} 条。`);
    } catch (err) {
      setDetailError(toErrorMessage(err, "删除正式题失败"));
    } finally {
      setDeletingQuestionId(null);
    }
  }

  async function exportQuestions() {
    if (!selectedExportPaperId) return;
    setExporting(true);
    setMessage("");
    setError("");
    try {
      const payload: QuestionBankPaperExportRequest = {
        paper_id: selectedExportPaperId,
        solution_mode: exportSolutionMode,
        subject_id: subjectFilter ? Number(subjectFilter) : null,
        category_id: categoryFilter ? Number(categoryFilter) : null,
        status: statusFilter ? (statusFilter as QuestionBankPaperExportRequest["status"]) : null,
        question_type: questionTypeFilter || null,
        keyword: keyword.trim() || null,
      };
      const markdown = await apiTextFetch("/api/question-bank/export", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const paper = exportPapers.find((item) => item.paper_id === selectedExportPaperId) || null;
      downloadMarkdown(
        markdown,
        buildExportFilename(paper?.paper_name || `paper-${selectedExportPaperId}`, exportSolutionMode),
      );
      setMessage(`已导出 ${paper?.paper_name || `试卷 ${selectedExportPaperId}`}。`);
    } catch (err) {
      setError(toErrorMessage(err, "导出 Markdown 失败"));
    } finally {
      setExporting(false);
    }
  }

  function resetFilters() {
    setKeyword("");
    setStatusFilter("");
    setQuestionTypeFilter("");
    setSubjectFilter("");
    setCategoryFilter("");
  }

  return (
    <div className="questionPageShell questionBankPageRoot">
      <header className="pageHeader">
        <div>
          <h1>正式题库</h1>
          <p>人工审核通过的题目会自动进入这里，后续章节练习、组卷和答题功能都从这个中间题库取题。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" onClick={() => void loadQuestions()} disabled={loading}>
            <RefreshCw size={16} aria-hidden />
            <span>{loading ? "刷新中..." : "刷新"}</span>
          </button>
          <Link className="button primary" href="/analysis/questions">
            返回题目审核
          </Link>
        </div>
      </header>

      {message ? <div className="calloutBox">{message}</div> : null}

      <section className="dashboardGrid twoCol questionBankStats">
        <article className="panel">
          <div className="panelHeader">
            <h2>
              <LibraryBig size={18} aria-hidden />
              入库概览
            </h2>
            <p>正式题只承接通过审核后的题目，答题功能不直接读取审核工作区。</p>
          </div>
          <div className="panelBody trainingStatsGrid">
            <div className="questionMiniStat">
              <span>正式题总数</span>
              <strong>{total}</strong>
            </div>
            <div className="questionMiniStat">
              <span>已上架</span>
              <strong>{statusCounts.active || 0}</strong>
            </div>
            <div className="questionMiniStat">
              <span>已下架</span>
              <strong>{statusCounts.inactive || 0}</strong>
            </div>
            <div className="questionMiniStat">
              <span>待完善</span>
              <strong>{statusCounts.draft || 0}</strong>
            </div>
          </div>
        </article>

        <article className="panel">
          <div className="panelHeader">
            <h2>
              <Search size={18} aria-hidden />
              筛选
            </h2>
            <p>按学科、类目、题型和状态定位题目。</p>
          </div>
          <div className="panelBody questionBankFilterGrid">
            <input
              className="input"
              value={keyword}
              onChange={(event) => setKeyword(event.target.value)}
              placeholder="搜索题干 / 答案 / 解析"
            />
            <select
              className="input"
              value={subjectFilter}
              onChange={(event) => {
                setSubjectFilter(event.target.value);
                setCategoryFilter("");
              }}
            >
              <option value="">全部学科</option>
              {subjects.map((subject) => (
                <option key={subject.id} value={subject.id}>
                  {subject.name}
                </option>
              ))}
            </select>
            <select className="input" value={categoryFilter} onChange={(event) => setCategoryFilter(event.target.value)}>
              <option value="">全部类目</option>
              {scopedCategories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
            <select className="input" value={questionTypeFilter} onChange={(event) => setQuestionTypeFilter(event.target.value)}>
              {questionTypeOptions.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <select className="input" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              {statusOptions.map((option) => (
                <option key={option.value || "all"} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button className="button" type="button" onClick={resetFilters}>
              重置
            </button>
          </div>
          <div className="panelBody questionBankFilterGrid" style={{ paddingTop: 0 }}>
            <select
              className="input"
              value={selectedExportPaperId ? String(selectedExportPaperId) : ""}
              onChange={(event) => setSelectedExportPaperId(Number(event.target.value) || null)}
              disabled={!exportPapers.length || exporting}
            >
              {!exportPapers.length ? (
                <option value="">当前筛选下暂无可导出试卷</option>
              ) : null}
              {exportPapers.map((paper) => (
                <option key={paper.paper_id} value={paper.paper_id}>
                  {paper.paper_name} · {paper.question_count} 题
                </option>
              ))}
            </select>
            <select
              className="input"
              value={exportSolutionMode}
              onChange={(event) => setExportSolutionMode(event.target.value as QuestionBankExportSolutionMode)}
              disabled={!exportPapers.length || exporting}
            >
              {exportModeOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <button
              className="button primary"
              type="button"
              onClick={() => void exportQuestions()}
              disabled={!selectedExportPaperId || !exportPapers.length || exporting}
            >
              <Download size={16} aria-hidden />
              <span>{exporting ? "导出中..." : "导出 Markdown"}</span>
            </button>
            <div className="muted" style={{ gridColumn: "1 / -1" }}>
              默认按试卷导出，并沿用当前筛选条件；共享题干只保留一次，答案解析支持题后跟随或文末统一附上。
            </div>
          </div>
        </article>
      </section>

      <LoadState loading={loading} error={error} empty={!loading && !questions.length} emptyLabel="暂无正式题，先在题目审核中通过一道题。" />

      {!loading && !error && questions.length ? (
        <section className="dashboardGrid twoCol questionWorkspace questionBankWorkspace">
          <article className="panel questionPanel questionQueuePanel">
            <div className="panelHeader">
              <h2>正式题列表</h2>
              <p>当前筛选命中 {total} 道题。</p>
            </div>
            <div className="panelBody questionQueueBody">
              <div className="questionQueueList">
                {questions.map((question) => {
                  const active = question.id === selectedQuestionId;
                  return (
                    <button
                      key={question.id}
                      type="button"
                      className={active ? "listButton questionListButton active" : "listButton questionListButton"}
                      onClick={() => setSelectedQuestionId(question.id)}
                    >
                      <div className="questionListContent">
                        <div className="trainingSampleCardHead">
                          <strong className="questionListTitle">{stripText(question.node_role === "group" ? (question.group_stem || question.stem_text || question.material_text || "") : question.stem_text) || `正式题 ${question.id}`}</strong>
                          <StatusBadge value={statusLabel(question.status)} tone={statusTone(question.status)} />
                        </div>
                        <span className="questionListMeta">
                          {question.subject_name || "未绑定学科"} · {question.category_name || "未分类"} · {questionTypeLabel(question.question_type)}{question.subquestions.length ? ` · ${question.subquestions.length} 个小问` : ""}
                        </span>
                        <span className="questionListNote">
                          来源 {question.source_count} · {question.first_source_paper_name || "暂无来源试卷"} · {formatTime(question.updated_at)}
                        </span>
                      </div>
                    </button>
                  );
                })}
              </div>
            </div>
          </article>

          <article className="panel questionPanel questionDetailPanel">
            <div className="panelHeader panelHeaderActions">
              <div>
                <h2>{activeQuestion ? `正式题 #${activeQuestion.id}` : "题目详情"}</h2>
                <p>{activeQuestion ? `${questionTypeLabel(activeQuestion.question_type)} · ${activeQuestion.question_uid}` : "选择左侧题目查看详情。"}</p>
              </div>
              {activeQuestion ? (
                <div className="buttonRow">
                  <button
                    className="button danger"
                    type="button"
                    disabled={deletingQuestionId === activeQuestion.id || updatingStatus}
                    onClick={() => void deleteQuestion()}
                  >
                    <Trash2 size={16} aria-hidden />
                    <span>{deletingQuestionId === activeQuestion.id ? "删除中..." : "删除"}</span>
                  </button>
                  {activeQuestion.status === "active" ? (
                    <button className="button" type="button" disabled={updatingStatus} onClick={() => updateQuestionStatus("inactive")}>
                      <EyeOff size={16} aria-hidden />
                      <span>{updatingStatus ? "处理中..." : "下架"}</span>
                    </button>
                  ) : (
                    <button className="button primary" type="button" disabled={updatingStatus} onClick={() => updateQuestionStatus("active")}>
                      <CheckCircle2 size={16} aria-hidden />
                      <span>{updatingStatus ? "处理中..." : "上架"}</span>
                    </button>
                  )}
                </div>
              ) : null}
            </div>

            <div className="panelBody questionDetailBody">
              {detailError ? <div className="errorPanel">{detailError}</div> : null}
              {activeQuestion ? (
                <div className="questionBankDetailGrid">
                  <section className="paperReviewEditorStack">
                    <div className="infoCard">
                      <div className="infoCardTop">
                        <strong>题目内容</strong>
                        <StatusBadge value={statusLabel(activeQuestion.status)} tone={statusTone(activeQuestion.status)} />
                      </div>
                      <div className="paperReviewComposeMain">
                        {activeQuestion.node_role === "group" ? (
                          <>
                            <ReadonlyHtml label="题组导语" value={activeQuestion.group_stem || activeQuestion.stem_text || "-"} />
                            <ReadonlyHtml label="共用材料" value={activeQuestion.material_text || "-"} />
                            <div className="trainingField trainingFieldFull">
                              <span>子问列表</span>
                              <div className="stackList">
                                {activeQuestion.subquestions.map((question) => (
                                  <div key={question.id} className="paperReviewInsightCard">
                                    <div className="paperReviewInsightTop">
                                      <strong>{`第 ${question.question_no} 题 · ${questionTypeLabel(question.question_type)}`}</strong>
                                    </div>
                                    <div className="stackList">
                                      <ReadonlyHtml label="题干" value={question.stem_text} />
                                      <div className="trainingField trainingFieldFull">
                                        <span>选项</span>
                                        <div className="trainingOptionList">
                                          {(question.options_json || []).length ? (
                                            (question.options_json || []).map((option, index) => (
                                              <div
                                                key={`${question.id}-option-${index}`}
                                                className="trainingFieldValue trainingFieldValueMultiline paperPreviewHtml"
                                                dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(formatOptionText(option, index)) }}
                                              />
                                            ))
                                          ) : (
                                            <div className="trainingFieldValue">-</div>
                                          )}
                                        </div>
                                      </div>
                                      <ReadonlyHtml label="答案" value={question.answer_text || "-"} />
                                      <ReadonlyHtml label="解析" value={question.analysis_text || "-"} />
                                    </div>
                                  </div>
                                ))}
                              </div>
                            </div>
                          </>
                        ) : (
                          <>
                            <ReadonlyHtml label="题干" value={activeQuestion.stem_text} />
                            <div className="trainingField trainingFieldFull">
                              <span>选项</span>
                              <div className="trainingOptionList">
                                {(activeQuestion.options_json || []).length ? (
                                  (activeQuestion.options_json || []).map((option, index) => (
                                    <div
                                      key={`${activeQuestion.id}-option-${index}`}
                                      className="trainingFieldValue trainingFieldValueMultiline paperPreviewHtml"
                                      dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(formatOptionText(option, index)) }}
                                    />
                                  ))
                                ) : (
                                  <div className="trainingFieldValue">-</div>
                                )}
                              </div>
                            </div>
                            <ReadonlyHtml label="答案" value={activeQuestion.answer_text || "-"} />
                            <ReadonlyHtml label="解析" value={activeQuestion.analysis_text || "-"} />
                          </>
                        )}
                      </div>
                    </div>
                  </section>

                  <aside className="paperReviewAside">
                    <div className="paperReviewInsightCard">
                      <div className="paperReviewInsightTop">
                        <strong>题目元信息</strong>
                      </div>
                      <div className="stackList">
                        <div className="detailRow">
                          <span>学科</span>
                          <strong>{activeQuestion.subject_name || "-"}</strong>
                        </div>
                        <div className="detailRow">
                          <span>类目</span>
                          <strong>{activeQuestion.category_name || "-"}</strong>
                        </div>
                        <div className="detailRow">
                          <span>题型</span>
                          <strong>{questionTypeLabel(activeQuestion.question_type)}</strong>
                        </div>
                        <div className="detailRow">
                          <span>质量分</span>
                          <strong>{formatScore(activeQuestion.quality_score)}</strong>
                        </div>
                        {activeQuestion.subquestions.length ? (
                          <div className="detailRow">
                            <span>子问数</span>
                            <strong>{activeQuestion.subquestions.length}</strong>
                          </div>
                        ) : null}
                      </div>
                    </div>

                    <div className="paperReviewInsightCard">
                      <div className="paperReviewInsightTop">
                        <strong>考点</strong>
                      </div>
                      <div className="tagList">
                        {activeQuestion.knowledge_points.length ? (
                          activeQuestion.knowledge_points.map((point) => (
                            <span key={point.id}>
                              {point.name}{point.relation_type === "primary" ? " · 主考点" : ""}{point.status === "suggested" ? " · 候选" : ""}
                            </span>
                          ))
                        ) : (
                          <span>暂无考点标注</span>
                        )}
                      </div>
                    </div>

                    <div className="paperReviewInsightCard">
                      <div className="paperReviewInsightTop">
                        <strong>来源记录</strong>
                      </div>
                      {loadingSources ? (
                        <p className="muted">来源加载中...</p>
                      ) : (
                        <div className="questionBankSourceList">
                          {sources.map((source) => (
                            <div key={source.id} className="questionBankSourceItem">
                              <strong>{source.paper_name || `来源题 ${source.source_question_id}`}</strong>
                              <span>
                                第 {source.question_no || "-"} 题 · {statusLabel(source.status)} · {formatTime(source.created_at)}
                              </span>
                            </div>
                          ))}
                          {!sources.length ? <p className="muted">暂无来源记录。</p> : null}
                        </div>
                      )}
                    </div>
                  </aside>
                </div>
              ) : (
                <div className="empty compact">请选择一道正式题。</div>
              )}
            </div>
          </article>
        </section>
      ) : null}
    </div>
  );
}

function ReadonlyHtml({ label, value }: { label: string; value: string }) {
  return (
    <div className="trainingField trainingFieldFull">
      <span>{label}</span>
      <div
        className="trainingFieldValue trainingFieldValueMultiline paperPreviewHtml"
        dangerouslySetInnerHTML={{ __html: renderDocumentPreviewHtml(value || "-") }}
      />
    </div>
  );
}

function normalizeBankQuestion(question: QuestionBankItemResponse): QuestionBankItemResponse {
  const subquestions = Array.isArray(question.subquestions)
    ? question.subquestions.map((item) => normalizeBankQuestion(item))
    : [];
  return {
    ...question,
    node_role: question.node_role || (subquestions.length ? "group" : "standalone"),
    group_stem: question.group_stem || "",
    material_text: question.material_text || "",
    options_json: Array.isArray(question.options_json) ? question.options_json.map(stripOptionLabel).filter((option) => option.trim()) : [],
    knowledge_points: Array.isArray(question.knowledge_points) ? question.knowledge_points : [],
    subquestions,
    subquestion_count: typeof question.subquestion_count === "number" ? question.subquestion_count : subquestions.length,
  };
}

function formatOptionText(option: string, index: number): string {
  return `${String.fromCharCode(65 + index)}. ${stripOptionLabel(option)}`;
}

function stripOptionLabel(value: string): string {
  return value.replace(/^\s*[A-Ha-h](?:[.、．)]\s*|\s+(?=[^A-Za-z]))/u, "").trim();
}

function buildQuestionBankFilterParams({
  keyword,
  statusFilter,
  questionTypeFilter,
  subjectFilter,
  categoryFilter,
}: {
  keyword: string;
  statusFilter: string;
  questionTypeFilter: string;
  subjectFilter: string;
  categoryFilter: string;
}) {
  const params = new URLSearchParams();
  if (keyword.trim()) params.set("keyword", keyword.trim());
  if (statusFilter) params.set("status", statusFilter);
  if (questionTypeFilter) params.set("question_type", questionTypeFilter);
  if (subjectFilter) params.set("subject_id", subjectFilter);
  if (categoryFilter) params.set("category_id", categoryFilter);
  return params;
}

function downloadMarkdown(content: string, filename: string) {
  const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

function buildExportFilename(paperName: string, solutionMode: QuestionBankExportSolutionMode) {
  const safeName = paperName.replace(/[\\/:*?"<>|]+/g, "_").trim() || "question-bank-paper";
  return `${safeName}-${solutionMode === "inline" ? "inline" : "appendix"}.md`;
}

function statusLabel(status?: string | null) {
  if (status === "active") return "已上架";
  if (status === "inactive") return "已下架";
  if (status === "draft") return "待完善";
  if (status === "archived") return "已归档";
  return status || "-";
}

function statusTone(status?: string | null) {
  if (status === "active") return "good" as const;
  if (status === "inactive") return "warn" as const;
  if (status === "draft") return "info" as const;
  if (status === "archived") return "default" as const;
  return "default" as const;
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

function stripText(value: string) {
  const text = value.replace(/<[^>]+>/g, " ").replace(/\s+/g, " ").trim();
  return text.length > 90 ? `${text.slice(0, 90)}...` : text;
}

function formatScore(score?: number | null) {
  if (score == null || Number.isNaN(score)) return "-";
  return Number(score).toFixed(2);
}

function formatTime(value?: string | null) {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}
