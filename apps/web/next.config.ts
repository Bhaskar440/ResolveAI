import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  // Self-contained runtime for the Docker image (no full node_modules copy).
  output: "standalone",
};

export default nextConfig;
