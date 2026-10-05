import Link from "next/link"
import { ThemeToggle } from "@/components/theme-toggle"
import { UserMenu } from "@/components/user-menu"
import type { Profile } from "@/lib/spotify"

export function SiteHeader({ profile }: { profile: Profile | null }) {
  return (
    <header className="absolute inset-x-0 top-0 z-40">
      <div className="mx-auto flex h-14 max-w-5xl items-center justify-between px-4">
        <Link
          href="/"
          aria-label="Eclectolog home"
          className="rounded-full focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
        >
          <img
            src="/eclectolog-icon.svg"
            alt=""
            width={36}
            height={36}
            className="size-9 hover:animate-[spin_2.4s_linear_infinite] motion-reduce:animate-none"
          />
        </Link>
        <div className="flex items-center gap-1">
          <ThemeToggle />
          {profile && <UserMenu profile={profile} />}
        </div>
      </div>
    </header>
  )
}
