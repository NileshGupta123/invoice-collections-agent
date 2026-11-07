const API_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000'

export class ApiError extends Error {
  constructor(message, status, details) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.details = details
  }
}

async function request(path, options = {}) {
  let response
  try {
    response = await fetch(`${API_URL}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    })
  } catch (err) {
    throw new ApiError('Cannot reach the backend. Is the server running?', 0, null)
  }

  let data = null
  const text = await response.text()
  if (text) {
    try {
      data = JSON.parse(text)
    } catch {
      data = { error: text }
    }
  }

  if (!response.ok) {
    const message =
      (data && (data.error || data.detail)) || `Request failed (${response.status})`
    throw new ApiError(
      typeof message === 'string' ? message : JSON.stringify(message),
      response.status,
      data,
    )
  }

  return data
}

export const api = {
  health: () => request('/health'),

  listInvoices: () => request('/invoices'),

  syncInvoices: () => request('/invoices/sync', { method: 'POST' }),

  createInvoice: (payload) =>
    request('/invoices', { method: 'POST', body: JSON.stringify(payload) }),

  refreshInvoice: (invoiceId) => request(`/invoices/${invoiceId}`),

  approveSend: (invoiceId) =>
    request(`/invoices/${invoiceId}/approve-send`, { method: 'POST' }),

  sendReminder: (invoiceId, payload = {}) =>
    request(`/invoices/${invoiceId}/remind`, {
      method: 'POST',
      body: JSON.stringify(payload),
    }),

  listActivity: (limit = 50) => request(`/activity?limit=${limit}`),

  clientsRisk: (asOf) =>
    request(`/clients/risk${asOf ? `?as_of=${encodeURIComponent(asOf)}` : ''}`),

  collectionsRun: (execute, asOf) =>
    request('/collections/run', {
      method: 'POST',
      body: JSON.stringify({ execute, as_of: asOf || null }),
    }),

  chat: (message, history = []) =>
    request('/agent/chat', {
      method: 'POST',
      body: JSON.stringify({ message, history }),
    }),
}