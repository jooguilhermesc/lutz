import { useEffect, useRef, useState } from 'react'
import { useNotifications, type JobInfo } from '../contexts/NotificationsContext'
import { useLanguage } from '../contexts/LanguageContext'
import { getJobLogs } from '../api/client'

const TYPE_ICON: Record<string, string> = {
  vectorize: '📄',
  analysis: '🔬',
  citations: '📚',
  roadmap: '🗺️',
}

function relativeTime(iso: string | null, t: (k: string) => string): string {
  if (!iso) return ''
  const diff = Math.round((Date.now() - new Date(iso).getTime()) / 1000)
  if (diff < 60) return t('notif.justNow')
  if (diff < 3600) return `${Math.floor(diff / 60)} ${t('notif.minAgo')}`
  if (diff < 86400) return `${Math.floor(diff / 3600)} ${t('notif.hAgo')}`
  return `${Math.floor(diff / 86400)} ${t('notif.dAgo')}`
}

function StatusDot({ status }: { status: JobInfo['status'] }) {
  if (status === 'running' || status === 'queued') {
    return (
      <span className="inline-block w-4 h-4 border-2 border-lutz-500 border-t-transparent rounded-full animate-spin flex-shrink-0" />
    )
  }
  if (status === 'done') {
    return <span className="text-green-500 font-bold flex-shrink-0">✓</span>
  }
  if (status === 'error') {
    return <span className="text-red-500 font-bold flex-shrink-0">✗</span>
  }
  return <span className="text-slate-400 flex-shrink-0">—</span>
}

function isErrorLine(line: string) {
  return /error|traceback|exception|failed|critical/i.test(line)
}

function JobRow({ job, onRemove }: { job: JobInfo; onRemove: (id: string) => void }) {
  const { t } = useLanguage()
  const isTerminal = job.status === 'done' || job.status === 'error' || job.status === 'cancelled'
  const [showLogs, setShowLogs] = useState(false)
  const [logs, setLogs] = useState<string[] | null>(null)
  const [logsLoading, setLogsLoading] = useState(false)
  const logRef = useRef<HTMLDivElement>(null)

  async function toggleLogs(e: React.MouseEvent) {
    e.stopPropagation()
    if (showLogs) { setShowLogs(false); return }
    setShowLogs(true)
    if (logs !== null) return
    setLogsLoading(true)
    try {
      const { job: data } = await getJobLogs(job.id)
      setLogs(data.logs ?? [])
    } catch {
      setLogs(['(não foi possível carregar os logs)'])
    } finally {
      setLogsLoading(false)
    }
  }

  // Scroll to bottom of logs when opened
  useEffect(() => {
    if (showLogs && logRef.current) {
      logRef.current.scrollTop = logRef.current.scrollHeight
    }
  }, [showLogs, logs])

  return (
    <li className="border-b border-slate-50 last:border-0">
      <div className="flex items-start gap-2.5 px-3 py-2.5 group">
        <span className="text-base mt-0.5 flex-shrink-0">{TYPE_ICON[job.type] ?? '⚙️'}</span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 truncate">{job.title}</p>
          <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
            <StatusDot status={job.status} />
            <span className="text-xs text-slate-500">
              {job.status === 'running' || job.status === 'queued'
                ? t('notif.running')
                : job.status === 'done'
                ? t('notif.done')
                : job.status === 'error'
                ? t('notif.error')
                : t('notif.cancelled')}
            </span>
            {(job.ended_at || job.started_at) && (
              <span className="text-xs text-slate-400">
                · {relativeTime(job.ended_at ?? job.started_at, t)}
              </span>
            )}
            {isTerminal && (
              <button
                onClick={toggleLogs}
                className="text-xs text-lutz-600 hover:text-lutz-800 font-medium ml-1"
              >
                {showLogs ? 'Ocultar logs' : 'Ver logs'}
              </button>
            )}
          </div>
        </div>
        {isTerminal && (
          <button
            className="opacity-0 group-hover:opacity-100 text-slate-400 hover:text-slate-600 transition-opacity text-xs px-1 flex-shrink-0"
            onClick={(e) => { e.stopPropagation(); onRemove(job.id) }}
            title={t('notif.remove')}
          >
            ✕
          </button>
        )}
      </div>

      {showLogs && (
        <div
          ref={logRef}
          style={{
            maxHeight: 220, overflowY: 'auto', margin: '0 8px 8px',
            background: '#0f1117', borderRadius: 8, padding: '8px 10px',
            fontFamily: 'IBM Plex Mono, monospace', fontSize: 11, lineHeight: 1.6,
          }}
        >
          {logsLoading ? (
            <span style={{ color: '#6b7280' }}>Carregando…</span>
          ) : !logs || logs.length === 0 ? (
            <span style={{ color: '#6b7280' }}>Sem logs disponíveis.</span>
          ) : logs.map((line, i) => (
            <div key={i} style={{ color: isErrorLine(line) ? '#f87171' : '#9ca3af', wordBreak: 'break-all' }}>
              {line}
            </div>
          ))}
        </div>
      )}
    </li>
  )
}

export function NotificationsPanel() {
  const { jobs, unreadCount, markAllRead, removeJob, clearDone, cancelJob } = useNotifications()
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  const panelRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [])

  const toggle = () => {
    setOpen((v) => {
      if (!v) markAllRead()
      return !v
    })
  }

  const hasDone = jobs.some(
    (j) => j.status === 'done' || j.status === 'error' || j.status === 'cancelled',
  )
  const hasRunning = jobs.some((j) => j.status === 'running' || j.status === 'queued')

  return (
    <div ref={panelRef} className="relative">
      <button
        onClick={toggle}
        className="relative p-1.5 rounded-lg hover:bg-slate-100 text-slate-500 hover:text-slate-700 transition-colors"
        title={t('notif.title')}
      >
        {hasRunning ? (
          <svg className="w-5 h-5 text-lutz-500 animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6 6 0 10-12 0v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9" />
          </svg>
        )}
        {unreadCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 bg-red-500 text-white text-[9px] font-bold rounded-full flex items-center justify-center px-1 leading-none">
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 bg-white rounded-xl shadow-lg border border-slate-200 z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-slate-100 bg-slate-50">
            <span className="text-sm font-semibold text-slate-700">{t('notif.title')}</span>
            <div className="flex items-center gap-2">
              {hasRunning && (
                <button
                  onClick={async () => {
                    const running = jobs.filter((j) => j.status === 'running' || j.status === 'queued')
                    await Promise.allSettled(running.map((j) => cancelJob(j.id)))
                  }}
                  className="text-xs text-red-500 hover:text-red-700"
                >
                  {t('notif.cancelAll')}
                </button>
              )}
              {hasDone && (
                <button onClick={clearDone} className="text-xs text-slate-500 hover:text-slate-700">
                  {t('notif.clear')}
                </button>
              )}
            </div>
          </div>

          {/* Job list */}
          {jobs.length === 0 ? (
            <p className="text-sm text-slate-400 text-center py-8">{t('notif.empty')}</p>
          ) : (
            <ul className="max-h-[480px] overflow-y-auto divide-y divide-slate-50">
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} onRemove={removeJob} />
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
