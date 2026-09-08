import { useQuery } from '@tanstack/react-query'

import { fetchHealth } from './api'

export const healthKeys = {
  all: ['health'] as const,
}

export function useHealthQuery() {
  return useQuery({
    queryKey: healthKeys.all,
    queryFn: fetchHealth,
  })
}
