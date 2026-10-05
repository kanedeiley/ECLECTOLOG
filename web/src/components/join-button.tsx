"use client"

import { AudioLinesIcon, Loader2Icon } from "lucide-react"
import { useFormStatus } from "react-dom"
import { signInWithSpotify } from "@/app/auth/actions"
import { Button } from "@/components/ui/button"

function SubmitButton() {
  const { pending } = useFormStatus()
  return (
    <Button type="submit" size="lg" className="h-11 w-full text-base" disabled={pending}>
      {pending ? <Loader2Icon className="animate-spin" /> : <AudioLinesIcon />}
      {pending ? "Opening Spotify…" : "Join with Spotify"}
    </Button>
  )
}

export function JoinButton() {
  return (
    <form action={signInWithSpotify} className="w-full">
      <SubmitButton />
    </form>
  )
}
