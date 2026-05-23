import { useEffect, useRef, useState, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import {
  listArticles, uploadArticles, deleteArticle, deleteAllArticles,
  getArticleFileUrl, suggestArticleRename, renameArticle,
  listProjects, listProjectArticles, addArticlesToProject,
  type Article, type Project,
} from '../api/client'
import StreamLog from '../components/StreamLog'
import { useLanguage } from '../contexts/LanguageContext'
import ConfirmDialog from '../components/ConfirmDialog'
import { useNotifications } from '../contexts/NotificationsContext'
import ActiveJobPanel from '../components/ActiveJobPanel'
import CollapsibleSection from '../components/CollapsibleSection'

// Configure PDF.js worker (CDN matching the installed pdfjs-dist version)
pdfjs.GlobalWorkerOptions.workerSrc = `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

function fmt(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// ── PDF Thumbnail ─────────────────────────────────────────────────────────────

function PdfThumbnail({ url }: { url: string }) {
  return (
    <Document
      file={url}
      loading={
        <div className="w-full h-full bg-slate-100 animate-pulse rounded" />
      }
      error={
        <div className="w-full h-full bg-slate-50 flex items-center justify-center text-slate-400 text-xs rounded">
          PDF
        </div>
      }
    >
      <Page
        pageNumber={1}
        width={160}
        renderAnnotationLayer={false}
        renderTextLayer={false}
        loading={null}
      />
    </Document>
  )
}

// ── PDF Reader Modal ──────────────────────────────────────────────────────────

function PdfReaderModal({ article, onClose }: { article: Article; onClose: () => void }) {
  const url = getArticleFileUrl(article.name)
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [pageInput, setPageInput] = useState('1')
  const [scale, setScale] = useState(1.2)
  const containerRef = useRef<HTMLDivElement>(null)

  function onDocumentLoadSuccess({ numPages }: { numPages: number }) {
    setNumPages(numPages)
    setPageNumber(1)
    setPageInput('1')
  }

  function goTo(n: number) {
    if (!numPages) return
    const clamped = Math.max(1, Math.min(numPages, n))
    setPageNumber(clamped)
    setPageInput(String(clamped))
    containerRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  function handlePageInput(e: React.ChangeEvent<HTMLInputElement>) {
    setPageInput(e.target.value)
    const n = parseInt(e.target.value)
    if (!isNaN(n)) goTo(n)
  }

  // Close on Escape
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70">
      {/* Toolbar */}
      <div className="bg-[#1A1A1A] text-white flex items-center gap-3 px-4 py-2 flex-shrink-0">
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-white text-lg leading-none px-1"
          title="Fechar"
        >
          ✕
        </button>
        <div className="w-px h-5 bg-white/20" />
        <span className="text-sm font-medium text-slate-200 truncate max-w-xs">{article.name}</span>
        <div className="flex-1" />

        {/* Scale */}
        <div className="flex items-center gap-1">
          <button
            className="text-slate-400 hover:text-white px-1.5 py-0.5 rounded text-sm"
            onClick={() => setScale((s) => Math.max(0.5, +(s - 0.2).toFixed(1)))}
          >−</button>
          <span className="text-xs text-slate-300 w-10 text-center">{Math.round(scale * 100)}%</span>
          <button
            className="text-slate-400 hover:text-white px-1.5 py-0.5 rounded text-sm"
            onClick={() => setScale((s) => Math.min(3, +(s + 0.2).toFixed(1)))}
          >+</button>
        </div>

        <div className="w-px h-5 bg-white/20" />

        {/* Page navigation */}
        <button
          className="text-slate-400 hover:text-white text-sm px-1.5"
          disabled={pageNumber <= 1}
          onClick={() => goTo(pageNumber - 1)}
        >‹</button>
        <div className="flex items-center gap-1 text-sm text-slate-300">
          <input
            type="number"
            value={pageInput}
            onChange={handlePageInput}
            className="w-10 text-center bg-white/10 text-white rounded px-1 py-0.5 text-xs"
          />
          <span className="text-slate-400">/ {numPages ?? '…'}</span>
        </div>
        <button
          className="text-slate-400 hover:text-white text-sm px-1.5"
          disabled={!numPages || pageNumber >= numPages}
          onClick={() => goTo(pageNumber + 1)}
        >›</button>

        <div className="w-px h-5 bg-white/20" />

        {/* Download */}
        <a
          href={url}
          download={article.name}
          className="text-slate-400 hover:text-white text-xs px-2"
          title="Baixar PDF"
        >
          ⬇
        </a>
      </div>

      {/* PDF area */}
      <div
        ref={containerRef}
        className="flex-1 overflow-auto flex justify-center py-6 bg-slate-700"
      >
        <Document
          file={url}
          onLoadSuccess={onDocumentLoadSuccess}
          loading={
            <div className="text-white text-sm mt-20">Carregando PDF…</div>
          }
          error={
            <div className="text-red-400 text-sm mt-20">Não foi possível carregar o PDF.</div>
          }
        >
          <Page
            pageNumber={pageNumber}
            scale={scale}
            className="shadow-2xl"
            renderAnnotationLayer
            renderTextLayer
          />
        </Document>
      </div>
    </div>
  )
}

// ── Article card (thumbnail view) ─────────────────────────────────────────────

function ArticleCard({
  article, onOpen, onDelete, projectBadge,
}: {
  article: Article
  onOpen: () => void
  onDelete: () => void
  projectBadge?: { name: string; color: string } | null
}) {
  const url = getArticleFileUrl(article.name)
  return (
    <div
      className="group relative flex flex-col bg-white border border-slate-200 rounded-xl overflow-hidden shadow-sm hover:shadow-md hover:border-lutz-300 transition-all cursor-pointer"
      onClick={onOpen}
    >
      {/* Thumbnail */}
      <div className="w-full aspect-[3/4] bg-slate-100 overflow-hidden flex items-start justify-center">
        <PdfThumbnail url={url} />
      </div>

      {/* Info */}
      <div className="px-3 py-2 flex-1 flex flex-col gap-0.5">
        <p className="text-xs font-medium text-slate-700 line-clamp-2 leading-tight">{article.name}</p>
        <p className="text-[10px] text-slate-400">{fmt(article.size)}</p>
        {projectBadge && (
          <span
            className="mt-1 self-start text-[9px] font-medium px-1.5 py-0.5 rounded-full text-white truncate max-w-full"
            style={{ backgroundColor: projectBadge.color }}
            title={projectBadge.name}
          >
            {projectBadge.name}
          </span>
        )}
      </div>

      {/* Delete button */}
      <button
        className="absolute top-1.5 right-1.5 bg-white/80 hover:bg-red-50 text-slate-400 hover:text-red-500 rounded-full w-6 h-6 flex items-center justify-center text-xs shadow opacity-0 group-hover:opacity-100 transition-opacity"
        title="Remover"
        onClick={(e) => { e.stopPropagation(); onDelete() }}
      >
        ✕
      </button>
    </div>
  )
}

// ── Rename suggestions modal ──────────────────────────────────────────────────

type SuggestStatus = 'idle' | 'loading' | 'done' | 'error' | 'applied'

interface SuggestRow {
  article: Article
  status: SuggestStatus
  suggested: string
  errorMsg?: string
}

function RenameSuggestModal({
  articles,
  onClose,
  onRenamed,
}: {
  articles: Article[]
  onClose: () => void
  onRenamed: () => void
}) {
  const { t } = useLanguage()
  const [rows, setRows] = useState<SuggestRow[]>(() =>
    articles.map((a) => ({
      article: a,
      status: 'idle' as SuggestStatus,
      suggested: a.name,
    }))
  )
  const [applyingAll, setApplyingAll] = useState(false)

  function setRow(name: string, patch: Partial<SuggestRow>) {
    setRows((prev) => prev.map((r) => r.article.name === name ? { ...r, ...patch } : r))
  }

  async function generateOne(name: string) {
    setRow(name, { status: 'loading' })
    try {
      const { suggested } = await suggestArticleRename(name)
      setRow(name, { status: 'done', suggested })
    } catch (e) {
      setRow(name, { status: 'error', errorMsg: (e as Error).message })
    }
  }

  async function generateAll() {
    const idle = rows.filter((r) => r.status === 'idle' || r.status === 'done')
    for (const r of idle) await generateOne(r.article.name)
  }

  async function applyOne(row: SuggestRow) {
    if (row.suggested === row.article.name) { setRow(row.article.name, { status: 'applied' }); return }
    try {
      await renameArticle(row.article.name, row.suggested)
      setRow(row.article.name, { status: 'applied' })
      onRenamed()
    } catch (e) {
      setRow(row.article.name, { status: 'error', errorMsg: (e as Error).message })
    }
  }

  async function applyAll() {
    setApplyingAll(true)
    const ready = rows.filter((r) => r.status === 'done')
    for (const r of ready) await applyOne(r)
    setApplyingAll(false)
  }

  const canGenerateAll = rows.some((r) => r.status === 'idle' || r.status === 'done')
  const canApplyAll = rows.some((r) => r.status === 'done')

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-2xl w-full max-w-3xl flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="flex items-start justify-between p-6 pb-3">
          <div>
            <h3 className="text-base font-semibold text-slate-800">{t('vectorize.rename.title')}</h3>
            <p className="text-xs text-slate-500 mt-0.5">{t('vectorize.rename.hint')}</p>
          </div>
          <button className="text-slate-400 hover:text-slate-600 text-lg leading-none ml-4" onClick={onClose}>✕</button>
        </div>

        {/* Table */}
        <div className="flex-1 overflow-y-auto px-6">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-slate-100 text-xs text-slate-500 uppercase tracking-wide">
                <th className="text-left py-2 pr-3 w-[35%]">{t('vectorize.rename.colOriginal')}</th>
                <th className="text-left py-2 pr-3">{t('vectorize.rename.colSuggested')}</th>
                <th className="text-right py-2 w-28">{t('vectorize.rename.colStatus')}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50">
              {rows.map((row) => (
                <tr key={row.article.name} className="align-middle">
                  <td className="py-2 pr-3 text-slate-600 text-xs break-all">{row.article.name}</td>
                  <td className="py-2 pr-3">
                    {row.status === 'loading' ? (
                      <span className="text-xs text-slate-400 animate-pulse">{t('vectorize.rename.generating')}</span>
                    ) : row.status === 'error' ? (
                      <span className="text-xs text-red-400">{row.errorMsg}</span>
                    ) : row.status === 'applied' ? (
                      <span className="text-xs text-green-600 font-medium">{row.suggested}</span>
                    ) : (
                      <input
                        className="input text-xs py-1 w-full"
                        value={row.suggested}
                        onChange={(e) => setRow(row.article.name, { suggested: e.target.value })}
                      />
                    )}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    {row.status === 'applied' ? (
                      <span className="text-xs text-green-600">✓ {t('vectorize.rename.applied')}</span>
                    ) : row.status === 'idle' ? (
                      <button
                        className="text-xs text-lutz-600 hover:text-lutz-700 underline"
                        onClick={() => generateOne(row.article.name)}
                      >
                        ✨ {t('vectorize.rename.generating').replace('...', '')}
                      </button>
                    ) : row.status === 'loading' ? (
                      <span className="text-xs text-slate-400">…</span>
                    ) : row.status === 'done' ? (
                      <button
                        className="text-xs bg-lutz-500 hover:bg-lutz-600 text-white px-2 py-0.5 rounded"
                        onClick={() => applyOne(row)}
                      >
                        {t('vectorize.rename.apply')}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between p-6 pt-4 border-t border-slate-100">
          <div className="flex gap-2">
            <button
              className="btn-ghost text-sm"
              onClick={generateAll}
              disabled={!canGenerateAll}
            >
              ✨ {t('vectorize.rename.generateAll')}
            </button>
          </div>
          <div className="flex gap-2">
            <button className="btn-ghost text-sm" onClick={onClose}>
              {t('dialog.cancel')}
            </button>
            <button
              className="btn-primary text-sm"
              onClick={applyAll}
              disabled={!canApplyAll || applyingAll}
            >
              {t('vectorize.rename.applyAll')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Vectorize() {
  const { t } = useLanguage()
  const { dispatchJob } = useNotifications()
  const [tab, setTab] = useState<'articles' | 'vectorize'>('articles')
  const [articles, setArticles] = useState<Article[]>([])
  const [uploading, setUploading] = useState(false)
  const [running, setRunning] = useState(false)
  const [logs, setLogs] = useState<string[]>([])
  const [done, setDone] = useState<boolean | null>(null)
  const [dispatched, setDispatched] = useState(false)
  const fileRef = useRef<HTMLInputElement>(null)
  const ctrlRef = useRef<AbortController | null>(null)

  const [viewMode, setViewMode] = useState<'list' | 'grid'>('list')
  const [openArticle, setOpenArticle] = useState<Article | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Article | null>(null)
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false)
  const [showRenameSuggest, setShowRenameSuggest] = useState(false)

  const [chunkSize, setChunkSize] = useState(512)
  const [chunkOverlap, setChunkOverlap] = useState(64)
  const [skipSecurity, setSkipSecurity] = useState(false)
  const [sectionParse, setSectionParse] = useState(false)
  const [quarantine, setQuarantine] = useState(false)
  const [extractionBackend, setExtractionBackend] = useState<'pymupdf' | 'marker' | 'auto'>('pymupdf')

  // Project association state (Feature 1)
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedArticles, setSelectedArticles] = useState<Set<string>>(new Set())
  const [associatingProject, setAssociatingProject] = useState('')
  const [associating, setAssociating] = useState(false)
  // article name -> project { name, color } map
  const [articleProjectMap, setArticleProjectMap] = useState<Map<string, { name: string; color: string }>>(new Map())

  // Vectorization scope state (Feature 2)
  const [vectorizeScope, setVectorizeScope] = useState<'all' | 'project'>('all')
  const [vectorizeScopeProject, setVectorizeScopeProject] = useState('')

  const loadProjects = useCallback(async () => {
    const { projects: list } = await listProjects()
    setProjects(list)
    // Build article→project map in parallel
    if (list.length > 0) {
      const entries = await Promise.all(
        list.map(async (p) => {
          try {
            const { articles: paths } = await listProjectArticles(p.id)
            return paths.map((path) => [path, { name: p.name, color: p.color }] as [string, { name: string; color: string }])
          } catch {
            return []
          }
        })
      )
      setArticleProjectMap(new Map(entries.flat()))
    } else {
      setArticleProjectMap(new Map())
    }
  }, [])

  const load = useCallback(() => {
    listArticles().then((r) => setArticles(r.articles ?? []))
  }, [])

  useEffect(() => {
    load()
    loadProjects()
  }, [load, loadProjects])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files?.length) return
    setUploading(true)
    await uploadArticles(files)
    load()
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function handleDelete(name: string) {
    await deleteArticle(name)
    load()
  }

  async function handleDeleteAll() {
    await deleteAllArticles()
    load()
  }

  function toggleArticleSelect(name: string) {
    setSelectedArticles((prev) => {
      const next = new Set(prev)
      if (next.has(name)) next.delete(name)
      else next.add(name)
      return next
    })
  }

  function toggleSelectAll() {
    if (selectedArticles.size === articles.length) {
      setSelectedArticles(new Set())
    } else {
      setSelectedArticles(new Set(articles.map((a) => a.name)))
    }
  }

  async function handleAssociateToProject() {
    if (!associatingProject || selectedArticles.size === 0) return
    setAssociating(true)
    try {
      await addArticlesToProject(associatingProject, Array.from(selectedArticles))
      await loadProjects()
      setSelectedArticles(new Set())
    } finally {
      setAssociating(false)
    }
  }

  async function startVectorize() {
    setLogs([])
    setDone(null)
    setRunning(true)
    setDispatched(false)
    try {
      // TODO: backend needs to support project_id filtering in the vectorize endpoint
      const jobBody: Record<string, unknown> = {
        chunk_size: chunkSize,
        chunk_overlap: chunkOverlap,
        skip_security: skipSecurity,
        section_parse: sectionParse,
        quarantine,
        extraction_backend: extractionBackend,
      }
      if (vectorizeScope === 'project' && vectorizeScopeProject) {
        jobBody.project_id = vectorizeScopeProject
      }
      const job = await dispatchJob('vectorize', jobBody)
      setDispatched(true)
      // Subscribe to live log stream while on this page
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

  const handleClose = useCallback(() => setOpenArticle(null), [])

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-800">{t('vectorize.title')}</h2>

      {/* Background job banner */}
      {!running && (
        <ActiveJobPanel jobType="vectorize" onDone={load} />
      )}

      {/* PDF Reader Modal */}
      {openArticle && (
        <PdfReaderModal article={openArticle} onClose={handleClose} />
      )}

      {/* Confirm delete single article */}
      {confirmDelete && (
        <ConfirmDialog
          title={t('vectorize.removeConfirm')}
          body={`"${confirmDelete.name}" — ${t('vectorize.removeConfirmBody')}`}
          confirmLabel={t('dialog.delete')}
          danger
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => { handleDelete(confirmDelete.name); setConfirmDelete(null) }}
        />
      )}

      {/* Confirm delete all articles */}
      {confirmDeleteAll && (
        <ConfirmDialog
          title={t('vectorize.removeAllConfirm')}
          body={t('vectorize.removeAllConfirmBody')}
          confirmLabel={t('dialog.delete')}
          danger
          onCancel={() => setConfirmDeleteAll(false)}
          onConfirm={() => { handleDeleteAll(); setConfirmDeleteAll(false) }}
        />
      )}

      {/* Rename suggestions modal */}
      {showRenameSuggest && (
        <RenameSuggestModal
          articles={articles}
          onClose={() => setShowRenameSuggest(false)}
          onRenamed={load}
        />
      )}

      {/* Tabs */}
      <div className="flex gap-2 border-b border-slate-200">
        {(['articles', 'vectorize'] as const).map((tab_) => (
          <button
            key={tab_}
            onClick={() => setTab(tab_)}
            className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors -mb-px ${
              tab === tab_
                ? 'border-lutz-500 text-lutz-600'
                : 'border-transparent text-slate-500 hover:text-slate-700'
            }`}
          >
            {tab_ === 'articles'
              ? `${t('vectorize.tab.articles')} (${articles.length})`
              : t('vectorize.tab.vectorize')}
          </button>
        ))}
      </div>

      {tab === 'articles' && (
        <CollapsibleSection title={t('vectorize.tab.articles')} storageKey="vectorize_articles">
        <div className="space-y-4">
          <div className="flex items-center gap-3 flex-wrap">
            <label className="btn-primary cursor-pointer">
              {uploading ? t('vectorize.uploading') : t('vectorize.upload')}
              <input ref={fileRef} type="file" accept=".pdf" multiple className="hidden" onChange={handleUpload} disabled={uploading} />
            </label>
            <span className="text-xs text-slate-400">{articles.length} arquivo(s)</span>

            {articles.length > 0 && (
              <button
                className="text-xs text-red-400 hover:text-red-600 transition-colors"
                onClick={() => setConfirmDeleteAll(true)}
              >
                {t('vectorize.removeAll')}
              </button>
            )}

            {articles.length > 0 && (
              <button
                className="text-xs text-lutz-600 hover:text-lutz-700 font-medium transition-colors"
                onClick={() => setShowRenameSuggest(true)}
              >
                {t('vectorize.suggestRename')}
              </button>
            )}

            {/* View toggle */}
            {articles.length > 0 && (
              <div className="ml-auto flex items-center gap-1 border border-slate-200 rounded-lg p-0.5">
                <button
                  onClick={() => setViewMode('list')}
                  className={`px-2 py-1 rounded text-xs transition-colors ${
                    viewMode === 'list'
                      ? 'bg-lutz-500 text-white'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                  title="Visualização em lista"
                >
                  ☰ Lista
                </button>
                <button
                  onClick={() => setViewMode('grid')}
                  className={`px-2 py-1 rounded text-xs transition-colors ${
                    viewMode === 'grid'
                      ? 'bg-lutz-500 text-white'
                      : 'text-slate-500 hover:text-slate-700'
                  }`}
                  title="Visualização em miniaturas"
                >
                  ⊞ Miniaturas
                </button>
              </div>
            )}
          </div>

          {/* Project association bar (Feature 1) */}
          {articles.length > 0 && projects.length > 0 && (
            <div className="flex items-center gap-2 flex-wrap p-3 bg-slate-50 rounded-xl border border-slate-200">
              <span className="text-xs font-medium text-slate-600">{t('vectorize.project.selector')}:</span>
              <select
                className="input text-xs py-1 h-auto"
                value={associatingProject}
                onChange={(e) => setAssociatingProject(e.target.value)}
              >
                <option value="">{t('vectorize.project.none')}</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>{p.name}</option>
                ))}
              </select>
              <button
                className="btn-primary text-xs py-1 px-3"
                disabled={!associatingProject || selectedArticles.size === 0 || associating}
                onClick={handleAssociateToProject}
              >
                {associating ? t('vectorize.project.associating') : `${t('vectorize.project.associate')} (${selectedArticles.size})`}
              </button>
              {selectedArticles.size > 0 && (
                <button
                  className="btn-ghost text-xs py-1"
                  onClick={() => setSelectedArticles(new Set())}
                >
                  ✕
                </button>
              )}
            </div>
          )}

          {articles.length === 0 ? (
            <div className="text-slate-400 text-sm py-8 text-center">
              {t('vectorize.empty')}
            </div>
          ) : viewMode === 'list' ? (
            <div className="card p-0 overflow-hidden">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                  <tr>
                    {projects.length > 0 && (
                      <th className="px-3 py-2 w-8">
                        <input
                          type="checkbox"
                          className="rounded"
                          checked={selectedArticles.size === articles.length && articles.length > 0}
                          onChange={toggleSelectAll}
                          title="Selecionar todos"
                        />
                      </th>
                    )}
                    <th className="text-left px-4 py-2">{t('vectorize.col.file')}</th>
                    <th className="text-left px-4 py-2 hidden sm:table-cell">Projeto</th>
                    <th className="text-right px-4 py-2">{t('vectorize.col.size')}</th>
                    <th className="px-4 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {articles.map((a) => {
                    const badge = articleProjectMap.get(a.name)
                    return (
                      <tr
                        key={a.name}
                        className={`border-t border-slate-100 hover:bg-slate-50 cursor-pointer ${
                          selectedArticles.has(a.name) ? 'bg-lutz-50' : ''
                        }`}
                        onClick={() => setOpenArticle(a)}
                      >
                        {projects.length > 0 && (
                          <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                            <input
                              type="checkbox"
                              className="rounded"
                              checked={selectedArticles.has(a.name)}
                              onChange={() => toggleArticleSelect(a.name)}
                            />
                          </td>
                        )}
                        <td className="px-4 py-2 font-medium text-slate-700 break-all">
                          <span className="text-lutz-600 hover:underline">{a.name}</span>
                        </td>
                        <td className="px-4 py-2 hidden sm:table-cell">
                          {badge ? (
                            <span
                              className="text-[10px] font-medium px-2 py-0.5 rounded-full text-white"
                              style={{ backgroundColor: badge.color }}
                            >
                              {badge.name}
                            </span>
                          ) : (
                            <span className="text-[10px] text-slate-300">—</span>
                          )}
                        </td>
                        <td className="px-4 py-2 text-right text-slate-400 whitespace-nowrap">{fmt(a.size)}</td>
                        <td className="px-4 py-2 text-right" onClick={(e) => e.stopPropagation()}>
                          <button onClick={() => setConfirmDelete(a)} className="text-red-400 hover:text-red-600 text-xs">
                            {t('vectorize.remove')}
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-4">
              {articles.map((a) => (
                <div
                  key={a.name}
                  className="relative"
                  onClick={(e) => {
                    if (projects.length > 0) {
                      e.stopPropagation()
                      toggleArticleSelect(a.name)
                    }
                  }}
                >
                  {projects.length > 0 && (
                    <div
                      className="absolute top-1.5 left-1.5 z-10"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        className="rounded shadow"
                        checked={selectedArticles.has(a.name)}
                        onChange={() => toggleArticleSelect(a.name)}
                      />
                    </div>
                  )}
                  <ArticleCard
                    article={a}
                    onOpen={() => setOpenArticle(a)}
                    onDelete={() => setConfirmDelete(a)}
                    projectBadge={articleProjectMap.get(a.name) ?? null}
                  />
                </div>
              ))}
            </div>
          )}
        </div>
        </CollapsibleSection>
      )}

      {tab === 'vectorize' && (
        <CollapsibleSection title={t('vectorize.tab.vectorize')} storageKey="vectorize_options">
        <div className="space-y-6">
          <div className="card grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="label">{t('vectorize.opt.chunkSize')}</label>
              <input type="number" className="input" value={chunkSize} onChange={(e) => setChunkSize(+e.target.value)} min={64} max={2048} />
            </div>
            <div>
              <label className="label">{t('vectorize.opt.chunkOverlap')}</label>
              <input type="number" className="input" value={chunkOverlap} onChange={(e) => setChunkOverlap(+e.target.value)} min={0} max={512} />
            </div>
            <div className="sm:col-span-2">
              <label className="label">{t('vectorize.opt.extractionBackend')}</label>
              <select
                className="input"
                value={extractionBackend}
                onChange={(e) => setExtractionBackend(e.target.value as 'pymupdf' | 'marker' | 'auto')}
              >
                <option value="pymupdf">{t('vectorize.opt.extraction.pymupdf')}</option>
                <option value="marker">{t('vectorize.opt.extraction.marker')}</option>
                <option value="auto">{t('vectorize.opt.extraction.auto')}</option>
              </select>
            </div>

            {/* Vectorization scope (Feature 2) */}
            {projects.length > 0 && (
              <div className="sm:col-span-2">
                <label className="label">{t('vectorize.project.scope.label')}</label>
                <div className="flex flex-col gap-2 mt-1">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="vectorize-scope"
                      value="all"
                      checked={vectorizeScope === 'all'}
                      onChange={() => setVectorizeScope('all')}
                    />
                    <span className="text-sm">{t('vectorize.project.scope.all')}</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="vectorize-scope"
                      value="project"
                      checked={vectorizeScope === 'project'}
                      onChange={() => setVectorizeScope('project')}
                    />
                    <span className="text-sm">{t('vectorize.project.scope.project')}</span>
                    <select
                      className="input text-xs py-1 h-auto ml-1"
                      value={vectorizeScopeProject}
                      onChange={(e) => {
                        setVectorizeScopeProject(e.target.value)
                        if (e.target.value) setVectorizeScope('project')
                      }}
                      disabled={vectorizeScope !== 'project'}
                    >
                      <option value="">— selecione —</option>
                      {projects.map((p) => (
                        <option key={p.id} value={p.id}>{p.name}</option>
                      ))}
                    </select>
                  </label>
                </div>
              </div>
            )}

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
        </CollapsibleSection>
      )}
    </div>
  )
}
