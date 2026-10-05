import { ShieldCheckIcon } from "lucide-react"
import { Hero } from "@/components/hero"
import { JoinButton } from "@/components/join-button"
import { SourceCard, SourcesHeading } from "@/components/source-card"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { DEFAULT_MIX, SOURCES } from "@/lib/mix"

export function Landing({ error }: { error?: string }) {
  return (
    <div className="glow">
      <Hero>
        <div className="w-full max-w-sm">
          <JoinButton />
        </div>
        <p className="flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
          <ShieldCheckIcon className="size-3.5" />
          We only use your Spotify account to build your mixes.
        </p>
        {error && (
          <Alert variant="destructive" className="mt-5 max-w-md text-left">
            <AlertTitle>Couldn&apos;t connect to Spotify</AlertTitle>
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
      </Hero>

      <section className="mx-auto max-w-5xl px-4 pb-24">
        <SourcesHeading>Four sources, one mix</SourcesHeading>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {SOURCES.map(({ key, icon, name, body }) => (
            <SourceCard key={key} icon={icon} name={name} body={body} share={DEFAULT_MIX[key]} />
          ))}
        </div>
      </section>
    </div>
  )
}
