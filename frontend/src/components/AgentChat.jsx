import { useEffect, useRef, useState } from 'react'
import { api } from '../api'

const SUGGESTIONS = [
  'Which of my clients are risky and why?',
  'Preview what you would do about my unpaid invoices',
  'Invoice Rahul for 500 dollars of web design',
]

const TOOL_LABELS = {
  list_invoices: 'Listed invoices',
  get_invoice_status: 'Checked status',
  create_draft_invoice: 'Drafted invoice',
  send_reminder: 'Sent reminder',
  run_collections: 'Ran collections',
  get_client_risk: 'Checked client risk',
}

function renderText(text) {
  const parts = String(text).split(/(\*\*[^*]+\*\*)/g)
  return parts.map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) {
      return <strong key={i}>{part.slice(2, -2)}</strong>
    }
    return <span key={i}>{part}</span>
  })
}

export default function AgentChat({ onAgentDone }) {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, sending])

  const send = async (text) => {
    const content = text.trim()
    if (!content || sending) return

    const history = messages.map((m) => ({ role: m.role, content: m.content }))
    setMessages((prev) => [...prev, { role: 'user', content }])
    setInput('')
    setSending(true)
    setError('')

    try {
      const data = await api.chat(content, history)
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply || '(no reply)',
          actions: data.actions || [],
        },
      ])
      if (data.actions && data.actions.length > 0) onAgentDone()
    } catch (err) {
      setError(err.message)
    } finally {
      setSending(false)
    }
  }

  const submit = (event) => {
    event.preventDefault()
    send(input)
  }

  return (
    <section className="flex h-[480px] flex-col rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-base font-semibold">Agent</h2>
        <p className="text-xs text-slate-500">
          Ask in plain language. It drafts invoices and chases payments.
        </p>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-4">
        {messages.length === 0 && (
          <div className="space-y-2">
            <p className="text-sm text-slate-400">Try one of these:</p>
            {SUGGESTIONS.map((text) => (
              <button
                key={text}
                onClick={() => send(text)}
                className="block w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-sm text-slate-600 hover:bg-slate-50"
              >
                {text}
              </button>
            ))}
          </div>
        )}

        {messages.map((m, index) => (
          <div
            key={index}
            className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] whitespace-pre-wrap rounded-2xl px-3 py-2 text-sm ${
                m.role === 'user'
                  ? 'bg-slate-900 text-white'
                  : 'bg-slate-100 text-slate-800'
              }`}
            >
              {renderText(m.content)}
              {m.actions && m.actions.length > 0 && (
                <div className="mt-2 flex flex-wrap gap-1">
                  {m.actions.map((a, i) => (
                    <span
                      key={i}
                      className={`rounded-full px-2 py-0.5 text-xs ${
                        a.result && a.result.error
                          ? 'bg-red-100 text-red-700'
                          : 'bg-purple-100 text-purple-700'
                      }`}
                    >
                      {TOOL_LABELS[a.tool] || a.tool}
                    </span>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}

        {sending && <div className="text-sm text-slate-400">Agent is working...</div>}
        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 p-2 text-sm text-red-700">
            {error}
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <form onSubmit={submit} className="flex gap-2 border-t border-slate-100 p-3">
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="e.g. Invoice Maya $400 for a landing page"
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <button
          type="submit"
          disabled={sending || !input.trim()}
          className="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </section>
  )
}