"use client";

import { useEffect, useState } from "react";
import { apiFetch, MockExamResponse } from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

export default function MockExamsPage() {
  const [items, setItems] = useState<MockExamResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useLatestRequestGate();

  useEffect(() => {
    async function load() {
      const requestId = requestGate.begin();
      try {
        const next = await apiFetch<MockExamResponse[]>("/api/question-bank/mock-exams");
        if (!requestGate.isCurrent(requestId)) return;
        setItems(next);
      } catch (err) {
        if (!requestGate.isCurrent(requestId)) return;
        setError(toErrorMessage(err, "加载模考试卷失败"));
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
          <h1>模考试卷</h1>
          <p>展示模考实体、时长和总分信息。</p>
        </div>
      </header>

      <div className="panel">
        <div className="panelBody">
          <LoadState loading={loading} error={error} empty={!items.length} emptyLabel="暂无模考试卷" />
          {!!items.length && (
            <div className="stackList">
              {items.map((item) => (
                <article key={item.id} className="infoCard">
                  <div className="infoCardTop">
                    <strong>{item.title}</strong>
                    <StatusBadge value={item.status} tone="good" />
                  </div>
                  <div className="metaLine">
                    <span>{item.exam_mode}</span>
                    <span>{item.duration_minutes || 0} 分钟</span>
                    <span>{item.total_score || 0} 分</span>
                  </div>
                </article>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
