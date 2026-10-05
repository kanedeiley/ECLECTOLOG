import { cn } from "@/lib/utils"

export function Logo({ className }: { className?: string }) {
  return <img src="/eclectolog.svg" alt="Eclectolog" className={cn("h-auto select-none", className)} draggable={false} />
}
