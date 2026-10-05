import { ThemeToggle } from "@/components/theme-toggle"
import { UserMenu } from "@/components/user-menu"
import type { Profile } from "@/lib/spotify"

// No wordmark here: the hero already shows it. A square "E" mark can go on the left later.
export function SiteHeader({ profile }: { profile: Profile | null }) {
  return (
    <header className="absolute inset-x-0 top-0 z-40">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-end gap-1 px-4">
        <ThemeToggle />
        {profile && <UserMenu profile={profile} />}
      </div>
    </header>
  )
}
