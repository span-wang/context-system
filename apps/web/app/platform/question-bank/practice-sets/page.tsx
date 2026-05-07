"use client";

import { useEffect, useState } from "react";
import { apiFetch, PracticeSetResponse } from "../../../../lib/pro-api";
import { LoadState } from "../../../../components/shared/LoadState";
import { StatusBadge } from "../../../../components/shared/StatusBadge";
import { toErrorMessage, useLatestRequestGate } from "../../../../lib/request-guard";

export default function PracticeSetsPage() {
  const [items, setItems] = useState<PracticeSetResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const requestGate = useLatestRequestGate();

  useEffect(() => {
    async function load() {
      const requestId = requestGate.begin();
      try {
        const next = await apiFetch<PracticeSetResponse[]>("/api/question-bank/practice-sets");
        if (!requestGate.isCurrent(requestId)) return;
        setItems(next);
      } catch (err) {
        if (!requestGate.isCurrent(requestId)) return;
        setError(toErrorMessage(err, "加载练习题包失败"));
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
          <h1>练习题包</h1>
          <p>展示专题训练包和高频题包。</p>
        </div>
      </header>

      <div className="panel">
        <div className="panelBody">
          <LoadState loading={loading} error={error} empty={!items.length} emptyLabel="暂无练习题包" />
          {!!items.length && (
            <div className="stackList">
              {items.map((item) => (
                <article key={item.id} className="infoCard">
                  <div className="infoCardTop">
                    <strong>{item.title}</strong>
                    <StatusBadge value={item.status} tone="good" />
                  </div>
                  <p>{item.description || "暂无说明"}</p>
                  <div className="metaLine">
                    <span>{item.set_type}</span>
                    <span>{item.question_count} 题</span>
                    <span>{item.difficulty_policy || "未配置策略"}</span>
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
