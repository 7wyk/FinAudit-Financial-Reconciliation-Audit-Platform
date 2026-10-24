import { useEffect, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { BrowserRouter, Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate, useParams } from 'react-router-dom'
import { apiError, assistantApi, auth, importsApi, reconciliationApi } from './api/finaudit'
import type { Candidate, ImportRecord, Organization, ReconciliationRun, Result, ResultDetail, User } from './api/finaudit'
import './index.css'

type Session = { user: User; organization: Organization }
type Notice = { type: 'success' | 'error'; message: string } | null

const label = (value: string) => value.replaceAll('_', ' ').toLowerCase().replace(/\b\w/g, (character) => character.toUpperCase())
const dateTime = (value: string | null) => value ? new Intl.DateTimeFormat('en', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(value)) : '—'
const money = (amount: string, currency: string) => `${currency || 'USD'} ${Number(amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 6 })}`

function Status({ value }: { value: string }) {
  const tone = value.toLowerCase().replaceAll('_', '-')
  return <span className={`status status-${tone}`}>{label(value)}</span>
}

function Loading({ label = 'Loading data' }: { label?: string }) {
  return <div className="loading" role="status"><div className="loading-card"><div className="skeleton skeleton-title" /><div className="skeleton skeleton-line" /><div className="skeleton skeleton-line skeleton-short" /><span>{label}</span></div></div>
}

function Empty({ title, message, action }: { title: string; message: string; action?: ReactNode }) {
  return <section className="empty"><div className="empty-mark">—</div><h2>{title}</h2><p>{message}</p>{action}</section>
}

function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <section className="error-state" role="alert"><strong>Unable to load this view.</strong><p>{message}</p>{retry && <button className="button button-secondary" onClick={retry}>Try again</button>}</section>
}

function Shell({ session, onLogout, children }: { session: Session; onLogout: () => void; children: ReactNode }) {
  const [open, setOpen] = useState(false)
  const nav = [
    ['/', 'Overview'], ['/imports', 'Imports'], ['/runs', 'Reconciliation'], ['/audit', 'Audit history'],
  ]
  return <div className="app-shell">
    <aside className={`sidebar ${open ? 'sidebar-open' : ''}`}>
      <Link to="/" className="brand" onClick={() => setOpen(false)}><span className="brand-mark">F</span><span>FinAudit</span></Link>
      <p className="workspace-label">Workspace</p><div className="organization-name">{session.organization.name}</div>
      <nav aria-label="Primary navigation">{nav.map(([to, text]) => <NavLink key={to} to={to} end={to === '/'} onClick={() => setOpen(false)} className={({ isActive }) => `nav-link ${isActive ? 'nav-active' : ''}`}>{text}</NavLink>)}</nav>
      <div className="sidebar-footer"><div className="user-email">{session.user.email}</div><button onClick={onLogout} className="link-button">Sign out</button></div>
    </aside>
    <main className="main"><header className="topbar"><button className="mobile-menu" aria-label="Open navigation" onClick={() => setOpen(!open)}>☰</button><div><p className="eyebrow">Financial operations</p><h1>Reconciliation workspace</h1></div><Status value="SECURE" /></header><div className="page-content">{children}</div></main>
    <AiAssistant session={session} />
  </div>
}

type AssistantMessage = { role: 'user' | 'assistant'; content: string }

function AiAssistant({ session }: { session: Session }) {
  const location = useLocation()
  const [open, setOpen] = useState(false)
  const [question, setQuestion] = useState('')
  const [messages, setMessages] = useState<AssistantMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const transactionMatch = location.pathname.match(/^\/runs\/([^/]+)\/transactions\/([^/]+)/)
  const runMatch = location.pathname.match(/^\/runs\/([^/]+)/)
  const context = transactionMatch
    ? { run_id: transactionMatch[1], transaction_reconciliation_id: transactionMatch[2] }
    : runMatch ? { run_id: runMatch[1] } : {}
  const suggestions = transactionMatch
    ? ['Explain this transaction', 'Why is this transaction a candidate?']
    : runMatch
      ? ['Summarize this reconciliation run', 'What transactions need attention?']
      : ['What transactions need attention?', 'Summarize recent audit activity']

  useEffect(() => {
    const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setOpen(false) }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [])

  const ask = async (value: string) => {
    const trimmed = value.trim()
    if (!trimmed || busy) return
    setBusy(true); setError(''); setQuestion('')
    setMessages((current) => [...current, { role: 'user', content: trimmed }])
    try {
      const response = await assistantApi.ask(session.organization.id, { question: trimmed, ...context, conversation: messages.slice(-6) })
      setMessages((current) => [...current, { role: 'assistant', content: response.answer }])
    } catch (err) { setError(apiError(err)) } finally { setBusy(false) }
  }

  return <><button className="assistant-trigger" onClick={() => setOpen(true)} aria-haspopup="dialog" aria-expanded={open}><span className="assistant-spark">✦</span>AI Assistant</button>{open && <div className="assistant-layer" role="presentation" onMouseDown={() => setOpen(false)}><section className="assistant-panel" role="dialog" aria-modal="true" aria-labelledby="assistant-title" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="eyebrow">FinAudit Copilot</p><h2 id="assistant-title">Ask about your data</h2><p>Explanations use only the organization data you can access.</p></div><button className="icon-button" onClick={() => setOpen(false)} aria-label="Close AI Assistant">×</button></header><div className="assistant-chat" aria-live="polite">{messages.length === 0 && <div className="assistant-welcome"><span>✦</span><p>Ask for an explanation of deterministic results, review queues, or recent audit activity.</p></div>}{messages.map((message, index) => <div key={`${message.role}-${index}`} className={`chat-message chat-${message.role}`}><span>{message.role === 'user' ? 'You' : 'Copilot'}</span><p>{message.content}</p></div>)}{busy && <div className="chat-message chat-assistant"><span>Copilot</span><p className="assistant-thinking"><i />Reviewing authorized reconciliation data…</p></div>}</div>{error && <div className="assistant-error" role="alert">{error}</div>}<div className="assistant-suggestions"><span>Suggested</span><div>{suggestions.map((item) => <button key={item} onClick={() => void ask(item)} disabled={busy}>{item}</button>)}</div></div><form className="assistant-form" onSubmit={(event) => { event.preventDefault(); void ask(question) }}><label className="sr-only" htmlFor="assistant-question">Ask FinAudit Copilot</label><textarea id="assistant-question" value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="Ask a question about this workspace…" rows={2} disabled={busy} /><button className="button button-primary" disabled={busy || !question.trim()}>{busy ? 'Thinking…' : 'Send'}</button></form></section></div>}</>
}

function Login({ onLogin }: { onLogin: (session: Session) => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async (event: FormEvent) => {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const tokens = await auth.login(email, password)
      localStorage.setItem('access_token', tokens.access); localStorage.setItem('refresh_token', tokens.refresh)
      const [user, organizations] = await Promise.all([auth.profile(), auth.organizations()])
      if (!organizations.results.length) throw new Error('Your account is not assigned to an organization.')
      onLogin({ user, organization: organizations.results[0] })
    } catch (err) { setError(apiError(err)) } finally { setBusy(false) }
  }
  return <div className="login-page"><section className="login-intro"><Link to="/login" className="brand"><span className="brand-mark">F</span><span>FinAudit</span></Link><div><p className="eyebrow">Financial reconciliation</p><h1>Operational clarity for every ledger close.</h1><p>Review imported records, investigate deterministic matching evidence, and document every decision.</p></div><small>Enterprise reconciliation workspace</small></section><main className="login-panel"><form className="login-card" onSubmit={submit}><p className="eyebrow">Secure sign in</p><h2>Welcome back</h2><p className="muted">Use your FinAudit account to access your organization.</p>{error && <div className="form-error" role="alert">{error}</div>}<label>Email<input required type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" /></label><label>Password<input required type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" /></label><button className="button button-primary button-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button></form></main></div>
}

function Dashboard({ session }: { session: Session }) {
  const [imports, setImports] = useState<ImportRecord[]>([]); const [runs, setRuns] = useState<ReconciliationRun[]>([]); const [error, setError] = useState(''); const [loading, setLoading] = useState(true)
  const load = async () => { setLoading(true); setError(''); try { const [importPage, runPage] = await Promise.all([importsApi.list(session.organization.id), reconciliationApi.runs(session.organization.id)]); setImports(importPage.results); setRuns(runPage.results) } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [session.organization.id])
  if (loading) return <Loading label="Loading operational overview" />; if (error) return <ErrorState message={error} retry={load} />
  const latestRun = runs[0]; const processed = imports.filter((item) => ['COMPLETED', 'PARTIALLY_COMPLETED'].includes(item.status)).length
  return <><div className="page-heading"><div><p className="eyebrow">Overview</p><h2>Close with confidence</h2><p className="muted">Monitor imported records and reconciliation activity for {session.organization.name}.</p></div><Link className="button button-primary" to="/imports">Upload data</Link></div><section className="metrics" aria-label="Operational metrics"><Metric label="Imported files" value={String(imports.length)} detail={`${processed} processed`} /><Metric label="Reconciliation runs" value={String(runs.length)} detail={latestRun ? `Latest: ${label(latestRun.status)}` : 'No runs yet'} /><Metric label="Latest matched" value={latestRun ? String(latestRun.matched_count) : '—'} detail={latestRun ? `of ${latestRun.total_source} source records` : 'Start a reconciliation'} /><Metric label="Exceptions" value={latestRun ? String(latestRun.exception_count + latestRun.conflict_count) : '—'} detail="Require investigation" /></section><section className="content-grid"><Panel title="Recent imports" action={<Link to="/imports">View all</Link>}>{imports.length ? <SimpleImportTable imports={imports.slice(0, 5)} /> : <Empty title="No imports yet" message="Upload a CSV or XLSX file to begin the reconciliation workflow." action={<Link className="button button-primary" to="/imports">Upload file</Link>} />}</Panel><Panel title="Recent reconciliation runs" action={<Link to="/runs">View all</Link>}>{runs.length ? <SimpleRunTable runs={runs.slice(0, 5)} /> : <Empty title="No reconciliation runs" message="Choose two completed imports to generate deterministic results." action={<Link className="button button-secondary" to="/runs">Create run</Link>} />}</Panel></section></>
}

function Metric({ label, value, detail }: { label: string; value: string; detail: string }) { return <article className="metric"><p>{label}</p><strong>{value}</strong><span>{detail}</span></article> }
function Panel({ title, action, children }: { title: string; action?: ReactNode; children: ReactNode }) { return <section className="panel"><header className="panel-header"><h2>{title}</h2>{action && <span className="panel-action">{action}</span>}</header>{children}</section> }
function SimpleImportTable({ imports }: { imports: ImportRecord[] }) { return <div className="table-wrap"><table><thead><tr><th>File</th><th>Source</th><th>Status</th><th>Rows</th></tr></thead><tbody>{imports.map((item) => <tr key={item.id}><td><Link to={`/imports/${item.id}`}>{item.original_filename}</Link></td><td>{label(item.source)}</td><td><Status value={item.status} /></td><td>{item.valid_rows}/{item.total_rows}</td></tr>)}</tbody></table></div> }
function SimpleRunTable({ runs }: { runs: ReconciliationRun[] }) { return <div className="table-wrap"><table><thead><tr><th>Created</th><th>Status</th><th>Matched</th><th>Review</th></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td><Link to={`/runs/${run.id}`}>{dateTime(run.created_at)}</Link></td><td><Status value={run.status} /></td><td>{run.matched_count}</td><td>{run.conflict_count + run.exception_count}</td></tr>)}</tbody></table></div> }

function Imports({ session }: { session: Session }) {
  const [imports, setImports] = useState<ImportRecord[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [notice, setNotice] = useState<Notice>(null); const [file, setFile] = useState<File | null>(null); const [source, setSource] = useState('ERP'); const [busy, setBusy] = useState(false)
  const load = async () => { setLoading(true); try { setImports((await importsApi.list(session.organization.id)).results); setError('') } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [session.organization.id])
  const upload = async (event: FormEvent) => { event.preventDefault(); if (!file) { setNotice({ type: 'error', message: 'Choose a CSV or XLSX file first.' }); return } setBusy(true); setNotice(null); try { const record = await importsApi.upload(session.organization.id, file, source); setNotice({ type: 'success', message: `${record.original_filename} was queued for processing.` }); setFile(null); await load() } catch (err) { setNotice({ type: 'error', message: apiError(err) }) } finally { setBusy(false) } }
  return <><div className="page-heading"><div><p className="eyebrow">Ingestion</p><h2>Imports</h2><p className="muted">Upload source records and monitor validation and normalization status.</p></div></div><section className="upload-panel"><form onSubmit={upload}><div><h3>Upload financial records</h3><p>CSV and XLSX files only. Files are validated and processed asynchronously.</p></div><label className="file-picker"><span>{file ? file.name : 'Choose a CSV or XLSX file'}</span><input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label><label>Source<select value={source} onChange={(event) => setSource(event.target.value)}><option value="ERP">ERP system</option><option value="BANK">Bank statement</option><option value="ACCOUNTING">Accounting system</option><option value="OTHER">Other</option></select></label><button className="button button-primary" disabled={busy}>{busy ? 'Uploading…' : 'Upload and validate'}</button></form></section>{notice && <NoticeBanner notice={notice} />}{loading ? <Loading /> : error ? <ErrorState message={error} retry={load} /> : <Panel title="Import history">{imports.length ? <SimpleImportTable imports={imports} /> : <Empty title="No import records" message="Upload your first source file to start a reconciliation." />}</Panel>}</>
}

function ImportDetail({ session }: { session: Session }) { const { importId } = useParams(); const [record, setRecord] = useState<ImportRecord | null>(null); const [error, setError] = useState(''); const load = async () => { if (!importId) return; try { setRecord(await importsApi.detail(session.organization.id, importId)) } catch (err) { setError(apiError(err)) } }; useEffect(() => { void load() }, [importId]); if (error) return <ErrorState message={error} retry={load} />; if (!record) return <Loading label="Loading import status" />; return <><div className="page-heading"><div><p className="eyebrow">Import status</p><h2>{record.original_filename}</h2><p className="muted">Uploaded {dateTime(record.created_at)}</p></div><Status value={record.status} /></div><section className="metrics"><Metric label="Total rows" value={String(record.total_rows)} detail="Rows parsed" /><Metric label="Valid rows" value={String(record.valid_rows)} detail="Ready for reconciliation" /><Metric label="Rejected rows" value={String(record.rejected_rows)} detail={`${record.error_count} validation errors`} /><Metric label="Source" value={label(record.source)} detail={record.file_type.toUpperCase()} /></section>{record.error_message && <NoticeBanner notice={{ type: 'error', message: record.error_message }} />}</> }

function Runs({ session }: { session: Session }) {
  const [runs, setRuns] = useState<ReconciliationRun[]>([]); const [imports, setImports] = useState<ImportRecord[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [notice, setNotice] = useState<Notice>(null); const [source, setSource] = useState(''); const [target, setTarget] = useState(''); const [busy, setBusy] = useState(false)
  const load = async () => { setLoading(true); try { const [runPage, importPage] = await Promise.all([reconciliationApi.runs(session.organization.id), importsApi.list(session.organization.id)]); setRuns(runPage.results); setImports(importPage.results.filter((item) => ['COMPLETED', 'PARTIALLY_COMPLETED'].includes(item.status))); setError('') } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [session.organization.id])
  const start = async (event: FormEvent) => { event.preventDefault(); if (!source || !target || source === target) { setNotice({ type: 'error', message: 'Choose two different completed imports.' }); return } setBusy(true); setNotice(null); try { const run = await reconciliationApi.start(session.organization.id, source, target); setNotice({ type: 'success', message: `Reconciliation run started and completed with ${run.matched_count} matches.` }); setSource(''); setTarget(''); await load() } catch (err) { setNotice({ type: 'error', message: apiError(err) }) } finally { setBusy(false) } }
  return <><div className="page-heading"><div><p className="eyebrow">Deterministic reconciliation</p><h2>Reconciliation runs</h2><p className="muted">Compare two tenant-scoped imports using the configured matching policy.</p></div></div><section className="run-form"><form onSubmit={start}><label>Source import<select value={source} onChange={(event) => setSource(event.target.value)}><option value="">Select import</option>{imports.map((item) => <option value={item.id} key={item.id}>{item.original_filename} · {label(item.source)}</option>)}</select></label><span className="compare-mark">⇄</span><label>Target import<select value={target} onChange={(event) => setTarget(event.target.value)}><option value="">Select import</option>{imports.map((item) => <option value={item.id} key={item.id}>{item.original_filename} · {label(item.source)}</option>)}</select></label><button className="button button-primary" disabled={busy}>{busy ? 'Running…' : 'Start reconciliation'}</button></form></section>{notice && <NoticeBanner notice={notice} />}{loading ? <Loading /> : error ? <ErrorState message={error} retry={load} /> : <Panel title="Run history">{runs.length ? <SimpleRunTable runs={runs} /> : <Empty title="No runs yet" message="Select two completed imports to create the first deterministic reconciliation run." />}</Panel>}</>
}

function Results({ session }: { session: Session }) { const { runId } = useParams(); const [results, setResults] = useState<Result[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const load = async () => { if (!runId) return; setLoading(true); try { setResults((await reconciliationApi.results(session.organization.id, runId)).results); setError('') } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }; useEffect(() => { void load() }, [runId]); if (loading) return <Loading label="Loading reconciliation results" />; if (error) return <ErrorState message={error} retry={load} />; return <><div className="page-heading"><div><p className="eyebrow">Run results</p><h2>Transaction results</h2><p className="muted">Inspect each deterministic outcome and open transactions requiring review.</p></div><Link className="button button-secondary" to="/runs">All runs</Link></div><Panel title={`${results.length} transaction records`}>{results.length ? <div className="table-wrap"><table><thead><tr><th>Date</th><th>Reference</th><th>Counterparty</th><th className="align-right">Amount</th><th>Side</th><th>State</th><th /></tr></thead><tbody>{results.map((result) => <tr key={result.id}><td>{result.transaction.transaction_date}</td><td>{result.transaction.reference || '—'}</td><td>{result.transaction.counterparty || '—'}</td><td className="align-right amount">{money(result.transaction.amount, result.transaction.currency)}</td><td>{label(result.side)}</td><td><Status value={result.state} /></td><td><Link to={`/runs/${runId}/transactions/${result.id}`}>Investigate</Link></td></tr>)}</tbody></table></div> : <Empty title="No result records" message="This run did not contain imported canonical transactions." />}</Panel></> }

function Investigation({ session }: { session: Session }) {
  const { runId, resultId } = useParams(); const navigate = useNavigate(); const [detail, setDetail] = useState<ResultDetail | null>(null); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const [notice, setNotice] = useState<Notice>(null); const [note, setNote] = useState(''); const [busy, setBusy] = useState(false); const [evidence, setEvidence] = useState<Candidate | null>(null)
  const load = async () => { if (!runId || !resultId) return; setLoading(true); try { setDetail(await reconciliationApi.transaction(session.organization.id, runId, resultId)); setError('') } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }
  useEffect(() => { void load() }, [runId, resultId])
  const action = async (name: 'confirm' | 'reject' | 'exception' | 'resolve', candidateId?: string) => { if (!runId || !resultId) return; setBusy(true); setNotice(null); try { const updated = await reconciliationApi.action(session.organization.id, runId, resultId, name, { candidate_id: candidateId, note: note || undefined }); setDetail(updated); setNote(''); setNotice({ type: 'success', message: `${label(name)} action recorded.` }) } catch (err) { setNotice({ type: 'error', message: apiError(err) }) } finally { setBusy(false) } }
  const addNote = async (event: FormEvent) => { event.preventDefault(); if (!runId || !resultId || !note.trim()) return; setBusy(true); try { await reconciliationApi.note(session.organization.id, runId, resultId, note.trim()); setNote(''); await load(); setNotice({ type: 'success', message: 'Investigation note added.' }) } catch (err) { setNotice({ type: 'error', message: apiError(err) }) } finally { setBusy(false) } }
  if (loading) return <Loading label="Loading investigation" />; if (error) return <ErrorState message={error} retry={load} />; if (!detail) return null
  const canReview = detail.side === 'SOURCE'
  return <><div className="page-heading"><div><p className="eyebrow">Investigation detail</p><h2>{detail.transaction.reference || 'Unreferenced transaction'}</h2><p className="muted">{detail.transaction.counterparty || 'No counterparty'} · {money(detail.transaction.amount, detail.transaction.currency)} · {detail.transaction.transaction_date}</p></div><div className="heading-actions"><Status value={detail.state} /><button className="button button-secondary" onClick={() => navigate(-1)}>Back to results</button></div></div>{notice && <NoticeBanner notice={notice} />}<section className="investigation-grid"><Panel title="Transaction"><dl className="detail-list"><dt>External ID</dt><dd>{detail.transaction.external_id || '—'}</dd><dt>Reference</dt><dd>{detail.transaction.reference || '—'}</dd><dt>Counterparty</dt><dd>{detail.transaction.counterparty || '—'}</dd><dt>Source row</dt><dd>{detail.transaction.source_row_number}</dd><dt>Description</dt><dd>{detail.transaction.description || '—'}</dd></dl></Panel><Panel title="Workflow"><div className="workflow"><p>Current state <Status value={detail.state} /></p>{canReview && <><label>Decision note<textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Document the rationale for this review decision…" /></label>{detail.state !== 'RESOLVED' && detail.state !== 'EXCEPTION' && detail.state !== 'UNDER_REVIEW' && <button className="button button-warning" disabled={busy} onClick={() => action('exception')}>Mark exception</button>}{(detail.state === 'EXCEPTION' || detail.state === 'UNDER_REVIEW') && <button className="button button-primary" disabled={busy} onClick={() => action('resolve')}>Resolve exception</button>}</>}</div></Panel></section><Panel title={`Candidates (${detail.candidates.length})`}>{detail.candidates.length ? <div className="candidate-list">{detail.candidates.map((candidate) => <article className="candidate" key={candidate.id}><div><div className="candidate-title"><strong>{candidate.target_transaction.reference || 'No reference'}</strong><Status value={candidate.review_status} /></div><p>{candidate.target_transaction.counterparty || 'No counterparty'} · {money(candidate.target_transaction.amount, candidate.target_transaction.currency)} · {candidate.target_transaction.transaction_date}</p><div className="score-line"><span>Composite score</span><strong>{Number(candidate.score).toFixed(2)}</strong><span className="score-track"><i style={{ width: `${Number(candidate.score) * 100}%` }} /></span></div></div><div className="candidate-actions"><button className="link-button" onClick={async () => { if (!runId) return; try { setEvidence(await reconciliationApi.candidate(session.organization.id, runId, candidate.id)) } catch (err) { setNotice({ type: 'error', message: apiError(err) }) } }}>View evidence</button>{canReview && candidate.review_status !== 'REJECTED' && detail.state !== 'RESOLVED' && <><button className="button button-primary button-small" disabled={busy} onClick={() => action('confirm', candidate.id)}>Confirm</button><button className="button button-secondary button-small" disabled={busy} onClick={() => action('reject', candidate.id)}>Reject</button></>}</div></article>)}</div> : <Empty title="No candidate matches" message="The deterministic engine found no transaction pairs above its configured threshold." />}</Panel><section className="content-grid"><Panel title="Investigation notes"><form className="note-form" onSubmit={addNote}><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add review context or supporting evidence…" /><button className="button button-secondary" disabled={busy || !note.trim()}>Add note</button></form>{detail.investigation_notes.length ? <ol className="timeline">{detail.investigation_notes.map((item) => <li key={item.id}><strong>{item.author_email || 'System user'}</strong><time>{dateTime(item.created_at)}</time><p>{item.content}</p></li>)}</ol> : <p className="muted">No investigation history yet.</p>}</Panel><Panel title="Audit history"><p className="muted">Decision notes and candidate review metadata are retained with this transaction for the demo audit trail.</p><dl className="detail-list"><dt>Created</dt><dd>{dateTime(detail.created_at)}</dd><dt>Candidate records</dt><dd>{detail.candidates.length}</dd><dt>Current state</dt><dd><Status value={detail.state} /></dd></dl></Panel></section>{evidence && <EvidenceModal candidate={evidence} onClose={() => setEvidence(null)} />}</>
}

function EvidenceModal({ candidate, onClose }: { candidate: Candidate; onClose: () => void }) { return <div className="modal-backdrop" role="presentation" onMouseDown={onClose}><section className="modal" role="dialog" aria-modal="true" aria-labelledby="evidence-title" onMouseDown={(event) => event.stopPropagation()}><header><div><p className="eyebrow">Deterministic evidence</p><h2 id="evidence-title">Candidate score {Number(candidate.score).toFixed(4)}</h2></div><button className="link-button" onClick={onClose}>Close</button></header><div className="evidence-grid">{[['Reference', candidate.reference_score], ['Amount', candidate.amount_score], ['Date', candidate.date_score], ['Counterparty', candidate.counterparty_score]].map(([name, score]) => <div key={String(name)}><span>{name}</span><strong>{String(score)}</strong></div>)}</div><pre>{JSON.stringify(candidate.evidence, null, 2)}</pre></section></div> }

function Audit({ session }: { session: Session }) { const [runs, setRuns] = useState<ReconciliationRun[]>([]); const [loading, setLoading] = useState(true); const [error, setError] = useState(''); const load = async () => { setLoading(true); try { setRuns((await reconciliationApi.runs(session.organization.id)).results); setError('') } catch (err) { setError(apiError(err)) } finally { setLoading(false) } }; useEffect(() => { void load() }, [session.organization.id]); if (loading) return <Loading label="Loading audit activity" />; if (error) return <ErrorState message={error} retry={load} />; return <><div className="page-heading"><div><p className="eyebrow">Audit history</p><h2>Reconciliation activity</h2><p className="muted">Run-level history with investigation notes available from each transaction result.</p></div></div><Panel title="Run activity">{runs.length ? <div className="table-wrap"><table><thead><tr><th>When</th><th>Event</th><th>Status</th><th>Summary</th><th /></tr></thead><tbody>{runs.map((run) => <tr key={run.id}><td>{dateTime(run.created_at)}</td><td>Reconciliation run</td><td><Status value={run.status} /></td><td>{run.matched_count} matched · {run.unmatched_count} unmatched · {run.conflict_count} conflicts</td><td><Link to={`/runs/${run.id}`}>Open results</Link></td></tr>)}</tbody></table></div> : <Empty title="No audit activity" message="Reconciliation activity will appear here once a run is created." />}</Panel></> }

function NoticeBanner({ notice }: { notice: Exclude<Notice, null> }) { return <div className={`notice notice-${notice.type}`} role={notice.type === 'error' ? 'alert' : 'status'}>{notice.message}</div> }

function Application() { const [session, setSession] = useState<Session | null>(null); const [loading, setLoading] = useState(Boolean(localStorage.getItem('access_token')))
  useEffect(() => { const restore = async () => { if (!localStorage.getItem('access_token')) { setLoading(false); return } try { const [user, organizations] = await Promise.all([auth.profile(), auth.organizations()]); if (organizations.results[0]) setSession({ user, organization: organizations.results[0] }) } catch { localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token') } finally { setLoading(false) } }; void restore() }, [])
  const logout = () => { localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); setSession(null) }
  if (loading) return <Loading label="Restoring your secure session" />
  return <Routes><Route path="/login" element={session ? <Navigate to="/" replace /> : <Login onLogin={setSession} />} /><Route path="*" element={session ? <Shell session={session} onLogout={logout}><Routes><Route index element={<Dashboard session={session} />} /><Route path="imports" element={<Imports session={session} />} /><Route path="imports/:importId" element={<ImportDetail session={session} />} /><Route path="runs" element={<Runs session={session} />} /><Route path="runs/:runId" element={<Results session={session} />} /><Route path="runs/:runId/transactions/:resultId" element={<Investigation session={session} />} /><Route path="audit" element={<Audit session={session} />} /><Route path="*" element={<Navigate to="/" replace />} /></Routes></Shell> : <Navigate to="/login" replace />} /></Routes>
}

export default function App() { return <BrowserRouter><Application /></BrowserRouter> }
