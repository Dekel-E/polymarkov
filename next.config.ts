import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  experimental: {
    // the dev proxy defaults to ~30s, but a full agent run takes ~60s
    proxyTimeout: 300_000,
  },
  async rewrites() {
    // In local dev, proxy /api/* to the FastAPI dev server (uvicorn on :8000).
    // On Vercel, api/index.py is routed via vercel.json instead.
    if (process.env.NODE_ENV === "development") {
      return [
        {
          source: "/api/:path*",
          destination: "http://127.0.0.1:8000/api/:path*",
        },
      ];
    }
    return [];
  },
};

export default nextConfig;
