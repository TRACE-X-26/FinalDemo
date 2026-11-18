import { useEffect, useState } from 'react'
import { api } from './api'
import HardwareMotorControls from './HardwareMotorControls'
import CircuitMeasurements from './CircuitMeasurements'
import { useCircuitTelemetry } from './useCircuitTelemetry'
import type { AutomatedRun, ElectricalBranch } from './types'

type CircuitSession = { id: string; state: string; power_on: boolean | null; stop_confirmed: boolean;
  ended_at: string | null; reason: string; measurements?: ElectricalBranch }
export type StationStatus = { selected_branch: 'MOTOR' | 'CIRCUIT' | null; circuit: CircuitSession | null;
  motor: AutomatedRun | null; hardware_runtime_enabled: boolean; dashboard_version?: string;
  reset?: { off_confirmed: boolean; reason: string } }

export default function TestStation({ onPowerRequested }: { onPowerRequested?: () => void }) {
  const { telemetry, online } = useCircuitTelemetry()
  const [status, setStatus] = useState<StationStatus | null>(null)
  const [confirmed, setConfirmed] = useState(false)
  const [duration, setDuration] = useState(5)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => {
    let mounted = true
    const refresh = () => api.stationStatus().then(next => { if (mounted) setStatus(next) })
      .catch(err => { if (mounted) setError(String(err)) })
    void refresh()
    const timer = window.setInterval(refresh, 750)
    return () => { mounted = false; window.clearInterval(timer) }
  }, [])
  const circuit = status?.circuit
  const circuitActive = !!circuit && !circuit.ended_at
  const busy = circuitActive || (!!status?.motor && !status.motor.ended_at)
  const branch = status?.selected_branch
  async function select(next: 'MOTOR' | 'CIRCUIT') {
    setPending(true); setError(''); setConfirmed(false)
    try { await api.selectBranch(next); setStatus(await api.stationStatus()) }
    catch (err) { setError(String(err)) }
    finally { setPending(false) }
  }
  async function confirmPower() {
    setPending(true); setError('')
    try {
      await api.stationConfirmPower(Math.round(duration * 1000), confirmed)
      onPowerRequested?.()
      setStatus(await api.stationStatus()); setConfirmed(false)
    } catch (err) { setError(String(err)) }
    finally { setPending(false) }
  }
  return <>
    <header><div><p className="eyebrow">TRACE-X TEST STATION</p><h1>What are you testing?</h1><p>Select a branch, then confirm its power. Motor power confirmation keeps PWM at zero.</p></div></header>
    <section className="branch-choice" aria-label="Select test branch">{(['MOTOR', 'CIRCUIT'] as const).map(choice =>
      <button key={choice} className={branch === choice ? 'branch-card selected' : 'branch-card'}
        aria-pressed={branch === choice} disabled={busy || pending || !status} onClick={() => select(choice)}>
        <strong>{choice === 'MOTOR' ? 'Motor' : 'Circuit'}</strong><span>{choice === 'MOTOR' ? '50% PWM motor test' : 'Supply and probe measurements'}</span>
      </button>)}</section>
    {error && <p role="alert">{error}</p>}
    {!branch && <p role="status">No branch selected. Select Motor or Circuit to begin. Use Reset / All Off to request and confirm both outputs off.</p>}
    {branch && <section className="panel">
      <h2>Confirm {branch === 'MOTOR' ? 'Motor' : 'Circuit'} power</h2>
      <p>{branch === 'MOTOR' ? 'Powers the motor driver with PWM at 0%. Start Motor Test is a separate action.' : 'Powers the circuit supply for the selected duration.'} The other branch is stopped before power is applied.</p>
      {branch === 'CIRCUIT' && !status?.hardware_runtime_enabled && <p role="status">Circuit power requires ADS_HARDWARE_CONTROL_ENABLED=true in the backend.</p>}
      <label><input type="checkbox" checked={confirmed} disabled={busy || pending} onChange={e => setConfirmed(e.target.checked)}/> I confirm the selected branch, its supply, and access to the physical power cutoff.</label>
      {branch === 'CIRCUIT' && <label>Duration (seconds)<input type="number" min="0.1" max="30" step="0.1" value={duration} disabled={busy || pending} onChange={e => setDuration(Number(e.target.value))}/></label>}
      <button className="primary" disabled={!confirmed || busy || pending || (branch === 'CIRCUIT' && !status?.hardware_runtime_enabled) || !Number.isFinite(duration) || duration < .1 || duration > 30} onClick={confirmPower}>Confirm &amp; Power On</button>
      <p>Use Reset / All Off before changing a powered branch. Relay state is acknowledged by firmware; physical contact feedback is not installed.</p>
    </section>}
    {branch === 'MOTOR' && <HardwareMotorControls/>}
    {branch === 'CIRCUIT' && <><CircuitMeasurements telemetry={telemetry} online={online}/>
      <section className="panel"><h2>Circuit supply</h2>
        <p role="status">{circuit ? `${circuit.state} · ${circuit.reason || 'Waiting for STM32 acknowledgment'}` : 'Circuit power has not been requested.'}</p>
        <p>Missing sensor readings stay invalid. Powering a branch does not verify its voltage or diagnose a circuit fault.</p>
        {circuit?.ended_at && <a href={`/api/station/circuit/${circuit.id}/csv`}>Download circuit supply CSV</a>}
      </section></>}
  </>
}
