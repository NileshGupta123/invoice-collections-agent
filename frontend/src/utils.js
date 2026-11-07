export const REMINDABLE = ['SENT', 'UNPAID', 'PARTIALLY_PAID', 'PAYMENT_PENDING']

const FINAL = ['PAID', 'MARKED_AS_PAID', 'CANCELLED', 'REFUNDED', 'MARKED_AS_REFUNDED']

export function daysOverdue(invoice) {
  if (!invoice.due_date) return null
  if (invoice.status === 'DRAFT' || FINAL.includes(invoice.status)) return null
  const due = new Date(`${invoice.due_date}T00:00:00`)
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((today - due) / 86400000)
}

export function formatMoney(value, currency = 'USD') {
  const amount = Number(value)
  if (Number.isNaN(amount)) return '-'
  try {
    return new Intl.NumberFormat('en-US', {
      style: 'currency',
      currency: currency || 'USD',
    }).format(amount)
  } catch {
    return `${amount.toFixed(2)} ${currency || ''}`.trim()
  }
}

export function formatTime(iso) {
  if (!iso) return ''
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  return date.toLocaleString('en-IN', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}