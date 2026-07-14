import { useEffect, useRef, useState } from 'react'
import {
  getProject, listArticles, getVectorStore, listReports, getReport,
  listPrompts, savePrompt, getPrompt,
  listContextFiles, uploadContextFiles, deleteContextFile,
  getConfig, saveConfig, getProviderModels, resetVectorStore,
  type Article, type VectorStoreInfo, type ReportMeta, type Report, type Prompt, type ProjectInfo,
  type ContextFile, type ModelInfo,
} from './api/client'
import { useLanguage } from './contexts/LanguageContext'
import { useNotifications } from './contexts/NotificationsContext'
import { NotificationsPanel } from './components/NotificationsPanel'
import BibliotecaTab from './tabs/BibliotecaTab'
import ResultadosTab from './tabs/ResultadosTab'
import RelatoriosTab from './tabs/RelatoriosTab'
import HistoryDrawer from './components/HistoryDrawer'
import SettingsModal from './components/SettingsModal'
import VectorStoreModal from './components/VectorStoreModal'
import { useTour } from './hooks/useTour'

// ── Constants ─────────────────────────────────────────────────────────────────

const PROVIDERS = [
  { id: 'anthropic',           name: 'Anthropic',            mono: 'A',  color: '#c96442', tagline: 'Claude — primário' },
  { id: 'openai',              name: 'OpenAI',               mono: 'OA', color: '#1a7f64', tagline: 'GPT family' },
  { id: 'openrouter',          name: 'OpenRouter',           mono: 'OR', color: '#7c3aed', tagline: 'Multi-provider' },
  { id: 'docker_model_runner', name: 'Docker Model Runner',  mono: 'D',  color: '#3b82f6', tagline: 'Modelos locais' },
]


const TEMPLATES = [
  { id: 'rct',    name: 'RCTs farmacológicos' },
  { id: 'sys',    name: 'Revisões sistemáticas' },
  { id: 'qualit', name: 'Qualitativo' },
]

type Tab = 'biblioteca' | 'resultados' | 'relatorios'

// ── Spinner SVG ───────────────────────────────────────────────────────────────

function Spinner({ color = '#fff' }: { color?: string }) {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
      style={{ animation: 'vspin .8s linear infinite', flexShrink: 0 }}>
      <circle cx="8" cy="8" r="6.4" stroke={`${color}59`} strokeWidth="2"/>
      <path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" stroke={color} strokeWidth="2" strokeLinecap="round"/>
    </svg>
  )
}

// ── Provider tile ─────────────────────────────────────────────────────────────

function ProviderTile({ mono, color, size = 28 }: { mono: string; color: string; size?: number }) {
  return (
    <span style={{
      flexShrink: 0, width: size, height: size, borderRadius: 7, background: color,
      color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center',
      fontSize: size > 28 ? 13 : 11, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace',
    }}>
      {mono}
    </span>
  )
}

// ── Main shell ────────────────────────────────────────────────────────────────

export default function AppShell() {
  const { reportLang } = useLanguage()
  const { jobs, dispatchJob } = useNotifications()
  const { startTour } = useTour()

  // ── Shared data ──
  const [project, setProject] = useState<ProjectInfo | null>(null)
  const [articles, setArticles] = useState<Article[]>([])
  const [vectorStore, setVectorStore] = useState<VectorStoreInfo | null>(null)
  const [reports, setReports] = useState<ReportMeta[]>([])
  const [activeReport, setActiveReport] = useState<Report | null>(null)
  const [savedPrompts, setSavedPrompts] = useState<Prompt[]>([])

  // ── Config / LLM ──
  const [llmProvider, setLlmProvider] = useState('anthropic')
  const [llmModel, setLlmModel] = useState('claude-sonnet-4-6')
  const [embModel, setEmbModel] = useState('text-embedding-3-small')
  const [, setConfigLoaded] = useState(false)
  const [providerKeys, setProviderKeys] = useState<Record<string, boolean>>({})
  const [providerModels, setProviderModels] = useState<ModelInfo[]>([])
  const [modelsLoading, setModelsLoading] = useState(false)
  const [modelSearch, setModelSearch] = useState('')
  const [embModels, setEmbModels] = useState<ModelInfo[]>([])
  const [embModelsLoading, setEmbModelsLoading] = useState(false)
  const [embMenuOpen, setEmbMenuOpen] = useState(false)
  const [embModelSearch, setEmbModelSearch] = useState('')

  // ── Prompt ──
  const [promptText, setPromptText] = useState('')
  const [activeTemplate, setActiveTemplate] = useState<string | null>(null)
  const [saveName, setSaveName] = useState('')
  const [savingPrompt, setSavingPrompt] = useState(false)

  // ── Context files ──
  const [contextFiles, setContextFiles] = useState<ContextFile[]>([])
  const [uploadingContext, setUploadingContext] = useState(false)
  const ctxInputRef = useRef<HTMLInputElement>(null)

  // ── Analysis ──
  const [analysisRunning, setAnalysisRunning] = useState(false)
  const [analysisLogs, setAnalysisLogs] = useState<string[]>([])
  const [analysisDone, setAnalysisDone] = useState<boolean | null>(null)
  const [workers, setWorkers] = useState(4)
  const ctrlRef = useRef<AbortController | null>(null)

  // ── UI state ──
  const [activeTab, setActiveTab] = useState<Tab>('biblioteca')
  const [showHistory, setShowHistory] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [providerMenuOpen, setProviderMenuOpen] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [showVectorStoreModal, setShowVectorStoreModal] = useState(false)
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem('lutz-theme')
    return saved ? saved === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches
  })

  // ── Vectorize job tracking ──
  const vectorizeJob = jobs.find(j => j.type === 'vectorize' && (j.status === 'running' || j.status === 'queued'))
  const vectorizeRunning = !!vectorizeJob

  // ── Theme ──
  useEffect(() => {
    document.documentElement.classList.toggle('dark', dark)
    localStorage.setItem('lutz-theme', dark ? 'dark' : 'light')
  }, [dark])

  // ── Load everything on mount ──
  useEffect(() => {
    loadAll()
  }, [])

  // Fetch LLM and embedding model lists whenever the provider changes
  useEffect(() => {
    let cancelled = false
    setModelsLoading(true)
    setProviderModels([])
    getProviderModels(llmProvider, 'llm').then(({ models }) => {
      if (!cancelled) { setProviderModels(models); setModelsLoading(false) }
    }).catch(() => { if (!cancelled) setModelsLoading(false) })
    setEmbModelsLoading(true)
    setEmbModels([])
    getProviderModels(llmProvider, 'embedding').then(({ models }) => {
      if (!cancelled) { setEmbModels(models); setEmbModelsLoading(false) }
    }).catch(() => { if (!cancelled) setEmbModelsLoading(false) })
    return () => { cancelled = true }
  }, [llmProvider])

  // Reset search when dropdowns close
  useEffect(() => {
    if (!modelMenuOpen) setModelSearch('')
  }, [modelMenuOpen])

  useEffect(() => {
    if (!embMenuOpen) setEmbModelSearch('')
  }, [embMenuOpen])

  // Reload vector store after vectorize job completes
  useEffect(() => {
    const allDone = jobs.every(j => j.status === 'done' || j.status === 'error' || j.status === 'cancelled')
    if (allDone && jobs.length > 0) {
      loadVectorStore()
    }
  }, [jobs])

  async function loadAll() {
    await Promise.allSettled([
      getProject().then(setProject).catch(() => {}),
      listArticles().then(r => setArticles(r.articles ?? [])).catch(() => {}),
      loadVectorStore(),
      loadContextFiles(),
      listReports().then(r => {
        const reps = r.reports ?? []
        setReports(reps)
        if (reps.length > 0) {
          getReport(reps[0].name).then(setActiveReport).catch(() => {})
        }
      }).catch(() => {}),
      listPrompts().then(r => setSavedPrompts(r.prompts ?? [])).catch(() => {}),
      getConfig().then(c => {
        if (c.LLM_PROVIDER) setLlmProvider(c.LLM_PROVIDER)
        if (c.LLM_MODEL) setLlmModel(c.LLM_MODEL)
        if (c.EMBEDDING_MODEL) setEmbModel(c.EMBEDDING_MODEL)
        if (c.ANALYSIS_WORKERS) setWorkers(Math.max(1, parseInt(c.ANALYSIS_WORKERS) || 4))
        setProviderKeys({ anthropic: !!c.has_anthropic_key, openai: !!c.has_openai_key, openrouter: !!c.has_openrouter_key, docker_model_runner: true })
        setConfigLoaded(true)
      }).catch(() => { setConfigLoaded(true) }),
    ])
  }

  async function loadVectorStore() {
    getVectorStore().then(setVectorStore).catch(() => {})
  }

  async function loadContextFiles() {
    try {
      const r = await listContextFiles()
      setContextFiles(r.files ?? [])
    } catch { /* ignore */ }
  }

  async function handleUploadContext(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files || files.length === 0) return
    // Show optimistic pills immediately so the user sees feedback right away
    const optimistic: ContextFile[] = Array.from(files).map(f => ({
      name: f.name, size: f.size, vectorized: false, chunks: 0,
    }))
    setContextFiles(prev => {
      const names = new Set(prev.map(x => x.name))
      return [...prev, ...optimistic.filter(o => !names.has(o.name))]
    })
    setUploadingContext(true)
    try {
      await uploadContextFiles(files)
      // Refresh once after server confirms — vectorization is synchronous on backend
      await loadContextFiles()
    } catch {
      // On error roll back optimistic entries
      await loadContextFiles()
    } finally {
      setUploadingContext(false)
      if (ctxInputRef.current) ctxInputRef.current.value = ''
    }
  }

  async function handleDeleteContext(name: string) {
    // Optimistic removal
    setContextFiles(prev => prev.filter(f => f.name !== name))
    await deleteContextFile(name).catch(() => {})
    await loadContextFiles()
  }

  async function loadReports() {
    try {
      const r = await listReports()
      setReports(r.reports ?? [])
    } catch { /* ignore */ }
  }

  async function loadArticles() {
    try {
      const r = await listArticles()
      setArticles(r.articles ?? [])
    } catch { /* ignore */ }
    loadVectorStore()
  }

  async function handleVectorize() {
    await dispatchJob('vectorize', { chunk_size: 512, chunk_overlap: 64 })
  }

  async function handleResetVectorStore() {
    await resetVectorStore().catch(() => {})
    await loadVectorStore()
  }

  function handleSettingsSaved() {
    getConfig().then(c => {
      if (c.LLM_PROVIDER) setLlmProvider(c.LLM_PROVIDER)
      if (c.LLM_MODEL) setLlmModel(c.LLM_MODEL)
      if (c.EMBEDDING_MODEL) setEmbModel(c.EMBEDDING_MODEL)
      if (c.ANALYSIS_WORKERS) setWorkers(Math.max(1, parseInt(c.ANALYSIS_WORKERS) || 4))
      setProviderKeys({ anthropic: !!c.has_anthropic_key, openai: !!c.has_openai_key, openrouter: !!c.has_openrouter_key, docker_model_runner: true })
    }).catch(() => {})
  }

  async function handleChangeProvider(providerId: string) {
    setProviderMenuOpen(false)
    setModelMenuOpen(false)
    setEmbMenuOpen(false)
    setLlmProvider(providerId)  // triggers useEffect → fetches both model lists
    try {
      const [{ models: llmMods }, { models: embMods }] = await Promise.all([
        getProviderModels(providerId, 'llm'),
        getProviderModels(providerId, 'embedding'),
      ])
      const firstLlm = llmMods[0]
      const firstEmb = embMods[0]
      const cfg: Record<string, string> = { LLM_PROVIDER: providerId }
      if (firstLlm) { setLlmModel(firstLlm.id); cfg['LLM_MODEL'] = firstLlm.id }
      if (firstEmb) { setEmbModel(firstEmb.id); cfg['EMBEDDING_MODEL'] = firstEmb.id }
      await saveConfig(cfg)
    } catch { /* ignore */ }
  }

  async function handleChangeModel(modelId: string) {
    setLlmModel(modelId)
    setModelMenuOpen(false)
    try {
      await saveConfig({ LLM_MODEL: modelId })
    } catch { /* ignore */ }
  }

  async function handleChangeEmbModel(modelId: string) {
    setEmbModel(modelId)
    setEmbMenuOpen(false)
    try {
      await saveConfig({ EMBEDDING_MODEL: modelId })
    } catch { /* ignore */ }
  }

  async function handleSavePrompt() {
    const name = saveName.trim()
    if (!name || !promptText.trim()) return
    setSavingPrompt(true)
    await savePrompt(name, promptText).catch(() => {})
    await listPrompts().then(r => setSavedPrompts(r.prompts ?? {})).catch(() => {})
    setSaveName('')
    setSavingPrompt(false)
  }

  async function runAnalysis() {
    if (analysisRunning || !promptText.trim()) return
    setAnalysisLogs([])
    setAnalysisDone(null)
    setAnalysisRunning(true)
    setActiveTab('resultados')
    try {
      const job = await dispatchJob('analysis', {
        inline_prompt: promptText,
        mode: 'per_article',
        workers,
        max_chunks: 0,
        use_context_files: contextFiles.length > 0,
        language: reportLang,
      })
      const ctrl = new AbortController()
      ctrlRef.current = ctrl
      const res = await fetch(`/api/jobs/${job.id}/stream`, { signal: ctrl.signal })
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
            setAnalysisRunning(false); setAnalysisDone(true)
            // Load the freshest report
            listReports().then(r => {
              const reps = r.reports ?? []
              setReports(reps)
              if (reps.length > 0) {
                getReport(reps[0].name).then(setActiveReport).catch(() => {})
              }
            }).catch(() => {})
          } else if (line.startsWith('__error__')) {
            setAnalysisRunning(false); setAnalysisDone(false)
          } else {
            setAnalysisLogs(p => [...p, line])
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') {
        setAnalysisRunning(false); setAnalysisDone(false)
      }
    }
  }

  // ── Derived values ─────────────────────────────────────────────────────────

  const provider = PROVIDERS.find(p => p.id === llmProvider) ?? PROVIDERS[0]

  const llmModelInList = providerModels.find(m => m.id === llmModel)
  const currentModel = llmModelInList ?? (llmModel ? { id: llmModel, name: llmModel } : providerModels[0])
  const providerModelsWithCurrent = (llmModelInList || !llmModel)
    ? providerModels
    : [{ id: llmModel, name: llmModel }, ...providerModels]

  const embModelInList = embModels.find(m => m.id === embModel)
  const currentEmbModel = embModelInList ?? (embModel ? { id: embModel, name: embModel } : embModels[0])
  const embModelsWithCurrent = (embModelInList || !embModel)
    ? embModels
    : [{ id: embModel, name: embModel }, ...embModels]

  const pricePerM = currentModel?.price ?? 3
  const filteredModels = modelSearch
    ? providerModelsWithCurrent.filter(m =>
        m.name.toLowerCase().includes(modelSearch.toLowerCase()) ||
        m.id.toLowerCase().includes(modelSearch.toLowerCase())
      )
    : providerModelsWithCurrent
  const filteredEmbModels = embModelSearch
    ? embModelsWithCurrent.filter(m =>
        m.name.toLowerCase().includes(embModelSearch.toLowerCase()) ||
        m.id.toLowerCase().includes(embModelSearch.toLowerCase())
      )
    : embModelsWithCurrent

  const vectorizedCount = vectorStore?.unique_documents ?? 0
  const totalArticles = articles.length
  const pendingCount = totalArticles - vectorizedCount

  const estimatedTokens = vectorizedCount * 9400
  const estimatedCost = currentModel?.price === undefined && !modelsLoading
    ? '—'
    : pricePerM === 0
      ? 'gratuito'
      : `$${((estimatedTokens / 1_000_000) * pricePerM).toFixed(2)}`

  // Pipeline step statuses
  const step1Done = totalArticles > 0
  const step2Done = pendingCount <= 0 && vectorizedCount > 0
  const step2Partial = vectorizedCount > 0 && pendingCount > 0
  const step3Done = activeReport !== null

  const TABS: Array<{ id: Tab; label: string; count: number }> = [
    { id: 'biblioteca', label: 'Biblioteca', count: totalArticles },
    { id: 'resultados', label: 'Resultados',  count: (activeReport?.articles ?? []).length },
    { id: 'relatorios', label: 'Relatórios',  count: reports.length },
  ]

  const canAnalyze = !analysisRunning && vectorizedCount > 0 && promptText.trim().length > 0

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100vh', overflow: 'hidden' }}>

      {/* ── TOP BAR ── */}
      <header style={{
        flexShrink: 0, height: 56, display: 'flex', alignItems: 'center', gap: 16,
        padding: '0 20px', background: 'var(--surface)', borderBottom: '1px solid var(--border)', zIndex: 20,
      }}>
        {/* Logo */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 11 }}>
          <div style={{
            width: 30, height: 30, borderRadius: 7, background: '#1A9494',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <svg width="15" height="15" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="5.5" stroke="#fff" strokeWidth="1.5"/>
              <path d="M8 4v4l2.5 1.5" stroke="#fff" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', lineHeight: 1.05 }}>
            <span style={{ fontSize: 15, fontWeight: 700, letterSpacing: '-.2px', color: 'var(--text)' }}>lutz</span>
            <span style={{ fontSize: 10, color: 'var(--text-faint)', fontWeight: 500, letterSpacing: '.3px' }}>RESEARCH</span>
          </div>
        </div>

        <div style={{ width: 1, height: 22, background: 'var(--border)' }} />

        {/* Project name */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '5px 8px' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ color: 'var(--text-muted)' }}>
            <path d="M2 5.5A1.5 1.5 0 0 1 3.5 4H7l1.5 1.8H12.5A1.5 1.5 0 0 1 14 7.3v5.2A1.5 1.5 0 0 1 12.5 14h-9A1.5 1.5 0 0 1 2 12.5V5.5Z"
              stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
          </svg>
          <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace' }}>
            {project?.root?.split('/').slice(-1)[0] ?? 'lutz project'}
          </span>
        </div>

        <div style={{ flex: 1 }} />

        {/* Cost chip */}
        <div id="tour-cost" style={{
          display: 'flex', alignItems: 'center', gap: 7, padding: '5px 11px',
          background: 'var(--surface-3)', border: '1px solid var(--border)', borderRadius: 7, whiteSpace: 'nowrap',
        }}>
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.5" stroke="var(--text-faint)" strokeWidth="1.3"/>
            <path d="M8 4.5v3.5l2.2 1.3" stroke="var(--text-faint)" strokeWidth="1.3" strokeLinecap="round"/>
          </svg>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>Est. análise</span>
          <span style={{ fontSize: 12, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)' }}>{estimatedCost}</span>
        </div>

        {/* Notifications */}
        <NotificationsPanel />

        {/* Tour button */}
        <button onClick={startTour} title="Tour pela interface" style={{
          display: 'flex', alignItems: 'center', gap: 7, background: 'none',
          border: '1px solid var(--border)', cursor: 'pointer', padding: '7px 11px',
          borderRadius: 7, color: 'var(--text-muted)', fontSize: 13, fontWeight: 500,
        }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3"/>
            <path d="M8 5v3.5M8 11v.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
          </svg>
          Tour
        </button>

        {/* History button */}
        <button id="tour-history" onClick={() => setShowHistory(v => !v)} style={{
          display: 'flex', alignItems: 'center', gap: 7, background: 'none',
          border: '1px solid var(--border)', cursor: 'pointer', padding: '7px 11px',
          borderRadius: 7, color: 'var(--text)', fontSize: 13, fontWeight: 500,
        }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.3"/>
            <path d="M8 4.5V8l2.5 1.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          Histórico
        </button>

        {/* Theme toggle */}
        <button onClick={() => setDark(v => !v)} title={dark ? 'Tema claro' : 'Tema escuro'} style={{
          width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'none', border: '1px solid var(--border)', cursor: 'pointer', borderRadius: 7,
          color: 'var(--text-muted)',
        }}>
          {dark ? (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="3.5" stroke="currentColor" strokeWidth="1.3"/>
              <path d="M8 1.5v1M8 13.5v1M14.5 8h-1M2.5 8h-1M12.3 3.7l-.7.7M4.4 11.6l-.7.7M12.3 12.3l-.7-.7M4.4 4.4l-.7-.7"
                stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
            </svg>
          ) : (
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
              <path d="M13.5 9.5A5.5 5.5 0 0 1 6.5 2.5a5.5 5.5 0 1 0 7 7Z"
                stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
            </svg>
          )}
        </button>

        {/* Settings */}
        <button id="tour-settings" onClick={() => setShowSettings(v => !v)} style={{
          width: 34, height: 34, display: 'flex', alignItems: 'center', justifyContent: 'center',
          background: 'none', border: '1px solid var(--border)', cursor: 'pointer', borderRadius: 7,
          color: 'var(--text-muted)',
        }}>
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
            <path d="M6.5 2h3l.4 1.5a4.5 4.5 0 0 1 1.1.65l1.45-.5 1.5 2.6-1.1 1.05c.04.23.05.46.05.7s-.01.47-.05.7l1.1 1.05-1.5 2.6-1.45-.5a4.5 4.5 0 0 1-1.1.65L9.5 14h-3l-.4-1.5a4.5 4.5 0 0 1-1.1-.65l-1.45.5-1.5-2.6 1.1-1.05A4.5 4.5 0 0 1 3.1 8c0-.24.01-.47.05-.7L2.05 6.25l1.5-2.6 1.45.5A4.5 4.5 0 0 1 6.1 3.5L6.5 2Z"
              stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"/>
            <circle cx="8" cy="8" r="2" stroke="currentColor" strokeWidth="1.3"/>
          </svg>
        </button>
      </header>

      {/* ── BODY ── */}
      <div style={{ flex: 1, display: 'flex', minHeight: 0 }}>

        {/* ── LEFT RAIL ── */}
        <aside style={{
          flexShrink: 0, width: 388, background: 'var(--surface)',
          borderRight: '1px solid var(--border)', display: 'flex', flexDirection: 'column', minHeight: 0,
        }}>
          <div style={{ flex: 1, overflowY: 'auto', padding: 20 }}>

            {/* Pipeline status */}
            <div id="tour-pipeline" style={{
              marginBottom: 20, background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 10, padding: '12px 14px',
            }}>
              <div className="section-label" style={{ marginBottom: 10 }}>Pipeline</div>

              {[
                {
                  label: 'Biblioteca',
                  sub: step1Done ? `${totalArticles} PDF${totalArticles !== 1 ? 's' : ''} carregados` : 'Nenhum arquivo ainda',
                  icon: step1Done ? '✓' : '○',
                  iconBg: step1Done ? '#e6f5ee' : '#eef0f3',
                  iconFg: step1Done ? '#0f6b47' : '#9aa3b0',
                  hasBtn: false, btnLabel: '', onBtn: () => {},
                },
                {
                  label: 'Vetorizado',
                  sub: step2Done ? `${vectorizedCount} artigos prontos` :
                       step2Partial ? `${vectorizedCount} / ${totalArticles} — ${pendingCount} pendentes` :
                       'Nenhum artigo vetorizado',
                  icon: step2Done ? '✓' : (step2Partial ? '…' : '○'),
                  iconBg: step2Done ? '#e6f5ee' : (step2Partial ? '#fbf1dd' : '#eef0f3'),
                  iconFg: step2Done ? '#0f6b47' : (step2Partial ? '#8a6414' : '#9aa3b0'),
                  hasBtn: (vectorizedCount > 0 || pendingCount > 0) && !vectorizeRunning,
                  btnLabel: pendingCount > 0 ? `Vetorizar (${pendingCount})` : 'Detalhes',
                  onBtn: () => setShowVectorStoreModal(true),
                },
                {
                  label: 'Análise',
                  sub: step3Done ? `Concluída · ${(activeReport?.articles ?? []).filter(a => a.relevance === 'INCLUDE').length} para incluir` :
                       vectorizedCount > 0 ? 'Pronto para analisar' : 'Aguardando vetorização',
                  icon: step3Done ? '✓' : '○',
                  iconBg: step3Done ? '#e6f5ee' : '#eef0f3',
                  iconFg: step3Done ? '#0f6b47' : '#9aa3b0',
                  hasBtn: false, btnLabel: '', onBtn: () => {},
                },
              ].map((s, i) => (
                <div key={i} style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  marginTop: i > 0 ? 10 : 0,
                  opacity: i === 1 && totalArticles === 0 ? 0.4 : i === 2 && vectorizedCount === 0 ? 0.4 : 1,
                }}>
                  <span style={{
                    flexShrink: 0, width: 20, height: 20, borderRadius: '50%',
                    background: s.iconBg, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 11, color: s.iconFg, fontWeight: 700,
                  }}>{s.icon}</span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 12.5, fontWeight: 600, color: '#1a1d23' }}>{s.label}</div>
                    <div style={{ fontSize: 11, color: '#8a92a0', marginTop: 1 }}>{s.sub}</div>
                  </div>
                  {s.hasBtn && (
                    <button onClick={s.onBtn} style={{
                      fontSize: 11, fontWeight: 600, padding: '4px 9px',
                      border: 'none', borderRadius: 6, background: '#1A9494',
                      cursor: 'pointer', color: '#fff', whiteSpace: 'nowrap',
                    }}>
                      {vectorizeRunning ? 'Vetorizando…' : s.btnLabel}
                    </button>
                  )}
                </div>
              ))}
            </div>

            {/* Prompt */}
            <div id="tour-criteria" style={{ marginBottom: 20 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
                <div className="section-label">Critério de triagem</div>
                <span style={{ fontSize: 11, color: '#b6bcc7', fontFamily: 'IBM Plex Mono, monospace' }}>
                  {promptText.length} chars
                </span>
              </div>
              <textarea
                value={promptText}
                onChange={e => setPromptText(e.target.value)}
                placeholder="Descreva os critérios de inclusão/exclusão para triagem dos artigos…"
                style={{
                  width: '100%', height: 96, resize: 'none', padding: '12px 13px',
                  border: '1px solid var(--border-2)', borderRadius: 9, fontSize: 13.5, lineHeight: 1.5,
                  color: 'var(--text)', outline: 'none', background: 'var(--surface-2)',
                  fontFamily: 'IBM Plex Sans, sans-serif',
                }}
              />

              {/* Context file attachments */}
              <div style={{ marginTop: 8 }}>
                {/* File pills */}
                {contextFiles.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: 8 }}>
                    {contextFiles.map(f => (
                      <div key={f.name} style={{
                        display: 'inline-flex', alignItems: 'center', gap: 5,
                        padding: '4px 8px 4px 9px', borderRadius: 8,
                        background: 'var(--surface-2)', border: '1px solid var(--border)',
                        fontSize: 11.5, maxWidth: 180,
                      }}>
                        <svg width="11" height="11" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                          <path d="M9 2H4a1.5 1.5 0 0 0-1.5 1.5v9A1.5 1.5 0 0 0 4 14h8a1.5 1.5 0 0 0 1.5-1.5V6.5L9 2Z"
                            stroke="#1A9494" strokeWidth="1.3" strokeLinejoin="round"/>
                          <path d="M9 2v4.5H13.5" stroke="#1A9494" strokeWidth="1.3" strokeLinejoin="round"/>
                        </svg>
                        <span style={{
                          color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace',
                          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                        }}>
                          {f.name}
                        </span>
                        {f.vectorized && (
                          <span style={{
                            width: 6, height: 6, borderRadius: '50%',
                            background: '#1f9d6b', flexShrink: 0,
                          }} title="Vetorizado" />
                        )}
                        <button onClick={() => handleDeleteContext(f.name)} style={{
                          flexShrink: 0, background: 'none', border: 'none', cursor: 'pointer',
                          color: 'var(--text-faint)', lineHeight: 1, padding: '0 1px', fontSize: 13,
                        }}>×</button>
                      </div>
                    ))}
                  </div>
                )}

                {/* Attach button */}
                <label style={{
                  display: 'inline-flex', alignItems: 'center', gap: 6, cursor: 'pointer',
                  fontSize: 12, fontWeight: 500, color: uploadingContext ? 'var(--text-faint)' : '#1A9494',
                  padding: '5px 10px', borderRadius: 7, border: '1px dashed',
                  borderColor: uploadingContext ? 'var(--border)' : '#9ecfcf',
                  background: 'transparent',
                }}>
                  <input
                    ref={ctxInputRef}
                    type="file"
                    multiple
                    accept=".pdf,.docx,.xlsx,.xls,.pptx"
                    style={{ display: 'none' }}
                    onChange={handleUploadContext}
                    disabled={uploadingContext}
                  />
                  {uploadingContext ? (
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
                      style={{ animation: 'vspin .8s linear infinite' }}>
                      <circle cx="8" cy="8" r="6" stroke="var(--border-2)" strokeWidth="2"/>
                      <path d="M8 2a6 6 0 0 1 6 6" stroke="#1A9494" strokeWidth="2" strokeLinecap="round"/>
                    </svg>
                  ) : (
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                      <path d="M13.5 10v1.5A1.5 1.5 0 0 1 12 13H4a1.5 1.5 0 0 1-1.5-1.5V10"
                        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                      <path d="M8 2v7M5.5 4.5 8 2l2.5 2.5"
                        stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                  )}
                  {uploadingContext ? 'Processando…' : 'Anexar arquivo'}
                  <span style={{ color: 'var(--text-faint)', fontSize: 10.5 }}>PDF · DOCX · XLSX · PPTX</span>
                </label>
              </div>

              {/* Templates row */}
              <div id="tour-templates" style={{ display: 'flex', flexWrap: 'wrap', gap: 7, marginTop: 10 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: '#8a92a0', alignSelf: 'center', marginRight: 1 }}>
                  Templates
                </span>
                {savedPrompts.map(p => (
                  <button key={p.name} onClick={async () => {
                    const { content } = await getPrompt(p.name)
                    setPromptText(content)
                    setActiveTemplate(p.name)
                  }} style={{
                    fontSize: 12, fontWeight: 500, padding: '5px 11px', borderRadius: 15, cursor: 'pointer',
                    border: `1px solid ${activeTemplate === p.name ? '#1A9494' : '#e4e6eb'}`,
                    background: activeTemplate === p.name ? '#e8f8f8' : '#fff',
                    color: activeTemplate === p.name ? '#1A9494' : '#5b6472',
                  }}>
                    {p.name}
                  </button>
                ))}
                {TEMPLATES.filter(t => !savedPrompts.find(p => p.name === t.name)).slice(0, 2).map(t => (
                  <button key={t.id} onClick={() => setActiveTemplate(t.id)} style={{
                    fontSize: 12, fontWeight: 500, padding: '5px 11px', borderRadius: 15, cursor: 'pointer',
                    border: `1px solid ${activeTemplate === t.id ? '#1A9494' : '#e4e6eb'}`,
                    background: activeTemplate === t.id ? '#e8f8f8' : '#fff',
                    color: activeTemplate === t.id ? '#1A9494' : '#5b6472',
                  }}>
                    {t.name}
                  </button>
                ))}
              </div>
              {/* Save prompt */}
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <input value={saveName} onChange={e => setSaveName(e.target.value)}
                  placeholder="Salvar como…"
                  style={{
                    flex: 1, padding: '5px 10px', border: '1px solid #d3d7de', borderRadius: 7,
                    fontSize: 12, outline: 'none', color: '#1a1d23', background: '#fcfcfd',
                  }} />
                <button onClick={handleSavePrompt}
                  disabled={savingPrompt || !saveName.trim() || !promptText.trim()}
                  style={{
                    padding: '5px 10px', border: '1px solid #d3d7de', borderRadius: 7,
                    background: 'none', cursor: 'pointer', fontSize: 12, fontWeight: 500,
                    color: '#5b6472', opacity: savingPrompt || !saveName.trim() || !promptText.trim() ? 0.5 : 1,
                  }}>
                  Salvar
                </button>
              </div>
            </div>

            {/* Provider */}
            <div id="tour-provider" style={{ marginBottom: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }}>
                <div className="section-label">Provedor LLM</div>
                <button onClick={() => setShowSettings(true)}
                  style={{ fontSize: 12, fontWeight: 500, color: '#1A9494', background: 'none', border: 'none', cursor: 'pointer' }}>
                  Gerenciar
                </button>
              </div>
              <div style={{ position: 'relative' }}>
                <button onClick={() => { setProviderMenuOpen(v => !v); setModelMenuOpen(false) }} style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 11, padding: '10px 12px',
                  border: '1px solid var(--border-2)', borderRadius: 9, background: 'var(--surface)', cursor: 'pointer', textAlign: 'left',
                }}>
                  <ProviderTile mono={provider.mono} color={provider.color} size={30} />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 13.5, fontWeight: 600, lineHeight: 1.2, color: 'var(--text)' }}>{provider.name}</div>
                    <div style={{ fontSize: 11.5, color: 'var(--text-faint)', lineHeight: 1.3 }}>{provider.tagline}</div>
                  </div>
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                    <path d="m4 6 4 4 4-4" stroke="var(--text-faint)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {providerMenuOpen && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
                    background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 10,
                    boxShadow: '0 12px 32px rgba(20,25,40,.22)', padding: 6, zIndex: 30,
                  }}>
                    {PROVIDERS.map(p => (
                      <button key={p.id} onClick={() => handleChangeProvider(p.id)} style={{
                        width: '100%', display: 'flex', alignItems: 'center', gap: 11, padding: '9px 10px',
                        border: 'none', borderRadius: 8,
                        background: p.id === llmProvider ? 'var(--surface-3)' : 'none', cursor: 'pointer',
                      }}>
                        <ProviderTile mono={p.mono} color={p.color} size={28} />
                        <div style={{ flex: 1, textAlign: 'left' }}>
                          <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--text)' }}>{p.name}</div>
                          <div style={{ fontSize: 11, color: 'var(--text-faint)' }}>{p.tagline}</div>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </div>

            {/* LLM Model */}
            <div style={{ marginBottom: 18 }}>
              <div className="section-label" style={{ marginBottom: 9 }}>Modelo LLM</div>
              <div style={{ position: 'relative' }}>
                <button onClick={() => { setModelMenuOpen(v => !v); setProviderMenuOpen(false) }} style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                  border: '1px solid var(--border-2)', borderRadius: 9, background: 'var(--surface)', cursor: 'pointer', textAlign: 'left',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {modelsLoading ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <Spinner color="var(--text-faint)" />
                        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Carregando modelos…</span>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontSize: 13.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', lineHeight: 1.2, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {currentModel?.name ?? llmModel ?? '—'}
                        </div>
                        {currentModel && currentModel.id !== currentModel.name && (
                          <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {currentModel.id}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                    <path d="m4 6 4 4 4-4" stroke="var(--text-faint)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {modelMenuOpen && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
                    background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 10,
                    boxShadow: '0 12px 32px rgba(20,25,40,.22)', zIndex: 30, overflow: 'hidden',
                  }}>
                    {!providerKeys[llmProvider] && (
                      <div style={{
                        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                        margin: '6px 6px 0', padding: '9px 11px', borderRadius: 8,
                        background: '#fff8ed', border: '1px solid #f5d08a',
                      }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                            <path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM8 5v3.5M8 10.5v.5" stroke="#b45309" strokeWidth="1.4" strokeLinecap="round"/>
                          </svg>
                          <span style={{ fontSize: 12, color: '#92400e' }}>API key não cadastrada</span>
                        </div>
                        <button onClick={() => { setModelMenuOpen(false); setShowSettings(true) }} style={{
                          fontSize: 11.5, fontWeight: 600, color: '#b45309',
                          background: 'none', border: '1px solid #f5d08a', borderRadius: 6,
                          padding: '3px 9px', cursor: 'pointer', whiteSpace: 'nowrap',
                        }}>
                          Configurar
                        </button>
                      </div>
                    )}
                    {providerModels.length > 8 && (
                      <div style={{ padding: '6px 6px 2px' }}>
                        <input
                          autoFocus
                          type="text"
                          placeholder="Filtrar modelos…"
                          value={modelSearch}
                          onChange={e => setModelSearch(e.target.value)}
                          onClick={e => e.stopPropagation()}
                          style={{
                            width: '100%', boxSizing: 'border-box',
                            border: '1px solid var(--border)', borderRadius: 7,
                            padding: '6px 10px', fontSize: 12.5,
                            background: 'var(--surface-2)', color: 'var(--text)', outline: 'none',
                          }}
                        />
                      </div>
                    )}
                    <div style={{ maxHeight: 300, overflowY: 'auto', padding: 6 }}>
                      {modelsLoading ? (
                        <div style={{ padding: '20px', display: 'flex', justifyContent: 'center' }}>
                          <Spinner color="var(--text-faint)" />
                        </div>
                      ) : filteredModels.length === 0 ? (
                        <div style={{ padding: '12px', fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>
                          {modelSearch ? 'Nenhum modelo encontrado' : 'Sem modelos disponíveis'}
                        </div>
                      ) : filteredModels.map(m => (
                        <button key={m.id} onClick={() => handleChangeModel(m.id)} style={{
                          width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                          border: 'none', borderRadius: 8,
                          background: m.id === llmModel ? 'var(--surface-3)' : 'none', cursor: 'pointer',
                        }}>
                          <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', lineHeight: 1.2, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {m.name}
                            </div>
                            {m.id !== m.name && (
                              <div style={{ fontSize: 10.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.id}</div>
                            )}
                          </div>
                          {m.price !== undefined && (
                            <span style={{ fontSize: 10.5, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', flexShrink: 0 }}>
                              {m.price === 0 ? 'grátis' : `$${m.price}/M`}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Embedding Model */}
            <div id="tour-emb-model" style={{ marginBottom: 18 }}>
              <div className="section-label" style={{ marginBottom: 9 }}>Modelo Embedding</div>
              <div style={{ position: 'relative' }}>
                <button onClick={() => { setEmbMenuOpen(v => !v); setProviderMenuOpen(false); setModelMenuOpen(false) }} style={{
                  width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '10px 12px',
                  border: '1px solid var(--border-2)', borderRadius: 9, background: 'var(--surface)', cursor: 'pointer', textAlign: 'left',
                }}>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    {embModelsLoading ? (
                      <div style={{ display: 'flex', alignItems: 'center', gap: 7 }}>
                        <Spinner color="var(--text-faint)" />
                        <span style={{ fontSize: 12, color: 'var(--text-faint)' }}>Carregando modelos…</span>
                      </div>
                    ) : (
                      <>
                        <div style={{ fontSize: 13.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', lineHeight: 1.2, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {currentEmbModel?.name ?? embModel ?? '—'}
                        </div>
                        {currentEmbModel && currentEmbModel.id !== currentEmbModel.name && (
                          <div style={{ fontSize: 11, color: 'var(--text-faint)', lineHeight: 1.3, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {currentEmbModel.id}
                          </div>
                        )}
                      </>
                    )}
                  </div>
                  <svg width="13" height="13" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                    <path d="m4 6 4 4 4-4" stroke="var(--text-faint)" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                  </svg>
                </button>
                {embMenuOpen && (
                  <div style={{
                    position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
                    background: 'var(--surface)', border: '1px solid var(--border-2)', borderRadius: 10,
                    boxShadow: '0 12px 32px rgba(20,25,40,.22)', zIndex: 30, overflow: 'hidden',
                  }}>
                    {embModels.length > 8 && (
                      <div style={{ padding: '6px 6px 2px' }}>
                        <input
                          autoFocus
                          type="text"
                          placeholder="Filtrar modelos…"
                          value={embModelSearch}
                          onChange={e => setEmbModelSearch(e.target.value)}
                          onClick={e => e.stopPropagation()}
                          style={{
                            width: '100%', boxSizing: 'border-box',
                            border: '1px solid var(--border)', borderRadius: 7,
                            padding: '6px 10px', fontSize: 12.5,
                            background: 'var(--surface-2)', color: 'var(--text)', outline: 'none',
                          }}
                        />
                      </div>
                    )}
                    <div style={{ maxHeight: 260, overflowY: 'auto', padding: 6 }}>
                      {embModelsLoading ? (
                        <div style={{ padding: '20px', display: 'flex', justifyContent: 'center' }}>
                          <Spinner color="var(--text-faint)" />
                        </div>
                      ) : filteredEmbModels.length === 0 ? (
                        <div style={{ padding: '12px', fontSize: 12, color: 'var(--text-faint)', textAlign: 'center' }}>
                          {embModelSearch ? 'Nenhum modelo encontrado' : 'Sem modelos disponíveis'}
                        </div>
                      ) : filteredEmbModels.map(m => (
                        <button key={m.id} onClick={() => handleChangeEmbModel(m.id)} style={{
                          width: '100%', display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px',
                          border: 'none', borderRadius: 8,
                          background: m.id === embModel ? 'var(--surface-3)' : 'none', cursor: 'pointer',
                        }}>
                          <div style={{ flex: 1, textAlign: 'left', minWidth: 0 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', lineHeight: 1.2, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {m.name}
                            </div>
                            {m.id !== m.name && (
                              <div style={{ fontSize: 10.5, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.id}</div>
                            )}
                          </div>
                        </button>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* Cost estimate */}
            <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 10, padding: '13px 14px' }}>
              {[
                { label: 'Artigos vetorizados', value: String(vectorizedCount) },
                { label: 'Est. tokens', value: vectorizedCount > 0 ? `~${Math.round(estimatedTokens / 1000)}K` : '—' },
              ].map(({ label, value }) => (
                <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
                  <span style={{ fontSize: 12, color: '#5b6472' }}>{label}</span>
                  <span style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace' }}>{value}</span>
                </div>
              ))}
              <div style={{
                display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                paddingTop: 8, borderTop: '1px dashed #dfe2e8',
              }}>
                <span style={{ fontSize: 12, color: '#5b6472' }}>Est. custo</span>
                <span style={{ fontSize: 13.5, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', color: '#1a1d23' }}>
                  {estimatedCost}
                </span>
              </div>
            </div>
          </div>

          {/* Analyze button */}
          <div id="tour-run-btn" style={{ flexShrink: 0, padding: '16px 20px', background: 'var(--surface)', borderTop: '1px solid var(--border)' }}>
            <button onClick={runAnalysis} disabled={!canAnalyze} style={{
              width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 9,
              padding: 12, border: 'none', borderRadius: 10, fontSize: 14, fontWeight: 600, color: '#fff',
              cursor: canAnalyze ? 'pointer' : 'default',
              background: analysisRunning ? '#5aacac' : (canAnalyze ? '#1A9494' : '#cfd4dc'),
            }}>
              {analysisRunning ? (
                <Spinner />
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                  <path d="M3 2.5v11l9-5.5-9-5.5Z" fill="#fff"/>
                </svg>
              )}
              {analysisRunning
                ? 'Analisando…'
                : canAnalyze
                ? `Analisar ${vectorizedCount} artigos`
                : vectorizedCount === 0
                ? 'Vetorize antes de analisar'
                : 'Insira um critério de triagem'
              }
            </button>
          </div>
        </aside>

        {/* ── MAIN AREA ── */}
        <main style={{ flex: 1, display: 'flex', flexDirection: 'column', minWidth: 0, background: 'var(--surface-3)' }}>

          {/* Tab bar */}
          <div style={{ flexShrink: 0, padding: '0 24px', display: 'flex', alignItems: 'flex-end', gap: 0 }}>
            {TABS.map(tab => {
              const active = activeTab === tab.id
              return (
                <button key={tab.id} id={`tour-tab-${tab.id}`} onClick={() => setActiveTab(tab.id)} style={{
                  padding: '12px 16px', border: 'none', background: 'none', cursor: 'pointer',
                  fontSize: 13.5, fontWeight: active ? 700 : 500,
                  color: active ? 'var(--text)' : 'var(--text-faint)',
                  borderBottom: `2px solid ${active ? '#1A9494' : 'transparent'}`,
                  display: 'flex', alignItems: 'center', whiteSpace: 'nowrap',
                }}>
                  {tab.label}
                  {tab.count > 0 && (
                    <span style={{
                      marginLeft: 6, fontSize: 11, fontWeight: 600,
                      fontFamily: 'IBM Plex Mono, monospace', padding: '1px 7px', borderRadius: 9,
                      background: active ? '#e8f8f8' : 'var(--surface-2)',
                      color: active ? '#1A9494' : 'var(--text-faint)',
                    }}>
                      {tab.count}
                    </span>
                  )}
                </button>
              )
            })}
            <div style={{ flex: 1, borderBottom: '2px solid var(--border)' }} />
          </div>

          {/* Tab content */}
          {activeTab === 'biblioteca' && (
            <BibliotecaTab
              articles={articles}
              vectorStore={vectorStore}
              vectorizeRunning={vectorizeRunning}
              onRefresh={loadArticles}
              onVectorize={handleVectorize}
            />
          )}
          {activeTab === 'resultados' && (
            <ResultadosTab
              report={activeReport}
              analysisRunning={analysisRunning}
              logs={analysisLogs}
              analysisDone={analysisDone}
            />
          )}
          {activeTab === 'relatorios' && (
            <RelatoriosTab
              reports={reports}
              onRefresh={loadReports}
            />
          )}
        </main>
      </div>

      {/* ── OVERLAYS ── */}
      {showVectorStoreModal && (
        <VectorStoreModal
          vectorStore={vectorStore}
          pendingCount={pendingCount}
          vectorizeRunning={vectorizeRunning}
          onVectorize={handleVectorize}
          onReset={handleResetVectorStore}
          onClose={() => setShowVectorStoreModal(false)}
        />
      )}

      {showHistory && (
        <HistoryDrawer
          reports={reports}
          projectName={project?.root?.split('/').slice(-1)[0] ?? 'projeto'}
          onClose={() => setShowHistory(false)}
          onOpenRelatorios={() => { setActiveTab('relatorios'); setShowHistory(false) }}
        />
      )}

      {showSettings && <SettingsModal
        onClose={() => setShowSettings(false)}
        onSaved={handleSettingsSaved}
      />}
    </div>
  )
}
