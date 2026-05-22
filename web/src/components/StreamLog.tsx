import { useEffect, useRef } from 'react'
import { useLanguage } from '../contexts/LanguageContext'

interface Props {
  lines: string[]
  running: boolean
  className?: string
}

export default function StreamLog({ lines, running, className = '' }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const { t } = useLanguage()

  useEffect(() => {
    if (ref.current) {
      ref.current.scrollTop = ref.current.scrollHeight
    }
  }, [lines])

  return (
    <div
      ref={ref}
      className={`font-mono text-xs bg-slate-900 text-slate-100 rounded-lg p-4 h-64 overflow-y-auto ${className}`}
    >
      {lines.length === 0 && !running && (
        <span className="text-slate-500">{t('streamlog.waiting')}</span>
      )}
      {lines.map((l, i) => (
        <div key={i} className="leading-5 whitespace-pre-wrap break-all">
          {l}
        </div>
      ))}
      {running && (
        <div className="flex items-center gap-2 mt-1 text-sky-400">
          <span className="inline-block w-2 h-2 rounded-full bg-sky-400 animate-pulse" />
          <span>{t('streamlog.running')}</span>
        </div>
      )}
    </div>
  )
}
