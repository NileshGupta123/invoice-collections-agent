import { formatMoney } from '../utils'

export default function ApprovalInbox({ drafts, draftedBy, busyId, onApprove }) {
  return (
    <section className="rounded-xl border border-amber-200 bg-amber-50/50 p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-base font-semibold">Approval Inbox</h2>
        <span className="rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-700">
          {drafts.length} waiting
        </span>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        The agent can draft invoices, but only you can send them.
      </p>

      {drafts.length === 0 ? (
        <div className="rounded-lg border border-dashed border-amber-200 bg-white p-4 text-center text-sm text-slate-400">
          Nothing waiting. Ask the agent to draft an invoice.
        </div>
      ) : (
        <ul className="space-y-3">
          {drafts.map((inv) => {
            const author = draftedBy[inv.invoice_id]
            return (
              <li
                key={inv.invoice_id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-3"
              >
                <div>
                  <div className="text-sm font-medium">
                    #{inv.invoice_number} · {inv.client_name}
                  </div>
                  <div className="text-xs text-slate-500">
                    {formatMoney(inv.total, inv.currency)} · due {inv.due_date} ·{' '}
                    {inv.client_email}
                  </div>
                  {author && (
                    <span
                      className={`mt-1 inline-block rounded-full px-2 py-0.5 text-xs font-medium ${
                        author === 'agent'
                          ? 'bg-purple-100 text-purple-700'
                          : 'bg-slate-100 text-slate-600'
                      }`}
                    >
                      {author === 'agent' ? 'Drafted by agent' : 'Drafted by you'}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => onApprove(inv)}
                  disabled={busyId === inv.invoice_id}
                  className="rounded-lg bg-green-600 px-4 py-2 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
                >
                  {busyId === inv.invoice_id ? 'Sending...' : 'Approve and Send'}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </section>
  )
}