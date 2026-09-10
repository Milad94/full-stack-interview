import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query'

import {
  deleteAdjustment,
  fetchAdjustments,
  fetchInvoices,
  saveAdjustment,
  type AdjustmentFilters,
} from './api'

export const adjustmentKeys = {
  all: ['adjustments'] as const,
  list: (filters: AdjustmentFilters) =>
    [...adjustmentKeys.all, filters] as const,
}

export const invoiceKeys = {
  all: ['invoices'] as const,
  search: (search: string) => [...invoiceKeys.all, search] as const,
}

export function useAdjustmentsQuery(filters: AdjustmentFilters) {
  return useQuery({
    queryKey: adjustmentKeys.list(filters),
    queryFn: () => fetchAdjustments(filters),
    placeholderData: keepPreviousData,
  })
}

export function useInvoicesQuery(search: string) {
  return useQuery({
    queryKey: invoiceKeys.search(search),
    queryFn: () => fetchInvoices(search),
  })
}

export function useSaveAdjustment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: saveAdjustment,
    onSuccess: () => client.invalidateQueries({ queryKey: adjustmentKeys.all }),
  })
}

export function useDeleteAdjustment() {
  const client = useQueryClient()
  return useMutation({
    mutationFn: deleteAdjustment,
    onSuccess: () => client.invalidateQueries({ queryKey: adjustmentKeys.all }),
  })
}
