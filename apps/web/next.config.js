function normalizeOriginValue(value) {
  const trimmed = String(value || "").trim();
  if (!trimmed) return "";
  try {
    const parsed = new URL(trimmed.includes("://") ? trimmed : `https://${trimmed}`);
    return parsed.host;
  } catch {
    return trimmed.replace(/^https?:\/\//, "").replace(/\/.*$/, "");
  }
}

function parseAllowedDevOrigins() {
  const defaults = ["context.panspan.cloud"];
  const envValues = [
    process.env.NEXT_ALLOWED_DEV_ORIGINS,
    process.env.PUBLIC_WEB_ORIGIN,
    process.env.PUBLIC_WEB_URL,
  ]
    .filter(Boolean)
    .flatMap((value) => String(value).split(/[,\s]+/))
    .map(normalizeOriginValue)
    .filter(Boolean);
  return Array.from(new Set([...defaults, ...envValues]));
}

/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  allowedDevOrigins: parseAllowedDevOrigins(),
  experimental: {
    proxyClientMaxBodySize: "50mb",
  },
  async rewrites() {
    const apiBase = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    const layoutBase = process.env.LAYOUT_PROXY_TARGET || "https://context.panspan.cloud";
    return [
      {
        source: "/api/:path*",
        destination: `${apiBase}/api/:path*`,
      },
      {
        source: "/layout/:path*",
        destination: `${layoutBase}/:path*`,
      },
      {
        source: "/platform/api/:path*",
        destination: `${apiBase}/platform/api/:path*`,
      },
    ];
  },
};

module.exports = nextConfig;
