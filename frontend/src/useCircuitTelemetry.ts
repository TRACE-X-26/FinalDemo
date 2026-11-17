import { useEffect, useState } from 'react'
import { api } from './api'
import type { CircuitTelemetry } from './types'

export function useCircuitTelemetry() {
  const [telemetry, setTelemetry] = useState<CircuitTelemetry | null>(null)
  const [online, setOnline] = useState(false)
  useEffect(() => {
    let active = true
    let controller: AbortController | null = null
    let busy = false
    async function refresh() {
      if (busy) return
      busy = true
      controller = new AbortController()
      const timeout = window.setTimeout(() => controller?.abort(), 2000)
      try {
        const result = await api.circuitTelemetry(controller.signal)
        if (active) { setTelemetry(result); setOnline(true) }
      } catch { if (active) setOnline(false) }
      finally { window.clearTimeout(timeout); busy = false }
    }
    void refresh()
    const timer = window.setInterval(refresh, 1000)
    return () => { active = false; window.clearInterval(timer); controller?.abort() }
  }, [])
  return { telemetry, online }
}
