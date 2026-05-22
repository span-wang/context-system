"use client";

import Link from "next/link";
import { useState, useEffect } from "react";

import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import {
  apiFetch,
  DailyPlanResponse,
  PracticeSessionCreateRequest,
  PracticeSessionDetailResponse,
} from "../../../lib/pro-api";
import { toErrorMessage } from "../../../lib/request-guard";

export default function PracticePlanPage() {
  const [plan, setPlan] = useState<DailyPlanResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [startingTaskId, setStartingTaskId] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    void loadPlan();
  }, []);

  async function loadPlan() {
    setLoading(true);
    setError("");
    try {
      const payload = await apiFetch<DailyPlanResponse>("/api/learning/daily-plan");
      setPlan(payload);
    } catch (err) {
      setError(toErrorMessage(err, "加载每日计划失败"));
    } finally {
      setLoading(false);
    }
  }

  async function startTask(taskId: string) {
    const task = plan?.tasks.find((item) => item.task_id === taskId);
    if (!task) return;
    setStartingTaskId(taskId);
    setError("");
    try {
      if (task.action_type === "review_today_start" && task.derived_session_payload) {
        const detail = await apiFetch<PracticeSessionDetailResponse>("/api/learning/review-today/start", {
          method: "POST",
          body: JSON.stringify(task.derived_session_payload),
        });
        window.location.href = `/practice/session/${detail.id}`;
        return;
      }
      if (task.action_type === "create_session" && task.session_create_payload) {
        const detail = await apiFetch<PracticeSessionDetailResponse>("/api/learning/sessions", {
          method: "POST",
          body: JSON.stringify(task.session_create_payload as PracticeSessionCreateRequest),
        });
        window.location.href = `/practice/session/${detail.id}`;
      }
    } catch (err) {
      setError(toErrorMessage(err, "启动计划任务失败"));
    } finally {
      setStartingTaskId("");
    }
  }

  return (
    <div className="practicePlanPage">
      <div className="pageHeader">
        <div>
          <h1>每日学习计划</h1>
          <p>把今天该复习、该巩固、该补弱点的任务排成一个顺序，避免刷题只停留在“做完一套”。</p>
        </div>
        <div className="practiceHeaderActions">
          <Link className="button" href="/practice">返回练习首页</Link>
        </div>
      </div>

      <LoadState loading={loading} error={error} />
      {!loading && !error && plan && (
        <div className="practicePlanLayout">
          <section className="panel">
            <div className="panelHeader">
              <h2>{plan.headline}</h2>
              <p>{plan.summary}</p>
            </div>
            <div className="panelBody practicePlanTaskList">
              {plan.tasks.map((task) => (
                <div key={task.task_id} className="practicePlanTaskCard">
                  <div className="practiceQuestionMeta">
                    <div>
                      <strong>{task.title}</strong>
                      <p className="practicePlanTaskText">{task.description}</p>
                    </div>
                    <StatusBadge value={priorityLabel(task.priority)} tone={task.priority === "high" ? "danger" : task.priority === "medium" ? "warn" : "info"} />
                  </div>
                  <div className="practiceTagRow">
                    <StatusBadge value={`${task.question_count} 题`} tone="info" />
                    <StatusBadge value={task.task_type} />
                  </div>
                  <div className="buttonRow">
                    <button
                      className="button primary"
                      type="button"
                      disabled={!task.action_type || startingTaskId === task.task_id}
                      onClick={() => void startTask(task.task_id)}
                    >
                      {startingTaskId === task.task_id ? "正在启动..." : task.action_type ? "开始这个任务" : "当前仅建议执行"}
                    </button>
                  </div>
                </div>
              ))}
            </div>
          </section>

          <aside className="panel">
            <div className="panelHeader">
              <h2>薄弱点提醒</h2>
              <p>每天先看最弱的 2-3 个知识点，学习动作会更聚焦。</p>
            </div>
            <div className="panelBody practiceListStack">
              {!plan.weak_points.length && <div className="empty compact">当前还没有足够练习数据生成薄弱点。</div>}
              {plan.weak_points.map((item) => (
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
          </aside>
        </div>
      )}
    </div>
  );
}

function priorityLabel(value: string) {
  if (value === "high") return "高优先级";
  if (value === "medium") return "中优先级";
  return "低优先级";
}
