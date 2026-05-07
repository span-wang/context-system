/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  allowedDevOrigins: ["context.panspan.cloud"],
  async rewrites() {
    const apiBase = process.env.API_PROXY_TARGET || "http://127.0.0.1:8000";
    const layoutBase = process.env.LAYOUT_PROXY_TARGET || "https://xhs.panspan.cloud";
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
