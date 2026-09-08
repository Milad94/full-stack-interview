import { Alert, Stack, Typography } from '@mui/material'

export function AdjustmentsPage() {
  return (
    <Stack spacing={3}>
      <Typography variant="h1">Manual adjustments</Typography>

      <Alert severity="info">
        Task 3 lives here: a react-hook-form + yup form, and a paginated, filterable table with
        edit/delete. See the README.
      </Alert>
    </Stack>
  )
}
