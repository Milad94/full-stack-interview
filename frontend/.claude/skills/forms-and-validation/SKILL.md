---
name: forms-and-validation
description: How to build forms in this frontend — react-hook-form for state, yup for schemas, MUI Controller-wrapped inputs, DRF field errors mapped back onto fields. Load before writing any form, input, or validation rule.
---

# Forms and validation

**react-hook-form for form state. yup for validation. Nothing else.** No Formik, no zod, no
`useState` per field, no manual `onChange` handlers, no validation logic inside components.

## The shape of a form

```tsx
import { useForm } from 'react-hook-form'
import { yupResolver } from '@hookform/resolvers/yup'
import * as yup from 'yup'

const schema = yup.object({
  invoiceId: yup.string().required('Pick an invoice.'),
  amount: yup
    .number()
    .typeError('Amount must be a number.')
    .required('Amount is required.')
    .moreThan(0, 'Amount must be greater than zero.'),
  reason: yup.string().required('Reason is required.').max(280),
})

type AdjustmentForm = yup.InferType<typeof schema>

const { control, handleSubmit, setError, reset, formState } = useForm<AdjustmentForm>({
  resolver: yupResolver(schema),
  defaultValues: { invoiceId: '', amount: 0, reason: '' },
})
```

## Rules

- Derive the TS type from the schema with `yup.InferType` — never declare the form type twice.
- Always pass `defaultValues`. Uncontrolled-to-controlled warnings mean you forgot.
- MUI inputs are controlled, so wrap them in `<Controller>`:

  ```tsx
  <Controller
    name="amount"
    control={control}
    render={({ field, fieldState }) => (
      <TextField
        {...field}
        label="Amount"
        type="number"
        error={!!fieldState.error}
        helperText={fieldState.error?.message}
        fullWidth
      />
    )}
  />
  ```

- Error text comes from the schema and renders in `helperText`. Never render a form-wide list of
  error strings above the form when the errors belong to fields.
- Disable submit with `formState.isSubmitting`, and `reset()` on success.
- **Server-side validation errors are field errors too.** DRF returns
  `{ amount: ["Adjustment exceeds invoice total."] }`; map that back with `setError`:

  ```ts
  const apiError = toApiError(error)
  for (const [field, messages] of Object.entries(apiError.fieldErrors ?? {})) {
    setError(field as keyof AdjustmentForm, { message: messages.join(' ') })
  }
  ```

  A rule the server enforces and the client can't know (an amount exceeding a balance) must still
  land on the right input, not in a toast.
- Client validation is for shape and obvious mistakes. It does not replace the serializer.

## Do not

- Do not validate by hand in `onSubmit`.
- Do not use `register()` on MUI components — that's what `Controller` is for.
- Do not swallow submit errors; if the request fails for a non-field reason, show an `<Alert>`.
