import { useEffect, useRef, useState } from 'react'
import {
  listPrompts, getPrompt, savePrompt,
  listContextFiles, uploadContextFiles, deleteContextFile,
  type Prompt, type ContextFile,
} from '../api/client'
import StreamLog from '../components/StreamLog'
import { useLanguage } from '../contexts/LanguageContext'
import { useNotifications } from '../contexts/NotificationsContext'
import ActiveJobPanel from '../components/ActiveJobPanel'

function fmtSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// ── Context files panel ───────────────────────────────────────────────────────

function ContextPanel() {
  const { t } = useLanguage()
  const [files, setFiles] = useState<ContextFile[]>([])
  const [uploading, setUploading] = useState(false)
  const [uploadError, setUploadError] = useState('')
  const [open, setOpen] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)

  const load = () => listContextFiles().then((r) => setFiles(r.files ?? []))
  useEffect(() => { load() }, [])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files
    if (!picked?.length) return
    setUploading(true)
    setUploadError('')
    try {
      const result = await uploadContextFiles(picked)
      if (result.errors?.length) setUploadError(result.errors.join('; '))
      await load()
    } catch (err) {
      setUploadError((err as Error).message)
    } finally {
      setUploading(false)
      if (fileRef.current) fileRef.current.value = ''
    }
  }

  async function handleDelete(name: string) {
    if (!confirm(`${t('analysis.context.title')}: ${name}?`)) return
    await deleteContextFile(name)
    await load()
  }

  return (
    <div className="border border-slate-200 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-slate-50 hover:bg-slate-100 transition-colors text-sm font-medium text-slate-700"
        onClick={() => setOpen((v) => !v)}
      >
        <span>
          {t('analysis.context.title')}
          {files.length > 0 && (
            <span className="ml-2 text-xs font-normal text-slate-500">
              {files.length} arquivo(s)
            </span>
          )}
        </span>
        <span className="text-slate-400 text-xs">{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <div className="p-4 space-y-3">
          <p className="text-xs text-slate-500">{t('analysis.context.desc')}</p>

          <div className="flex items-center gap-3">
            <label className="btn-ghost text-xs cursor-pointer">
              {uploading ? t('analysis.context.uploading') : t('analysis.context.upload')}
              <input
                ref={fileRef}
                type="file"
                accept=".pdf,.docx,.xlsx,.xls,.pptx"
                multiple
                className="hidden"
                onChange={handleUpload}
                disabled={uploading}
              />
            </label>
            <button className="text-xs text-slate-400 hover:text-slate-600" onClick={load}>↺</button>
          </div>

          {uploadError && <p className="text-xs text-red-500">{uploadError}</p>}

          {files.length === 0 ? (
            <p className="text-xs text-slate-400 py-2 text-center">{t('analysis.context.empty')}</p>
          ) : (
            <div className="border border-slate-200 rounded-lg overflow-hidden">
              <table className="w-full text-xs">
                <tbody>
                  {files.map((f) => (
                    <tr key={f.name} className="border-t border-slate-100 first:border-t-0 hover:bg-slate-50">
                      <td className="px-3 py-2 text-slate-700 break-all">{f.name}</td>
                      <td className="px-3 py-2 text-slate-400 whitespace-nowrap">{fmtSize(f.size)}</td>
                      <td className="px-3 py-2 whitespace-nowrap">
                        {f.vectorized
                          ? <span className="text-green-600">✓ {f.chunks} chunks</span>
                          : <span className="text-amber-500">{t('analysis.context.pending')}</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button onClick={() => handleDelete(f.name)} className="text-red-400 hover:text-red-600">×</button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Analysis() {
  const { t, reportLang } = useLanguage()
  const { dispatchJob } = useNotifications()

  const [promptSource, setPromptSource] = useState<'load' | 'write'>('load')
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selected, setSelected] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)

  const [mode, setMode] = useState<'per_article' | 'rag'>('per_article')
  const [workers, setWorkers] = useState(4)
  const [maxChunks, setMaxChunks] = useState(0)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState<boolean | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  const loadPrompts = () => listPrompts().then((r) => setPrompts(r.prompts ?? []))
  useEffect(() => { loadPrompts() }, [])

  useEffect(() => {
    if (promptSource !== 'load' || !selected) { setContent(''); return }
    getPrompt(selected).then((r) => setContent(r.content))
  }, [selected, promptSource])

  async function handleSave() {
    if (!selected) return
    setSaving(true)
    await savePrompt(selected, content)
    setSaving(false)
  }

  async function startAnalysis() {
    if (promptSource === 'load' && !selected) return
    if (promptSource === 'write' && !content.trim()) return

    setLogs([])
    setDone(null)
    setRunning(true)
    setDispatched(false)
    try {
      const job = await dispatchJob('analysis', {
        prompt: promptSource === 'load' ? selected : '',
        inline_prompt: promptSource === 'write' ? content : '',
        mode,
        workers,
        max_chunks: maxChunks,
        language: reportLang,
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

  const canRun = !running && (
    promptSource === 'load' ? !!selected : content.trim().length > 0
  )

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-800">{t('analysis.title')}</h2>

      {!running && <ActiveJobPanel jobType="analysis" />}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ── Prompt ── */}
        <div className="card space-y-3">
          <label className="label">{t('analysis.prompt.label')}</label>

          <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
            {(['load', 'write'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setPromptSource(s)}
                className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${
                  promptSource === s
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {s === 'load' ? t('analysis.prompt.load') : t('analysis.prompt.write')}
              </button>
            ))}
          </div>

          {promptSource === 'load' ? (
            <>
              <div className="flex gap-2">
                <select
                  className="select flex-1"
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                >
                  <option value="">{t('analysis.prompt.select')}</option>
                  {prompts.map((p) => (
                    <option key={p.name} value={p.name}>{p.name}</option>
                  ))}
                </select>
                <button className="btn-ghost text-xs" onClick={loadPrompts}>↺</button>
              </div>

              {selected && (
                <>
                  <textarea
                    className="input font-mono text-xs h-48 resize-y"
                    value={content}
                    onChange={(e) => setContent(e.target.value)}
                    placeholder={t('analysis.prompt.placeholder')}
                  />
                  <button className="btn-ghost text-xs" onClick={handleSave} disabled={saving}>
                    {saving ? t('analysis.prompt.saving') : t('analysis.prompt.save')}
                  </button>
                </>
              )}
            </>
          ) : (
            <textarea
              className="input font-mono text-xs h-64 resize-y"
              value={content}
              onChange={(e) => setContent(e.target.value)}
              placeholder={t('analysis.prompt.inline.placeholder')}
            />
          )}
        </div>

        {/* ── Options ── */}
        <div className="card space-y-4">
          <div>
            <label className="label">{t('analysis.mode.label')}</label>
            <div className="flex gap-2">
              {(['per_article', 'rag'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setMode(m)}
                  className={`btn text-sm ${mode === m ? 'btn-primary' : 'btn-ghost'}`}
                >
                  {m === 'per_article' ? t('analysis.mode.per_article') : t('analysis.mode.rag')}
                </button>
              ))}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              {mode === 'per_article' ? t('analysis.mode.per_article.desc') : t('analysis.mode.rag.desc')}
            </p>
          </div>

          <div>
            <button
              className="flex items-center gap-1 text-xs text-slate-400 hover:text-slate-600 transition-colors"
              onClick={() => setAdvancedOpen((v) => !v)}
            >
              <span>{advancedOpen ? '▾' : '▸'}</span>
              {t('analysis.opt.advanced')}
            </button>
            {advancedOpen && (
              <div className="mt-3 grid grid-cols-2 gap-3">
                <div>
                  <label className="label">{t('analysis.opt.workers')}</label>
                  <input type="number" className="input" value={workers} min={1} max={32} onChange={(e) => setWorkers(+e.target.value)} />
                </div>
                <div>
                  <label className="label">{t('analysis.opt.maxChunks')}</label>
                  <input type="number" className="input" value={maxChunks} min={0} onChange={(e) => setMaxChunks(+e.target.value)} />
                </div>
              </div>
            )}
          </div>

          <div className="pt-2 flex gap-3 items-center flex-wrap">
            <button className="btn-primary" onClick={startAnalysis} disabled={!canRun}>
              {running ? t('analysis.running') : t('analysis.run')}
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
              {done ? t('analysis.done') : t('analysis.error')}
            </div>
          )}
        </div>
      </div>

      <ContextPanel />
      <StreamLog lines={logs} running={running} />
    </div>
  )
}
