"use client"

import { useState, useTransition } from "react"
import { Loader2Icon, RotateCcwIcon } from "lucide-react"
import { toast } from "sonner"
import { saveMix } from "@/app/actions/preferences"
import { SourceCard } from "@/components/source-card"
import { Button } from "@/components/ui/button"
import { Slider } from "@/components/ui/slider"
import { DEFAULT_MIX, MIX_KEYS, rebalance, SOURCES, type Mix } from "@/lib/mix"

const sameMix = (a: Mix, b: Mix) => MIX_KEYS.every((key) => a[key] === b[key])

export function MixEditor({ initial }: { initial: Mix }) {
  const [saved, setSaved] = useState(initial)
  const [mix, setMix] = useState(initial)
  const [pending, startTransition] = useTransition()
  const dirty = !sameMix(mix, saved)

  function save() {
    startTransition(async () => {
      const result = await saveMix(mix)
      if (result.ok) {
        setSaved(mix)
        toast.success("Mix saved. Your next playlist will use it.")
      } else {
        toast.error(result.error)
      }
    })
  }

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {SOURCES.map(({ key, icon, name, body }) => (
          <SourceCard key={key} icon={icon} name={name} body={body} share={mix[key]}>
            <Slider
              value={[mix[key]]}
              min={0}
              max={100}
              step={1}
              onValueChange={([value]) => setMix((current) => rebalance(current, key, value))}
              aria-label={`${name} share`}
              disabled={pending}
            />
          </SourceCard>
        ))}
      </div>

      <div className="flex flex-col-reverse items-center justify-center gap-3 sm:flex-row">
        <Button
          variant="ghost"
          onClick={() => setMix(DEFAULT_MIX)}
          disabled={pending || sameMix(mix, DEFAULT_MIX)}
        >
          <RotateCcwIcon />
          Reset to defaults
        </Button>
        {dirty && (
          <Button variant="outline" onClick={() => setMix(saved)} disabled={pending}>
            Discard changes
          </Button>
        )}
        <Button size="lg" className="min-w-36" onClick={save} disabled={!dirty || pending}>
          {pending && <Loader2Icon className="animate-spin" />}
          {dirty ? "Save mix" : "Saved"}
        </Button>
      </div>
    </div>
  )
}
