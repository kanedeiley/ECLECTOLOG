import type { Metadata } from "next"
import { redirect } from "next/navigation"
import { ProfilePage } from "@/components/pages/profile"
import { SiteFooter } from "@/components/site-footer"
import { SiteHeader } from "@/components/site-header"
import { getMix, getProfile } from "@/lib/data"

export const metadata: Metadata = { title: "Tune your mix · Eclectolog" }

export default async function Page() {
  const profile = await getProfile()
  if (!profile) redirect("/")
  const mix = await getMix()

  return (
    <>
      <SiteHeader profile={profile} />
      <main className="flex-1">
        <ProfilePage profile={profile} mix={mix} />
      </main>
      <SiteFooter />
    </>
  )
}
