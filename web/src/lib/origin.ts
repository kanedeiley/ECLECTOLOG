import "server-only"

/**
 * The origin the browser actually used (e.g. http://192.168.4.51:3000 from a phone on the LAN,
 * or the Vercel domain), built from the Host / X-Forwarded-* headers. `request.url` can report
 * localhost in dev, which would bounce people to the wrong host after signing in.
 */
export function originFrom(headers: Headers): string {
  const host = headers.get("x-forwarded-host") ?? headers.get("host") ?? "localhost:3000"
  const proto =
    headers.get("x-forwarded-proto")?.split(",")[0] ??
    (/^(localhost|127\.|\d+\.\d+\.\d+\.\d+)(:|$)/.test(host) ? "http" : "https")
  return `${proto}://${host}`
}
