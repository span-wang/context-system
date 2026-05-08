"use client";

import { useEffect, useState } from "react";
import {
  apiFetch,
  LearningHomeResponse,
  MasteryResponse,
  PracticeSetResponse,
  PracticeSessionResponse,
  WrongBookResponse,
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

export default function LearnersPage() {
  const [home, setHome] = useState<LearningHomeResponse | null>(null);
  const [practiceSets, setPracticeSets] = useState<PracticeSetResponse[]>([]);
  const [sessions, setSessions] = useState<PracticeSessionResponse[]>([]);
  const [wrongBook, setWrongBook] = useState<WrongBookResponse[]>([]);
  const [mastery, setMastery] = useState<MasteryResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [working, setWorking] = useState(false);
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
      const [nextHome, nextPracticeSets, nextSessions, nextWrongBook, nextMastery] = await Promise.allSettled([
        apiFetch<LearningHomeResponse>("/api/learning/home"),
        apiFetch<PracticeSetResponse[]>("/api/learning/practice-sets"),
        apiFetch<PracticeSessionResponse[]>("/api/learning/sessions"),
        apiFetch<WrongBookResponse[]>("/api/learning/wrong-book"),
        apiFetch<MasteryResponse[]>("/api/learning/mastery"),
      ]);

      if (!requestGate.isCurrent(requestId)) return;
      const results = [nextHome, nextPracticeSets, nextSessions, nextWrongBook, nextMastery];
      if (allRejected(results)) {
        throw firstRejectedReason(results) || new Error("No learner requests succeeded.");
      }

      setHome(nextHome.status === "fulfilled" ? nextHome.value : null);
      setPracticeSets(nextPracticeSets.status === "fulfilled" ? nextPracticeSets.value : []);
      setSessions(nextSessions.status === "fulfilled" ? nextSessions.value : []);
      setWrongBook(nextWrongBook.status === "fulfilled" ? nextWrongBook.value : []);
      setMastery(nextMastery.status === "fulfilled" ? nextMastery.value : []);
      setLoadWarning(
        summarizeRejectedRequests([
          { label: "学习首页", result: nextHome },
          { label: "练习题包", result: nextPracticeSets },
          { label: "练习记录", result: nextSessions },
          { label: "错题本", result: nextWrongBook },
          { label: "掌握度", result: nextMastery },
        ]),
      );
    } catch (err) {
      if (!requestGate.isCurrent(requestId)) return;
      setError(toErrorMessage(err, "加载学员学习数据失败"));
    } finally {
      if (requestGate.isCurrent(requestId)) setLoading(false);
    }
  }

  useEffect(() => {
    loadData();
  }, []);

  async function runDemoPractice() {
    const practiceSet = practiceSets[0];
    if (!practiceSet) {
      setError("暂无可开始的练习题包");
      return;
    }
    setWorking(true);
    setMessage("");
    setError("");
    try {
      const session = await apiFetch<PracticeSessionResponse>("/api/learning/sessions", {
        method: "POST",
        body: JSON.stringify({ practice_set_id: practiceSet.id, practice_mode: "deferred_feedback" }),
      });
      const submitted = await apiFetch<PracticeSessionResponse>(`/api/learning/sessions/${session.id}/submit`, {
        method: "POST",
        body: JSON.stringify({
          duration_seconds: 900,
          answers: [
            { bank_question_id: 1, learner_answer: "A", spent_seconds: 120 },
            { bank_question_id: 2, learner_answer: "C", spent_seconds: 140 },
          ],
        }),
      });
      setMessage(`已提交练习：得分 ${submitted.score || 0}，正确率 ${submitted.accuracy_rate || 0}`);
      await loadData();
    } catch (err) {
      setError(toErrorMessage(err, "提交练习失败"));
    } finally {
      setWorking(false);
    }
  }

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>学员学习</h1>
          <p>这里展示学习首页、练习记录、错题本和掌握度快照的联通情况。</p>
        </div>
        <button className="button primary" type="button" disabled={working} onClick={runDemoPractice}>
          {working ? "提交中..." : "开始并提交演示练习"}
        </button>
      </header>
      {message && <div className="calloutBox">{message}</div>}
      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <LoadState
        loading={loading}
        error={error}
        empty={!home && !practiceSets.length && !sessions.length && !wrongBook.length && !mastery.length}
        emptyLabel="暂无学员学习数据"
      />

      {!loading && !error && (home || practiceSets.length || sessions.length || wrongBook.length || mastery.length) && (
        <>
          {home && (
            <section className="statsGrid">
              <article className="statCard">
                <span>目标考试</span>
                <strong>{home.target_exam || "-"}</strong>
                <small>{home.active_subject || "未设置主学科"}</small>
              </article>
              <article className="statCard">
                <span>练习场次</span>
                <strong>{home.total_sessions}</strong>
                <small>已联通练习会话数据</small>
              </article>
              <article className="statCard">
                <span>错题数量</span>
                <strong>{home.wrong_book_count}</strong>
                <small>错题本实体已生效</small>
              </article>
              <article className="statCard">
                <span>收藏数量</span>
                <strong>{home.favorite_count}</strong>
                <small>收藏能力已预留</small>
              </article>
            </section>
          )}

          <section className="dashboardGrid">
            <div className="panel">
              <div className="panelHeader">
                <h2>最近练习</h2>
                <p>示例学习会话与提交状态。</p>
              </div>
              <div className="panelBody">
                <div className="stackList">
                  {sessions.map((session) => (
                    <article key={session.id} className="infoCard">
                      <div className="infoCardTop">
                        <strong>{formatSessionLabel(session)}</strong>
                        <StatusBadge value={session.status} tone={session.status === "submitted" ? "good" : "warn"} />
                      </div>
                      <div className="metaLine">
                        <span>得分 {session.score || 0}</span>
                        <span>正确率 {session.accuracy_rate || 0}</span>
                        <span>{session.duration_seconds || 0} 秒</span>
                      </div>
                    </article>
                  ))}
                </div>
              </div>
            </div>

            <div className="panel">
              <div className="panelHeader">
                <h2>错题与薄弱点</h2>
                <p>为后续推荐系统和学习计划打基础。</p>
              </div>
              <div className="panelBody stackList">
                <div className="subsection">
                  <strong>错题本</strong>
                  <div className="metricTable">
                    {wrongBook.map((item) => (
                      <div key={item.id} className="metricRow">
                        <div>
                          <strong>题目 #{item.bank_question_id}</strong>
                          <span className="muted">累计错 {item.wrong_count} 次</span>
                        </div>
                        <StatusBadge value={item.mastered ? "已掌握" : "未掌握"} tone={item.mastered ? "good" : "warn"} />
                      </div>
                    ))}
                  </div>
                </div>
                <div className="subsection">
                  <strong>掌握度快照</strong>
                  <div className="metricTable">
                    {mastery.map((item) => (
                      <div key={item.id} className="metricRow">
                        <div>
                          <strong>{item.knowledge_point_name || `考点 #${item.knowledge_point_id}`}</strong>
                          <span className="muted">
                            答题 {item.answered_count} 次，答对 {item.correct_count} 次
                          </span>
                        </div>
                        <StatusBadge value={item.mastery_score} tone={item.mastery_score >= 0.7 ? "good" : "warn"} />
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          </section>
        </>
      )}
    </>
  );
}

function formatSessionLabel(session: PracticeSessionResponse) {
  const modeLabel = session.practice_mode === "instant_feedback" ? "逐题判题" : "整套交卷";
  return session.session_type.startsWith("practice_set") ? `题包练习 · ${modeLabel}` : session.session_type;
}
