import type { NextConfig } from "next"

const nextConfig: NextConfig = {
  // A stray package-lock.json in the home directory otherwise confuses root detection.
  turbopack: { root: import.meta.dirname },
  // Lets other devices on the local network (e.g. a phone) load the dev server.
  allowedDevOrigins: ["192.168.4.51"],
}

export default nextConfig
