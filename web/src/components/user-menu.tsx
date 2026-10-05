"use client"

import Link from "next/link"
import { ExternalLinkIcon, HouseIcon, LogOutIcon, SlidersHorizontalIcon } from "lucide-react"
import { signOut } from "@/app/auth/actions"
import { Avatar, AvatarFallback, AvatarImage } from "@/components/ui/avatar"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { initials, profileName, type Profile } from "@/lib/spotify"

export function UserMenu({ profile }: { profile: Profile }) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="rounded-full" aria-label="Account menu">
          <Avatar className="size-8 ring-1 ring-gold/40">
            <AvatarImage src={profile.avatar_url ?? undefined} alt="" />
            <AvatarFallback>{initials(profile)}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-56">
        <DropdownMenuLabel className="flex flex-col">
          <span className="truncate text-foreground">{profileName(profile)}</span>
          <span className="truncate text-xs font-normal text-muted-foreground">@{profile.spotify_id}</span>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link href="/">
            <HouseIcon />
            Home
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <Link href="/profile">
            <SlidersHorizontalIcon />
            Profile &amp; mix
          </Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild>
          <a href={`https://open.spotify.com/user/${profile.spotify_id}`} target="_blank" rel="noreferrer">
            <ExternalLinkIcon />
            Open in Spotify
          </a>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={() => void signOut()}>
          <LogOutIcon />
          Sign out
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  )
}
