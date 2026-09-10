import { apiClient } from '@/lib/apiClient'

export interface SyncRun {
  id: string
  status:
    'queued' | 'running' | 'succeeded' | 'failed' | 'skipped' | 'interrupted'
  created_at: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  records_touched: number
  error: string
}

export interface CurrencyAmount {
  currency: string
  amount: string
}

export interface Dashboard {
  total_invoices: number
  outstanding_by_currency: CurrencyAmount[]
  collected_this_month_by_currency: CurrencyAmount[]
  collection_period: { start: string; end: string; timezone: string }
  invoices_by_status: { status: string; count: number }[]
  last_sync: SyncRun | null
  generated_at: string
}

export function isSyncActive(run: SyncRun | null | undefined): boolean {
  return run?.status === 'queued' || run?.status === 'running'
}

export async function fetchDashboard() {
  const { data } = await apiClient.get<Dashboard>('/dashboard/')
  return data
}

export async function startSync() {
  const { data } = await apiClient.post<SyncRun>('/sync-runs/')
  return data
}

export async function fetchSyncRun(id: string) {
  const { data } = await apiClient.get<SyncRun>(`/sync-runs/${id}/`)
  return data
}
