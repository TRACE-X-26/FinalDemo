import { useEffect, useState } from 'react'
import { api } from './api'
import LiveSensors from './LiveSensors'
import TestStation from './TestStation'

type Page = 'station' | 'sensors'
const NAV: { key: Page; label: string }[] = [
  { key: 'station', label: 'Test Station' },
  { key: 'sensors', label: 'STM32 Sensors' },
]

export default function App() {
  const [page, setPage] = useState<Page>('station')
  const [online, setOnline] = useState(false)
  const [resetPending, setResetPending] = useState(false)
  const [resetMessage, setResetMessage] = useState('')
  async function reset() {
    setResetPending(true); setResetMessage('Stopping both branches…')
    try {
      const result = await api.stationReset()
      setResetMessage(result.reason)
    } catch (error) { setResetMessage(`Off not confirmed · ${String(error)}`) }
    finally { setResetPending(false) }
  }

  useEffect(() => {
    let disposed = false
    async function refresh() {
      try {
        const health = await api.health()
        if (!disposed) setOnline(health.status === 'ok')
      } catch {
        if (!disposed) setOnline(false)
      }
    }
    void refresh()
    const timer = window.setInterval(refresh, 5000)
    return () => { disposed = true; window.clearInterval(timer) }
  }, [])

  return <div className="app">
    <aside>
      <div className="brand">
        <div className="brand-mark">A</div>
        <div><strong>TRACE-X</strong><span>Diagnostic station · v0.9.0</span></div>
      </div>
      <nav aria-label="Main navigation">
        {NAV.map(item => <button key={item.key}
          className={page === item.key ? 'active' : ''}
          aria-current={page === item.key ? 'page' : undefined}
          onClick={() => { setPage(item.key); window.scrollTo(0, 0) }}>
          {item.label}
        </button>)}
      </nav>
      <div className="connection">
        <i className={online ? 'dot ready' : 'dot danger'}/>
        <div><strong>{online ? 'API connected' : 'API offline'}</strong><span>Motor and circuit testing</span></div>
      </div>
    </aside>
    <main>
      <div className="source-banner" role="status">
        <strong>{page === 'station' ? 'TEST STATION' : 'STM32 SENSORS'}</strong>
        <span>{online ? 'Backend connected' : 'Backend unavailable'}</span>
        <button className="danger" disabled={resetPending} onClick={reset}>{resetPending ? 'Resetting…' : 'Reset / All Off'}</button>
      </div>
      {resetMessage && <p role="status">{resetMessage}</p>}
      {page === 'station' ? <TestStation onPowerRequested={() => setResetMessage('')}/> : <LiveSensors/>}
    </main>
  </div>
}
