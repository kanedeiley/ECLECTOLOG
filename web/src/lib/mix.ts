import { CompassIcon, Disc3Icon, ShuffleIcon, UsersIcon, type LucideIcon } from "lucide-react"

/** Keys match the `mix:` section of config.yaml and the columns of public.preferences. */
export const MIX_KEYS = ["deep_cuts", "genre_neighbors", "wildcard", "compass"] as const
export type MixKey = (typeof MIX_KEYS)[number]

/** Whole percentages that always add up to 100. */
export type Mix = Record<MixKey, number>

export const DEFAULT_MIX: Mix = { deep_cuts: 25, genre_neighbors: 35, wildcard: 20, compass: 20 }

export const SOURCES: { key: MixKey; icon: LucideIcon; name: string; body: string }[] = [
  {
    key: "deep_cuts",
    icon: Disc3Icon,
    name: "Deep cuts",
    body: "Unheard tracks from albums you already play, or the artist's latest releases.",
  },
  {
    key: "genre_neighbors",
    icon: UsersIcon,
    name: "Neighbors",
    body: "New artists in the genres you listen to, dug out at random search depth.",
  },
  {
    key: "wildcard",
    icon: ShuffleIcon,
    name: "Wildcard",
    body: "Genres you don't listen to, from about 200 global and historical styles.",
  },
  {
    key: "compass",
    icon: CompassIcon,
    name: "Compass",
    body: "Artists and genres you point it toward from your Compass playlist.",
  },
]

export function isValidMix(value: unknown): value is Mix {
  if (typeof value !== "object" || value === null) return false
  const mix = value as Record<string, unknown>
  const parts = MIX_KEYS.map((key) => mix[key])
  return (
    parts.every((n) => Number.isInteger(n) && (n as number) >= 0 && (n as number) <= 100) &&
    parts.reduce<number>((sum, n) => sum + (n as number), 0) === 100
  )
}

/**
 * Sets one source to `value` and rescales the others proportionally so the total stays 100.
 * Rounds with the largest-remainder method so the parts are whole numbers.
 */
export function rebalance(mix: Mix, key: MixKey, value: number): Mix {
  const target = Math.max(0, Math.min(100, Math.round(value)))
  const others = MIX_KEYS.filter((k) => k !== key)
  const remaining = 100 - target
  const otherTotal = others.reduce((sum, k) => sum + mix[k], 0)

  const exact = others.map((k) => ({
    key: k,
    share: otherTotal > 0 ? (mix[k] / otherTotal) * remaining : remaining / others.length,
  }))
  const next: Mix = { ...mix, [key]: target }
  let assigned = 0
  for (const { key: k, share } of exact) {
    next[k] = Math.floor(share)
    assigned += next[k]
  }
  exact
    .sort((a, b) => (b.share % 1) - (a.share % 1))
    .slice(0, remaining - assigned)
    .forEach(({ key: k }) => (next[k] += 1))
  return next
}
