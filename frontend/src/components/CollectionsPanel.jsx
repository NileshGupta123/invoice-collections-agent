import { useCallback, useEffect, useState } from 'react'
import { api } from '../api'
import { formatMoney } from '../utils'

const LEVEL_STYLES = {
  LOW: 'bg-green-100 text-green-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  HIGH: 'bg-red-100 text-red-700',
}

const BAR_STYLES = {
  LOW: 'bg-green-500',
  MEDIUM: 'bg-amber-500',
  HIGH: 'bg-red-500',
}

const ACTION_STYLES = {
  REMIND: 'bg-blue-100 text-blue-700',
  WAIT: 'bg-slate-100 text-slate-600',
  SKIP: 'bg-slate-100 text-slate-600',
  ESCALATE: 'bg-red-100 text-red-700',
}

const TONE_STYLES = {
  friendly: 'bg-green-100 text-green-700',
  firm: 'bg-amber-100 text-amber-700',
  final: 'bg-red-100 text-red-700',
}

function dueLabel(days) {
  if (days === null || days === undefined) return ''
  if (days > 0) return `${days}d overdue`
  if (days === 0) return 'due today'
  return `due in ${Math.abs(days)}d`
}

function Pill({ className, children }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium ${className}`}>
      {children}
    </span>
  )
}

function ClientCard({ client }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="truncate text-sm font-medium">{client.client_name}</div>
          <div className="truncate text-xs text-slate-400">{client.client_email}</div>
        </div>
        <Pill className={LEVEL_STYLES[client.level]}>{client.level}</Pill>
      </div>

      <div className="mt-3 flex items-center gap-2">
        <div className="h-2 flex-1 overflow-hidden rounded-full bg-slate-100">
          <div
            className={`h-full ${BAR_STYLES[client.level]}`}
            style={{ width: `${client.score}%` }}
          />
        </div>
        <span className="text-xs font-semibold">{client.score}/100</span>
      </div>

      <ul className="mt-2 list-disc space-y-0.5 pl-4 text-xs text-slate-500">
        {client.reasons.map((reason, i) => (
          <li key={i}>{reason}</li>
        ))}
      </ul>

      <div className="mt-2 text-xs text-slate-400">
        Open balance {formatMoney(client.open_amount)} · {client.paid_count} paid invoice
        {client.paid_count === 1 ? '' : 's'}
      </div>
    </div>
  )
}

function DecisionRow({ decision }) {
  return (
    <li className="rounded-lg border border-slate-200 bg-white p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm font-medium">
          #{decision.invoice_number} · {decision.client_name}
        </span>
        <Pill className={ACTION_STYLES[decision.action]}>{decision.action}</Pill>
        {decision.tone && (
          <Pill className={TONE_STYLES[decision.tone]}>{decision.tone} tone</Pill>
        )}
        <Pill className={LEVEL_STYLES[decision.risk_level]}>
          {decision.risk_level} risk
        </Pill>
        {decision.sent && (
          <Pill className="bg-green-600 text-white">Sent</Pill>
        )}
        <span className="ml-auto text-xs text-slate-400">
          {formatMoney(decision.due_amount, decision.currency)} ·{' '}
          {dueLabel(decision.days_overdue)}
        </span>
      </div>

      <p className="mt-1 text-xs text-slate-600">{decision.reason}</p>

      {decision.error && (
        <p className="mt-1 text-xs text-red-600">Error: {decision.error}</p>
      )}

      {decision.message && (
        <details className="mt-2 rounded-md bg-slate-50 p-2 text-xs">
          <summary className="cursor-pointer font-medium text-slate-700">
            Message: {decision.message.subject}
            <span className="ml-2 font-normal text-slate-400">
              ({decision.message.source === 'ai' ? 'written by AI' : 'template'})
            </span>
          </summary>
          <p className="mt-2 whitespace-pre-wrap text-slate-600">
            {decision.message.note}
          </p>
        </details>
      )}
    </li>
  )
}

export default function CollectionsPanel({ refreshKey, onDone }) {
  const [asOf, setAsOf] = useState('')
  const [clients, setClients] = useState([])
  const [result, setResult] = useState(null)
  const [running, setRunning] = useState(null)
  const [error, setError] = useState('')

  const loadRisk = useCallback(async () => {
    try {
      const data = await api.clientsRisk(asOf)
      setClients(data.clients)
    } catch (err) {
      setError(err.message)
    }
  }, [asOf])

  useEffect(() => {
    loadRisk()
  }, [loadRisk, refreshKey])

  const execute = async (send) => {
    if (send) {
      const when = asOf ? `as of ${asOf}` : 'today'
      const ok = window.confirm(
        `Run collections ${when}? The agent will send the reminders it decides on.`,
      )
      if (!ok) return
    }

    setRunning(send ? 'run' : 'preview')
    setError('')
    try {
      const data = await api.collectionsRun(send, asOf)
      setResult(data)
      if (data.clients) setClients(data.clients)
      if (send) await onDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setRunning(null)
    }
  }

  const summary = result ? result.summary : null

  return (
    <section className="rounded-xl border border-purple-200 bg-purple-50/40 p-4">
      <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-semibold">Collections agent</h2>
        <div className="flex flex-wrap items-center gap-2">
          <label className="flex items-center gap-1.5 text-xs text-slate-500">
            Simulate date
            <input
              type="date"
              value={asOf}
              onChange={(e) => {
                setAsOf(e.target.value)
                setResult(null)
              }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs"
            />
          </label>
          {asOf && (
            <button
              onClick={() => {
                setAsOf('')
                setResult(null)
              }}
              className="rounded-md border border-slate-300 bg-white px-2 py-1 text-xs hover:bg-slate-50"
            >
              Today
            </button>
          )}
          <button
            onClick={() => execute(false)}
            disabled={running !== null}
            className="rounded-lg border border-slate-300 bg-white px-3 py-1.5 text-sm font-medium hover:bg-slate-50 disabled:opacity-50"
          >
            {running === 'preview' ? 'Thinking...' : 'Preview'}
          </button>
          <button
            onClick={() => execute(true)}
            disabled={running !== null}
            className="rounded-lg bg-purple-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
          >
            {running === 'run' ? 'Running...' : 'Run now'}
          </button>
        </div>
      </div>
      <p className="mb-3 text-xs text-slate-500">
        Scores clients from their payment history, then decides per invoice: wait,
        remind, skip or escalate. Preview sends nothing.
        {asOf && ' The date is simulated for decisions only.'}
      </p>

      {error && (
        <div className="mb-3 rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">
          {error}
        </div>
      )}

      <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-500">
        Client risk
      </h3>
      {clients.length === 0 ? (
        <div className="rounded-lg border border-dashed border-slate-200 bg-white p-3 text-center text-sm text-slate-400">
          No clients yet.
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {clients.map((client) => (
            <ClientCard key={client.client_email} client={client} />
          ))}
        </div>
      )}

      {result && (
        <div className="mt-4">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
              {result.executed ? 'Run result' : 'Preview'} · as of {result.as_of}
            </h3>
            <Pill className="bg-white text-slate-600">
              {summary.reviewed} reviewed
            </Pill>
            <Pill className="bg-blue-100 text-blue-700">{summary.remind} remind</Pill>
            <Pill className="bg-slate-100 text-slate-600">{summary.wait} wait</Pill>
            <Pill className="bg-slate-100 text-slate-600">{summary.skip} skip</Pill>
            <Pill className="bg-red-100 text-red-700">
              {summary.escalate} escalate
            </Pill>
            {result.executed && (
              <Pill className="bg-green-600 text-white">{summary.sent} sent</Pill>
            )}
          </div>

          {!result.executed && (
            <p className="mb-2 text-xs text-slate-400">
              Preview only. Nothing was sent.
            </p>
          )}

          {result.decisions.length === 0 ? (
            <div className="rounded-lg border border-dashed border-slate-200 bg-white p-3 text-center text-sm text-slate-400">
              No unpaid invoices to review.
            </div>
          ) : (
            <ul className="space-y-2">
              {result.decisions.map((decision) => (
                <DecisionRow key={decision.invoice_id} decision={decision} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  )
}