import { useEffect, useState } from 'react'
import { Controller, useForm, useWatch } from 'react-hook-form'
import { yupResolver } from '@hookform/resolvers/yup'
import {
  Alert,
  Autocomplete,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Skeleton,
  Stack,
  TextField,
  Typography,
} from '@mui/material'

import { toApiError } from '@/lib/apiClient'
import type { Adjustment } from './api'
import { useInvoicesQuery, useSaveAdjustment } from './queries'
import { adjustmentSchema, type AdjustmentFormValues } from './schema'

export function AdjustmentForm({
  adjustment,
  onClose,
  onSaved,
}: {
  adjustment: Adjustment | null
  onClose: () => void
  onSaved: () => void
}) {
  const save = useSaveAdjustment()
  const { control, handleSubmit, setError, reset, formState } =
    useForm<AdjustmentFormValues>({
      resolver: yupResolver(adjustmentSchema),
      defaultValues: {
        invoice: adjustment
          ? {
              id: adjustment.invoice,
              external_id: adjustment.invoice_external_id,
              customer_name: adjustment.customer_name,
              currency: adjustment.currency,
            }
          : undefined,
        invoiceSearch: '',
        amount: adjustment?.amount ?? '',
        reason: adjustment?.reason ?? '',
      },
    })
  const selectedInvoice = useWatch({ control, name: 'invoice' })
  const search = useWatch({ control, name: 'invoiceSearch' })
  const [debouncedSearch, setDebouncedSearch] = useState(search)
  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedSearch(search), 300)
    return () => window.clearTimeout(timer)
  }, [search])
  const invoices = useInvoicesQuery(debouncedSearch)
  const currency =
    adjustment && selectedInvoice?.id === adjustment.invoice
      ? adjustment.currency
      : selectedInvoice?.currency

  async function submit(values: AdjustmentFormValues) {
    try {
      await save.mutateAsync({
        id: adjustment?.id,
        values: {
          invoice: values.invoice.id,
          amount: values.amount,
          reason: values.reason,
        },
      })
      reset()
      onSaved()
    } catch (error) {
      const apiError = toApiError(error)
      const generalErrors: string[] = []
      for (const [field, messages] of Object.entries(
        apiError.fieldErrors ?? {},
      )) {
        if (field === 'invoice' || field === 'amount' || field === 'reason') {
          setError(
            field,
            { type: 'server', message: messages.join(' ') },
            { shouldFocus: true },
          )
        } else {
          generalErrors.push(messages.join(' '))
        }
      }
      if (!apiError.fieldErrors || generalErrors.length) {
        setError('root.server', {
          message: generalErrors.join(' ') || apiError.message,
        })
      }
    }
  }

  return (
    <Dialog
      open
      fullWidth
      maxWidth="sm"
      onClose={formState.isSubmitting ? undefined : onClose}
      aria-labelledby="adjustment-form-title"
    >
      <form onSubmit={handleSubmit(submit)} noValidate>
        <DialogTitle id="adjustment-form-title">
          {adjustment ? 'Edit adjustment' : 'New adjustment'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            {formState.errors.root?.server && (
              <Alert severity="error">
                {formState.errors.root.server.message}
              </Alert>
            )}
            {invoices.isPending && (
              <Skeleton variant="rounded" sx={{ height: 40 }} />
            )}
            {invoices.error && (
              <Alert
                severity="error"
                action={
                  <Button
                    color="inherit"
                    onClick={() => void invoices.refetch()}
                  >
                    Retry
                  </Button>
                }
              >
                Could not load invoices: {toApiError(invoices.error).message}
              </Alert>
            )}
            <Controller
              name="invoice"
              control={control}
              render={({ field, fieldState }) => (
                <Controller
                  name="invoiceSearch"
                  control={control}
                  render={({ field: searchField }) => (
                    <Autocomplete
                      options={invoices.data?.results ?? []}
                      value={field.value ?? null}
                      onChange={(_, value) => field.onChange(value)}
                      onBlur={field.onBlur}
                      onInputChange={(_, value, reason) => {
                        if (reason === 'input' || reason === 'clear')
                          searchField.onChange(value)
                      }}
                      getOptionLabel={(invoice) =>
                        `${invoice.external_id} · ${invoice.customer_name} · ${invoice.currency}`
                      }
                      isOptionEqualToValue={(option, value) =>
                        option.id === value.id
                      }
                      filterOptions={(options) => options}
                      loading={invoices.isFetching}
                      disabled={formState.isSubmitting}
                      noOptionsText={
                        invoices.error
                          ? 'Invoice search unavailable.'
                          : 'No invoices found. Try another search or sync first.'
                      }
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          inputRef={field.ref}
                          label="Invoice"
                          required
                          error={Boolean(fieldState.error)}
                          helperText={
                            fieldState.error?.message ??
                            'Search by invoice ID or customer. Shows up to 25 matches; type to narrow results.'
                          }
                        />
                      )}
                    />
                  )}
                />
              )}
            />
            <Controller
              name="amount"
              control={control}
              render={({ field, fieldState }) => (
                <TextField
                  {...field}
                  label={currency ? `Amount (${currency})` : 'Amount'}
                  required
                  fullWidth
                  disabled={formState.isSubmitting}
                  error={Boolean(fieldState.error)}
                  helperText={
                    fieldState.error?.message ??
                    'Negative reduces the amount; positive increases it. Zero is not allowed.'
                  }
                  slotProps={{ htmlInput: { inputMode: 'decimal' } }}
                />
              )}
            />
            {adjustment &&
              selectedInvoice &&
              selectedInvoice.id !== adjustment.invoice && (
                <Alert severity="warning">
                  Changing the invoice uses {selectedInvoice.currency} for the
                  entered amount. No currency conversion is performed.
                </Alert>
              )}
            <Controller
              name="reason"
              control={control}
              render={({ field, fieldState }) => (
                <TextField
                  {...field}
                  label="Reason"
                  required
                  fullWidth
                  multiline
                  minRows={3}
                  disabled={formState.isSubmitting}
                  error={Boolean(fieldState.error)}
                  helperText={
                    fieldState.error?.message ??
                    `${field.value.length}/1,000 characters`
                  }
                />
              )}
            />
            <Typography variant="body2" color="text.secondary">
              Adjustments are recorded separately and do not change the
              dashboard totals.
            </Typography>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={onClose} disabled={formState.isSubmitting}>
            Cancel
          </Button>
          <Button
            type="submit"
            variant="contained"
            disabled={formState.isSubmitting}
          >
            {formState.isSubmitting ? 'Saving…' : 'Save adjustment'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
