import { Controller, useForm } from 'react-hook-form'
import { yupResolver } from '@hookform/resolvers/yup'
import { Button, MenuItem, Stack, TextField } from '@mui/material'

import { filterSchema, type FilterValues } from './schema'

export function AdjustmentFilters({
  onApply,
}: {
  onApply: (values: FilterValues) => void
}) {
  const { control, handleSubmit, reset } = useForm<FilterValues>({
    resolver: yupResolver(filterSchema),
    defaultValues: { search: '', currency: '' },
  })

  return (
    <Stack
      component="form"
      onSubmit={handleSubmit(onApply)}
      direction={{ xs: 'column', sm: 'row' }}
      spacing={2}
    >
      <Controller
        name="search"
        control={control}
        render={({ field }) => (
          <TextField
            {...field}
            label="Search adjustments"
            placeholder="Reason, invoice ID or customer"
            size="small"
            sx={{ flexGrow: 1 }}
          />
        )}
      />
      <Controller
        name="currency"
        control={control}
        render={({ field }) => (
          <TextField
            {...field}
            select
            label="Currency"
            size="small"
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="">All currencies</MenuItem>
            {['USD', 'EUR', 'GBP'].map((currency) => (
              <MenuItem key={currency} value={currency}>
                {currency}
              </MenuItem>
            ))}
          </TextField>
        )}
      />
      <Button type="submit" variant="outlined">
        Apply
      </Button>
      <Button
        onClick={() => {
          reset()
          onApply({ search: '', currency: '' })
        }}
      >
        Clear
      </Button>
    </Stack>
  )
}
