import { useState, useEffect } from 'react'

interface CollapsibleSectionProps {
  title: string
  storageKey: string
  children: React.ReactNode
  defaultOpen?: boolean
}

export default function CollapsibleSection({
  title,
  storageKey,
  children,
  defaultOpen = true,
}: CollapsibleSectionProps) {
  const lsKey = `lutz_collapsed_${storageKey}`

  const [open, setOpen] = useState<boolean>(() => {
    try {
      const stored = localStorage.getItem(lsKey)
      if (stored !== null) return stored !== 'true'
      return defaultOpen
    } catch {
      return defaultOpen
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(lsKey, open ? 'false' : 'true')
    } catch {
      // ignore storage errors
    }
  }, [lsKey, open])

  return (
    <div>
      <button
        type="button"
        className="flex items-center gap-2 w-full text-left group mb-3"
        onClick={() => setOpen((v) => !v)}
      >
        {/* Inline chevron SVG */}
        <svg
          width="16"
          height="16"
          viewBox="0 0 16 16"
          fill="none"
          xmlns="http://www.w3.org/2000/svg"
          className={`text-slate-400 group-hover:text-slate-600 transition-transform duration-200 flex-shrink-0 ${
            open ? '' : '-rotate-90'
          }`}
        >
          <path
            d="M4 6l4 4 4-4"
            stroke="currentColor"
            strokeWidth="1.5"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
        <span className="text-sm font-semibold text-slate-700 group-hover:text-slate-900 select-none">
          {title}
        </span>
      </button>
      <div
        className={`transition-all duration-200 overflow-hidden ${
          open ? 'opacity-100' : 'max-h-0 opacity-0 pointer-events-none'
        }`}
        style={open ? undefined : { maxHeight: 0 }}
      >
        {children}
      </div>
    </div>
  )
}
