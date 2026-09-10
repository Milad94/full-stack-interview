import assert from 'node:assert/strict'
import test from 'node:test'

import { formatMoney } from '../src/lib/format.ts'
import { adjustmentSchema } from '../src/features/adjustments/schema.ts'

const correction = {
  invoice: {
    id: 1,
    external_id: 'INV-1',
    customer_name: 'Customer',
    currency: 'EUR',
  },
  invoiceSearch: '',
  amount: '-12.34',
  reason: 'Write-off',
}

test('large totals and signed corrections are displayed without losing cents', () => {
  assert.equal(
    formatMoney('99999999999999999999.99', 'USD'),
    'USD 99,999,999,999,999,999,999.99',
  )
  assert.equal(formatMoney('-1234.01', 'EUR'), 'EUR -1,234.01')
  assert.equal(formatMoney('0.00', 'GBP'), 'GBP 0.00')
})

test('valid signed amounts retain their exact decimal strings', async () => {
  for (const amount of [
    '-0.01',
    '0.01',
    '+12.34',
    '-9999999999999999.99',
    '9999999999999999.99',
  ]) {
    const result = await adjustmentSchema.validate({ ...correction, amount })
    assert.equal(result.amount, amount)
  }
})

test('zero, excessive precision, oversized and malformed amounts are rejected on the amount field', async () => {
  for (const amount of [
    '',
    '0',
    '-0.00',
    '+0.00',
    '1.001',
    '10000000000000000',
    'NaN',
    'Infinity',
    '1e3',
    '1,000.00',
  ]) {
    await assert.rejects(adjustmentSchema.validate({ ...correction, amount }), {
      path: 'amount',
    })
  }
})

test('a correction requires an invoice and a nonblank reason no longer than 1,000 characters', async () => {
  await assert.rejects(
    adjustmentSchema.validate({ ...correction, invoice: null }),
    { path: 'invoice' },
  )
  await assert.rejects(
    adjustmentSchema.validate({ ...correction, reason: '   ' }),
    { path: 'reason' },
  )
  await assert.rejects(
    adjustmentSchema.validate({ ...correction, reason: 'x'.repeat(1001) }),
    { path: 'reason' },
  )
  const result = await adjustmentSchema.validate({
    ...correction,
    reason: '  Write-off  ',
  })
  assert.equal(result.reason, 'Write-off')
})
