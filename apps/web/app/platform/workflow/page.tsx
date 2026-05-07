"use client";

import { useEffect, useState } from "react";
import { apiFetch, ReviewTaskResponse, WorkflowTopicResponse } from "../../../lib/pro-api";
import { LoadState } from "../../../components/shared/LoadState";
import { StatusBadge } from "../../../components/shared/StatusBadge";
import {
  allRejected,
  firstRejectedReason,
  summarizeRejectedRequests,
  toErrorMessage,
  useLatestRequestGate,
} from "../../../lib/request-guard";

export default function WorkflowPage() {
  const [topics, setTopics] = useState<WorkflowTopicResponse[]>([]);
  const [tasks, setTasks] = useState<ReviewTaskResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [loadWarning, setLoadWarning] = useState("");
  const requestGate = useLatestRequestGate();

  useEffect(() => {
    async function load() {
      const requestId = requestGate.begin();
      setLoading(true);
      setError("");
      setLoadWarning("");
      try {
        const [nextTopics, nextTasks] = await Promise.allSettled([
          apiFetch<WorkflowTopicResponse[]>("/api/workflow/topics"),
          apiFetch<ReviewTaskResponse[]>("/api/workflow/review-tasks"),
        ]);

        if (!requestGate.isCurrent(requestId)) return;

        const results = [nextTopics, nextTasks];
        if (allRejected(results)) {
          throw firstRejectedReason(results) || new Error("No workflow requests succeeded.");
        }

        setTopics(nextTopics.status === "fulfilled" ? nextTopics.value : []);
        setTasks(nextTasks.status === "fulfilled" ? nextTasks.value : []);
        setLoadWarning(
          summarizeRejectedRequests([
            { label: "内容选题建议", result: nextTopics },
            { label: "复核任务", result: nextTasks },
          ]),
        );
      } catch (err) {
        if (!requestGate.isCurrent(requestId)) return;
        setError(toErrorMessage(err, "加载工作流数据失败"));
      } finally {
        if (requestGate.isCurrent(requestId)) setLoading(false);
      }
    }

    load();
  }, []);

  return (
    <>
      <header className="pageHeader">
        <div>
          <h1>工作流联动</h1>
          <p>选题建议和复核任务分开加载，避免其中一个接口失败时整页一起表现成数据缺失。</p>
        </div>
      </header>

      {loadWarning && <div className="calloutBox">{loadWarning}</div>}

      <section className="dashboardGrid twoCol">
        <div className="panel">
          <div className="panelHeader">
            <h2>内容选题建议</h2>
            <p>由分析报告自动衍生的待生产选题。</p>
          </div>
          <div className="panelBody">
            <LoadState loading={loading} error={error} empty={!topics.length} emptyLabel="当前没有可转化的工作流主题" />
            {!!topics.length && (
              <div className="stackList">
                {topics.map((topic, index) => (
                  <article key={`${topic.title}-${index}`} className="infoCard">
                    <div className="infoCardTop">
                      <strong>{topic.title}</strong>
                      <StatusBadge value={topic.priority} tone={topic.priority === "high" ? "warn" : "info"} />
                    </div>
                    <p>{topic.source_report}</p>
                    <div className="metaLine">
                      <span>{topic.task_type}</span>
                      <span>{topic.status}</span>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panelHeader">
            <h2>复核任务</h2>
            <p>需要人工补充、复核或打回的任务。</p>
          </div>
          <div className="panelBody">
            <LoadState loading={loading} error={error} empty={!tasks.length} emptyLabel="当前没有复核任务" />
            {!!tasks.length && (
              <div className="stackList">
                {tasks.map((task) => (
                  <article key={task.id} className="infoCard">
                    <div className="infoCardTop">
                      <strong>{task.task_type}</strong>
                      <StatusBadge value={task.status} tone={task.status === "pending" ? "warn" : "good"} />
                    </div>
                    <p>{task.review_note || "暂无备注"}</p>
                    <div className="metaLine">
                      <span>{task.target_type}</span>
                      <span>#{task.target_id}</span>
                      <span>{new Date(task.created_at).toLocaleString()}</span>
                    </div>
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      </section>
    </>
  );
}
