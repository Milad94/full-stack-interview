import axios, { AxiosError } from 'axios'

export const apiClient = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '/api',
  timeout: 15_000,
  headers: { 'Content-Type': 'application/json' },
})

/** Field-level errors as DRF returns them: `{ amount: ["This field is required."] }`. */
export type FieldErrors = Record<string, string[]>

export interface ApiError {
  message: string
  status?: number
  fieldErrors?: FieldErrors
}

export function toApiError(error: unknown): ApiError {
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const data = error.response?.data as Record<string, unknown> | undefined

    if (data && typeof data === 'object' && !Array.isArray(data)) {
      const fieldErrors: FieldErrors = {}
      for (const [key, value] of Object.entries(data)) {
        if (Array.isArray(value)) fieldErrors[key] = value.map(String)
      }
      if (Object.keys(fieldErrors).length > 0) {
        return { message: 'Please fix the highlighted fields.', status, fieldErrors }
      }
      if (typeof data.detail === 'string') return { message: data.detail, status }
    }

    return { message: error.message, status }
  }

  return { message: error instanceof Error ? error.message : 'Unexpected error' }
}
