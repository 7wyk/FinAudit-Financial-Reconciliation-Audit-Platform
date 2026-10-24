import apiClient from './client'

export type Page<T> = { count: number; next: string | null; previous: string | null; results: T[] }

export type Organization = { id: string; name: string; slug: string }
export type User = { id: string; email: string; username: string; first_name: string; last_name: string }
export type ImportRecord = {
  id: string; original_filename: string; file_type: string; file_size: number; source: string
  status: string; total_rows: number; valid_rows: number; rejected_rows: number
  error_message: string; error_count: number; created_at: string; processing_completed_at: string | null
}
export type ReconciliationRun = {
  id: string; source_import: string; target_import: string; status: string; total_source: number
  total_target: number; matched_count: number; unmatched_count: number; conflict_count: number
  exception_count: number; started_at: string | null; completed_at: string | null; created_at: string
}
export type Transaction = {
  id: string; external_id: string; transaction_date: string; amount: string; currency: string
  reference: string; description: string; counterparty: string; source: string; source_row_number: number
}
export type Result = { id: string; transaction: Transaction; side: 'SOURCE' | 'TARGET'; state: string; candidate_count: number; created_at: string }
export type Candidate = {
  id: string; score: string; reference_score: string; amount_score: string; date_score: string
  counterparty_score: string; evidence: Record<string, unknown>; is_selected: boolean; review_status: string
  reviewed_at: string | null; source_transaction: Transaction; target_transaction: Transaction
}
export type Note = { id: string; author_email: string; content: string; created_at: string }
export type ResultDetail = Result & { candidates: Candidate[]; investigation_notes: Note[] }

export const unwrap = <T>(data: T[] | Page<T>): Page<T> => Array.isArray(data)
  ? { count: data.length, next: null, previous: null, results: data }
  : data

export const apiError = (error: unknown) => {
  const response = error as { response?: { data?: { error?: { message?: string }; detail?: string } } }
  return response.response?.data?.error?.message || response.response?.data?.detail || 'Something went wrong. Please try again.'
}

export const auth = {
  login: async (email: string, password: string) => (await apiClient.post('/auth/token/', { email, password })).data as { access: string; refresh: string },
  profile: async () => (await apiClient.get('/auth/profile/')).data as User,
  organizations: async () => unwrap<Organization>((await apiClient.get('/organizations/')).data),
}

export const importsApi = {
  list: async (orgId: string) => unwrap<ImportRecord>((await apiClient.get(`/organizations/${orgId}/imports/`)).data),
  detail: async (orgId: string, importId: string) => (await apiClient.get(`/organizations/${orgId}/imports/${importId}/`)).data as ImportRecord,
  upload: async (orgId: string, file: File, source: string) => {
    const form = new FormData()
    form.append('file', file)
    form.append('source', source)
    return (await apiClient.post(`/organizations/${orgId}/imports/upload/`, form, { headers: { 'Content-Type': 'multipart/form-data' } })).data as ImportRecord
  },
}

export const reconciliationApi = {
  runs: async (orgId: string) => unwrap<ReconciliationRun>((await apiClient.get(`/organizations/${orgId}/reconciliation/runs/`)).data),
  start: async (orgId: string, source_import: string, target_import: string) => (await apiClient.post(`/organizations/${orgId}/reconciliation/runs/`, { source_import, target_import })).data as ReconciliationRun,
  results: async (orgId: string, runId: string) => unwrap<Result>((await apiClient.get(`/organizations/${orgId}/reconciliation/runs/${runId}/results/`)).data),
  transaction: async (orgId: string, runId: string, id: string) => (await apiClient.get(`/organizations/${orgId}/reconciliation/runs/${runId}/transactions/${id}/`)).data as ResultDetail,
  candidate: async (orgId: string, runId: string, id: string) => (await apiClient.get(`/organizations/${orgId}/reconciliation/runs/${runId}/candidates/${id}/`)).data as Candidate,
  action: async (orgId: string, runId: string, resultId: string, action: 'confirm' | 'reject' | 'exception' | 'resolve', body: { candidate_id?: string; note?: string }) =>
    (await apiClient.post(`/organizations/${orgId}/reconciliation/runs/${runId}/transactions/${resultId}/${action}/`, body)).data as ResultDetail,
  note: async (orgId: string, runId: string, resultId: string, content: string) =>
    (await apiClient.post(`/organizations/${orgId}/reconciliation/runs/${runId}/transactions/${resultId}/notes/`, { content })).data as Note,
}

export const assistantApi = {
  ask: async (orgId: string, body: { question: string; run_id?: string; transaction_reconciliation_id?: string; conversation?: { role: 'user' | 'assistant'; content: string }[] }) =>
    (await apiClient.post(`/organizations/${orgId}/ai/assist/`, body)).data as { answer: string },
}
