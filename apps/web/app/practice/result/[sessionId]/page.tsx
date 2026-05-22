"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import {
  apiFetch,
  PracticeAnswerReflectionRequest,
  PracticeDerivedSessionRequest,
  PracticeResultItemResponse,
  PracticeResultResponse,
  PracticeSessionDetailResponse,
} from "../../../../lib/pro-api";
import {
  formatDuration,
  formatPracticeAnswer,
  formatShortDuration,
  modeLabel,
  questionTypeLabel,
  sessionLabel,
} from "../../../../lib/practice";
import { toErrorMessage } from "../../../../lib/request-guard";

type WrongReasonCode =
  | "concept_unclear"
  | "memory_unstable"
  | "misread_question"
  | "calculation_error"
  | "careless"
  | "method_unfamiliar";

type ReviewFilter = "all" | "wrong" | "marked";

type ReflectionDraft = {
  wrong_reason_tags: WrongReasonCode[];
  reflection_note: string;
};

const wrongReasonOptions: Array<{ value: WrongReasonCode; label: string }> = [
  { value: "concept_unclear", label: "概念没吃透" },
  { value: "memory_unstable", label: "记忆不稳定" },
  { value: "misread_question", label: "审题偏了" },
  { value: "calculation_error", label: "计算出错" },
  { value: "careless", label: "粗心失误" },
  { value: "method_unfamiliar", label: "方法不熟" },
];

export default function PracticeResultPage() {
  const params = useParams<{ sessionId: string }>();
  const sessionId = Number(params.sessionId || 0);
  const [result, setResult] = useState<PracticeResultResponse | null>(null);
  const [reflectionDrafts, setReflectionDrafts] = useState<Record<number, ReflectionDraft>>({});
  const [reviewFilter, setReviewFilter] = useState<ReviewFilter>("all");
  const [loading, setLoading] = useState(true);
  const [derivingAction, setDerivingAction] = useState<"" | "retry" | "similar">("");
  const [savingItemId, setSavingItemId] = useState<number | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!sessionId) return;
    void loadResult();
  }, [sessionId]);

  const reviewStats = useMemo(() => {
    if (!result) {
      return { allCount: 0, wrongCount: 0, markedCount: 0 };
    }
    return {
      allCount: result.items.length,
      wrongCount: result.items.filter((item) => item.is_correct === false).length,
      markedCount: result.items.filter((item) => item.marked).length,
    };
  }, [result]);

  const filteredItems = useMemo(() => {
    if (!result) return [];
    if (reviewFilter === "wrong") {
      return result.items.filter((item) => item.is_correct === false);
    }
    if (reviewFilter === "marked") {
      return result.items.filter((item) => item.marked);
    }
    return result.items;
  }, [result, reviewFilter]);

  async function loadResult() {
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetch<PracticeResultResponse>(`/api/learning/sessions/${sessionId}/result`);
      setResult(payload);
      setReflectionDrafts(buildReflectionDrafts(payload.items));
    } catch (err) {
      setError(toErrorMessage(err, "加载结果页失败"));
    } finally {
      setLoading(false);
    }
  }

  async function saveReflection(item: PracticeResultItemResponse) {
    const draft = reflectionDrafts[item.id];
    if (!draft) return;
    setSavingItemId(item.id);
    setError("");
    setMessage("");
    try {
      const payload: PracticeAnswerReflectionRequest = {
        item_id: item.id,
        wrong_reason_tags: draft.wrong_reason_tags,
        reflection_note: draft.reflection_note || null,
      };
      const nextResult = await apiFetch<PracticeResultResponse>(`/api/learning/sessions/${sessionId}/reflection`, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setResult(nextResult);
      setReflectionDrafts(buildReflectionDrafts(nextResult.items));
      setMessage("错因和复盘备注已保存。");
    } catch (err) {
      setError(toErrorMessage(err, "保存错因失败"));
    } finally {
      setSavingItemId(null);
    }
  }

  async function startDerivedPractice(kind: "retry" | "similar") {
    if (!result) return;
    setDerivingAction(kind);
    setError("");
    try {
      const payload: PracticeDerivedSessionRequest = {
        answer_mode: "memorize",
        question_count: kind === "retry" ? Math.min(Math.max(result.retry_wrong_count, 1), 20) : 10,
      };
      const path =
        kind === "retry"
          ? `/api/learning/sessions/${sessionId}/retry-wrong`
          : `/api/learning/sessions/${sessionId}/similar-practice`;
      const nextDetail = await apiFetch<PracticeSessionDetailResponse>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      window.location.href = `/practice/session/${nextDetail.id}`;
    } catch (err) {
      setError(toErrorMessage(err, kind === "retry" ? "创建错题重练失败" : "创建同类题再练失败"));
    } finally {
      setDerivingAction("");
    }
  }

  function toggleReason(itemId: number, reason: WrongReasonCode) {
    setReflectionDrafts((current) => {
      const existing = current[itemId] || { wrong_reason_tags: [], reflection_note: "" };
      const nextTags = existing.wrong_reason_tags.includes(reason)
        ? existing.wrong_reason_tags.filter((item) => item !== reason)
        : [...existing.wrong_reason_tags, reason].slice(0, 4);
      return {
        ...current,
        [itemId]: { ...existing, wrong_reason_tags: nextTags },
      };
    });
  }

  function updateReflectionNote(itemId: number, value: string) {
    setReflectionDrafts((current) => ({
      ...current,
      [itemId]: {
        ...(current[itemId] || { wrong_reason_tags: [], reflection_note: "" }),
        reflection_note: value,
      },
    }));
  }

  return (
    <div className="practiceResultPage">
      <div className="pageHeader">
        <div>
          <h1>{result?.title || "练习结果"}</h1>
          <p>这里集中做练后复盘：看整体结果、标错因、记录备注，再决定是重做错题还是转去做同类题。</p>
        </div>
        <div className="practiceHeaderActions">
          <Link className="button" href={`/practice/session/${sessionId}`}>返回答题页</Link>
          <Link className="button" href="/practice/plan">每日计划</Link>
          <Link className="button" href="/practice">练习首页</Link>
        </div>
      </div>

      <LoadState loading={loading} error={error} />
      {!loading && !error && result && (
        <div className="practiceResultLayout">
          <section className="panel">
            <div className="panelHeader panelHeaderActions">
              <div>
                <h2>结果总览</h2>
                <p>{sessionLabel(result.session_type)} · {modeLabel(result.answer_mode)} · {result.submitted_at ? formatTime(result.submitted_at) : "刚刚交卷"}</p>
              </div>
              <div className="buttonRow">
                <button
                  className="button primary"
                  type="button"
                  disabled={!result.retry_wrong_count || derivingAction !== ""}
                  onClick={() => void startDerivedPractice("retry")}
                >
                  {derivingAction === "retry" ? "正在生成..." : `只重做错题${result.retry_wrong_count ? ` · ${result.retry_wrong_count} 题` : ""}`}
                </button>
                <button
                  className="button"
                  type="button"
                  disabled={!result.similar_practice_available || derivingAction !== ""}
                  onClick={() => void startDerivedPractice("similar")}
                >
                  {derivingAction === "similar" ? "正在生成..." : "同类题再练 10 题"}
                </button>
              </div>
            </div>

            <div className="panelBody practiceResultBody">
              {message && <div className="calloutBox">{message}</div>}
              <div className="statsGrid">
                <StatCard label="正确率" value={`${result.accuracy_rate ?? 0}%`} />
                <StatCard label="正确题数" value={`${result.correct_count}`} />
                <StatCard label="错题数" value={`${result.wrong_count}`} />
                <StatCard label="用时" value={formatDuration(result.duration_seconds)} />
              </div>

              <div className="practiceResultSplit">
                <div className="practiceResultSummaryCard">
                  <strong>练后建议</strong>
                  <div className="practiceSuggestionList">
                    {result.review_suggestions.map((item, index) => (
                      <div key={`${index}-${item}`} className="practiceSuggestionItem">
                        {item}
                      </div>
                    ))}
                  </div>
                </div>

                <div className="practiceResultSummaryCard">
                  <strong>错因分布</strong>
                  {!result.wrong_reason_counts.length && <div className="empty compact">先给错题补上错因标签，这里就会自动汇总。</div>}
                  {!!result.wrong_reason_counts.length && (
                    <div className="practiceReasonCountList">
                      {result.wrong_reason_counts.map((item) => (
                        <div key={item.reason_code} className="practiceReasonCountRow">
                          <span>{item.reason_label}</span>
                          <StatusBadge value={`${item.count} 次`} tone="warn" />
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>

              {!!result.weak_points.length && (
                <div className="practiceResultSummaryCard">
                  <strong>当前薄弱知识点</strong>
                  <div className="practiceWeakPointList">
                    {result.weak_points.map((item) => (
                      <div key={item.knowledge_point_id} className="practiceWeakPointCard">
                        <div>
                          <strong>{item.name}</strong>
                          <span>{item.path}</span>
                        </div>
                        <StatusBadge
                          value={`${item.mastery_score}%`}
                          tone={item.mastery_score >= 80 ? "good" : item.mastery_score >= 60 ? "warn" : "danger"}
                        />
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="practiceResultSummaryCard">
                <div className="practiceReviewToolbar">
                  <strong>逐题复盘</strong>
                  <div className="practiceFilterTabs">
                    <button
                      className={reviewFilter === "all" ? "practiceFilterTab active" : "practiceFilterTab"}
                      type="button"
                      onClick={() => setReviewFilter("all")}
                    >
                      全部 · {reviewStats.allCount}
                    </button>
                    <button
                      className={reviewFilter === "wrong" ? "practiceFilterTab active" : "practiceFilterTab"}
                      type="button"
                      onClick={() => setReviewFilter("wrong")}
                    >
                      错题 · {reviewStats.wrongCount}
                    </button>
                    <button
                      className={reviewFilter === "marked" ? "practiceFilterTab active" : "practiceFilterTab"}
                      type="button"
                      onClick={() => setReviewFilter("marked")}
                    >
                      已标记 · {reviewStats.markedCount}
                    </button>
                  </div>
                </div>

                {!filteredItems.length && <div className="empty compact">当前筛选条件下没有题目。</div>}
                {!!filteredItems.length && (
                  <div className="practiceReviewItemList">
                    {filteredItems.map((item) => {
                      const draft = reflectionDrafts[item.id] || { wrong_reason_tags: [], reflection_note: "" };
                      return (
                        <div key={item.id} className="practiceReviewItemCard">
                          <div className="practiceQuestionMeta">
                            <strong>第 {item.sort_order} 题</strong>
                            <div className="practiceTagRow">
                              <StatusBadge value={reviewResultLabel(item.is_correct)} tone={reviewResultTone(item.is_correct)} />
                              <StatusBadge value={questionTypeLabel(item.question.question_type)} tone="info" />
                              {item.marked && <StatusBadge value="已标记" tone="warn" />}
                              <StatusBadge value={`用时 ${formatShortDuration(item.spent_seconds)}`} />
                            </div>
                          </div>

                          {item.question.source_paper_name && (
                            <div className="practiceTagRow">
                              <StatusBadge value={item.question.source_paper_name} />
                              {item.question.source_question_no && <StatusBadge value={`原题 ${item.question.source_question_no}`} />}
                            </div>
                          )}

                          <div className="practiceQuestionBlock">
                            <strong>题目</strong>
                            <p>{item.question.stem_text}</p>
                          </div>

                          {!!item.question.knowledge_points.length && (
                            <div className="practiceKnowledgeRow">
                              {item.question.knowledge_points.map((point) => (
                                <span key={`${item.id}-${point.id}-${point.relation_type}`} className="chip">
                                  {point.name}
                                </span>
                              ))}
                            </div>
                          )}

                          <div className="practiceResultAnswerGrid">
                            <div className="practiceQuestionBlock">
                              <strong>你的答案</strong>
                              <p>{formatPracticeAnswer(item.question, item.user_answer)}</p>
                            </div>
                            <div className="practiceQuestionBlock">
                              <strong>正确答案</strong>
                              <p>{item.question.answer_text ? formatPracticeAnswer(item.question, item.question.answer_text) : "当前题目暂无标准答案"}</p>
                            </div>
                          </div>

                          <div className="practiceQuestionBlock">
                            <strong>解析</strong>
                            <p>{item.question.analysis_text || "当前题目暂无解析"}</p>
                          </div>

                          {item.is_correct === false && (
                            <div className="practiceReflectionPanel">
                              <div className="practiceReflectionHeader">
                                <strong>错因标签</strong>
                                <span>最多 4 个</span>
                              </div>
                              <div className="practiceReasonTagGrid">
                                {wrongReasonOptions.map((option) => (
                                  <button
                                    key={`${item.id}-${option.value}`}
                                    className={draft.wrong_reason_tags.includes(option.value) ? "practiceReasonTag active" : "practiceReasonTag"}
                                    type="button"
                                    onClick={() => toggleReason(item.id, option.value)}
                                  >
                                    {option.label}
                                  </button>
                                ))}
                              </div>
                              <div className="field">
                                <label>复盘备注</label>
                                <textarea
                                  value={draft.reflection_note}
                                  onChange={(event) => updateReflectionNote(item.id, event.target.value)}
                                  placeholder="这题为什么会错，下次准备怎么避免"
                                />
                              </div>
                              <div className="buttonRow">
                                <button
                                  className="button"
                                  type="button"
                                  disabled={savingItemId === item.id}
                                  onClick={() => void saveReflection(item)}
                                >
                                  {savingItemId === item.id ? "正在保存..." : "保存复盘"}
                                </button>
                              </div>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            </div>
          </section>

          <aside className="panel practiceResultAside">
            <div className="panelHeader">
              <h2>下一步建议</h2>
              <p>做完这套之后，优先把积压复习和错题回炉处理掉。</p>
            </div>
            <div className="panelBody practiceListStack">
              <div className="practiceWrongCard">
                <div>
                  <strong>今日待复习</strong>
                  <span>建议今天优先把到期回顾清掉。</span>
                </div>
                <div className="practiceWrongMeta">
                  <StatusBadge value={`${result.today_review_count} 题`} tone={result.today_review_count ? "warn" : "good"} />
                </div>
              </div>
              <Link className="practiceListCard" href="/practice/plan">
                <div>
                  <strong>查看每日学习计划</strong>
                  <span>把今天该做的任务按优先级排出来。</span>
                </div>
                <div className="practiceListMeta">
                  <StatusBadge value="去查看" tone="info" />
                </div>
              </Link>
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

function buildReflectionDrafts(items: PracticeResultItemResponse[]) {
  return Object.fromEntries(
    items.map((item) => [
      item.id,
      {
        wrong_reason_tags: [...item.wrong_reason_tags],
        reflection_note: item.reflection_note || "",
      },
    ]),
  );
}

function StatCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="statCard">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function formatTime(value: string) {
  try {
    return new Date(value).toLocaleString("zh-CN", { hour12: false });
  } catch {
    return value;
  }
}

function reviewResultLabel(value: boolean | null | undefined) {
  if (value === true) return "正确";
  if (value === false) return "错误";
  return "待判定";
}

function reviewResultTone(value: boolean | null | undefined): "good" | "danger" | "warn" {
  if (value === true) return "good";
  if (value === false) return "danger";
  return "warn";
}
