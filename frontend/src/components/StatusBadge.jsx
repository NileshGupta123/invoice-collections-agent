const STYLES = {
    DRAFT: 'bg-slate-100 text-slate-700',
    SENT: 'bg-blue-100 text-blue-700',
    PAID: 'bg-green-100 text-green-700',
    MARKED_AS_PAID: 'bg-green-100 text-green-700',
    CANCELLED: 'bg-red-100 text-red-700',
  }
  
  export default function StatusBadge({ status }) {
    const style = STYLES[status] || 'bg-amber-100 text-amber-700'
    return (
      <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${style}`}>
        {status}
      </span>
    )
  }