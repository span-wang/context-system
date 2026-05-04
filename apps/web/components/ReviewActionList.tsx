"use client";

import { ChangeEvent, RefObject, useMemo, useState } from "react";
import { Check, LocateFixed, Replace, Save, X } from "lucide-react";
import { apiFetch, GenerationJob, ReviewItem, ReviewItemStatus } from "../lib/api";

type ReviewActionListProps = {
  job: GenerationJob;
  onJobChange: (job: GenerationJob) => void;
  onMessage?: (message: string) => void;
  markdownRef?: RefObject<HTMLElement>;
};

type ReviewDraft = {
  original_text: string;
  replacement_text: string;
};

const statusLabels: Record<ReviewItemStatus, string> = {
  pending: "待确认",
  confirmed: "已确认",
  replaced: "已替换",
  skipped: "已跳过",
};

export default function ReviewActionList({ job, onJobChange, onMessage, markdownRef }: ReviewActionListProps) {
  const markdown = job.result?.raw_markdown || "";
  const items = useMemo(() => reviewItems(job), [job]);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [busyItem, setBusyItem] = useState<string | null>(null);

  function draftFor(item: ReviewItem) {
    return drafts[item.id] || {
      original_text: item.original_text || guessOriginalText(item, markdown),
      replacement_text: item.replacement_text || "",
    };
  }

  function updateDraft(item: ReviewItem, field: keyof ReviewDraft, value: string) {
    setDrafts((current) => ({
      ...current,
      [item.id]: {
        ...draftFor(item),
        [field]: value,
      },
    }));
  }

  async function updateItem(item: ReviewItem, payload: Partial<ReviewItem> & { status?: ReviewItemStatus }) {
    setBusyItem(item.id);
    try {
      const draft = draftFor(item);
      const updated = await apiFetch<GenerationJob>(`/api/generate/${job.id}/review/items/${item.id}`, {
        method: "PATCH",
        body: JSON.stringify({
          original_text: payload.original_text ?? draft.original_text,
          replacement_text: payload.replacement_text ?? draft.replacement_text,
          status: payload.status,
        }),
      });
      onJobChange(updated);
      onMessage?.("审查条目已保存。");
    } catch (error) {
      onMessage?.(error instanceof Error ? error.message : "审查条目保存失败");
    } finally {
      setBusyItem(null);
    }
  }

  async function replaceItem(item: ReviewItem) {
    const draft = draftFor(item);
    setBusyItem(item.id);
    try {
      const updated = await apiFetch<GenerationJob>(`/api/generate/${job.id}/review/items/${item.id}/replace`, {
        method: "POST",
        body: JSON.stringify({
          original_text: draft.original_text,
          replacement_text: draft.replacement_text,
          replace_all: false,
        }),
      });
      onJobChange(updated);
      onMessage?.("已在 Markdown 中完成替换。");
      window.setTimeout(() => markdownRef?.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
    } catch (error) {
      onMessage?.(error instanceof Error ? error.message : "替换失败");
    } finally {
      setBusyItem(null);
    }
  }

  function focusOriginal(item: ReviewItem) {
    const draft = draftFor(item);
    if (!draft.original_text.trim()) {
      onMessage?.("请先填写要定位的原文片段。");
      return;
    }
    if (!markdown.includes(draft.original_text)) {
      onMessage?.("当前 Markdown 中没有找到这段原文。");
      return;
    }
    markdownRef?.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    onMessage?.("已定位到 Markdown 预览，请核对原文后再替换。");
  }

  if (!items.length) {
    return <div className="empty">暂未发现审查问题。</div>;
  }

  return (
    <div className="reviewActionList">
      {items.map((item, index) => {
        const draft = draftFor(item);
        const originalFound = Boolean(draft.original_text) && markdown.includes(draft.original_text);
        const disabled = busyItem === item.id;
        return (
          <article className="reviewActionItem" key={item.id}>
            <div className="reviewActionTop">
              <span className={`badge reviewStatus ${item.status}`}>{statusLabels[item.status]}</span>
              <strong>#{index + 1}</strong>
            </div>
            <p className="reviewIssueText">{item.issue}</p>
            {item.suggestion && <p className="reviewSuggestionText">{item.suggestion}</p>}
            <div className="reviewReplaceGrid">
              <label>
                <span>原文</span>
                <textarea
                  value={draft.original_text}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                    updateDraft(item, "original_text", event.target.value)
                  }
                  placeholder="粘贴文中需要替换的原文片段"
                />
              </label>
              <label>
                <span>替换为</span>
                <textarea
                  value={draft.replacement_text}
                  onChange={(event: ChangeEvent<HTMLTextAreaElement>) =>
                    updateDraft(item, "replacement_text", event.target.value)
                  }
                  placeholder="填写确认后的替换内容"
                />
              </label>
            </div>
            <div className="reviewActionFooter">
              <span className={originalFound ? "replaceHint found" : "replaceHint"}>
                {draft.original_text ? (originalFound ? "已匹配文中原文" : "未匹配到原文") : "等待填写原文"}
              </span>
              <div className="buttonRow">
                <button className="button" disabled={disabled} type="button" onClick={() => focusOriginal(item)}>
                  <LocateFixed size={16} />
                  定位
                </button>
                <button className="button" disabled={disabled} type="button" onClick={() => updateItem(item, {})}>
                  <Save size={16} />
                  保存
                </button>
                <button
                  className="button primary"
                  disabled={disabled || !draft.original_text.trim() || !originalFound}
                  type="button"
                  onClick={() => replaceItem(item)}
                >
                  <Replace size={16} />
                  替换
                </button>
                <button
                  className="button"
                  disabled={disabled}
                  type="button"
                  onClick={() => updateItem(item, { status: "confirmed" })}
                >
                  <Check size={16} />
                  确认
                </button>
                <button
                  className="button"
                  disabled={disabled}
                  type="button"
                  onClick={() => updateItem(item, { status: "skipped" })}
                >
                  <X size={16} />
                  跳过
                </button>
              </div>
            </div>
          </article>
        );
      })}
    </div>
  );
}

function reviewItems(job: GenerationJob): ReviewItem[] {
  if (!job.review) return [];
  if (job.review.items?.length) return job.review.items;
  return (job.review.issues || []).map((issue, index) => ({
    id: `legacy-${index}`,
    issue,
    suggestion: job.review?.suggestions?.[index] || null,
    original_text: null,
    replacement_text: null,
    status: "pending",
    replace_count: 0,
  }));
}

function guessOriginalText(item: ReviewItem, markdown: string) {
  const candidates = [item.original_text, firstQuotedText(item.issue), firstQuotedText(item.suggestion || "")];
  return candidates.find((candidate) => candidate && markdown.includes(candidate)) || "";
}

function firstQuotedText(text: string) {
  const match = text.match(/[“"']([^“”"']{2,80})[”"']/);
  return match?.[1] || "";
}
