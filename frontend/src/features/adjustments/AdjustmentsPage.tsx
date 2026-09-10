import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  Skeleton,
  Snackbar,
  Stack,
  Typography,
} from '@mui/material'
import AddIcon from '@mui/icons-material/Add'
import DeleteIcon from '@mui/icons-material/DeleteOutline'
import EditIcon from '@mui/icons-material/EditOutlined'
import {
  DataGrid,
  GridActionsCellItem,
  type GridColDef,
} from '@mui/x-data-grid'

import { toApiError } from '@/lib/apiClient'
import { formatDate, formatMoney } from '@/lib/format'
import type { Adjustment } from './api'
import { useAdjustmentsQuery } from './queries'
import type { FilterValues } from './schema'
import { AdjustmentFilters } from './AdjustmentFilters'
import { AdjustmentForm } from './AdjustmentForm'
import { DeleteAdjustmentDialog } from './DeleteAdjustmentDialog'

function EmptyAdjustments() {
  return (
    <Stack
      sx={{ height: '100%', p: 2 }}
      justifyContent="center"
      alignItems="center"
    >
      <Typography variant="body2">
        No adjustments found. Create one or change your filters.
      </Typography>
    </Stack>
  )
}

export function AdjustmentsPage() {
  const [pagination, setPagination] = useState({ page: 0, pageSize: 25 })
  const [filters, setFilters] = useState<FilterValues>({
    search: '',
    currency: '',
  })
  const [form, setForm] = useState<{ adjustment: Adjustment | null } | null>(
    null,
  )
  const [deleting, setDeleting] = useState<Adjustment | null>(null)
  const [notice, setNotice] = useState('')
  const query = useAdjustmentsQuery({
    ...filters,
    page: pagination.page + 1,
    page_size: pagination.pageSize,
  })
  const columns: GridColDef<Adjustment>[] = [
    { field: 'invoice_external_id', headerName: 'Invoice', width: 160 },
    { field: 'customer_name', headerName: 'Customer', minWidth: 160, flex: 1 },
    {
      field: 'amount',
      headerName: 'Amount',
      width: 230,
      renderCell: ({ row }) => formatMoney(row.amount, row.currency),
    },
    { field: 'reason', headerName: 'Reason', minWidth: 220, flex: 2 },
    {
      field: 'created_at',
      headerName: 'Created',
      width: 190,
      valueFormatter: (value: string) => formatDate(value),
    },
    {
      field: 'updated_at',
      headerName: 'Updated',
      width: 190,
      valueFormatter: (value: string) => formatDate(value),
    },
    {
      field: 'actions',
      type: 'actions',
      headerName: 'Actions',
      width: 100,
      getActions: ({ row }) => [
        <GridActionsCellItem
          icon={<EditIcon />}
          label={`Edit adjustment ${row.id}`}
          onClick={() => setForm({ adjustment: row })}
          disabled={query.isFetching}
        />,
        <GridActionsCellItem
          icon={<DeleteIcon />}
          label={`Delete adjustment ${row.id}`}
          onClick={() => setDeleting(row)}
          disabled={query.isFetching}
        />,
      ],
    },
  ]

  return (
    <Stack spacing={3}>
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        justifyContent="space-between"
        alignItems={{ sm: 'center' }}
      >
        <Typography variant="h1">Manual adjustments</Typography>
        <Button
          variant="contained"
          startIcon={<AddIcon />}
          onClick={() => setForm({ adjustment: null })}
        >
          New adjustment
        </Button>
      </Stack>
      <Typography variant="body2" color="text.secondary">
        Record corrections against synced invoices. These entries do not change
        vendor balances or dashboard totals.
      </Typography>
      <AdjustmentFilters
        onApply={(values) => {
          setFilters(values)
          setPagination((current) => ({ ...current, page: 0 }))
        }}
      />
      {query.isPending && <Skeleton variant="rounded" sx={{ height: 300 }} />}
      {query.error && (
        <Alert
          severity="error"
          action={
            <Button
              color="inherit"
              onClick={() => {
                if (
                  pagination.page > 0 &&
                  toApiError(query.error).status === 404
                )
                  setPagination((current) => ({ ...current, page: 0 }))
                else void query.refetch()
              }}
            >
              {toApiError(query.error).status === 404 && pagination.page > 0
                ? 'First page'
                : 'Retry'}
            </Button>
          }
        >
          {toApiError(query.error).message}
        </Alert>
      )}
      {query.data && (
        <Box sx={{ height: 560, width: '100%' }}>
          <DataGrid
            aria-label="Manual adjustments"
            rows={query.data.results}
            columns={columns.map((column) => ({
              ...column,
              sortable: false,
              filterable: false,
            }))}
            rowCount={query.data.count}
            loading={query.isFetching}
            paginationMode="server"
            filterMode="server"
            paginationModel={pagination}
            onPaginationModelChange={setPagination}
            pageSizeOptions={[10, 25, 50, 100]}
            disableRowSelectionOnClick
            disableColumnMenu
            slots={{ noRowsOverlay: EmptyAdjustments }}
            slotProps={{
              loadingOverlay: {
                variant: 'linear-progress',
                noRowsVariant: 'skeleton',
              },
            }}
          />
        </Box>
      )}
      {form && (
        <AdjustmentForm
          adjustment={form.adjustment}
          onClose={() => setForm(null)}
          onSaved={() => {
            setForm(null)
            setPagination((current) => ({ ...current, page: 0 }))
            setNotice('Adjustment saved.')
          }}
        />
      )}
      {deleting && (
        <DeleteAdjustmentDialog
          adjustment={deleting}
          onClose={() => setDeleting(null)}
          onDeleted={() => {
            setDeleting(null)
            setPagination((current) => ({ ...current, page: 0 }))
            setNotice('Adjustment deleted.')
          }}
        />
      )}
      <Snackbar
        open={Boolean(notice)}
        autoHideDuration={4000}
        onClose={() => setNotice('')}
        message={notice}
      />
    </Stack>
  )
}
