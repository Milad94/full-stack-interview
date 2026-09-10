import {
  Alert,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
} from '@mui/material'

import { toApiError } from '@/lib/apiClient'
import { formatMoney } from '@/lib/format'
import type { Adjustment } from './api'
import { useDeleteAdjustment } from './queries'

export function DeleteAdjustmentDialog({
  adjustment,
  onClose,
  onDeleted,
}: {
  adjustment: Adjustment
  onClose: () => void
  onDeleted: () => void
}) {
  const deletion = useDeleteAdjustment()

  return (
    <Dialog
      open
      fullWidth
      maxWidth="xs"
      onClose={deletion.isPending ? undefined : onClose}
      aria-labelledby="delete-adjustment-title"
    >
      <DialogTitle id="delete-adjustment-title">Delete adjustment?</DialogTitle>
      <DialogContent>
        <DialogContentText>
          Delete {formatMoney(adjustment.amount, adjustment.currency)} against{' '}
          {adjustment.invoice_external_id}? This cannot be undone.
        </DialogContentText>
        {deletion.error && (
          <Alert severity="error" sx={{ mt: 2 }}>
            {toApiError(deletion.error).message}
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={deletion.isPending}>
          Cancel
        </Button>
        <Button
          color="error"
          variant="contained"
          disabled={deletion.isPending}
          onClick={() =>
            deletion.mutate(adjustment.id, { onSuccess: onDeleted })
          }
        >
          {deletion.isPending ? 'Deleting…' : 'Delete'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
