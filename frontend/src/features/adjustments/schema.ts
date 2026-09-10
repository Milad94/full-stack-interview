import * as yup from 'yup'

export const adjustmentSchema = yup.object({
  invoice: yup
    .object({
      id: yup.number().required(),
      external_id: yup.string().required(),
      customer_name: yup.string().defined(),
      currency: yup.string().required(),
    })
    .nullable()
    .default(null)
    .required('Pick an invoice.'),
  invoiceSearch: yup.string().defined(),
  amount: yup
    .string()
    .trim()
    .required('Enter an amount.')
    .matches(
      /^[+-]?\d{1,16}(\.\d{1,2})?$/,
      'Use up to 16 integer digits and 2 decimal places.',
    )
    .test(
      'nonzero',
      'Amount must not be zero.',
      (value) => !value || /[1-9]/.test(value),
    ),
  reason: yup
    .string()
    .trim()
    .required('Enter a reason.')
    .max(1000, 'Use at most 1,000 characters.'),
})

export type AdjustmentFormValues = yup.InferType<typeof adjustmentSchema>

export const filterSchema = yup.object({
  search: yup.string().trim().defined(),
  currency: yup.string().oneOf(['', 'USD', 'EUR', 'GBP']).defined(),
})

export type FilterValues = yup.InferType<typeof filterSchema>
