import type { CircuitTelemetry } from './types'

export default function CircuitMeasurements({ telemetry, online }: { telemetry: CircuitTelemetry | null; online: boolean }) {
  const branch = telemetry?.ina219?.CIRCUIT
  const probe = telemetry?.circuit_probe
  const connected = online && telemetry?.connected
  const supplyLive = connected && !telemetry?.stale && branch?.valid && !branch.stale
  const probeLive = connected && probe?.valid && !probe.stale && probe.voltage != null
  const status = !online ? 'BACKEND DISCONNECTED' : !telemetry?.connected ? 'STM32 DISCONNECTED' : probe?.status ?? 'NOT REPORTED'
  return <section className="panel">
    <div className="panel-title"><div><h2>Live circuit measurements</h2><p>Supply: INA219 0x41 · Diagnostic probe: STM32 A0</p></div><span className="mode-chip">HARDWARE</span></div>
    <section className="metric-grid">
      {(['voltage', 'current', 'power'] as const).map(key => {
        const item = branch?.measurements[key]
        return <div className="metric" key={key}><span>Circuit Supply {key[0].toUpperCase() + key.slice(1)} — INA219</span><strong>{supplyLive && item?.valid && item.value != null ? item.value.toFixed(3) : '—'}<small> {({ voltage: 'V', current: 'A', power: 'W' })[key]}</small></strong></div>
      })}
      <div className="metric"><span>Probe Voltage — STM32 A0 ADC</span><strong>{probeLive ? probe.voltage!.toFixed(3) : '—'}<small> V</small></strong></div>
    </section>
    <p role="status">Probe: {status} · Calibration: {probe?.calibrated ? 'reported calibrated' : 'nominal scale / uncalibrated'}</p>
    <p>ADC count: {connected && !probe?.stale ? probe?.raw_adc ?? '—' : '—'} · ADC pin: {connected && !probe?.stale ? probe?.adc_pin_voltage?.toFixed(4) ?? '—' : '—'} V · Sample: {probe?.timestamp_ms ?? '—'} ms · Age: {probe?.age_seconds?.toFixed(1) ?? '—'} s</p>
    <p>Supply sensor: {connected ? branch?.status ?? 'NOT REPORTED' : 'DISCONNECTED'} · Supply calibration: {branch?.calibrated ? 'reported calibrated' : 'unverified'}.</p>
    <p>Probe range: 0–12 V DC relative to common ground. A valid zero is a measured low voltage; this input cannot distinguish an unplugged probe from ground or measure negative voltage.</p>
  </section>
}
