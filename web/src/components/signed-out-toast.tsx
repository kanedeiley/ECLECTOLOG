"use client"

import { useEffect } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"

/** Shows a toast after sign-out, then drops the query flag from the URL. */
export function SignedOutToast() {
  const router = useRouter()
  useEffect(() => {
    toast("Signed out of Eclectolog")
    router.replace("/")
  }, [router])
  return null
}
