import { useState } from 'react'

const TERMS = ['DUE_ON_RECEIPT', 'NET_10', 'NET_15', 'NET_30', 'NET_45', 'NET_60', 'NET_90']

const EMPTY = {
  client_name: '',
  client_email: '',
  item_name: '',
  quantity: '1',
  unit_amount: '',
  payment_term: 'NET_10',
  note: '',
}

export default function CreateInvoiceForm({ onCreate }) {
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState(EMPTY)
  const [submitting, setSubmitting] = useState(false)

  const set = (key) => (event) => setForm({ ...form, [key]: event.target.value })

  const submit = async (event) => {
    event.preventDefault()
    setSubmitting(true)
    const ok = await onCreate({
      client_name: form.client_name.trim(),
      client_email: form.client_email.trim(),
      items: [
        {
          name: form.item_name.trim(),
          quantity: Number(form.quantity),
          unit_amount: Number(form.unit_amount),
        },
      ],
      currency: 'USD',
      note: form.note.trim() || null,
      payment_term: form.payment_term,
    })
    setSubmitting(false)
    if (ok) {
      setForm(EMPTY)
      setOpen(false)
    }
  }

  const inputClass =
    'w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none'

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold">Create invoice manually</h2>
        <button
          onClick={() => setOpen(!open)}
          className="rounded-md border border-slate-300 px-2.5 py-1 text-xs font-medium hover:bg-slate-50"
        >
          {open ? 'Close' : 'New draft'}
        </button>
      </div>

      {open && (
        <form onSubmit={submit} className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
          <input
            required
            placeholder="Client name"
            value={form.client_name}
            onChange={set('client_name')}
            className={inputClass}
          />
          <input
            required
            type="email"
            placeholder="Client email"
            value={form.client_email}
            onChange={set('client_email')}
            className={inputClass}
          />
          <input
            required
            placeholder="Item (e.g. Logo design)"
            value={form.item_name}
            onChange={set('item_name')}
            className={`${inputClass} sm:col-span-2`}
          />
          <input
            required
            type="number"
            min="0.01"
            step="any"
            placeholder="Quantity"
            value={form.quantity}
            onChange={set('quantity')}
            className={inputClass}
          />
          <input
            required
            type="number"
            min="0.01"
            step="any"
            placeholder="Unit price (USD)"
            value={form.unit_amount}
            onChange={set('unit_amount')}
            className={inputClass}
          />
          <select
            value={form.payment_term}
            onChange={set('payment_term')}
            className={inputClass}
          >
            {TERMS.map((term) => (
              <option key={term} value={term}>
                {term}
              </option>
            ))}
          </select>
          <input
            placeholder="Note (optional)"
            value={form.note}
            onChange={set('note')}
            className={inputClass}
          />
          <button
            type="submit"
            disabled={submitting}
            className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50 sm:col-span-2"
          >
            {submitting ? 'Creating...' : 'Create draft'}
          </button>
        </form>
      )}
    </section>
  )
}