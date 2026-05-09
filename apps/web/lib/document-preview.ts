import katex from "katex";

export function renderDocumentPreviewHtml(
  content: string,
  resolveImageSrc?: (src: string) => string,
): string {
  if (!content) return "";
  const { text, images } = tokenizePreviewContent(content, resolveImageSrc);
  return renderPreviewBlocks(text, images);
}

type PreviewImageToken = {
  token: string;
  src: string;
  alt: string;
};

function tokenizePreviewContent(
  content: string,
  resolveImageSrc?: (src: string) => string,
): { text: string; images: PreviewImageToken[] } {
  const images: PreviewImageToken[] = [];
  let index = 0;
  const nextToken = () => `[[PAPER_IMAGE_${index++}]]`;
  let text = content
    .replace(/<img\b[^>]*src=["']([^"']+)["'][^>]*alt=["']([^"']*)["'][^>]*\/?>/gi, (_match, src, alt) => {
      const token = nextToken();
      images.push({
        token,
        src: resolveImageSrc ? resolveImageSrc(String(src)) : String(src),
        alt: String(alt || ""),
      });
      return token;
    })
    .replace(/<img\b[^>]*src=["']([^"']+)["'][^>]*\/?>/gi, (_match, src) => {
      const token = nextToken();
      images.push({
        token,
        src: resolveImageSrc ? resolveImageSrc(String(src)) : String(src),
        alt: "",
      });
      return token;
    })
    .replace(/!\[([^\]]*)\]\(([^)]+)\)/g, (_match, alt, src) => {
      const token = nextToken();
      images.push({
        token,
        src: resolveImageSrc ? resolveImageSrc(String(src)) : String(src),
        alt: String(alt || ""),
      });
      return token;
    })
    .replace(/<\/?(?:div|section|article|p|span|body|html|table|tbody|thead|tfoot|tr|td|th)[^>]*>/gi, "\n")
    .replace(/<br\s*\/?>/gi, "\n");

  for (const image of images) {
    text = text.replaceAll(image.token, `\n${image.token}\n`);
  }

  return { text, images };
}

function renderPreviewBlocks(text: string, images: PreviewImageToken[]) {
  const lines = text.split(/\r?\n/);
  const parts: string[] = [];
  let blockMathBuffer: string[] | null = null;

  for (const line of lines) {
    const trimmed = line.trim();
    if (trimmed === "$$") {
      if (blockMathBuffer === null) {
        blockMathBuffer = [];
      } else {
        parts.push(renderBlockMath(blockMathBuffer.join("\n")));
        blockMathBuffer = null;
      }
      continue;
    }
    if (blockMathBuffer !== null) {
      blockMathBuffer.push(line);
      continue;
    }
    parts.push(renderPreviewLine(line, images));
  }

  if (blockMathBuffer !== null) {
    parts.push(renderPreviewLine(`$$ ${blockMathBuffer.join(" ")} $$`, images));
  }

  return parts.join("");
}

function renderPreviewLine(line: string, images: PreviewImageToken[]) {
  const trimmed = line.trim();
  if (!trimmed) return '<div class="paperPreviewBlank"></div>';

  const headingMatch = trimmed.match(/^(#{1,6})\s+(.*)$/);
  const content = escapeHtml(trimmed);
  const withImages = images.reduce(
    (acc, image) =>
      acc.replaceAll(
        escapeHtml(image.token),
        `<img class="paperPreviewImage" src="${escapeAttr(image.src)}" alt="${escapeAttr(image.alt)}" loading="lazy" />`,
      ),
    content,
  );
  const rendered = renderInlineMath(withImages);

  if (headingMatch) {
    const level = Math.min(6, headingMatch[1].length);
    return `<div class="paperPreviewHeading paperPreviewHeading${level}">${rendered.replace(/^#{1,6}\s+/, "")}</div>`;
  }

  return `<div class="paperPreviewLine">${rendered}</div>`;
}

function renderBlockMath(source: string) {
  const rendered = renderMath(source, true);
  if (rendered) {
    return `<div class="paperPreviewMathBlock">${rendered}</div>`;
  }
  return `<div class="paperPreviewLine">${escapeHtml(`$$\n${source}\n$$`)}</div>`;
}

function renderInlineMath(html: string) {
  let result = html;
  result = result.replace(/\\\((.+?)\\\)/g, (_match, expr) => renderMath(unescapeHtml(expr), false) || escapeHtml(`\\(${unescapeHtml(expr)}\\)`));
  result = result.replace(/\\\[(.+?)\\\]/g, (_match, expr) => renderMath(unescapeHtml(expr), true) || escapeHtml(`\\[${unescapeHtml(expr)}\\]`));
  result = result.replace(/(^|[^\\])\$(.+?)\$/g, (_match, prefix, expr) => {
    const rendered = renderMath(unescapeHtml(expr), false);
    if (!rendered) {
      return `${prefix}${escapeHtml(`$${unescapeHtml(expr)}$`)}`;
    }
    return `${prefix}${rendered}`;
  });
  return result;
}

function renderMath(source: string, displayMode: boolean) {
  const expr = source.trim();
  if (!expr) return "";
  try {
    return katex.renderToString(expr, {
      throwOnError: false,
      displayMode,
      output: "html",
      strict: "ignore",
    });
  } catch {
    return "";
  }
}

function escapeHtml(value: string) {
  return value
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function escapeAttr(value: string) {
  return escapeHtml(value).replaceAll("`", "&#96;");
}

function unescapeHtml(value: string) {
  return value
    .replaceAll("&lt;", "<")
    .replaceAll("&gt;", ">")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&amp;", "&");
}
