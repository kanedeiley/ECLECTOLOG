import { LogOutIcon } from "lucide-react"
import { signOut } from "@/app/auth/actions"
import { Hero } from "@/components/hero"
import { MixEditor } from "@/components/mix-editor"
import { SourcesHeading } from "@/components/source-card"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import type { Mix } from "@/lib/mix"
import { initials, profileName, type Profile } from "@/lib/spotify"

export function ProfilePage({ profile, mix }: { profile: Profile; mix: Mix }) {
  return (
    <div className="glow">
      <Hero>
        <div className="flex w-full max-w-sm items-center gap-3 rounded-xl border bg-card p-3 text-left">
          <Avatar className="size-10 ring-1 ring-gold/40">
            <AvatarImage src={profile.avatar_url ?? undefined} alt="" />
            <AvatarFallback>{initials(profile)}</AvatarFallback>
          </Avatar>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-medium">{profileName(profile)}</p>
            <p className="text-xs text-muted-foreground">Connected to Spotify</p>
          </div>
          <form action={signOut}>
            <Button type="submit" variant="outline" size="sm">
              <LogOutIcon />
              Log out
            </Button>
          </form>
        </div>
      </Hero>

      <section className="mx-auto max-w-5xl px-4 pb-24">
        <SourcesHeading>Tune your mix</SourcesHeading>
        <MixEditor initial={mix} />
      </section>
    </div>
  )
}
