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

export default function Analysis() {
  const { t, reportLang } = useLanguage()
  const { dispatchJob } = useNotifications()

  const [promptSource, setPromptSource] = useState<'write' | 'load'>('write')
  const [prompts, setPrompts] = useState<Prompt[]>([])
  const [selected, setSelected] = useState('')
  const [content, setContent] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveName, setSaveName] = useState('')

  const [workers, setWorkers] = useState(4)
  const [maxChunks, setMaxChunks] = useState(0)
  const [advancedOpen, setAdvancedOpen] = useState(false)

  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState<boolean | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const ctrlRef = useRef<AbortController | null>(null)

  // Context files
  const [contextFiles, setContextFiles] = useState<ContextFile[]>([])
  const [uploadingCtx, setUploadingCtx] = useState(false)
  const [uploadCtxError, setUploadCtxError] = useState('')
  const ctxFileRef = useRef<HTMLInputElement>(null)

  const loadPrompts = () => listPrompts().then((r) => setPrompts(r.prompts ?? []))
  const loadContextFiles = () => listContextFiles().then((r) => setContextFiles(r.files ?? []))

  useEffect(() => {
    loadPrompts()
    loadContextFiles()
  }, [])

  useEffect(() => {
    if (promptSource !== 'load' || !selected) { setContent(''); return }
    getPrompt(selected).then((r) => setContent(r.content))
  }, [selected, promptSource])

  async function handleSave() {
    const name = promptSource === 'load' ? selected : saveName.trim()
    if (!name) return
    setSaving(true)
    await savePrompt(name, content)
    await loadPrompts()
    if (promptSource === 'write') setSaveName('')
    setSaving(false)
  }

  async function handleCtxUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const picked = e.target.files
    if (!picked?.length) return
    setUploadingCtx(true)
    setUploadCtxError('')
    try {
      const result = await uploadContextFiles(picked)
      if (result.errors?.length) setUploadCtxError(result.errors.join('; '))
      await loadContextFiles()
    } catch (err) {
      setUploadCtxError((err as Error).message)
    } finally {
      setUploadingCtx(false)
      if (ctxFileRef.current) ctxFileRef.current.value = ''
    }
  }

  async function handleCtxDelete(name: string) {
    if (!confirm(`${t('analysis.context.title')}: ${name}?`)) return
    await deleteContextFile(name)
    await loadContextFiles()
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
        mode: 'per_article',
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
        {/* ── Prompt + Context ── */}
        <div className="card space-y-3">
          <label className="label">{t('analysis.prompt.label')}</label>

          {/* Toggle: write first, load second */}
          <div className="flex gap-1 bg-slate-100 rounded-lg p-1">
            {(['write', 'load'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setPromptSource(s)}
                className={`flex-1 text-xs font-medium py-1.5 rounded-md transition-colors ${
                  promptSource === s
                    ? 'bg-white text-slate-800 shadow-sm'
                    : 'text-slate-500 hover:text-slate-700'
                }`}
              >
                {s === 'write' ? t('analysis.prompt.write') : t('analysis.prompt.load')}
              </button>
            ))}
          </div>

          {promptSource === 'write' ? (
            <>
              <textarea
                className="input font-mono text-xs h-48 resize-y"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                placeholder={t('analysis.prompt.inline.placeholder')}
              />
              <div className="flex gap-2 items-center">
                <input
                  className="input text-xs flex-1"
                  value={saveName}
                  onChange={(e) => setSaveName(e.target.value)}
                  placeholder={t('analysis.prompt.saveName.placeholder')}
                />
                <button
                  className="btn-ghost text-xs whitespace-nowrap"
                  onClick={handleSave}
                  disabled={saving || !saveName.trim() || !content.trim()}
                >
                  {saving ? t('analysis.prompt.saving') : t('analysis.prompt.save')}
                </button>
              </div>
            </>
          ) : (
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
          )}

          {/* Context files — inline */}
          <div className="border-t border-slate-100 pt-3 space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-xs font-medium text-slate-600">
                {t('analysis.context.title')}
                {contextFiles.length > 0 && (
                  <span className="ml-1.5 font-normal text-slate-400">({contextFiles.length})</span>
                )}
              </span>
              <div className="flex items-center gap-2">
                <label className="btn-ghost text-xs cursor-pointer">
                  {uploadingCtx ? t('analysis.context.uploading') : '+ Adicionar'}
                  <input
                    ref={ctxFileRef}
                    type="file"
                    accept=".pdf,.docx,.xlsx,.xls,.pptx"
                    multiple
                    className="hidden"
                    onChange={handleCtxUpload}
                    disabled={uploadingCtx}
                  />
                </label>
                <button className="text-xs text-slate-400 hover:text-slate-600" onClick={loadContextFiles}>↺</button>
              </div>
            </div>

            <p className="text-xs text-slate-400">{t('analysis.context.desc')}</p>

            {uploadCtxError && <p className="text-xs text-red-500">{uploadCtxError}</p>}

            {contextFiles.length > 0 && (
              <div className="border border-slate-200 rounded-lg overflow-hidden">
                <table className="w-full text-xs">
                  <tbody>
                    {contextFiles.map((f) => (
                      <tr key={f.name} className="border-t border-slate-100 first:border-t-0 hover:bg-slate-50">
                        <td className="px-3 py-1.5 text-slate-700 break-all">{f.name}</td>
                        <td className="px-3 py-1.5 text-slate-400 whitespace-nowrap">{fmtSize(f.size)}</td>
                        <td className="px-3 py-1.5 whitespace-nowrap">
                          {f.vectorized
                            ? <span className="text-green-600">✓ {f.chunks} chunks</span>
                            : <span className="text-amber-500">{t('analysis.context.pending')}</span>}
                        </td>
                        <td className="px-3 py-1.5 text-right">
                          <button onClick={() => handleCtxDelete(f.name)} className="text-red-400 hover:text-red-600">×</button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        {/* ── Options ── */}
        <div className="card space-y-4">
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

      <StreamLog lines={logs} running={running} />
    </div>
  )
}
