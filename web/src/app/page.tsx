import type { Metadata } from "next"
import { Home } from "@/components/pages/home"
import { Landing } from "@/components/pages/landing"
import { SignedOutToast } from "@/components/signed-out-toast"
import { SiteFooter } from "@/components/site-footer"
import { SiteHeader } from "@/components/site-header"
import { getLatestRun, getProfile } from "@/lib/data"
import { profileName } from "@/lib/spotify"

export async function generateMetadata(): Promise<Metadata> {
  const profile = await getProfile()
  if (!profile) return {}
  const first = profileName(profile).split(/\s+/)[0]
  return { title: `${first}${first.endsWith("s") ? "'" : "'s"} Eclectolog` }
}

export default async function Page({ searchParams }: PageProps<"/">) {
  const params = await searchParams
  const error = typeof params.error === "string" ? params.error : undefined
  const profile = await getProfile()
  const run = profile ? await getLatestRun() : null

  return (
    <>
      <SiteHeader profile={profile} />
      <main className="flex-1">{profile ? <Home profile={profile} run={run} /> : <Landing error={error} />}</main>
      <SiteFooter />
      {params.signed_out && <SignedOutToast />}
    </>
  )
}
