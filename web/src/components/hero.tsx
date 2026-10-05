import type { ReactNode } from "react"
import { AudioLinesIcon } from "lucide-react"
import { Logo } from "@/components/logo"
import { Badge } from "@/components/ui/badge"

/** Logo, tagline and intro shared by the landing and profile screens. `children` is the action area. */
export function Hero({ children }: { children: ReactNode }) {
  return (
    <section className="mx-auto flex max-w-3xl flex-col items-center px-4 pt-20 pb-16 text-center sm:pt-28">
      <Badge variant="outline" className="mb-8 gap-1.5 border-gold/40 text-gold">
        <AudioLinesIcon />
        A new mix every day
      </Badge>
      <Logo className="w-full max-w-xl" />
      <h1 className="mt-10 text-3xl font-semibold tracking-tight text-balance sm:text-4xl">
        A playlist that refuses to settle.
      </h1>
      <p className="mt-4 max-w-xl text-base text-pretty text-muted-foreground sm:text-lg">
        Eclectolog learns from what you play, then deliberately wanders away from it. Recent listens count a
        little more, everything else gets flattened, and the mix keeps branching out.
      </p>
      <div className="mt-10 flex w-full flex-col items-center gap-3">{children}</div>
    </section>
  )
}
