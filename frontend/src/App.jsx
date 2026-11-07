import { useCallback, useEffect, useMemo, useState } from 'react'
import { api } from './api'
import StatsCards from './components/StatsCards'
import ApprovalInbox from './components/ApprovalInbox'
import CollectionsPanel from './components/CollectionsPanel'
import InvoiceTable from './components/InvoiceTable'
import CreateInvoiceForm from './components/CreateInvoiceForm'
import AgentChat from './components/AgentChat'
import ActivityLog from './components/ActivityLog'

export default function App() {
  const [invoices, setInvoices] = useState([])
  const [activity, setActivity] = useState([])
  const [loading, setLoading] = useState(true)
  const [syncing, setSyncing] = useState(false)
  const [busyId, setBusyId] = useState(null)
  const [notice, setNotice] = useState(null)

  const loadAll = useCallback(async () => {
    try {
      const [inv, act] = await Promise.all([
        api.listInvoices(),
        api.listActivity(100),
      ])
      setInvoices(inv.invoices)
      setActivity(act.activity)
    } catch (err) {
      setNotice({ type: 'error', text: err.message })
    }
  }, [])

  useEffect(() => {
    loadAll().finally(() => setLoading(false))
  }, [loadAll])

  const drafts = useMemo(
    () => invoices.filter((i) => i.status === 'DRAFT'),
    [invoices],
  )

  const draftedBy = useMemo(() => {
    const map = {}
    for (const item of activity) {
      if (item.action === 'create_draft' && item.invoice_id) {
        map[item.invoice_id] = item.actor
      }
    }
    return map
  }, [activity])

  const numberById = useMemo(() => {
    const map = {}
    for (const inv of invoices) map[inv.invoice_id] = inv.invoice_number
    return map
  }, [invoices])

  const refreshKey = useMemo(
    () => invoices.map((i) => `${i.invoice_id}:${i.status}`).join('|'),
    [invoices],
  )

  const sync = async () => {
    setSyncing(true)
    setNotice(null)
    try {
      await api.syncInvoices()
      await loadAll()
      setNotice({ type: 'success', text: 'Synced with PayPal.' })
    } catch (err) {
      setNotice({ type: 'error', text: err.message })
    } finally {
      setSyncing(false)
    }
  }

  const runForInvoice = async (invoice, action, successText) => {
    setBusyId(invoice.invoice_id)
    setNotice(null)
    try {
      await action()
      await loadAll()
      setNotice({ type: 'success', text: successText })
    } catch (err) {
      setNotice({ type: 'error', text: err.message })
    } finally {
      setBusyId(null)
    }
  }

  const approve = (invoice) => {
    const ok = window.confirm(
      `Send invoice #${invoice.invoice_number} for ${invoice.total} ${invoice.currency} to ${invoice.client_email}?`,
    )
    if (!ok) return
    runForInvoice(
      invoice,
      () => api.approveSend(invoice.invoice_id),
      `Invoice #${invoice.invoice_number} sent.`,
    )
  }

  const remind = (invoice) =>
    runForInvoice(
      invoice,
      () => api.sendReminder(invoice.invoice_id, {}),
      `Reminder sent for #${invoice.invoice_number}.`,
    )

  const createInvoice = async (payload) => {
    setNotice(null)
    try {
      const created = await api.createInvoice(payload)
      await loadAll()
      setNotice({
        type: 'success',
        text: `Draft #${created.invoice_number} created. Approve it in the inbox.`,
      })
      return true
    } catch (err) {
      setNotice({ type: 'error', text: err.message })
      return false
    }
  }

  return (
    <div className="mx-auto max-w-7xl p-6">
      <header className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold">Invoice and Collections Agent</h1>
          <p className="text-sm text-slate-500">
            PayPal sandbox · the agent drafts and chases, you approve.
          </p>
        </div>
        <button
          onClick={sync}
          disabled={syncing || loading}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          {syncing ? 'Syncing...' : 'Sync with PayPal'}
        </button>
      </header>

      {notice && (
        <div
          className={`mb-4 flex items-start justify-between gap-3 rounded-lg border p-3 text-sm ${
            notice.type === 'error'
              ? 'border-red-200 bg-red-50 text-red-700'
              : 'border-green-200 bg-green-50 text-green-700'
          }`}
        >
          <span>{notice.text}</span>
          <button onClick={() => setNotice(null)} className="font-medium">
            x
          </button>
        </div>
      )}

      <StatsCards invoices={invoices} />

      <div className="mt-6 grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <ApprovalInbox
            drafts={drafts}
            draftedBy={draftedBy}
            busyId={busyId}
            onApprove={approve}
          />
          <CollectionsPanel refreshKey={refreshKey} onDone={loadAll} />
          <InvoiceTable invoices={invoices} busyId={busyId} onRemind={remind} />
          <CreateInvoiceForm onCreate={createInvoice} />
        </div>
        <div className="space-y-6">
          <AgentChat onAgentDone={loadAll} />
          <ActivityLog activity={activity} numberById={numberById} />
        </div>
      </div>
    </div>
  )
}