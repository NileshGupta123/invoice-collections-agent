import { formatTime } from '../utils'

const LABELS = {
  create_draft: 'Drafted invoice',
  send_invoice: 'Sent invoice',
  send_reminder: 'Sent reminder',
  sync: 'Synced with PayPal',
  collections_run: 'Ran collections',
  collections_escalate: 'Escalated to a human',
}

const ACTOR_STYLES = {
  agent: 'bg-purple-100 text-purple-700',
  user: 'bg-slate-100 text-slate-700',
  system: 'bg-blue-100 text-blue-700',
}

const TONE_STYLES = {
  friendly: 'bg-green-100 text-green-700',
  firm: 'bg-amber-100 text-amber-700',
  final: 'bg-red-100 text-red-700',
}

function detailLine(item) {
  const d = item.details || {}
  if (item.action === 'collections_run') {
    return `Reviewed ${d.reviewed ?? 0}, sent ${d.sent ?? 0}, skipped ${d.skip ?? 0}, waiting ${d.wait ?? 0}, escalated ${d.escalate ?? 0}`
  }
  if (item.action === 'collections_escalate') {
    return d.reason || ''
  }
  return d.subject || ''
}

export default function ActivityLog({ activity, numberById }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-base font-semibold">Activity log</h2>
        <p className="text-xs text-slate-500">Every action, and who did it.</p>
      </div>
      <ul className="max-h-[320px] divide-y divide-slate-100 overflow-y-auto">
        {activity.length === 0 && (
          <li className="px-4 py-6 text-center text-sm text-slate-400">
            No activity yet.
          </li>
        )}
        {activity.map((item) => {
          const line = detailLine(item)
          const tone = item.details && item.details.tone
          return (
            <li key={item.id} className="flex items-start gap-3 px-4 py-3">
              <span
                className={`mt-0.5 rounded-full px-2 py-0.5 text-xs font-medium ${
                  ACTOR_STYLES[item.actor] || ACTOR_STYLES.system
                }`}
              >
                {item.actor}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5 text-sm">
                  <span>
                    {LABELS[item.action] || item.action}
                    {item.invoice_id && numberById[item.invoice_id] && (
                      <span className="text-slate-500">
                        {' '}
                        #{numberById[item.invoice_id]}
                      </span>
                    )}
                  </span>
                  {tone && TONE_STYLES[tone] && (
                    <span
                      className={`rounded-full px-1.5 py-0.5 text-xs ${TONE_STYLES[tone]}`}
                    >
                      {tone}
                    </span>
                  )}
                </div>
                {line && (
                  <div className="truncate text-xs text-slate-400">{line}</div>
                )}
              </div>
              <span className="whitespace-nowrap text-xs text-slate-400">
                {formatTime(item.timestamp)}
              </span>
            </li>
          )
        })}
      </ul>
    </section>
  )
}