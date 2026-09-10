import { apiClient } from '@/lib/apiClient'

export interface Page<T> {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export interface Invoice {
  id: number
  external_id: string
  customer_name: string
  currency: string
}

export interface Adjustment {
  id: number
  invoice: number
  invoice_external_id: string
  customer_name: string
  currency: string
  amount: string
  reason: string
  created_at: string
  updated_at: string
}

export interface AdjustmentInput {
  invoice: number
  amount: string
  reason: string
}

export interface AdjustmentFilters {
  page: number
  page_size: number
  search: string
  currency: string
}

export async function fetchAdjustments(filters: AdjustmentFilters) {
  const { data } = await apiClient.get<Page<Adjustment>>('/adjustments/', {
    params: filters,
  })
  return data
}

export async function fetchInvoices(search: string) {
  const { data } = await apiClient.get<Page<Invoice>>('/invoices/', {
    params: { search, page_size: 25 },
  })
  return data
}

export async function saveAdjustment({
  id,
  values,
}: {
  id?: number
  values: AdjustmentInput
}) {
  const { data } =
    id === undefined
      ? await apiClient.post<Adjustment>('/adjustments/', values)
      : await apiClient.patch<Adjustment>(`/adjustments/${id}/`, values)
  return data
}

export async function deleteAdjustment(id: number) {
  await apiClient.delete(`/adjustments/${id}/`)
}
