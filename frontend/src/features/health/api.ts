import { apiClient } from '@/lib/apiClient'

export interface HealthResponse {
  status: string
}

export async function fetchHealth(): Promise<HealthResponse> {
  const { data } = await apiClient.get<HealthResponse>('/health/')
  return data
}
