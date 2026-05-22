import { useEffect, useRef, useState } from 'react'
import { listReports, type ReportMeta } from '../api/client'
import StreamLog from '../components/StreamLog'
import { useLanguage } from '../contexts/LanguageContext'
import { useNotifications } from '../contexts/NotificationsContext'
import ActiveJobPanel from '../components/ActiveJobPanel'
import { LANG_LOCALES } from '../i18n'

export default function Roadmap() {
  const { t, lang, reportLang } = useLanguage()
  const { dispatchJob } = useNotifications()
  const locale = LANG_LOCALES[lang]

  const [reports, setReports] = useState<ReportMeta[]>([])
  const [selectedReport, setSelectedReport] = useState('')
  const [onlyRelevant, setOnlyRelevant] = useState(true)
  const [userInstructions, setUserInstructions] = useState('')
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState<boolean | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  const loadReports = () =>
    listReports().then((r) => setReports(r.reports ?? []))

  useEffect(() => { loadReports() }, [])

  async function start() {
    if (!selectedReport) return
    setLogs([])
    setDone(null)
    setRunning(true)
    setDispatched(false)
    try {
      const job = await dispatchJob('roadmap', {
        report: selectedReport,
        only_relevant: onlyRelevant,
        language: reportLang,
        user_instructions: userInstructions,
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
          if (line === '__done__') { setRunning(false); setDone(true) }
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
      <h2 className="text-xl font-bold text-slate-800">{t('roadmap.title')}</h2>
      <p className="text-sm text-slate-500">{t('roadmap.desc')}</p>

      {!running && <ActiveJobPanel jobType="roadmap" />}

      <div className="card space-y-4">
        <div>
          <label className="label">{t('roadmap.report.label')}</label>
          <div className="flex gap-2">
            <select
              className="select flex-1"
              value={selectedReport}
              onChange={(e) => setSelectedReport(e.target.value)}
            >
              <option value="">{t('roadmap.report.select')}</option>
              {reports.map((r) => (
                <option key={r.name} value={r.name}>
                  {r.name} · {new Date(r.started_at).toLocaleString(locale)} · {r.articles} artigos
                </option>
              ))}
            </select>
            <button className="btn-ghost text-xs" onClick={loadReports}>↺</button>
          </div>
          {reports.length === 0 && (
            <p className="text-xs text-slate-400 mt-1">{t('roadmap.report.empty')}</p>
          )}
        </div>

        <div className="flex items-center gap-2">
          <input
            id="only-relevant-roadmap"
            type="checkbox"
            className="rounded border-slate-300 text-lutz-500 focus:ring-lutz-400"
            checked={onlyRelevant}
            onChange={(e) => setOnlyRelevant(e.target.checked)}
          />
          <label htmlFor="only-relevant-roadmap" className="text-sm text-slate-700 cursor-pointer">
            {t('roadmap.onlyRelevant')}
          </label>
        </div>

        <div>
          <label className="label">{t('roadmap.instructions.label')}</label>
          <textarea
            className="input resize-y min-h-[80px]"
            placeholder={t('roadmap.instructions.placeholder')}
            value={userInstructions}
            onChange={(e) => setUserInstructions(e.target.value)}
            disabled={running}
          />
          <p className="text-xs text-slate-400 mt-1">{t('roadmap.instructions.hint')}</p>
        </div>

        <div className="flex gap-3 pt-2 items-center flex-wrap">
          <button className="btn-primary" onClick={start} disabled={running || !selectedReport}>
            {running ? t('roadmap.running') : t('roadmap.run')}
          </button>
          {running && (
            <button className="btn-ghost" onClick={() => { ctrlRef.current?.abort(); setRunning(false) }}>
              ✕ Cancelar
            </button>
          )}
          {dispatched && running && (
            <span className="text-xs text-lutz-600 bg-lutz-50 px-2.5 py-1 rounded-full border border-lutz-200">
              Rodando em segundo plano — você pode navegar livremente
            </span>
          )}
        </div>

        {done !== null && (
          <div className={`text-sm font-medium ${done ? 'text-green-600' : 'text-red-600'}`}>
            {done ? t('roadmap.done') : t('roadmap.error')}
          </div>
        )}
      </div>

      <StreamLog lines={logs} running={running} />
    </div>
  )
}
