import { useEffect } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { adjustmentKeys, invoiceKeys } from '@/features/adjustments/queries'
import { fetchDashboard, fetchSyncRun, isSyncActive, startSync } from './api'

export const dashboardKeys = {
  all: ['dashboard'] as const,
  run: (id: string | null) => ['sync-run', id] as const,
}

export function useDashboardQuery() {
  return useQuery({
    queryKey: dashboardKeys.all,
    queryFn: fetchDashboard,
    refetchInterval: (query) =>
      isSyncActive(query.state.data?.last_sync) ? 3000 : 15000,
  })
}

export function useStartSync() {
  return useMutation({ mutationFn: startSync, retry: false })
}

export function useSyncRunQuery(id: string | null) {
  const client = useQueryClient()
  const query = useQuery({
    queryKey: dashboardKeys.run(id),
    queryFn: () => {
      if (!id) throw new Error('No sync selected.')
      return fetchSyncRun(id)
    },
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) =>
      !query.state.data || isSyncActive(query.state.data) ? 3000 : false,
  })

  const completedId =
    query.data && !isSyncActive(query.data) ? query.data.id : null
  useEffect(() => {
    if (!completedId) return
    // Failed runs can also have committed pages, so refresh on every final outcome.
    void client.invalidateQueries({ queryKey: dashboardKeys.all })
    void client.invalidateQueries({ queryKey: invoiceKeys.all })
    void client.invalidateQueries({ queryKey: adjustmentKeys.all })
  }, [client, completedId])

  return query
}
