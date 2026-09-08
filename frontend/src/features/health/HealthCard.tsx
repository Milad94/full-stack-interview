import { Alert, Card, CardContent, Chip, Skeleton, Stack, Typography } from '@mui/material'

import { toApiError } from '@/lib/apiClient'
import { useHealthQuery } from './queries'

/**
 * Reference slice: api.ts -> queries.ts -> component. Every feature in this app
 * should look like this. Delete it once you have real features.
 */
export function HealthCard() {
  const { data, isPending, error } = useHealthQuery()

  return (
    <Card>
      <CardContent>
        <Stack spacing={1.5}>
          <Typography variant="overline" color="text.secondary">
            Backend
          </Typography>

          {isPending && <Skeleton variant="rounded" width={80} height={32} />}

          {error && <Alert severity="error">{toApiError(error).message}</Alert>}

          {data && <Chip label={data.status} color="success" sx={{ alignSelf: 'flex-start' }} />}
        </Stack>
      </CardContent>
    </Card>
  )
}
