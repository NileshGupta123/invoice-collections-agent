import StatusBadge from './StatusBadge'
import { REMINDABLE, daysOverdue, formatMoney } from '../utils'

function DueCell({ invoice }) {
  const days = daysOverdue(invoice)
  if (days === null) return <span>{invoice.due_date}</span>
  if (days > 0) {
    return (
      <span>
        {invoice.due_date}{' '}
        <span className="text-xs font-medium text-red-600">({days}d overdue)</span>
      </span>
    )
  }
  if (days === 0) {
    return (
      <span>
        {invoice.due_date}{' '}
        <span className="text-xs font-medium text-amber-600">(due today)</span>
      </span>
    )
  }
  return (
    <span>
      {invoice.due_date}{' '}
      <span className="text-xs text-slate-400">(in {Math.abs(days)}d)</span>
    </span>
  )
}

export default function InvoiceTable({ invoices, busyId, onRemind }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-base font-semibold">All invoices</h2>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-slate-500">
            <tr>
              <th className="px-4 py-3 font-medium">No.</th>
              <th className="px-4 py-3 font-medium">Client</th>
              <th className="px-4 py-3 font-medium">Status</th>
              <th className="px-4 py-3 font-medium">Total</th>
              <th className="px-4 py-3 font-medium">Due</th>
              <th className="px-4 py-3 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {invoices.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-slate-400">
                  No invoices yet.
                </td>
              </tr>
            )}
            {invoices.map((inv) => (
              <tr key={inv.invoice_id} className="border-t border-slate-100">
                <td className="px-4 py-3 font-medium">{inv.invoice_number}</td>
                <td className="px-4 py-3">{inv.client_name}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={inv.status} />
                </td>
                <td className="px-4 py-3">{formatMoney(inv.total, inv.currency)}</td>
                <td className="px-4 py-3">
                  <DueCell invoice={inv} />
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    {REMINDABLE.includes(inv.status) && (
                      <button
                        onClick={() => onRemind(inv)}
                        disabled={busyId === inv.invoice_id}
                        className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50 disabled:opacity-50"
                      >
                        {busyId === inv.invoice_id ? 'Sending...' : 'Send reminder'}
                      </button>
                    )}
                    {inv.status === 'DRAFT' && (
                      <span className="text-xs text-amber-600">In approval inbox</span>
                    )}
                    {inv.payer_view_url && (
                      <a
                        href={inv.payer_view_url}
                        target="_blank"
                        rel="noreferrer"
                        className="text-xs text-blue-600 hover:underline"
                      >
                        View
                      </a>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}