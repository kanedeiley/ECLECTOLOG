import Link from "next/link"
import { BanIcon, CompassIcon, HeartIcon, SlidersHorizontalIcon } from "lucide-react"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { LatestMix } from "@/components/latest-mix"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Separator } from "@/components/ui/separator"
import type { MixRun } from "@/lib/data"
import { initials, profileName, type Profile } from "@/lib/spotify"

const STEERING = [
  { icon: CompassIcon, name: "Eclectolog · Compass", body: "Add songs you want more of." },
  { icon: BanIcon, name: "Eclectolog · Avoid", body: "Add a song to ban that artist." },
  { icon: HeartIcon, name: "Eclectolog", body: "Like tracks you love to boost their artists." },
]

export function Home({ profile, run }: { profile: Profile; run: MixRun | null }) {
  const firstName = profileName(profile).split(/\s+/)[0]

  return (
    <div className="glow">
      <div className="mx-auto max-w-5xl space-y-6 px-4 pt-20 pb-12">
        <section className="flex flex-col items-start gap-5 sm:flex-row sm:items-center">
          <Avatar className="size-20 ring-2 ring-gold/50 ring-offset-4 ring-offset-background">
            <AvatarImage src={profile.avatar_url ?? undefined} alt="" />
            <AvatarFallback className="text-xl">{initials(profile)}</AvatarFallback>
          </Avatar>
          <div className="flex-1 space-y-2">
            <h1 className="text-3xl font-semibold tracking-tight">You're in, {firstName}.</h1>
            <div className="flex flex-wrap gap-2">
              <Badge variant="outline" className="border-gold/40 text-gold">
                Connected
              </Badge>
              {profile.product && (
                <Badge variant="secondary" className="capitalize">
                  {profile.product}
                </Badge>
              )}
              {profile.country && <Badge variant="secondary">{profile.country}</Badge>}
            </div>
          </div>
          <Button asChild variant="outline">
            <Link href="/profile">
              <SlidersHorizontalIcon />
              Tune your mix
            </Link>
          </Button>
        </section>

        <div className="grid gap-6 lg:grid-cols-5">
          <LatestMix run={run} className="lg:col-span-3" />

          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Steer it from Spotify</CardTitle>
              <CardDescription>The first run creates these playlists in your library.</CardDescription>
            </CardHeader>
            <CardContent>
              {STEERING.map(({ icon: Icon, name, body }, i) => (
                <div key={name}>
                  {i > 0 && <Separator className="my-4" />}
                  <div className="flex gap-3">
                    <span className="flex size-8 shrink-0 items-center justify-center rounded-md bg-gold/10 text-gold">
                      <Icon className="size-4" />
                    </span>
                    <div>
                      <p className="text-sm font-medium">{name}</p>
                      <p className="text-sm text-muted-foreground">{body}</p>
                    </div>
                  </div>
                </div>
              ))}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  )
}
