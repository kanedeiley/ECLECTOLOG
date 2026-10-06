// Same scopes the cron job requests in scripts/get_refresh_token.py.
export const SPOTIFY_SCOPES = [
  "user-read-private", // market=from_token (the listener's country)
  "user-read-recently-played",
  "user-top-read",
  "user-library-read",
  "playlist-read-private",
  "playlist-read-collaborative",
  "playlist-modify-private",
  "playlist-modify-public",
  "ugc-image-upload", // playlist covers
].join(" ")

export interface SpotifyMe {
  id: string
  display_name: string | null
  country?: string
  product?: string
  images: { url: string }[]
}

export class SpotifyForbiddenError extends Error {}

export async function fetchSpotifyMe(accessToken: string): Promise<SpotifyMe> {
  const res = await fetch("https://api.spotify.com/v1/me", {
    headers: { Authorization: `Bearer ${accessToken}` },
    cache: "no-store",
  })
  if (res.status === 403) throw new SpotifyForbiddenError("Account not allowed by the Spotify app")
  if (!res.ok) throw new Error(`Spotify /me failed (${res.status})`)
  return res.json()
}

export type Profile = {
  spotify_id: string
  display_name: string | null
  avatar_url: string | null
  country: string | null
  product: string | null
}

export function profileName(profile: Profile): string {
  return profile.display_name || profile.spotify_id
}

export function initials(profile: Profile): string {
  return profileName(profile)
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("")
}
