import type { Metadata } from "next";
import Script from "next/script";
import { Nav } from "../components/Nav";
import "./globals.css";

export const metadata: Metadata = {
  title: "Exam Kit",
  description: "小红书备考资料生产工具",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <Script
          id="strip-injected-text-size-adjust"
          strategy="beforeInteractive"
          dangerouslySetInnerHTML={{
            __html: `
(function () {
  var TEXT_SIZE_ADJUST_NAMES = {
    "-webkit-text-size-adjust": true,
    "text-size-adjust": true,
    "webkittextsizeadjust": true
  };

  function stripInjectedTextSizeAdjust(element) {
    if (!element || !element.getAttribute) return;
    var style = element.getAttribute("style");
    if (!style) return;

    var changed = false;
    var kept = style
      .split(";")
      .map(function (part) { return part.trim(); })
      .filter(Boolean)
      .filter(function (declaration) {
        var separatorIndex = declaration.indexOf(":");
        if (separatorIndex === -1) return true;
        var propertyName = declaration.slice(0, separatorIndex).trim().toLowerCase();
        if (!TEXT_SIZE_ADJUST_NAMES[propertyName]) return true;
        changed = true;
        return false;
      });

    if (!changed) return;
    if (kept.length) {
      element.setAttribute("style", kept.join("; "));
    } else {
      element.removeAttribute("style");
    }
  }

  function stripTree(root) {
    stripInjectedTextSizeAdjust(root);
    if (!root || !root.querySelectorAll) return;
    root.querySelectorAll("[style]").forEach(stripInjectedTextSizeAdjust);
  }

  stripTree(document.documentElement);

  if (window.MutationObserver) {
    var observer = new MutationObserver(function (mutations) {
      mutations.forEach(function (mutation) {
        if (mutation.type === "attributes") {
          stripInjectedTextSizeAdjust(mutation.target);
          return;
        }
        mutation.addedNodes.forEach(stripTree);
      });
    });

    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["style"],
      childList: true,
      subtree: true
    });

    window.addEventListener("load", function () {
      window.setTimeout(function () { observer.disconnect(); }, 1000);
    });
  }
})();
`,
          }}
        />
      </head>
      <body>
        <Nav />
        <main className="pageShell">{children}</main>
      </body>
    </html>
  );
}
