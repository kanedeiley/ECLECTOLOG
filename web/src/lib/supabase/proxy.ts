import { createServerClient } from "@supabase/ssr"
import { NextResponse, type NextRequest } from "next/server"

/** Refreshes the Supabase session cookie on every request. */
export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL!,
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY!,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet, headers) {
          cookiesToSet.forEach(({ name, value }) => request.cookies.set(name, value))
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) => response.cookies.set(name, value, options))
          Object.entries(headers).forEach(([key, value]) => response.headers.set(key, value))
        },
      },
    },
  )

  // Don't run code between createServerClient and getClaims: it can cause random sign-outs.
  const { error } = await supabase.auth.getClaims()
  if (error?.code === "refresh_token_not_found") {
    // A stale session cookie (signed out elsewhere, or the user was deleted): clear it instead of
    // erroring on every request. The person simply shows as signed out.
    await supabase.auth.signOut({ scope: "local" })
  }

  return response
}
