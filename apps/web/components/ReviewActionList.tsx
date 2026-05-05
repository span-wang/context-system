"use client";

import { ChangeEvent, RefObject, useMemo, useState } from "react";
import { Check, LocateFixed, Replace, Save, X } from "lucide-react";
import { apiFetch, GenerationJob, ReviewItem, ReviewItemStatus } from "../lib/api";
import { extractPublishBody } from "./PublishPackagePreview";

type ReviewActionListProps = {
  job: GenerationJob;
  onJobChange: (job: GenerationJob) => void;
  onMessage?: (message: string) => void;
  markdownRef?: RefObject<HTMLElement>;
  onLocate?: (text: string) => void;
};

type ReviewDraft = {
  original_text: string;
  replacement_text: string;
};

type PendingReplaceState = {
  itemId: string;
  matchedOriginal: string;
};

export const statusLabels: Record<ReviewItemStatus, string> = {
  pending: "待确认",
  confirmed: "已确认",
  replaced: "已替换",
  skipped: "已跳过",
};

export default function ReviewActionList({
  job,
  onJobChange,
  onMessage,
  markdownRef,
  onLocate,
}: ReviewActionListProps) {
  const markdown = job.result?.raw_markdown || "";
  const publishBody = extractPublishBody(job.result?.publish_package?.body || markdown);
  const items = useMemo(() => reviewItems(job), [job]);
  const [drafts, setDrafts] = useState<Record<string, ReviewDraft>>({});
  const [busyItem, setBusyItem] = useState<string | null>(null);
  const [pendingReplace, setPendingReplace] = useState<PendingReplaceState | null>(null);

  function draftFor(item: ReviewItem) {
    return drafts[item.id] || {
      original_text: item.original_text || guessOriginalText(item, publishBody),
      replacement_text: item.replacement_text || "",
    };
  }

  function updateDraft(item: ReviewItem, field: keyof ReviewDraft, value: string) {
    if (field === "original_text" && pendingReplace?.itemId === item.id) {
      setPendingReplace(null);
      onLocate?.("");
    }
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
    const matchedOriginal = pendingReplace?.itemId === item.id ? pendingReplace.matchedOriginal : "";
    if (!matchedOriginal) {
      onMessage?.("请先定位并确认正文高亮片段，再执行替换。");
      return;
    }
    setBusyItem(item.id);
    try {
      const updated = await apiFetch<GenerationJob>(`/api/generate/${job.id}/review/items/${item.id}/replace`, {
        method: "POST",
        body: JSON.stringify({
          original_text: matchedOriginal,
          replacement_text: draft.replacement_text,
          replace_all: false,
        }),
      });
      onJobChange(updated);
      setPendingReplace(null);
      onLocate?.("");
      onMessage?.("已在正文中完成替换，并同步到发布包正文。");
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
    const matchedOriginal = findMatchedOriginal(publishBody, draft.original_text);
    if (!matchedOriginal) {
      onMessage?.("当前正文中没有找到这段原文。");
      return;
    }
    setPendingReplace({ itemId: item.id, matchedOriginal });
    onLocate?.(matchedOriginal);
    window.setTimeout(() => {
      const target = markdownRef?.current?.querySelector?.('[data-highlight-target="true"]');
      if (target instanceof HTMLElement) {
        target.scrollIntoView({ behavior: "smooth", block: "center" });
        return;
      }
      markdownRef?.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }, 50);
    onMessage?.("已定位并高亮正文原文，请确认后再替换。");
  }

  if (!items.length) {
    return <div className="empty compact">暂未发现审查问题。</div>;
  }

  return (
    <div className="reviewActionList">
      {items.map((item, index) => {
        const draft = draftFor(item);
        const matchedInBody = findMatchedOriginal(publishBody, draft.original_text);
        const originalFound = Boolean(draft.original_text) && Boolean(matchedInBody);
        const disabled = busyItem === item.id;
        const waitingConfirm = pendingReplace?.itemId === item.id && pendingReplace.matchedOriginal === matchedInBody;
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
                {draft.original_text
                  ? waitingConfirm
                    ? "已定位正文原文，可确认替换"
                    : originalFound
                      ? "已匹配正文原文"
                      : "未匹配到正文原文"
                  : "等待填写原文"}
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
                  disabled={
                    disabled ||
                    !draft.original_text.trim() ||
                    !draft.replacement_text.trim() ||
                    !originalFound ||
                    !waitingConfirm
                  }
                  type="button"
                  onClick={() => replaceItem(item)}
                >
                  <Replace size={16} />
                  确认替换
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

export function reviewItems(job: GenerationJob): ReviewItem[] {
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
  return candidates.find((candidate) => candidate && findMatchedOriginal(markdown, candidate)) || "";
}

function firstQuotedText(text: string) {
  const match = text.match(/[“"']([^“”"']{2,80})[”"']/);
  return match?.[1] || "";
}

export function findMatchedOriginal(markdown: string, originalText: string) {
  if (!markdown || !originalText) return "";
  if (markdown.includes(originalText)) return originalText;

  const { normalizedText: normalizedMarkdown, positions } = normalizeForMatch(markdown);
  const { normalizedText: normalizedOriginal } = normalizeForMatch(originalText);
  if (!normalizedOriginal) return "";

  const matchIndex = normalizedMarkdown.indexOf(normalizedOriginal);
  if (matchIndex < 0) return "";

  const start = positions[matchIndex];
  const end = positions[matchIndex + normalizedOriginal.length - 1] + 1;
  return markdown.slice(start, end);
}

function normalizeForMatch(text: string) {
  const normalizedChars: string[] = [];
  const positions: number[] = [];
  for (const [index, char] of Array.from(text).entries()) {
    if (/\s/u.test(char)) continue;
    if (char === "*" || char === "`" || char === "_") continue;
    const normalized = normalizePunctuation(char).normalize("NFKC");
    for (const normalizedChar of Array.from(normalized)) {
      if (/\s/u.test(normalizedChar)) continue;
      normalizedChars.push(normalizedChar);
      positions.push(index);
    }
  }
  return {
    normalizedText: normalizedChars.join(""),
    positions,
  };
}

function normalizePunctuation(char: string) {
  const punctuationMap: Record<string, string> = {
    "“": '"',
    "”": '"',
    "‘": "'",
    "’": "'",
    "（": "(",
    "）": ")",
    "：": ":",
    "，": ",",
    "；": ";",
    "。": ".",
    "、": ",",
    "＋": "+",
    "－": "-",
    "—": "-",
    "–": "-",
    "−": "-",
    "＝": "=",
    "…": "...",
    "·": ".",
  };
  return punctuationMap[char] || char;
}
