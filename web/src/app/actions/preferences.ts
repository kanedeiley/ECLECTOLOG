"use server"

import { revalidatePath } from "next/cache"
import { isValidMix, type Mix } from "@/lib/mix"
import { createClient } from "@/lib/supabase/server"

export async function saveMix(mix: Mix): Promise<{ ok: true } | { ok: false; error: string }> {
  if (!isValidMix(mix)) return { ok: false, error: "The mix has to add up to 100%." }

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return { ok: false, error: "You're signed out. Sign in again to save." }

  const { deep_cuts, genre_neighbors, wildcard, compass } = mix
  const { error } = await supabase
    .from("preferences")
    .upsert({ user_id: user.id, deep_cuts, genre_neighbors, wildcard, compass })
  if (error) {
    console.error("Saving preferences failed", error)
    return { ok: false, error: "Couldn't save your mix. Please try again." }
  }

  revalidatePath("/")
  return { ok: true }
}
