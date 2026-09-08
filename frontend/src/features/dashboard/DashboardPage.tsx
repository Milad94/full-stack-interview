import { Alert, Box, Stack, Typography } from '@mui/material'

import { HealthCard } from '@/features/health/HealthCard'

export function DashboardPage() {
  return (
    <Stack spacing={3}>
      <Typography variant="h1">Dashboard</Typography>

      <Alert severity="info">
        Task 2 lives here: summary figures, one chart, sync status, and a &ldquo;Sync now&rdquo; action.
        See the README.
      </Alert>

      <Box sx={{ maxWidth: 260 }}>
        <HealthCard />
      </Box>
    </Stack>
  )
}
