"use client";

import { useEffect, useState } from "react";
import {
  apiFetch,
  MockExamResponse,
  PracticeSetResponse,
  QuestionBankItemResponse,
  StandardizeQuestionsResponse,
} from "../../../lib/pro-api";
import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../lib/request-guard";

export default function QuestionBankOverviewPage() {
  const [questions, setQuestions] = useState<QuestionBankItemResponse[]>([]);
  const [practiceSets, setPracticeSets] = useState<PracticeSetResponse[]>([]);
  const [mockExams, setMockExams] = useState<MockExamResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const requestGate = useLatestRequestGate();

  async function loadData() {
    const requestId = requestGate.begin();
    setLoading(true);
    setError("");
    setLoadWarning("");
    try {
      const [nextQuestions, nextPracticeSets, nextMockExams] = await Promise.allSettled([
        apiFetch<QuestionBankItemResponse[]>("/api/question-bank/questions"),
        apiFetch<PracticeSetResponse[]>("/api/question-bank/practice-sets"),
        apiFetch<MockExamResponse[]>("/api/question-bank/mock-exams"),
      ]);

      if (!requestGate.isCurrent(requestId)) return;

      const results = [nextQuestions, nextPracticeSets, nextMockExams];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No question-bank requests succeeded.");
      }

      setQuestions(nextQuestions.status === "fulfilled" ? nextQuestions.value : []);
      setPracticeSets(nextPracticeSets.status === "fulfilled" ? nextPracticeSets.value : []);
      setMockExams(nextMockExams.status === "fulfilled" ? nextMockExams.value : []);
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "标准题", result: nextQuestions },
          { label: "练习题包", result: nextPracticeSets },
          { label: "模考试卷", result: nextMockExams },
        ]),
      );
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载题库数据失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function runAction(kind: "standardize" | "practice" | "mock") {
    setWorking(kind);
    setMessage("");
    setError("");
    try {
      if (kind === "standardize") {
        const result = await apiFetch<StandardizeQuestionsResponse>("/api/question-bank/standardize", {
          method: "POST",
          body: JSON.stringify({ publish: true }),
        });
        setMessage(`标准题同步完成：新增 ${result.created}，关联 ${result.linked}，跳过 ${result.skipped}`);
      }

      if (kind === "practice") {
        const item = await apiFetch<PracticeSetResponse>("/api/question-bank/practice-sets/generate", {
          method: "POST",
          body: JSON.stringify({ title: "自动高频练习题包", question_limit: 10, set_type: "auto_hot" }),
        });
        setMessage(`已生成题包：${item.title}`);
      }

      if (kind === "mock") {
        const item = await apiFetch<MockExamResponse>("/api/question-bank/mock-exams/generate", {
          method: "POST",
          body: JSON.stringify({ title: "自动模考试卷", question_limit: 20, duration_minutes: 45 }),
        });
        setMessage(`已生成模考：${item.title}`);
      }

      await loadData();
    } catch (err) {
      setError(toErrorMessage(err, "操作失败"));
    } finally {
      setWorking("");
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>题库中心</h1>
          <p>标准题、练习题包和模考试卷分开加载，避免单个接口失败时整页一起空掉。</p>
        </div>
        <div className="buttonRow">
          <button className="button" type="button" disabled={!!working} onClick={() => runAction("standardize")}>
            {working === "standardize" ? "同步中..." : "标准化题目"}
          </button>
          <button className="button" type="button" disabled={!!working} onClick={() => runAction("practice")}>
            {working === "practice" ? "生成中..." : "生成练习题包"}
          </button>
          <button className="button primary" type="button" disabled={!!working} onClick={() => runAction("mock")}>
            {working === "mock" ? "组卷中..." : "生成模考"}
          </button>
        </div>
      </header>

      {message && <div className="calloutBox">{message}</div>}
      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <LoadState
        loading={loading}
        error={error}
        empty={!questions.length && !practiceSets.length && !mockExams.length}
        emptyLabel="暂无题库数据"
      />

      {!loading && !error && (
        <>
          <section className="statsGrid">
            <article className="statCard">
              <span>标准题</span>
              <strong>{questions.length}</strong>
              <small>原始题到标准题的承接已接通</small>
            </article>
            <article className="statCard">
              <span>练习题包</span>
              <strong>{practiceSets.length}</strong>
              <small>支持专题、高频和章节题包</small>
            </article>
            <article className="statCard">
              <span>模考试卷</span>
              <strong>{mockExams.length}</strong>
              <small>支持模考与学习记录联动</small>
            </article>
          </section>

          <section className="dashboardGrid">
            <div className="panel">
              <div className="panelHeader">
                <h2>标准题样例</h2>
                <p>当前已经标准化的题目。</p>
              </div>
              <div className="panelBody">
                <div className="stackList">
                  {questions.map((question) => (
                    <article key={question.id} className="infoCard">
                      <div className="infoCardTop">
                        <strong>{question.canonical_stem}</strong>
                        <StatusBadge value={question.status} tone="good" />
                      </div>
                      <div className="metaLine">
                        <span>{question.question_type}</span>
                        <span>来源 {question.source_count} 次</span>
                        <span>难度 {question.difficulty_level || "-"}</span>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panelHeader">
                <h2>训练与模考</h2>
                <p>题包和试卷的当前状态。</p>
              </div>
              <div className="panelBody stackList">
                {practiceSets.map((item) => (
                  <div key={`ps-${item.id}`} className="detailRow">
                    <span>{item.title}</span>
                    <StatusBadge value={`${item.question_count} 题`} tone="info" />
                  </div>
                ))}
                {mockExams.map((item) => (
                  <div key={`me-${item.id}`} className="detailRow">
                    <span>{item.title}</span>
                    <StatusBadge value={`${item.duration_minutes || 0} 分钟`} tone="warn" />
                  </div>
                ))}
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}
