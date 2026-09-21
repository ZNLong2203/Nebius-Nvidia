import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Exported as static files so the FastAPI service can serve the UI itself:
  // one process, one URL, no CORS, and nothing to deploy separately.
  output: "export",
  distDir: "out",
  // Set only for a build hosted under a sub-path, such as GitHub Pages
  // (/Nebius-Nvidia). The FastAPI-served build lives at the root.
  basePath: process.env.NEXT_PUBLIC_BASE_PATH || undefined,
  images: { unoptimized: true },
  // Development only: `next dev` proxies the API so the UI can be iterated on
  // with hot reload. The export is served by FastAPI itself, which already has
  // the API on the same origin, so no rewrite is needed (or possible) there.
  async rewrites() {
    if (process.env.NODE_ENV !== "development") return [];
    return [{ source: "/api/:path*", destination: "http://127.0.0.1:8000/api/:path*" }];
  },
};

export default nextConfig;
