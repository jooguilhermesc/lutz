/**
 * ActiveJobPanel — shown on pages that have a running background job of the
 * matching type. Displays a pulsing card; clicking "Acompanhar" opens the live
 * log stream without leaving the page.
 */
import { useEffect, useRef, useState } from 'react'
import { useNotifications, type JobInfo } from '../contexts/NotificationsContext'
import StreamLog from './StreamLog'

const TYPE_LABEL: Record<string, string> = {
  vectorize: 'Processando biblioteca',
  analysis:  'Análise em andamento',
  citations: 'Gerando citações',
  roadmap:   'Gerando roteiro',
}

interface Props {
  jobType: 'vectorize' | 'analysis' | 'citations' | 'roadmap'
  /** Called when the job finishes while the log is being watched */
  onDone?: () => void
}

export default function ActiveJobPanel({ jobType, onDone }: Props) {
  const { jobs } = useNotifications()

  // Find the most recent running/queued job of this type
  const activeJob = jobs.find(
    (j) => j.type === jobType && (j.status === 'running' || j.status === 'queued'),
  ) ?? null

  if (!activeJob) return null

  return <Panel job={activeJob} onDone={onDone} />
}

// Separate component so we can use hooks that depend on a non-null job
function Panel({ job, onDone }: { job: JobInfo; onDone?: () => void }) {
  const { jobs } = useNotifications()
  const [expanded, setExpanded] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [streamDone, setStreamDone] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  // Keep job status up to date from context
  const liveJob = jobs.find((j) => j.id === job.id) ?? job
  const isRunning = liveJob.status === 'running' || liveJob.status === 'queued'

  // When user expands, subscribe to the SSE log stream for this job
  useEffect(() => {
    if (!expanded) return

    const ctrl = new AbortController()
    ctrlRef.current = ctrl

    // Fetch buffered + live logs
    fetch(`/api/jobs/${job.id}/stream`, { signal: ctrl.signal })
      .then(async (res) => {
        if (!res.body) return
        const reader = res.body.getReader()
        const dec = new TextDecoder()
        let buf = ''
        while (true) {
          const { done, value } = await reader.read()
          if (done) break
          buf += dec.decode(value, { stream: true })
          const parts = buf.split('\n\n')
          buf = parts.pop() ?? ''
          for (const part of parts) {
            const line = part.replace(/^data: /, '').trim()
            if (!line) continue
            if (line === '__done__') {
              setStreamDone(true)
              onDone?.()
            } else if (!line.startsWith('__error__')) {
              setLogs((p) => [...p, line])
            }
          }
        }
      })
      .catch((e) => {
        if (e?.name !== 'AbortError') setStreamDone(true)
      })

    return () => ctrl.abort()
  }, [expanded, job.id, onDone])

  const label = TYPE_LABEL[job.type] ?? 'Em processamento'
  const done = !isRunning || streamDone

  return (
    <div
      className={`rounded-xl border shadow-md overflow-hidden transition-all ${
        done
          ? liveJob.status === 'done'
            ? 'border-green-200 bg-green-50'
            : 'border-red-200 bg-red-50'
          : 'border-lutz-200 bg-lutz-50'
      }`}
    >
      {/* Header bar */}
      <button
        className="w-full flex items-center gap-3 px-4 py-3 text-left"
        onClick={() => setExpanded((v) => !v)}
      >
        {/* Status indicator */}
        {done ? (
          liveJob.status === 'done' ? (
            <span className="text-green-500 text-lg font-bold leading-none">✓</span>
          ) : (
            <span className="text-red-500 text-lg font-bold leading-none">✗</span>
          )
        ) : (
          <span className="inline-block w-3 h-3 rounded-full bg-lutz-500 animate-pulse flex-shrink-0" />
        )}

        <div className="flex-1 min-w-0">
          <p className={`text-sm font-semibold ${done ? (liveJob.status === 'done' ? 'text-green-700' : 'text-red-700') : 'text-lutz-700'}`}>
            {done
              ? liveJob.status === 'done'
                ? label.replace('em andamento', 'concluído').replace('andamento', 'concluído') + ' — concluído'
                : label + ' — erro'
              : label + '...'}
          </p>
          <p className="text-xs text-slate-500 truncate">{job.title}</p>
        </div>

        <div className="flex items-center gap-2 flex-shrink-0">
          {!done && (
            <span className="text-xs text-lutz-600 bg-lutz-100 px-2 py-0.5 rounded-full">
              segundo plano
            </span>
          )}
          <span className={`text-xs font-medium ${done ? 'text-slate-500' : 'text-lutz-600'}`}>
            {expanded ? '▲ ocultar' : '▼ acompanhar'}
          </span>
        </div>
      </button>

      {/* Log panel */}
      {expanded && (
        <div className="px-4 pb-4">
          <StreamLog lines={logs} running={!done} className="h-52" />
        </div>
      )}
    </div>
  )
}
