import "server-only"
import { cache } from "react"
import { DEFAULT_MIX, type Mix } from "@/lib/mix"
import type { Profile } from "@/lib/spotify"
import { createClient } from "@/lib/supabase/server"

/** The signed-in user's profile, or null when signed out. Cached per request. */
export const getProfile = cache(async (): Promise<Profile | null> => {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return null

  const { data } = await supabase
    .from("profiles")
    .select("spotify_id, display_name, avatar_url, country, product")
    .eq("id", user.id)
    .maybeSingle()
  return data
})

/** The signed-in user's saved mix, falling back to the defaults. RLS limits it to their own row. */
export async function getMix(): Promise<Mix> {
  const supabase = await createClient()
  const { data } = await supabase
    .from("preferences")
    .select("deep_cuts, genre_neighbors, wildcard, compass")
    .maybeSingle()
  return data ?? DEFAULT_MIX
}

export type MixTrack = {
  id: string
  name: string
  artists: [string, string][] // [spotify artist id, name]
  album?: string
  source: string
  reason?: string
}

export type MixRun = {
  ran_at: string
  playlist_name: string
  playlist_url: string | null
  tracks: MixTrack[]
}

/** The signed-in user's most recent mix from the daily job, or null before their first run. */
export async function getLatestRun(): Promise<MixRun | null> {
  const supabase = await createClient()
  const { data } = await supabase
    .from("mix_runs")
    .select("ran_at, playlist_name, playlist_url, tracks")
    .order("ran_at", { ascending: false })
    .limit(1)
    .maybeSingle()
  return data
}
