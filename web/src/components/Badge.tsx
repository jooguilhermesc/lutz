const COLORS: Record<string, string> = {
  INCLUDE:      'bg-lutz-50 text-lutz-700 border-lutz-300',
  EXCLUDE:      'bg-red-50 text-red-700 border-red-300',
  UNCERTAIN:    'bg-amber-50 text-amber-700 border-amber-300',
  UNKNOWN:      'bg-slate-100 text-slate-500 border-slate-300',
  HIGH:         'bg-lutz-50 text-lutz-700 border-lutz-300',
  MEDIUM:       'bg-amber-50 text-amber-700 border-amber-300',
  LOW:          'bg-red-50 text-red-700 border-red-300',
}

export default function Badge({ label }: { label: string }) {
  const key = label?.toUpperCase().replace(/\s/g, '_') ?? 'UNKNOWN'
  const cls = COLORS[key] ?? 'bg-slate-100 text-slate-600 border-slate-300'
  return (
    <span className={`inline-block px-2 py-0.5 rounded-full text-xs font-bold border ${cls}`}>
      {label}
    </span>
  )
}
