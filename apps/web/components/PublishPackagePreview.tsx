import { RefObject } from "react";

import { XiaohongshuPublishPackage } from "../lib/api";

type PublishPackagePreviewProps = {
  packageData?: XiaohongshuPublishPackage | null;
  fallbackMarkdown: string;
  fallbackTitle: string;
  refEl?: RefObject<HTMLPreElement>;
  highlightText?: string | null;
};

export default function PublishPackagePreview({
  packageData,
  fallbackMarkdown,
  fallbackTitle,
  refEl,
  highlightText,
}: PublishPackagePreviewProps) {
  const materialPackage = packageData || derivePackageFromMarkdown(fallbackMarkdown, fallbackTitle);
  const body = formatPublishBody(materialPackage, fallbackMarkdown);
  const titleOptions = ensureTitleOptions(materialPackage.title_options, fallbackTitle);
  return (
    <div className="publishPackage">
      <section className="publishBodySection">
        <div className="publishSectionHeader">
          <h3>正文</h3>
          <span>{packageData ? "只包含发布正文" : "旧结果已临时拆分物料"}</span>
        </div>
        <pre className="markdown" ref={refEl}>
          {renderHighlightedBody(body, highlightText || "")}
        </pre>
      </section>
      <aside className="publishAssetsPanel">
        <section className="publishAssetSection titleOptions">
          <div className="publishSectionHeader">
            <h3>标题备选</h3>
            <span>{titleOptions.length} 条</span>
          </div>
          <ol className="titleOptionList">
            {titleOptions.map((item, index) => (
              <li key={item}>
                <span>{index + 1}</span>
                <strong>{item}</strong>
              </li>
            ))}
          </ol>
        </section>
        <section className="publishAssetSection coverSection">
          <div className="publishSectionHeader">
            <h3>封面</h3>
          </div>
          <div className="coverCopy">{materialPackage.cover_text || fallbackTitle}</div>
        </section>
        <section className="publishAssetSection tagSection">
          <div className="publishSectionHeader">
            <h3>标签</h3>
          </div>
          <div className="tagList">
            {materialPackage.tags.map((tag) => (
              <span key={tag}>#{tag.replace(/^#/, "")}</span>
            ))}
          </div>
        </section>
      </aside>
    </div>
  );
}

export function formatPublishBody(
  packageData: XiaohongshuPublishPackage | null | undefined,
  fallbackMarkdown: string
) {
  return extractPublishBody(packageData?.body || fallbackMarkdown);
}

export function formatPublishPackage(
  packageData: XiaohongshuPublishPackage | null | undefined,
  fallbackTitle: string,
  fallbackMarkdown: string
) {
  const materialPackage = packageData || derivePackageFromMarkdown(fallbackMarkdown, fallbackTitle);
  const titleOptions = ensureTitleOptions(materialPackage.title_options, fallbackTitle);
  const lines = [
    "# 小红书发布包",
    "",
    "## 笔记标题 5 个备选",
    ...titleOptions.map((item, index) => `${index + 1}. ${item}`),
    "",
    "## 正文",
    "",
    extractPublishBody(materialPackage.body || fallbackMarkdown),
    "",
    "## 封面文案",
    "",
    materialPackage.cover_text || fallbackTitle,
    "",
    "## 标签建议",
    "",
    materialPackage.tags.map((tag) => `#${tag.replace(/^#/, "")}`).join(" "),
  ];
  return lines.join("\n").trim() + "\n";
}

export function extractPublishBody(markdown: string) {
  const bodyMatch = markdown.match(/^\s{0,3}#{1,6}\s*(?:正文|发布正文)\s*$/m);
  const nonBodyPattern =
    /^\s{0,3}#{1,6}\s*(?:笔记标题(?:\s*5\s*个)?备选|标题(?:备选|建议)?|封面文案|轮播图逐页文案|轮播图|标签建议|评论区引导|评论引导)\s*$/m;
  if (bodyMatch?.index != null) {
    const start = bodyMatch.index + bodyMatch[0].length;
    const rest = markdown.slice(start);
    const next = rest.search(nonBodyPattern);
    return (next >= 0 ? rest.slice(0, next) : rest).trim();
  }
  const firstNonBody = markdown.search(nonBodyPattern);
  return (firstNonBody >= 0 ? markdown.slice(0, firstNonBody) : markdown).trim();
}

function ensureTitleOptions(items: string[], fallbackTitle: string) {
  const result = [...new Set(items.filter(Boolean))];
  while (result.length < 5) result.push(`${fallbackTitle} 备选 ${result.length + 1}`);
  return result.slice(0, 5);
}

function derivePackageFromMarkdown(markdown: string, fallbackTitle: string): XiaohongshuPublishPackage {
  const body = extractPublishBody(markdown);
  const points = keyPointsFromMarkdown(body);
  const coverSeed = points[0] || fallbackTitle;
  return {
    title_options: ensureTitleOptions(
      [
        `${shortText(fallbackTitle, 18)}，考前直接背`,
        `${shortText(coverSeed, 18)}，这篇帮你理顺`,
        `${shortText(fallbackTitle, 16)}高频考点合集`,
        `别再死记硬背：${shortText(fallbackTitle, 16)}`,
        `${shortText(fallbackTitle, 16)}一图流速记`,
      ],
      fallbackTitle
    ),
    body,
    cover_text: `${shortText(coverSeed, 18)}\n考前别漏`,
    carousel_pages: [],
    tags: ["备考", "考前冲刺", "小红书学习"],
    comment_guides: [],
  };
}

function keyPointsFromMarkdown(markdown: string) {
  return markdown
    .split("\n")
    .map((line) => line.replace(/^#{1,6}\s*/, "").replace(/^[-*]\s*/, "").trim())
    .filter((line) => line.length >= 8 && !line.startsWith("> 未核验"))
    .slice(0, 8);
}

function shortText(text: string, limit: number) {
  const cleaned = text.replace(/\s+/g, " ").replace(/[*_`>#\[\]()-]+/g, "").trim();
  return cleaned.length > limit ? `${cleaned.slice(0, limit)}...` : cleaned;
}

function renderHighlightedBody(body: string, highlightText: string) {
  const matchedText = findMatchedOriginal(body, highlightText);
  if (!matchedText) return body;

  const start = body.indexOf(matchedText);
  if (start < 0) return body;

  return (
    <>
      {body.slice(0, start)}
      <mark className="inlineHighlightTarget" data-highlight-target="true">
        {matchedText}
      </mark>
      {body.slice(start + matchedText.length)}
    </>
  );
}

function findMatchedOriginal(markdown: string, originalText: string) {
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
