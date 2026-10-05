"use server"

import { headers } from "next/headers"
import { redirect } from "next/navigation"
import { SPOTIFY_SCOPES } from "@/lib/spotify"
import { createClient } from "@/lib/supabase/server"

export async function signInWithSpotify() {
  const h = await headers()
  const origin = h.get("origin") ?? `https://${h.get("host")}`
  const supabase = await createClient()

  const { data, error } = await supabase.auth.signInWithOAuth({
    provider: "spotify",
    options: {
      redirectTo: `${origin}/auth/callback`,
      scopes: SPOTIFY_SCOPES,
    },
  })
  if (error) redirect(`/?error=${encodeURIComponent(error.message)}`)
  redirect(data.url)
}

export async function signOut() {
  const supabase = await createClient()
  await supabase.auth.signOut()
  redirect("/?signed_out=1")
}
