import { useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import './App.css'

type Status = 'queued' | 'running' | 'done' | 'failed'
type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
type Risk = { party?: string; name?: string; consequences?: string[] }
type Evidence = { label?: string; text?: string }
type Finding = {
  kind?: string; severity?: Severity; clause?: string; quote?: string
  char_start?: number; char_end?: number; codes?: string[]; risks?: Risk[]
  explanation?: { summary?: string; recommendation?: string } | null; basis?: Evidence[]
}
type Run = {
  id: string; status: Status; stage?: string | null; filename?: string
  error?: { code?: string; message?: string } | null
  document?: { text?: string } | null; items?: Finding[]
  warnings?: { stage?: string; message?: string }[]; seconds?: number
}

const STAGES = [
  ['ingest', 'Đọc và trích xuất'], ['detect', 'Phát hiện rủi ro'],
  ['legal_basis', 'Truy xuất căn cứ'], ['explain', 'Giải thích kết quả'],
] as const
const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
const SEVERITY_VI: Record<Severity, string> = { CRITICAL: 'Nghiêm trọng', HIGH: 'Cao', MEDIUM: 'Trung bình', LOW: 'Thấp' }
const ERROR_VI: Record<string, string> = {
  empty: 'Tệp rỗng.', too_large: 'Tệp quá lớn.', unsupported_type: 'Định dạng chưa được hỗ trợ.',
  encrypted: 'Tệp có mật khẩu.', no_text: 'Không đọc được văn bản.',
  conversion_failed: 'Không chuyển đổi được tệp.', not_implemented: 'Định dạng chưa được hỗ trợ.',
  llm_error: 'Dịch vụ mô hình không phản hồi.', detection_failed: 'Kết quả mô hình không hợp lệ.',
  internal: 'Lỗi xử lý nội bộ.',
}

function errorMessage(error: unknown): string { return error instanceof Error ? error.message : 'Đã xảy ra lỗi không xác định.' }

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) {
    let reason = `HTTP ${response.status}`
    try {
      const data: { detail?: string | { msg?: string }[]; error?: { message?: string } } = await response.json()
      if (typeof data.detail === 'string') reason = data.detail
      else if (Array.isArray(data.detail)) reason = data.detail.map(item => item.msg).join('; ')
      else if (data.error?.message) reason = data.error.message
    } catch { /* Non-JSON HTTP failure */ }
    throw new Error(reason)
  }
  return response.json() as Promise<T>
}

function ContractText({ text, items, onSelect }: { text: string; items: Finding[]; onSelect: (index: number) => void }) {
  const matches = items.map((item, index) => ({ item, index }))
    .filter(({ item }) => item.kind === 'present' && Number.isInteger(item.char_start) && Number.isInteger(item.char_end) &&
      (item.char_start as number) >= 0 && (item.char_end as number) <= text.length && (item.char_end as number) > (item.char_start as number))
    .sort((a, b) => (a.item.char_start as number) - (b.item.char_start as number))
  const parts: ReactNode[] = []
  let cursor = 0
  matches.forEach(({ item, index }) => {
    const start = item.char_start as number
    const end = item.char_end as number
    if (start < cursor) return // Ignore overlapping or malformed ranges
    parts.push(text.slice(cursor, start))
    parts.push(<mark key={index} className={`highlight ${item.severity || ''}`} onClick={() => onSelect(index)} title="Xem rủi ro tương ứng">{text.slice(start, end)}</mark>)
    cursor = end
  })
  parts.push(text.slice(cursor))
  return <div className="contract-text">{parts}</div>
}

function FindingCard({ finding, index, selected }: { finding: Finding; index: number; selected: boolean }) {
  const risks = finding.risks ?? []
  const parties = [...new Set(risks.map(r => r.party === 'A' ? 'Bên cho thuê' : r.party === 'B' ? 'Bên thuê' : r.party).filter(Boolean))]
  return <article id={`finding-${index}`} className={`finding ${finding.severity || ''} ${selected ? 'selected' : ''}`}>
    <div className="chips">
      {finding.severity && <span className={`severity ${finding.severity}`}>{SEVERITY_VI[finding.severity] ?? finding.severity}</span>}
      {finding.clause && <span className="chip">{finding.clause}</span>}
      {parties.length > 0 && <span className="chip">Rủi ro cho: {parties.join(', ')}</span>}
      {(finding.codes ?? []).map(code => <span className="chip" key={code}>{code}</span>)}
    </div>
    {risks.map((risk, i) => <div className="risk-name" key={i}>{risk.name}</div>)}
    {finding.quote && <blockquote>“{finding.quote}”</blockquote>}
    {finding.explanation?.summary ? <><h4>Giải thích</h4><p>{finding.explanation.summary}</p></> : <p className="muted">Chưa có lời giải thích tự động cho mục này.</p>}
    {finding.explanation?.recommendation && <><h4>Khuyến nghị</h4><p>{finding.explanation.recommendation}</p></>}
    <h4>Căn cứ pháp luật</h4>
    {(finding.basis ?? []).length ? (finding.basis ?? []).map((source, i) =>
      <details key={i} className="basis"><summary>{source.label || 'Nguồn tham chiếu'}</summary><p>{source.text || 'Không có trích đoạn.'}</p></details>
    ) : <p className="muted">Chưa tìm thấy căn cứ phù hợp trong kho dữ liệu.</p>}
    {finding.kind !== 'present' && <p className="muted caveat">Nội dung có thể nằm trong phụ lục hoặc được diễn đạt khác. Cần kiểm tra thủ công.</p>}
  </article>
}

function App() {
  const [file, setFile] = useState<File | null>(null)
  const [run, setRun] = useState<Run | null>(null)
  const [runId, setRunId] = useState(() => new URLSearchParams(window.location.search).get('id') ?? '')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [selected, setSelected] = useState<number | null>(null)
  const [elapsed, setElapsed] = useState(0)
  const startedAt = useRef<number | null>(null)

  useEffect(() => {
    if (!runId) return
    startedAt.current = Date.now()
    let cancelled = false
    let timer: ReturnType<typeof setTimeout> | undefined
    const poll = async () => {
      try {
        const result = await request<Run>(`/analyses/${encodeURIComponent(runId)}`)
        if (cancelled) return
        setRun(result)
        setError('')
        if (result.status === 'queued' || result.status === 'running') timer = setTimeout(() => { void poll() }, 2500)
      } catch (err) {
        if (cancelled) return
        setError(`Không thể tải phiên phân tích: ${errorMessage(err)}`)
        timer = setTimeout(() => { void poll() }, 5000)
      }
    }
    void poll()
    return () => { cancelled = true; if (timer) clearTimeout(timer) }
  }, [runId])

  useEffect(() => {
    if (!runId || (run && run.status !== 'running' && run.status !== 'queued')) return
    const timer = window.setInterval(() => {
      if (startedAt.current === null) return

      setElapsed(
        Math.round((Date.now() - startedAt.current) / 1000)
      )
    }, 1000)
    return () => window.clearInterval(timer)
  }, [run, runId])

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    if (!file || busy) return
    setBusy(true); setError(''); setRun(null); setSelected(null)
    const form = new FormData()
    form.append('file', file)
    try {
      const response = await request<{ id: string; status: Status }>('/analyses', { method: 'POST', body: form })
      if (!response.id) throw new Error('API không trả về id của phiên phân tích.')
      startedAt.current = Date.now(); setElapsed(0)
      window.history.replaceState(null, '', `?id=${encodeURIComponent(response.id)}`)
      setRunId(response.id)
      setRun({ id: response.id, status: response.status })
    } catch (err) { setError(`Không gửi được hợp đồng: ${errorMessage(err)}`) }
    finally { setBusy(false) }
  }

  const items = run?.items ?? []
  const present = items.map((item, index) => ({ item, index })).filter(x => x.item.kind === 'present')
  const missing = items.map((item, index) => ({ item, index })).filter(x => x.item.kind !== 'present')
  const order = (a: { item: Finding }, b: { item: Finding }) => SEVERITIES.indexOf(a.item.severity ?? 'LOW') - SEVERITIES.indexOf(b.item.severity ?? 'LOW')
  const stageIndex = STAGES.findIndex(([key]) => key === run?.stage)

  function selectFinding(index: number) {
    setSelected(index)
    document.getElementById(`finding-${index}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })
  }

  return <main className="app">
    <header className="app-header"><div><span className="eyebrow">LEGAL AI · MVP</span><h1>Rà soát hợp đồng thuê nhà</h1><p>Phân tích rủi ro và tham chiếu căn cứ pháp luật Việt Nam.</p></div><span className="header-label">Contract Risk Analyzer</span></header>
    <p className="disclaimer">Kết quả do AI hỗ trợ tạo ra và chỉ mang tính tham khảo, không thay thế tư vấn pháp lý chuyên nghiệp.</p>
    <section className="panel upload-panel" aria-label="Tải hợp đồng">
      <form onSubmit={event => { void submit(event) }} className="upload-form">
        <label className="file-field"><span className="file-icon">↥</span><strong>{file ? file.name : 'Chọn hợp đồng để phân tích'}</strong><span>PDF, DOCX, DOC, TXT hoặc ảnh PNG/JPG</span><input type="file" accept=".pdf,.docx,.doc,.txt,.png,.jpg,.jpeg,.webp" onChange={event => setFile(event.target.files?.[0] ?? null)} /></label>
        <button className="primary" disabled={!file || busy || (run?.status === 'running' || run?.status === 'queued')} type="submit">{busy ? 'Đang gửi…' : 'Phân tích hợp đồng'}</button>
      </form>
      {run && <div className="progress" aria-live="polite"><div className="progress-title"><strong>{run.status === 'done' ? 'Đã phân tích xong' : run.status === 'failed' ? 'Phân tích thất bại' : run.status === 'queued' ? 'Đang chờ xử lý' : 'Đang phân tích…'}</strong><span>#{run.id} · {run.seconds ?? elapsed} giây</span></div><div className="steps">{STAGES.map(([key, label], index) => <span key={key} className={`step ${run.status === 'done' || index < stageIndex ? 'completed' : index === stageIndex && run.status === 'running' ? 'current' : ''}`}>{label}</span>)}</div></div>}
      {run?.status === 'failed' && <p className="error" role="alert">{ERROR_VI[run.error?.code ?? ''] || 'Phân tích thất bại.'} {run.error?.message}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
    {run?.status === 'done' && <section className="results" aria-label="Kết quả phân tích">
      <div className="stats"><div><strong>{present.length}</strong><span>Điều khoản rủi ro</span></div><div><strong>{missing.length}</strong><span>Nội dung còn thiếu</span></div>{SEVERITIES.filter(s => items.some(item => item.severity === s)).map(s => <div key={s}><strong>{items.filter(item => item.severity === s).length}</strong><span>{SEVERITY_VI[s]}</span></div>)}</div>
      {!!run.warnings?.length && <details className="panel warnings"><summary>{run.warnings.length} cảnh báo kỹ thuật</summary><ul>{run.warnings.map((warning, index) => <li key={index}>[{warning.stage}] {warning.message}</li>)}</ul></details>}
      <div className="result-grid"><section className="panel source"><h2>Văn bản hợp đồng</h2><p className="muted">Nhấn vào đoạn được đánh dấu để xem rủi ro tương ứng.</p>{run.document?.text ? <ContractText text={run.document.text} items={items} onSelect={selectFinding} /> : <p>Không có văn bản trích xuất để hiển thị.</p>}</section><section className="findings"><h2>Điều khoản có rủi ro</h2>{present.length ? present.sort(order).map(({ item, index }) => <FindingCard key={index} finding={item} index={index} selected={selected === index} />) : <p className="panel muted">Không phát hiện điều khoản rủi ro trong phạm vi phân tích.</p>}<h2 className="missing-title">Nội dung hợp đồng còn thiếu</h2>{missing.length ? missing.sort(order).map(({ item, index }) => <FindingCard key={index} finding={item} index={index} selected={selected === index} />) : <p className="panel muted">Không có mục nào.</p>}</section></div>
    </section>}
  </main>
}

export default App
