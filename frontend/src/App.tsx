
import { useEffect, useState } from 'react'
import './App.css'

type HealthStatus = 'checking' | 'connected' | 'error'

function App() {
  const [status, setStatus] = useState<HealthStatus>('checking')

  useEffect(() => {
    const checkBackend = async () => {
      try {
        const response = await fetch('http://127.0.0.1:8000/health')

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`)
        }

        const data: { status: string } = await response.json()

        setStatus(data.status === 'ok' ? 'connected' : 'error')
      } catch {
        setStatus('error')
      }
    }

    void checkBackend()
  }, [])

  return (
    <main>
      <h1>ContractRiskAnalyzer</h1>
      <p>Kiểm tra kết nối giữa frontend và backend.</p>

      <p>
        Trạng thái backend:{' '}
        {status === 'checking' && 'Đang kiểm tra...'}
        {status === 'connected' && 'Đã kết nối'}
        {status === 'error' && 'Không thể kết nối'}
      </p>

      <button
        type="button"
        onClick={() => window.location.reload()}
      >
        Kiểm tra lại
      </button>
    </main>
  )
}

export default App
