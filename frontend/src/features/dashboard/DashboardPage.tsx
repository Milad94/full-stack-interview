import { useState } from 'react'
import {
  Alert,
  Button,
  Card,
  CardContent,
  Grid,
  Skeleton,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material'
import SyncIcon from '@mui/icons-material/Sync'
import { BarChart } from '@mui/x-charts/BarChart'
import { useTheme } from '@mui/material/styles'

import { toApiError } from '@/lib/apiClient'
import { formatDate, formatMoney } from '@/lib/format'
import { isSyncActive, type CurrencyAmount } from './api'
import { useDashboardQuery, useStartSync, useSyncRunQuery } from './queries'
import { SyncStatus } from './SyncStatus'

function MoneySummary({
  title,
  rows,
}: {
  title: string
  rows: CurrencyAmount[]
}) {
  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <Stack spacing={1}>
          <Typography variant="h2">{title}</Typography>
          {rows.length === 0 && (
            <Typography variant="body2" color="text.secondary">
              No matching amounts.
            </Typography>
          )}
          {rows.map((row) => (
            <Typography
              key={row.currency}
              variant="h6"
              sx={{ overflowWrap: 'anywhere' }}
            >
              {formatMoney(row.amount, row.currency)}
            </Typography>
          ))}
        </Stack>
      </CardContent>
    </Card>
  )
}

export function DashboardPage() {
  const theme = useTheme()
  const dashboard = useDashboardQuery()
  const startSync = useStartSync()
  const [runId, setRunId] = useState<string | null>(() =>
    sessionStorage.getItem('accounting.syncRunId'),
  )
  const [notice, setNotice] = useState(false)
  const run = useSyncRunQuery(runId)
  const data = dashboard.data
  const trackedRun =
    run.data ?? (startSync.data?.id === runId ? startSync.data : undefined)
  const lastRun = data?.last_sync
  const displayedRun =
    trackedRun &&
    (!lastRun ||
      trackedRun.id === lastRun.id ||
      isSyncActive(trackedRun) ||
      Date.parse(trackedRun.created_at) >
        Date.parse(lastRun.started_at ?? lastRun.created_at))
      ? trackedRun
      : lastRun
  const busy =
    startSync.isPending ||
    (Boolean(runId) && run.isPending && !run.error) ||
    isSyncActive(trackedRun) ||
    isSyncActive(data?.last_sync)

  function syncNow() {
    startSync.mutate(undefined, {
      onSuccess: (created) => {
        sessionStorage.setItem('accounting.syncRunId', created.id)
        setRunId(created.id)
        setNotice(true)
      },
    })
  }

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ sm: 'center' }}
      >
        <Typography variant="h1">Dashboard</Typography>
        <Button
          variant="contained"
          startIcon={<SyncIcon />}
          disabled={busy}
          onClick={syncNow}
        >
          {startSync.isPending
            ? 'Requesting sync…'
            : busy
              ? 'Sync in progress'
              : 'Sync now'}
        </Button>
      </Stack>
      {startSync.error && (
        <Alert severity="error">
          {toApiError(startSync.error).message} Check sync status before trying
          again; the request may already have reached the server.
        </Alert>
      )}
      {dashboard.isPending && (
        <Skeleton variant="rounded" sx={{ height: 200 }} />
      )}
      {dashboard.error && (
        <Alert
          severity="error"
          action={
            <Button color="inherit" onClick={() => void dashboard.refetch()}>
              Retry
            </Button>
          }
        >
          {toApiError(dashboard.error).message}
          {data && ' Showing previously loaded figures.'}
        </Alert>
      )}
      {data && (
        <>
          <Grid container spacing={2}>
            <Grid size={{ xs: 12, md: 4 }}>
              <Card sx={{ height: '100%' }}>
                <CardContent>
                  <Typography variant="h2" gutterBottom>
                    Total invoices
                  </Typography>
                  <Typography variant="h4">
                    {data.total_invoices.toLocaleString()}
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <MoneySummary
                title="Outstanding"
                rows={data.outstanding_by_currency}
              />
            </Grid>
            <Grid size={{ xs: 12, md: 4 }}>
              <MoneySummary
                title="Collected this month"
                rows={data.collected_this_month_by_currency}
              />
            </Grid>
          </Grid>
          <Typography variant="body2" color="text.secondary">
            Collections are gross payments, excluding refunds and fees. Period:{' '}
            {data.collection_period.start.slice(0, 10)} to{' '}
            {data.collection_period.end.slice(0, 10)} (end exclusive,{' '}
            {data.collection_period.timezone}). Amounts are separate by
            currency.
          </Typography>
          {data.total_invoices === 0 && (
            <Alert severity="info">
              No invoices have been synced yet. Use Sync now to load accounting
              data.
            </Alert>
          )}
        </>
      )}
      <Grid container spacing={2}>
        {data && (
          <Grid size={{ xs: 12, md: 7 }}>
            <Card>
              <CardContent>
                <Typography variant="h2" gutterBottom>
                  Invoices by status
                </Typography>
                {data.invoices_by_status.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    No invoices to chart.
                  </Typography>
                ) : (
                  <BarChart
                    height={300}
                    xAxis={[
                      {
                        scaleType: 'band',
                        height: 40,
                        data: data.invoices_by_status.map((row) => row.status),
                      },
                    ]}
                    yAxis={[{ min: 0, tickMinStep: 1 }]}
                    series={[
                      {
                        data: data.invoices_by_status.map((row) => row.count),
                        label: 'Invoices',
                        color: theme.palette.primary.main,
                      },
                    ]}
                  />
                )}
              </CardContent>
            </Card>
          </Grid>
        )}
        <Grid size={{ xs: 12, md: data ? 5 : 12 }}>
          <Card>
            <CardContent>
              <Typography variant="h2" gutterBottom>
                Sync status
              </Typography>
              {((runId && run.isPending && !trackedRun) ||
                dashboard.isPending) && (
                <Skeleton variant="rounded" sx={{ height: 100 }} />
              )}
              {run.error && (
                <Alert
                  severity="error"
                  action={
                    <Button color="inherit" onClick={() => void run.refetch()}>
                      Retry
                    </Button>
                  }
                >
                  Could not refresh this sync: {toApiError(run.error).message}
                </Alert>
              )}
              {displayedRun && <SyncStatus run={displayedRun} />}
              {data && !displayedRun && !runId && (
                <Typography variant="body2" color="text.secondary">
                  No sync has started yet.
                </Typography>
              )}
            </CardContent>
          </Card>
        </Grid>
      </Grid>
      {data && (
        <Typography variant="caption" color="text.secondary">
          Dashboard refreshed: {formatDate(data.generated_at)}. Changes from a
          running sync may appear before it finishes.
        </Typography>
      )}
      <Snackbar
        open={notice}
        autoHideDuration={4000}
        onClose={() => setNotice(false)}
        message="Sync request queued."
      />
    </Stack>
  )
}
