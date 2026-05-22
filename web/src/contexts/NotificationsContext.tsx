import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from 'react'

export interface JobInfo {
  id: string
  type: 'vectorize' | 'analysis' | 'citations' | 'roadmap'
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled'
  title: string
  started_at: string | null
  ended_at: string | null
  error_code: number | null
}

interface NotificationsCtx {
  jobs: JobInfo[]
  unreadCount: number
  markAllRead: () => void
  removeJob: (id: string) => Promise<void>
  clearDone: () => Promise<void>
  dispatchJob: (type: string, params: Record<string, unknown>) => Promise<JobInfo>
  cancelJob: (id: string) => Promise<void>
}

const Ctx = createContext<NotificationsCtx>({
  jobs: [],
  unreadCount: 0,
  markAllRead: () => {},
  removeJob: async () => {},
  clearDone: async () => {},
  dispatchJob: async () => { throw new Error('not mounted') },
  cancelJob: async () => {},
})

export function useNotifications() {
  return useContext(Ctx)
}

export function NotificationsProvider({ children }: { children: React.ReactNode }) {
  const [jobs, setJobs] = useState<JobInfo[]>([])
  const [seenIds, setSeenIds] = useState<Set<string>>(new Set())
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectRef = useRef<ReturnType<typeof setTimeout>>()

  const connect = useCallback(() => {
    const proto = location.protocol === 'https:' ? 'wss' : 'ws'
    const ws = new WebSocket(`${proto}://${location.host}/ws/notifications`)
    wsRef.current = ws

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data as string)
        if (msg.event === 'init') {
          setJobs(msg.jobs as JobInfo[])
        } else if (msg.event === 'job_update') {
          const updated = msg.job as JobInfo
          setJobs((prev) => {
            const exists = prev.some((j) => j.id === updated.id)
            return exists
              ? prev.map((j) => (j.id === updated.id ? updated : j))
              : [updated, ...prev]
          })
        } else if (msg.event === 'job_removed') {
          setJobs((prev) => prev.filter((j) => j.id !== msg.job_id))
          setSeenIds((prev) => { const s = new Set(prev); s.delete(msg.job_id); return s })
        }
        // job_log events are consumed by pages via SSE, not here
      } catch {
        // ignore parse errors
      }
    }

    ws.onclose = () => {
      reconnectRef.current = setTimeout(connect, 3000)
    }
  }, [])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectRef.current)
      wsRef.current?.close()
    }
  }, [connect])

  const unreadCount = jobs.filter(
    (j) =>
      j.status === 'running' ||
      j.status === 'queued' ||
      ((j.status === 'done' || j.status === 'error') && !seenIds.has(j.id)),
  ).length

  const markAllRead = useCallback(() => {
    setSeenIds(new Set(jobs.map((j) => j.id)))
  }, [jobs])

  const removeJob = useCallback(async (id: string) => {
    await fetch(`/api/jobs/${id}`, { method: 'DELETE' })
    // WS will deliver job_removed event
  }, [])

  const clearDone = useCallback(async () => {
    const terminal = jobs.filter((j) =>
      j.status === 'done' || j.status === 'error' || j.status === 'cancelled',
    )
    await Promise.allSettled(terminal.map((j) => fetch(`/api/jobs/${j.id}`, { method: 'DELETE' })))
  }, [jobs])

  const dispatchJob = useCallback(async (type: string, params: Record<string, unknown>) => {
    const res = await fetch('/api/jobs', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type, ...params }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }))
      throw new Error((err as { detail?: string }).detail ?? res.statusText)
    }
    const data = await res.json() as { job: JobInfo }
    return data.job
  }, [])

  const cancelJob = useCallback(async (id: string) => {
    await fetch(`/api/jobs/${id}`, { method: 'DELETE' })
  }, [])

  return (
    <Ctx.Provider value={{ jobs, unreadCount, markAllRead, removeJob, clearDone, dispatchJob, cancelJob }}>
      {children}
    </Ctx.Provider>
  )
}
