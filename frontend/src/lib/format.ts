/** Keep decimal strings exact, including totals larger than Number.MAX_SAFE_INTEGER. */
export function formatMoney(amount: string, currency: string): string {
  const [integer, fraction = ''] = amount.split('.')
  return `${currency} ${integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')}.${fraction.padEnd(2, '0')}`
}

export function formatDate(value: string | null): string {
  return value ? new Date(value).toLocaleString() : '—'
}
