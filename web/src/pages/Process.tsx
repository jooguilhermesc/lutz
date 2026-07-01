import { useEffect, useRef, useState, useCallback } from 'react'
import { listArticles } from '../api/client'
import StreamLog from '../components/StreamLog'
import { useLanguage } from '../contexts/LanguageContext'
import ActiveJobPanel from '../components/ActiveJobPanel'
import { useNotifications } from '../contexts/NotificationsContext'

export default function Process() {
  const { t } = useLanguage()
  const { dispatchJob } = useNotifications()

  const [articles, setArticles] = useState<{ name: string; size: number }[]>([])
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState<boolean | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  const [chunkSize, setChunkSize] = useState(512)
  const [chunkOverlap, setChunkOverlap] = useState(64)
  const [skipSecurity, setSkipSecurity] = useState(false)
  const [sectionParse, setSectionParse] = useState(false)
  const [quarantine, setQuarantine] = useState(false)

  const load = useCallback(() => {
    listArticles().then((r) => setArticles(r.articles ?? []))
  }, [])

  useEffect(() => { load() }, [load])

  async function startVectorize() {
    setLogs([])
    setDone(null)
    setRunning(true)
    setDispatched(false)
    try {
      const job = await dispatchJob('vectorize', {
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        skip_security: skipSecurity,
        section_parse: sectionParse,
        quarantine,
      })
      setDispatched(true)
      const ctrl = new AbortController()
      ctrlRef.current = ctrl
      const res = await fetch(`/api/jobs/${job.id}/stream`, { signal: ctrl.signal })
      if (!res.body) return
      const reader = res.body.getReader()
      const dec = new TextDecoder()
      let buf = ''
      while (true) {
        const { done: rdDone, value } = await reader.read()
        if (rdDone) break
        buf += dec.decode(value, { stream: true })
        const parts = buf.split('\n\n')
        buf = parts.pop() ?? ''
        for (const part of parts) {
          const line = part.replace(/^data: /, '').trim()
          if (!line) continue
          if (line === '__done__') { setRunning(false); setDone(true); load() }
          else if (line.startsWith('__error__')) { setRunning(false); setDone(false) }
          else setLogs((p) => [...p, line])
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') {
        setRunning(false); setDone(false)
      }
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-800">{t('process.title')}</h2>

      {!running && (
        <ActiveJobPanel jobType="vectorize" onDone={load} />
      )}

      <div className="card grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div>
          <label className="label">{t('vectorize.opt.chunkSize')}</label>
          <input type="number" className="input" value={chunkSize} onChange={(e) => setChunkSize(+e.target.value)} min={64} max={2048} />
        </div>
        <div>
          <label className="label">{t('vectorize.opt.chunkOverlap')}</label>
          <input type="number" className="input" value={chunkOverlap} onChange={(e) => setChunkOverlap(+e.target.value)} min={0} max={512} />
        </div>
        <div className="flex flex-col gap-2">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="rounded" checked={skipSecurity} onChange={(e) => setSkipSecurity(e.target.checked)} />
            <span className="text-sm">{t('vectorize.opt.skipSecurity')}</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="rounded" checked={sectionParse} onChange={(e) => setSectionParse(e.target.checked)} />
            <span className="text-sm">{t('vectorize.opt.sectionParse')}</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" className="rounded" checked={quarantine} onChange={(e) => setQuarantine(e.target.checked)} />
            <span className="text-sm">{t('vectorize.opt.quarantine')}</span>
          </label>
        </div>
      </div>

      <div className="flex gap-3 items-center">
        <button className="btn-primary" onClick={startVectorize} disabled={running || articles.length === 0}>
          {running ? t('vectorize.running') : t('vectorize.run')}
        </button>
        {running && (
          <button className="btn-ghost" onClick={() => { ctrlRef.current?.abort(); setRunning(false) }}>
            ✕ Cancelar
          </button>
        )}
        {articles.length === 0 && !running && (
          <span className="text-xs text-slate-400">{t('process.noArticles')}</span>
        )}
        {dispatched && running && (
          <span className="text-xs text-lutz-600 bg-lutz-50 px-2.5 py-1 rounded-full border border-lutz-200">
            Rodando em segundo plano — você pode navegar livremente
          </span>
        )}
      </div>

      {done !== null && (
        <div className={`text-sm font-medium ${done ? 'text-green-600' : 'text-red-600'}`}>
          {done ? t('vectorize.done') : t('vectorize.error')}
        </div>
      )}

      <StreamLog lines={logs} running={running} />
    </div>
  )
}
