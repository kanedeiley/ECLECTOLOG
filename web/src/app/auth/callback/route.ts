import { NextResponse, type NextRequest } from "next/server"
import { originFrom } from "@/lib/origin"
import { fetchSpotifyMe, SpotifyForbiddenError } from "@/lib/spotify"
import { createAdminClient } from "@/lib/supabase/admin"
import { createClient } from "@/lib/supabase/server"

// Spotify access tokens last an hour; Supabase doesn't pass through the exact expiry.
const SPOTIFY_TOKEN_TTL_MS = 3600 * 1000

// Supabase Auth error codes worth translating for people signing in.
const FRIENDLY_ERRORS: Record<string, string> = {
  provider_email_needs_verification:
    "Supabase wants your Spotify email confirmed before creating an account. Turn off \"Confirm email\" under Authentication → Sign In / Providers → Email, then try again.",
  over_email_send_rate_limit: "Too many sign-in attempts. Wait a minute, then try again.",
}

const NOT_INVITED =
  "Your Spotify account isn't on the invite list yet. Ask whoever runs this Eclectolog to add your Spotify email, then try again."

function fail(origin: string, error: string) {
  return NextResponse.redirect(`${origin}/?error=${encodeURIComponent(error)}`)
}

/**
 * True when this browser already holds a working session with a saved profile. On iPhones the
 * Spotify redirect can hit the callback twice with the same one-time state: the first hit signs
 * the person in, the second is rejected. That rejection shouldn't replace a successful sign-in.
 */
async function alreadySignedIn(supabase: Awaited<ReturnType<typeof createClient>>): Promise<boolean> {
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) return false
  const { data } = await supabase.from("profiles").select("id").eq("id", user.id).maybeSingle()
  return Boolean(data)
}

export async function GET(request: NextRequest) {
  const { searchParams } = new URL(request.url)
  const origin = originFrom(request.headers)
  const supabase = await createClient()
  const code = searchParams.get("code")
  const errorCode = searchParams.get("error_code")
  const oauthError = searchParams.get("error_description") ?? searchParams.get("error")
  if (oauthError) {
    // Shows up in the Vercel / dev server logs, so failed sign-ins can be diagnosed.
    console.error("Sign-in failed before the callback", {
      error: searchParams.get("error"),
      error_code: errorCode,
      error_description: searchParams.get("error_description"),
    })
  }
  // Supabase reports Spotify's Development Mode 403 (account not on the app's User Management list) this way.
  if (oauthError?.includes("Error getting user profile from external provider")) return fail(origin, NOT_INVITED)
  if (oauthError && (await alreadySignedIn(supabase))) {
    console.warn("Ignoring a repeated sign-in callback; this browser is already signed in", { error_code: errorCode })
    return NextResponse.redirect(`${origin}/`)
  }
  if (errorCode && errorCode in FRIENDLY_ERRORS) return fail(origin, FRIENDLY_ERRORS[errorCode])
  if (oauthError) return fail(origin, errorCode ? `${oauthError} (${errorCode})` : oauthError)
  if (!code) return fail(origin, "Spotify did not return an authorization code.")

  const { data, error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) {
    console.error("Exchanging the sign-in code failed", { code: error.code, status: error.status, message: error.message })
    if (await alreadySignedIn(supabase)) return NextResponse.redirect(`${origin}/`)
    // The PKCE verifier cookie lives in the browser that started sign-in; finishing in another one loses it.
    if (error.code === "pkce_code_verifier_not_found" || /code verifier/i.test(error.message)) {
      return fail(origin, "Sign-in has to start and finish in the same browser. Open this site in Safari or Chrome directly (not inside another app) and try again.")
    }
    return fail(origin, error.code ? `${error.message} (${error.code})` : error.message)
  }

  // provider_token / provider_refresh_token are only available right here, at sign-in.
  const { user, provider_token: accessToken, provider_refresh_token: refreshToken } = data.session
  if (!accessToken || !refreshToken) {
    await supabase.auth.signOut({ scope: "local" })
    return fail(origin, "Spotify did not return tokens. Please try again.")
  }

  let me
  try {
    me = await fetchSpotifyMe(accessToken)
  } catch (err) {
    await supabase.auth.signOut({ scope: "local" })
    return fail(
      origin,
      err instanceof SpotifyForbiddenError ? NOT_INVITED : "Couldn't load your Spotify profile. Please try again.",
    )
  }

  const admin = createAdminClient()
  const [profile, tokens] = await Promise.all([
    admin.from("profiles").upsert({
      id: user.id,
      spotify_id: me.id,
      display_name: me.display_name,
      avatar_url: me.images[0]?.url ?? null,
      country: me.country ?? null,
      product: me.product ?? null,
    }),
    admin.from("spotify_tokens").upsert({
      user_id: user.id,
      refresh_token: refreshToken,
      access_token: accessToken,
      expires_at: new Date(Date.now() + SPOTIFY_TOKEN_TTL_MS).toISOString(),
    }),
  ])
  const dbError = profile.error ?? tokens.error
  if (dbError) {
    console.error("Saving Spotify connection failed", dbError)
    await supabase.auth.signOut({ scope: "local" })
    return fail(origin, "Signed in, but saving your account failed. Please try again.")
  }

  return NextResponse.redirect(`${origin}/`)
}
