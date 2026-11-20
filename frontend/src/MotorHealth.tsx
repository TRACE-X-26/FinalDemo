import { useEffect, useState } from 'react'
import { api } from './api'
import type { MotorHealthComparison, MotorHealthDiagnosis, MotorHealthMetricName, MotorHealthOverview } from './types'

const measurements: { key: MotorHealthMetricName; name: string; unit: string; decimals: number }[] = [
  { key: 'rpm', name: 'Output speed', unit: 'RPM', decimals: 0 },
  { key: 'current', name: 'Motor current', unit: 'A', decimals: 3 },
  { key: 'voltage', name: 'Supply voltage', unit: 'V', decimals: 3 },
]
const terminal = new Set(['COMPLETED', 'FAILED', 'CANCELLED', 'EMERGENCY_STOP', 'DISCONNECTED'])
const statusClass = { 'Within reference': 'status-healthy', 'Deviation detected': 'status-warning', 'Not assessed': 'status-hold' }
const date = (value: string) => new Date(value).toLocaleString(undefined, { dateStyle: 'short', timeStyle: 'short' })

export default function MotorHealth() {
  const [overview, setOverview] = useState<MotorHealthOverview | null>(null)
  const [testId, setTestId] = useState('')
  const [comparison, setComparison] = useState<MotorHealthComparison | null>(null)
  const [diagnosis, setDiagnosis] = useState<MotorHealthDiagnosis | null>(null)
  const [historyId, setHistoryId] = useState<number | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState('')
  const selected = overview?.tests.find(test => test.id === testId)

  useEffect(() => {
    const controller = new AbortController()
    api.motorHealth(controller.signal).then(data => {
      if (controller.signal.aborted) return
      setOverview(data)
      setTestId(data.tests[0]?.id ?? '')
    }).catch((err: Error) => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [])

  useEffect(() => {
    if (!testId || historyId !== null) return
    const controller = new AbortController()
    api.motorHealthTest(testId, controller.signal).then(result => {
      if (!controller.signal.aborted) setComparison(result)
    }).catch((err: Error) => { if (!controller.signal.aborted) setError(err.message) })
    return () => controller.abort()
  }, [testId, historyId])

  function selectTest(id: string) {
    if (id === testId && historyId === null) return
    setError('')
    setComparison(null)
    setDiagnosis(null)
    setHistoryId(null)
    setTestId(id)
  }

  function viewHistory(entry: MotorHealthDiagnosis) {
    setTestId(entry.run_id)
    setHistoryId(entry.id)
    setComparison(entry)
    setDiagnosis(entry)
    setError('')
    document.getElementById('health-diagnostic-title')?.scrollIntoView({ block: 'nearest' })
  }

  async function diagnose() {
    setPending(true)
    setError('')
    try {
      const result = await api.runMotorDiagnostic(testId)
      setComparison(result)
      setDiagnosis(result)
      setOverview(previous => previous && { ...previous, history: [result, ...previous.history] })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  const reference = comparison?.reference ?? overview?.reference
  return <>
    <header className="health-title">
      <div><h1>Motor Health</h1><p>Compare saved motor tests against a provisional reference.</p></div>
    </header>
    {error && <p role="alert" className="circuit-error">{error}</p>}
    <div className="health-grid">
      <section className="panel" aria-labelledby="health-tests-title">
        <h2 id="health-tests-title">Motor Tests</h2>
        <p>Select a saved test. A 15-second run covers the 3–13 second analysis window.</p>
        <div className="session-list health-test-list" aria-label="Saved motor tests">
          {overview?.tests.map(test => <button key={test.id}
            className={testId === test.id ? 'session selected' : 'session'}
            aria-pressed={testId === test.id} disabled={pending} onClick={() => selectTest(test.id)}>
            <span><strong>Test #{test.number}</strong><small>{date(test.created_at)}</small>
              <small>{test.pwm_percent == null ? 'PWM unknown' : `${test.pwm_percent}% PWM`} · {test.duration_ms == null ? 'Duration unknown' : `${test.duration_ms / 1000} s`}</small>
            </span>
            <span className={`status ${test.state === 'COMPLETED' ? 'status-complete' : ''}`}>{test.state.replaceAll('_', ' ')}</span>
          </button>)}
        </div>
        {overview?.tests.length === 0 && <p>No hardware motor tests have been saved.</p>}
        {!overview && !error && <p role="status">Loading motor tests…</p>}
      </section>
      <section className="panel" aria-labelledby="health-diagnostic-title">
        <div className="panel-title"><div><h2 id="health-diagnostic-title">Diagnostic</h2>
          <p>{selected ? `Test #${selected.number} · ${selected.direction} · Load ${selected.load_id || 'unknown'}` : 'Select a motor test to compare.'}</p>
        </div></div>
        {reference && <>
          <div className="health-baseline"><strong>Provisional reference</strong><span>{reference.run_ids.join(' and ')} · {reference.pwm_percent}% target PWM</span></div>
          <p>{reference.motor_model} · Observed min–max across {reference.archive_sample_count} archived running readings. Archived RPM and matching load are unverified.</p>
          <div className="table-wrap"><table aria-label="Test readings against archived reference">
            <thead><tr><th scope="col">Measurement</th><th scope="col">Test median</th><th scope="col">Observed range</th></tr></thead>
            <tbody>{measurements.map(({ key, name, unit, decimals }) => {
              const metric = comparison?.metrics[key]
              const [min, max] = metric?.range ?? reference.ranges[key]
              return <tr key={key}><th scope="row">{name}</th>
                <td className={`health-reading ${metric?.outside ? 'health-deviation' : ''}`}>
                  {metric?.value == null ? 'Unavailable' : `${metric.value.toFixed(key === 'rpm' ? 1 : decimals)} ${unit}`}
                  {key === 'rpm' && metric?.value != null && comparison?.rpm_calibrated === false && <small> · Unverified</small>}
                </td>
                <td className="health-reading">{min.toFixed(decimals)}–{max.toFixed(decimals)} {unit}</td>
              </tr>
            })}</tbody>
          </table></div>
        </>}
        <div className="health-actions">
          <span>{reference && (!reference.rpm_verified || comparison?.rpm_calibrated === false)
            ? 'RPM range is for reference only.' : 'Uses saved readings only.'}</span>
          <button className="primary" disabled={pending || !comparison || !selected || !terminal.has(selected.state)} onClick={() => void diagnose()}>
            {pending ? 'Running diagnostic…' : 'Run Diagnostic'}
          </button>
        </div>
        {diagnosis && <div className={`finding ${diagnosis.status === 'Within reference' ? 'finding-pass' : 'finding-warning'}`} role="status">
          <strong>{diagnosis.status}{diagnosis.status === 'Within reference' &&
            (!diagnosis.reference.rpm_verified || !diagnosis.rpm_calibrated) ? ' · Voltage and current' : ''}</strong>
          {diagnosis.findings.length > 0
            ? <ul>{diagnosis.findings.map(finding => <li key={finding}>{finding}</li>)}</ul>
            : <p>Assessed readings are within the provisional two-run reference.</p>}
        </div>}
        <details><summary>View RPM calculation</summary><p>Output RPM = (60,000 × change in encoder counts) ÷ (counts per output-shaft revolution × elapsed milliseconds).</p></details>
      </section>
    </div>
    <section className="panel" aria-labelledby="health-history-title">
      <div className="panel-title"><div><h2 id="health-history-title">Diagnostic History</h2><p>Saved results from previous comparisons.</p></div></div>
      {!overview?.history.length ? <p>No diagnostics saved yet.</p> : <div className="table-wrap"><table className="health-history">
        <thead><tr><th scope="col">Motor test</th><th scope="col">Result</th><th scope="col">Finding</th><th scope="col">Date</th></tr></thead>
        <tbody>{overview.history.map(entry => <tr key={entry.id}>
          <td><button className="secondary" disabled={pending} onClick={() => viewHistory(entry)}>View Test #{entry.number}</button></td>
          <td><span className={`status ${statusClass[entry.status]}`}>{entry.status}</span></td>
          <td>{entry.findings[0] ?? 'Readings within observed ranges'}</td>
          <td>{date(entry.created_at)}</td>
        </tr>)}</tbody>
      </table></div>}
    </section>
  </>
}
