import { useCallback, useEffect, useRef, useState } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/Page/AnnotationLayer.css'
import 'react-pdf/dist/Page/TextLayer.css'
import {
  uploadArticles, deleteArticle, deleteAllArticles,
  getArticleFileUrl, suggestArticleRename, renameArticle,
  type Article, type VectorStoreInfo,
} from '../api/client'
import ConfirmDialog from '../components/ConfirmDialog'
import { useLanguage } from '../contexts/LanguageContext'

pdfjs.GlobalWorkerOptions.workerSrc =
  `https://unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

function fmt(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`
}

// ── PDF Reader Modal ──────────────────────────────────────────────────────────

function PdfReaderModal({ article, onClose }: { article: Article; onClose: () => void }) {
  const url = getArticleFileUrl(article.name)
  const [numPages, setNumPages] = useState<number | null>(null)
  const [pageNumber, setPageNumber] = useState(1)
  const [pageInput, setPageInput] = useState('1')
  const [scale, setScale] = useState(1.2)
  const containerRef = useRef<HTMLDivElement>(null)

  function goTo(n: number) {
    if (!numPages) return
    const c = Math.max(1, Math.min(numPages, n))
    setPageNumber(c); setPageInput(String(c))
    containerRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }

  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose() }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-black/70">
      <div className="bg-[#1a1d23] text-white flex items-center gap-3 px-4 py-2 flex-shrink-0">
        <button onClick={onClose} className="text-[#8a92a0] hover:text-white text-lg px-1">✕</button>
        <div className="w-px h-5 bg-white/20" />
        <span className="text-sm font-medium text-slate-200 truncate max-w-xs font-mono">{article.name}</span>
        <div className="flex-1" />
        <div className="flex items-center gap-1">
          <button className="text-[#8a92a0] hover:text-white px-1.5 py-0.5 rounded text-sm"
            onClick={() => setScale(s => Math.max(0.5, +(s - 0.2).toFixed(1)))}>−</button>
          <span className="text-xs text-slate-300 w-10 text-center">{Math.round(scale * 100)}%</span>
          <button className="text-[#8a92a0] hover:text-white px-1.5 py-0.5 rounded text-sm"
            onClick={() => setScale(s => Math.min(3, +(s + 0.2).toFixed(1)))}>+</button>
        </div>
        <div className="w-px h-5 bg-white/20" />
        <button className="text-[#8a92a0] hover:text-white text-sm px-1.5" disabled={pageNumber <= 1}
          onClick={() => goTo(pageNumber - 1)}>‹</button>
        <div className="flex items-center gap-1 text-sm text-slate-300">
          <input type="number" value={pageInput}
            onChange={e => { setPageInput(e.target.value); const n = parseInt(e.target.value); if (!isNaN(n)) goTo(n) }}
            className="w-10 text-center bg-white/10 text-white rounded px-1 py-0.5 text-xs" />
          <span className="text-[#8a92a0]">/ {numPages ?? '…'}</span>
        </div>
        <button className="text-[#8a92a0] hover:text-white text-sm px-1.5"
          disabled={!numPages || pageNumber >= numPages} onClick={() => goTo(pageNumber + 1)}>›</button>
        <div className="w-px h-5 bg-white/20" />
        <a href={url} download={article.name} className="text-[#8a92a0] hover:text-white text-xs px-2">⬇</a>
      </div>
      <div ref={containerRef} className="flex-1 overflow-auto flex justify-center py-6 bg-slate-700">
        <Document file={url}
          onLoadSuccess={({ numPages: n }) => { setNumPages(n); setPageNumber(1); setPageInput('1') }}
          loading={<div className="text-white text-sm mt-20">Carregando PDF…</div>}
          error={<div className="text-red-400 text-sm mt-20">Não foi possível carregar.</div>}>
          <Page pageNumber={pageNumber} scale={scale} className="shadow-2xl"
            renderAnnotationLayer renderTextLayer />
        </Document>
      </div>
    </div>
  )
}

// ── Rename Modal ──────────────────────────────────────────────────────────────

type SuggestStatus = 'idle' | 'loading' | 'done' | 'error' | 'applied'
interface SuggestRow { article: Article; status: SuggestStatus; suggested: string; errorMsg?: string }

function RenameSuggestModal({ articles, onClose, onRenamed }: {
  articles: Article[]; onClose: () => void; onRenamed: () => void
}) {
  const { t } = useLanguage()
  const [rows, setRows] = useState<SuggestRow[]>(() =>
    articles.map(a => ({ article: a, status: 'idle' as SuggestStatus, suggested: a.name }))
  )
  const [applyingAll, setApplyingAll] = useState(false)

  function setRow(name: string, patch: Partial<SuggestRow>) {
    setRows(prev => prev.map(r => r.article.name === name ? { ...r, ...patch } : r))
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
    for (const r of rows.filter(r => r.status === 'done')) await applyOne(r)
    setApplyingAll(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div style={{ position: 'relative', background: 'var(--surface)', borderRadius: 16, boxShadow: '0 24px 60px rgba(20,25,40,.4)', width: '100%', maxWidth: 768, display: 'flex', flexDirection: 'column', maxHeight: '85vh' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', padding: '24px 24px 12px' }}>
          <div>
            <h3 style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', margin: 0 }}>{t('vectorize.rename.title')}</h3>
            <p style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 3 }}>{t('vectorize.rename.hint')}</p>
          </div>
          <button style={{ color: 'var(--text-faint)', background: 'none', border: 'none', cursor: 'pointer', fontSize: 18, marginLeft: 16 }} onClick={onClose}>✕</button>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px' }}>
          <table className="w-full text-sm">
            <thead style={{ position: 'sticky', top: 0, background: 'var(--surface)' }}>
              <tr style={{ borderBottom: '1px solid var(--border)' }} className="text-xs uppercase tracking-wide" data-color="faint">
                <th className="text-left py-2 pr-3 w-[35%]" style={{ color: 'var(--text-faint)' }}>{t('vectorize.rename.colOriginal')}</th>
                <th className="text-left py-2 pr-3" style={{ color: 'var(--text-faint)' }}>{t('vectorize.rename.colSuggested')}</th>
                <th className="text-right py-2 w-28" style={{ color: 'var(--text-faint)' }}>{t('vectorize.rename.colStatus')}</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(row => (
                <tr key={row.article.name} style={{ borderTop: '1px solid var(--border)', verticalAlign: 'middle' }}>
                  <td className="py-2 pr-3 text-xs break-all font-mono" style={{ color: 'var(--text-muted)' }}>{row.article.name}</td>
                  <td className="py-2 pr-3">
                    {row.status === 'loading' ? (
                      <span className="text-xs text-[#8a92a0] animate-pulse">{t('vectorize.rename.generating')}</span>
                    ) : row.status === 'error' ? (
                      <span className="text-xs text-red-400">{row.errorMsg}</span>
                    ) : row.status === 'applied' ? (
                      <span className="text-xs text-lutz-600 font-medium font-mono">{row.suggested}</span>
                    ) : (
                      <input className="input text-xs py-1 font-mono" value={row.suggested}
                        onChange={e => setRow(row.article.name, { suggested: e.target.value })} />
                    )}
                  </td>
                  <td className="py-2 text-right whitespace-nowrap">
                    {row.status === 'applied' ? (
                      <span className="text-xs text-lutz-600">✓ {t('vectorize.rename.applied')}</span>
                    ) : row.status === 'idle' ? (
                      <button className="text-xs text-lutz-600 hover:text-lutz-700 underline"
                        onClick={() => generateOne(row.article.name)}>
                        ✨ Sugerir
                      </button>
                    ) : row.status === 'loading' ? (
                      <span className="text-xs" style={{ color: 'var(--text-faint)' }}>…</span>
                    ) : row.status === 'done' ? (
                      <button className="text-xs bg-lutz-500 hover:bg-lutz-600 text-white px-2 py-0.5 rounded"
                        onClick={() => applyOne(row)}>
                        {t('vectorize.rename.apply')}
                      </button>
                    ) : null}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px', borderTop: '1px solid var(--border)' }}>
          <button className="btn-ghost text-sm"
            onClick={() => rows.filter(r => r.status === 'idle' || r.status === 'done').forEach(r => generateOne(r.article.name))}>
            ✨ {t('vectorize.rename.generateAll')}
          </button>
          <div className="flex gap-2">
            <button className="btn-ghost text-sm" onClick={onClose}>{t('dialog.cancel')}</button>
            <button className="btn-primary text-sm" onClick={applyAll}
              disabled={!rows.some(r => r.status === 'done') || applyingAll}>
              {t('vectorize.rename.applyAll')}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Status chip helpers ───────────────────────────────────────────────────────

const VEC_CHIP: Record<string, { label: string; bg: string; fg: string; dot: string }> = {
  vectorized: { label: 'Vetorizado',  bg: '#e6f5ee', fg: '#0f6b47', dot: '#1f9d6b' },
  pending:    { label: 'Pendente',    bg: '#fbf1dd', fg: '#8a6414', dot: '#d69a2d' },
  quarantine: { label: 'Quarentena', bg: '#fdeaea', fg: '#9c2424', dot: '#e05252' },
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  articles: Article[]
  vectorStore: VectorStoreInfo | null
  vectorizeRunning: boolean
  onRefresh: () => void
  onVectorize: () => void
}

export default function BibliotecaTab({ articles, vectorStore, vectorizeRunning, onRefresh, onVectorize }: Props) {
  const { t } = useLanguage()
  const fileRef = useRef<HTMLInputElement>(null)
  const [uploading, setUploading] = useState(false)
  const [openArticle, setOpenArticle] = useState<Article | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<Article | null>(null)
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false)
  const [showRename, setShowRename] = useState(false)
  const [query, setQuery] = useState('')

  // vectorize.py stores pdf.stem (without .pdf); articles API returns f.name (with .pdf).
  // Normalise both sides to stem for comparison.
  const stem = (name: string) => name.replace(/\.pdf$/i, '')
  const vectorizedSet = new Set(vectorStore?.articles.map(a => stem(a.filename)) ?? [])
  const chunkMap = Object.fromEntries(
    (vectorStore?.articles ?? []).map(a => [stem(a.filename), a.chunk_count])
  )

  const handleClose = useCallback(() => setOpenArticle(null), [])

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const files = e.target.files
    if (!files?.length) return
    setUploading(true)
    await uploadArticles(files)
    onRefresh()
    setUploading(false)
    if (fileRef.current) fileRef.current.value = ''
  }

  async function handleDelete(name: string) {
    await deleteArticle(name)
    onRefresh()
  }

  async function handleDeleteAll() {
    await deleteAllArticles()
    onRefresh()
  }

  const filtered = articles.filter(a =>
    !query || a.name.toLowerCase().includes(query.toLowerCase())
  )

  const pendingCount = articles.filter(a => !vectorizedSet.has(stem(a.name))).length

  return (
    <>
      {openArticle && <PdfReaderModal article={openArticle} onClose={handleClose} />}

      {confirmDelete && (
        <ConfirmDialog
          title={t('vectorize.removeConfirm')}
          body={`"${confirmDelete.name}" — ${t('vectorize.removeConfirmBody')}`}
          confirmLabel={t('dialog.delete')} danger
          onCancel={() => setConfirmDelete(null)}
          onConfirm={() => { handleDelete(confirmDelete.name); setConfirmDelete(null) }}
        />
      )}
      {confirmDeleteAll && (
        <ConfirmDialog
          title={t('vectorize.removeAllConfirm')}
          body={t('vectorize.removeAllConfirmBody')}
          confirmLabel={t('dialog.delete')} danger
          onCancel={() => setConfirmDeleteAll(false)}
          onConfirm={() => { handleDeleteAll(); setConfirmDeleteAll(false) }}
        />
      )}
      {showRename && (
        <RenameSuggestModal articles={articles} onClose={() => setShowRename(false)} onRenamed={onRefresh} />
      )}

      {/* Toolbar */}
      <div className="flex-none flex items-center gap-3 px-6 py-4">
        <div className="flex items-center gap-2 rounded-lg px-3 py-2 flex-1 min-w-0"
          style={{ background: 'var(--surface)', border: '1px solid var(--border-2)' }}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" className="flex-none text-[#8a92a0]">
            <circle cx="7" cy="7" r="4.5" stroke="currentColor" strokeWidth="1.3"/>
            <path d="m11 11 3 3" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
          </svg>
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Filtrar artigos…"
            style={{ border: 'none', outline: 'none', fontSize: 13.5, width: '100%', minWidth: 0, background: 'transparent', color: 'var(--text)' }} />
        </div>

        {articles.length > 0 && (
          <button className="shell-btn text-xs" onClick={() => setShowRename(true)}>
            ✨ Renomear
          </button>
        )}
        {articles.length > 0 && (
          <button className="text-xs text-red-400 hover:text-red-600 transition-colors px-2"
            onClick={() => setConfirmDeleteAll(true)}>
            {t('vectorize.removeAll')}
          </button>
        )}
        <label className="shell-btn cursor-pointer">
          {uploading ? t('vectorize.uploading') : (
            <>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M8 10.5V2m0 0L5 5m3-3 3 3M2.5 10.5v2A1 1 0 0 0 3.5 13.5h9a1 1 0 0 0 1-1v-2"
                  stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
              </svg>
              Carregar PDFs
            </>
          )}
          <input ref={fileRef} type="file" accept=".pdf" multiple className="hidden"
            onChange={handleUpload} disabled={uploading} />
        </label>

        <button
          onClick={onVectorize}
          disabled={pendingCount === 0 || vectorizeRunning}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            padding: '8px 13px', border: 'none', borderRadius: 8,
            background: pendingCount > 0 && !vectorizeRunning ? '#1A9494' : '#cfd4dc',
            color: '#fff', fontSize: 13, fontWeight: 600, cursor: pendingCount > 0 && !vectorizeRunning ? 'pointer' : 'default',
          }}
        >
          {vectorizeRunning ? (
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none"
              style={{ animation: 'vspin .8s linear infinite' }}>
              <circle cx="8" cy="8" r="6.4" stroke="rgba(255,255,255,.35)" strokeWidth="2"/>
              <path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" stroke="#fff" strokeWidth="2" strokeLinecap="round"/>
            </svg>
          ) : null}
          {vectorizeRunning ? 'Vetorizando…' : `Vetorizar (${pendingCount})`}
        </button>
      </div>

      {/* Article list */}
      <div className="flex-1 overflow-y-auto px-6 pb-6">
        {articles.length === 0 ? (
          <div className="text-center py-16 text-[#8a92a0] text-sm">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" className="mx-auto mb-3 opacity-30">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <polyline points="14,2 14,8 20,8" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
            </svg>
            {t('vectorize.empty')}
          </div>
        ) : (
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 11, overflow: 'hidden' }}>
            <table className="w-full border-collapse">
              <thead>
                <tr style={{ borderBottom: '1px solid var(--border)' }}>
                  <th className="text-left px-4 py-2.5 section-label">Arquivo</th>
                  <th className="text-left px-4 py-2.5 section-label">Tamanho</th>
                  <th className="text-left px-4 py-2.5 section-label">Status</th>
                  <th className="text-right px-4 py-2.5 section-label">Chunks</th>
                  <th className="px-4 py-2.5" />
                </tr>
              </thead>
              <tbody>
                {filtered.map(a => {
                  const artStem = stem(a.name)
                  const isVec = vectorizedSet.has(artStem)
                  const chip = VEC_CHIP[isVec ? 'vectorized' : 'pending']
                  return (
                    <tr key={a.name}
                      style={{ borderTop: '1px solid var(--border)', cursor: 'pointer' }}
                      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-3)')}
                      onMouseLeave={e => (e.currentTarget.style.background = '')}
                      onClick={() => setOpenArticle(a)}>
                      <td className="px-4 py-2.5">
                        <div className="text-sm font-semibold font-mono truncate max-w-xs"
                          style={{ color: 'var(--text)' }}>{a.name}</div>
                      </td>
                      <td className="px-4 py-2.5 text-xs font-mono whitespace-nowrap"
                        style={{ color: 'var(--text-muted)' }}>{fmt(a.size)}</td>
                      <td className="px-4 py-2.5">
                        <span style={{
                          display: 'inline-flex', alignItems: 'center', gap: 6,
                          fontSize: 11.5, fontWeight: 600, padding: '4px 10px', borderRadius: 20,
                          background: chip.bg, color: chip.fg,
                        }}>
                          <span style={{ width: 7, height: 7, borderRadius: '50%', background: chip.dot, flexShrink: 0 }} />
                          {chip.label}
                        </span>
                      </td>
                      <td className="px-4 py-2.5 text-right text-xs font-mono"
                        style={{ color: 'var(--text-faint)' }}>
                        {isVec ? (chunkMap[artStem] ?? 0) : '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right" onClick={e => e.stopPropagation()}>
                        <button onClick={() => setConfirmDelete(a)}
                          className="text-red-300 hover:text-red-500 text-xs px-1">
                          ✕
                        </button>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  )
}
