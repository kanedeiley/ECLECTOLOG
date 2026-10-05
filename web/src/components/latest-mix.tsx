import { ExternalLinkIcon, ListMusicIcon } from "lucide-react"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card, CardAction, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"
import { Skeleton } from "@/components/ui/skeleton"
import type { MixRun } from "@/lib/data"
import { SOURCES } from "@/lib/mix"

const SOURCE_BY_KEY = Object.fromEntries(SOURCES.map((s) => [s.key, s]))

function formatRunDate(iso: string) {
  return new Date(iso).toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric", timeZone: "UTC" })
}

export function LatestMix({ run, className }: { run: MixRun | null; className?: string }) {
  return (
    <Card className={className}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ListMusicIcon className="size-4 text-gold" />
          {run ? "Your latest mix" : "Your daily mix"}
        </CardTitle>
        <CardDescription>
          {run
            ? `${formatRunDate(run.ran_at)} · ${run.tracks.length} tracks, each with why it was picked`
            : "Each track with the reason it was picked."}
        </CardDescription>
        <CardAction>
          {run?.playlist_url ? (
            <Button asChild variant="outline" size="sm">
              <a href={run.playlist_url} target="_blank" rel="noreferrer">
                <ExternalLinkIcon />
                Open
              </a>
            </Button>
          ) : (
            !run && <Badge variant="outline">After the next daily run</Badge>
          )}
        </CardAction>
      </CardHeader>

      {run ? (
        <CardContent className="max-h-[32rem] space-y-0.5 overflow-y-auto">
          {run.tracks.map((track, i) => {
            const source = SOURCE_BY_KEY[track.source]
            const Icon = source?.icon
            return (
              <div key={track.id} className="flex items-start gap-3 rounded-md px-1 py-2 hover:bg-muted/50">
                <span className="w-5 pt-0.5 text-right font-mono text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                <div className="min-w-0 flex-1">
                  <a
                    href={`https://open.spotify.com/track/${track.id}`}
                    target="_blank"
                    rel="noreferrer"
                    className="block truncate text-sm font-medium hover:underline"
                  >
                    {track.name}
                  </a>
                  <p className="truncate text-xs text-muted-foreground">
                    {track.artists.map(([, name]) => name).join(", ")}
                  </p>
                  {track.reason && <p className="mt-0.5 text-xs text-muted-foreground/80 italic">{track.reason}</p>}
                </div>
                {source && Icon && (
                  <Badge variant="secondary" className="shrink-0 gap-1">
                    <Icon className="text-gold" />
                    {source.name}
                  </Badge>
                )}
              </div>
            )
          })}
        </CardContent>
      ) : (
        <CardContent className="space-y-1" aria-hidden>
          {Array.from({ length: 6 }, (_, i) => (
            <div key={i} className="flex items-center gap-3 py-2" style={{ opacity: 1 - i * 0.14 }}>
              <span className="w-4 text-right font-mono text-xs text-muted-foreground">{i + 1}</span>
              <Skeleton className="size-10 rounded-md" />
              <div className="flex-1 space-y-1.5">
                <Skeleton className="h-3.5" style={{ width: `${55 - ((i * 17) % 25)}%` }} />
                <Skeleton className="h-3" style={{ width: `${35 - ((i * 11) % 15)}%` }} />
              </div>
              <Skeleton className="h-5 w-16 rounded-full" />
            </div>
          ))}
        </CardContent>
      )}
    </Card>
  )
}
