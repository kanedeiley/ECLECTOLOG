import "server-only"
import { createClient } from "@supabase/supabase-js"

/** Service-role client. Bypasses RLS, so only use it in server code for writes users can't make. */
export function createAdminClient() {
  return createClient(process.env.NEXT_PUBLIC_SUPABASE_URL!, process.env.SUPABASE_SERVICE_ROLE_KEY!, {
    auth: { persistSession: false, autoRefreshToken: false },
  })
}
