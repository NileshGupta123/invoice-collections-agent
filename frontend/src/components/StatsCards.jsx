import { REMINDABLE, daysOverdue, formatMoney } from '../utils'

function Card({ label, value, hint, tone }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${tone}`}>{value}</div>
      <div className="mt-1 text-xs text-slate-400">{hint}</div>
    </div>
  )
}

export default function StatsCards({ invoices }) {
  const open = invoices.filter((i) => REMINDABLE.includes(i.status))
  const outstanding = open.reduce((sum, i) => sum + Number(i.due_amount || 0), 0)
  const overdue = open.filter((i) => (daysOverdue(i) ?? -1) > 0)
  const paid = invoices
    .filter((i) => i.status === 'PAID' || i.status === 'MARKED_AS_PAID')
    .reduce((sum, i) => sum + Number(i.paid_amount || 0), 0)
  const drafts = invoices.filter((i) => i.status === 'DRAFT')

  return (
    <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
      <Card
        label="Outstanding"
        value={formatMoney(outstanding)}
        hint={`${open.length} unpaid invoice${open.length === 1 ? '' : 's'}`}
        tone="text-blue-700"
      />
      <Card
        label="Overdue"
        value={overdue.length}
        hint="Past due date"
        tone={overdue.length ? 'text-red-600' : 'text-slate-900'}
      />
      <Card
        label="Collected"
        value={formatMoney(paid)}
        hint="Paid invoices"
        tone="text-green-700"
      />
      <Card
        label="Awaiting approval"
        value={drafts.length}
        hint="Drafts in the inbox"
        tone={drafts.length ? 'text-amber-600' : 'text-slate-900'}
      />
    </div>
  )
}