import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // A stray package-lock.json in the home directory otherwise confuses root detection.
  turbopack: { root: import.meta.dirname },
}

export default nextConfig
