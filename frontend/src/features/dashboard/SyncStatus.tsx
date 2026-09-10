import { Alert, Chip, Stack, Typography } from '@mui/material'

import { formatDate } from '@/lib/format'
import type { SyncRun } from './api'

const statusColors = {
  queued: 'default',
  running: 'info',
  succeeded: 'success',
  failed: 'error',
  skipped: 'warning',
  interrupted: 'error',
} as const

export function SyncStatus({ run }: { run: SyncRun }) {
  return (
    <Stack spacing={1}>
      <Chip
        label={run.status}
        color={statusColors[run.status]}
        sx={{ alignSelf: 'flex-start' }}
      />
      <Typography variant="body2">
        Requested: {formatDate(run.created_at)}
      </Typography>
      <Typography variant="body2">
        Started: {formatDate(run.started_at)}
      </Typography>
      <Typography variant="body2">
        Finished: {formatDate(run.finished_at)}
      </Typography>
      <Typography variant="body2">
        {run.records_touched.toLocaleString()} records created or updated
        {run.duration_seconds !== null &&
          ` · ${Math.round(run.duration_seconds)} seconds`}
      </Typography>
      {run.status === 'queued' && (
        <Alert severity="info">Queued. Waiting for a worker to start.</Alert>
      )}
      {run.status === 'running' && (
        <Alert severity="info">
          Sync is running. This page updates automatically.
        </Alert>
      )}
      {run.status === 'skipped' && (
        <Alert severity="warning">
          Skipped because another sync was already running.
        </Alert>
      )}
      {run.error && (
        <Alert severity="error" sx={{ overflowWrap: 'anywhere' }}>
          {run.error}
        </Alert>
      )}
    </Stack>
  )
}
