import type { ReactNode } from "react"
import type { LucideIcon } from "lucide-react"
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card"

export function SourceCard({
  icon: Icon,
  name,
  body,
  share,
  children,
}: {
  icon: LucideIcon
  name: string
  body: string
  share: number
  /** Replaces the default share bar, e.g. with a slider. */
  children?: ReactNode
}) {
  return (
    <Card className="transition-colors hover:border-gold/40">
      <CardHeader>
        <div className="mb-2 flex items-center justify-between">
          <span className="flex size-9 items-center justify-center rounded-lg bg-gold/10 text-gold">
            <Icon className="size-5" />
          </span>
          <span className="font-mono text-sm text-muted-foreground tabular-nums">{share}%</span>
        </div>
        <CardTitle>{name}</CardTitle>
        <CardDescription>{body}</CardDescription>
      </CardHeader>
      <CardContent className="mt-auto">
        {children ?? (
          <div className="h-1 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-gold" style={{ width: `${share}%` }} />
          </div>
        )}
      </CardContent>
    </Card>
  )
}

export function SourcesHeading({ children }: { children: ReactNode }) {
  return (
    <h2 className="mb-6 text-center text-sm font-medium tracking-widest text-muted-foreground uppercase">
      {children}
    </h2>
  )
}
