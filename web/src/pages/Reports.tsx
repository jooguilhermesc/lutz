import { useEffect, useState } from 'react'
import {
  listReports, getReport, getRawReport, deleteReport, deleteAllReports,
  type ReportMeta, type Report, type ReportArticle,
  type RoadmapReport, type CitationsReport, type CitationsArticleEntry,
} from '../api/client'
import Badge from '../components/Badge'
import { useLanguage } from '../contexts/LanguageContext'
import { LANG_LOCALES } from '../i18n'

// ── Delete dialog with optional "also wipe vector store" checkbox ─────────────

function DeleteReportDialog({
  title, body, onCancel, onConfirm,
}: {
  title: string
  body: string
  onCancel: () => void
  onConfirm: (alsoVectorStore: boolean) => void
}) {
  const { t } = useLanguage()
  const [alsoVectorStore, setAlsoVectorStore] = useState(false)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4">
        <h3 className="text-base font-semibold text-slate-800">{title}</h3>
        <p className="text-sm text-slate-500">{body}</p>
        <label className="flex items-start gap-3 cursor-pointer p-3 rounded-xl border border-amber-200 bg-amber-50">
          <input
            type="checkbox"
            className="rounded border-amber-400 text-amber-500 focus:ring-amber-400 mt-0.5 flex-shrink-0"
            checked={alsoVectorStore}
            onChange={(e) => setAlsoVectorStore(e.target.checked)}
          />
          <div>
            <p className="text-sm font-medium text-amber-800">{t('reports.delete.alsoVectorStore')}</p>
            <p className="text-xs text-amber-600 mt-0.5">{t('reports.delete.alsoVectorStore.hint')}</p>
          </div>
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost text-sm px-4" onClick={onCancel}>
            {t('dialog.cancel')}
          </button>
          <button
            className="text-sm px-4 py-1.5 rounded-lg font-medium bg-red-500 hover:bg-red-600 text-white transition-colors"
            onClick={() => onConfirm(alsoVectorStore)}
          >
            {t('dialog.delete')}
          </button>
        </div>
      </div>
    </div>
  )
}

function fmtNum(n: number, locale: string) { return n.toLocaleString(locale) }

// ── Analysis detail ───────────────────────────────────────────────────────────

function ArticleCard({ art }: { art: ReportArticle }) {
  const { t } = useLanguage()
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-slate-200 rounded-lg p-3 hover:bg-slate-50 transition-colors">
      <div className="flex items-center gap-2 justify-between">
        <span className="font-medium text-sm text-slate-700 break-all">{art.filename}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-slate-400">{art.llm_total_tokens} tok</span>
          <Badge label={art.relevance ?? 'UNKNOWN'} />
        </div>
      </div>
      {art.analysis && (
        <button
          className="text-xs text-slate-400 hover:text-slate-600 mt-1 underline"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? t('reports.analysis.hide') : t('reports.analysis.show')}
        </button>
      )}
      {art.error && <p className="text-xs text-red-500 mt-1">Erro: {art.error}</p>}
      {open && art.analysis && (
        <pre className="mt-2 text-xs bg-slate-50 border border-slate-200 rounded p-3 whitespace-pre-wrap max-h-64 overflow-y-auto">
          {art.analysis}
        </pre>
      )}
    </div>
  )
}

function AnalysisDetail({ name, onBack }: { name: string; onBack: () => void }) {
  const { t, lang } = useLanguage()
  const locale = LANG_LOCALES[lang]
  const [report, setReport] = useState<Report | null>(null)
  const [filter, setFilter] = useState('all')

  useEffect(() => { getReport(name).then(setReport) }, [name])

  if (!report) return <div className="text-slate-400 animate-pulse text-sm">{t('reports.detail.loading')}</div>

  const arts = report.articles ?? []
  const counts: Record<string, number> = {}
  for (const a of arts) {
    const k = (a.relevance ?? 'UNKNOWN').toUpperCase()
    counts[k] = (counts[k] ?? 0) + 1
  }
  const visible = filter === 'all' ? arts : arts.filter((a) => (a.relevance ?? 'UNKNOWN').toUpperCase() === filter)

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button className="text-sm text-sky-600 hover:underline" onClick={onBack}>{t('reports.back')}</button>
        <button className="btn-ghost text-xs" onClick={() => window.open(`/api/reports/${encodeURIComponent(name)}/pdf`, '_blank')}>
          {t('reports.exportPdf')}
        </button>
      </div>
      <div className="card bg-slate-800 text-white space-y-2">
        <h3 className="font-bold text-sky-400">{name}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-300">
          <span>{t('reports.col.mode')}: <strong>{report.metadata.mode}</strong></span>
          <span>{t('reports.col.model')}: <strong>{report.metadata.llm?.model}</strong></span>
          <span>{t('reports.col.tokens')}: <strong>{fmtNum(report.metadata.llm?.total_tokens ?? 0, locale)}</strong></span>
          <span>{t('reports.col.duration')}: <strong>{report.metadata.elapsed_seconds?.toFixed(1)}s</strong></span>
        </div>
      </div>
      <div className="flex gap-2 flex-wrap items-center">
        <button
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${filter === 'all' ? 'bg-slate-800 text-white border-slate-800' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
          onClick={() => setFilter('all')}
        >
          {t('reports.filter.all')} ({arts.length})
        </button>
        {Object.entries(counts).map(([k, n]) => (
          <button key={k} onClick={() => setFilter(k)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${filter === k ? 'bg-slate-800 text-white border-slate-800' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
          >
            {k} ({n})
          </button>
        ))}
      </div>
      <div className="space-y-2">
        {visible.map((a) => <ArticleCard key={a.filename} art={a} />)}
        {visible.length === 0 && <div className="text-slate-400 text-sm py-6 text-center">{t('reports.noArticles')}</div>}
      </div>
    </div>
  )
}

// ── Roadmap detail ────────────────────────────────────────────────────────────

function RoadmapDetail({ name, onBack }: { name: string; onBack: () => void }) {
  const { t, lang } = useLanguage()
  const locale = LANG_LOCALES[lang]
  const [report, setReport] = useState<RoadmapReport | null>(null)

  useEffect(() => { getRawReport(name).then((d) => setReport(d as unknown as RoadmapReport)) }, [name])

  if (!report) return <div className="text-slate-400 animate-pulse text-sm">{t('reports.detail.loading')}</div>

  const { metadata, roadmap } = report

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button className="text-sm text-sky-600 hover:underline" onClick={onBack}>{t('reports.back')}</button>
        <button className="btn-ghost text-xs" onClick={() => window.open(`/api/reports/${encodeURIComponent(name)}/pdf`, '_blank')}>
          {t('reports.exportPdf')}
        </button>
      </div>

      <div className="card bg-slate-800 text-white space-y-2">
        <h3 className="font-bold text-sky-400">{t('nav.roadmap')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-300">
          <span>{t('reports.col.model')}: <strong>{metadata.llm?.model}</strong></span>
          <span>{t('reports.col.tokens')}: <strong>{fmtNum(metadata.llm?.total_tokens ?? 0, locale)}</strong></span>
          <span>{t('reports.col.duration')}: <strong>{metadata.elapsed_seconds?.toFixed(1)}s</strong></span>
          <span>{new Date(metadata.generated_at).toLocaleString(locale)}</span>
        </div>
      </div>

      {roadmap.overview && (
        <div className="card">
          <p className="text-sm text-slate-600 leading-relaxed">{roadmap.overview}</p>
        </div>
      )}

      <div className="space-y-4">
        {roadmap.stages?.map((stage) => (
          <div key={stage.stage_number} className="card space-y-3">
            <div>
              <span className="text-xs font-bold text-lutz-500 uppercase tracking-wide">Etapa {stage.stage_number}</span>
              <h4 className="font-semibold text-slate-800 mt-0.5">{stage.stage_name}</h4>
              <p className="text-sm text-slate-500 mt-1">{stage.description}</p>
            </div>
            <div className="space-y-2">
              {stage.articles?.map((art) => (
                <div key={art.filename} className="border border-slate-200 rounded-lg p-3">
                  <p className="font-medium text-sm text-slate-700 break-all">{art.filename}</p>
                  {art.reading_note && (
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">{art.reading_note}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Citations detail ──────────────────────────────────────────────────────────

function CitationArticleCard({ art }: { art: CitationsArticleEntry }) {
  const [open, setOpen] = useState(false)
  return (
    <div className="border border-slate-200 rounded-lg p-3">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium text-sm text-slate-700 break-all">{art.filename}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-slate-400">{art.llm_total_tokens} tok</span>
          <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500">{art.confidence}%</span>
          <Badge label={art.label ?? 'UNKNOWN'} />
        </div>
      </div>
      {art.reasoning && (
        <button className="text-xs text-slate-400 hover:text-slate-600 mt-1 underline" onClick={() => setOpen((v) => !v)}>
          {open ? 'Ocultar análise' : 'Ver análise'}
        </button>
      )}
      {open && (
        <div className="mt-2 space-y-2">
          {art.reasoning && (
            <p className="text-xs text-slate-600 leading-relaxed bg-slate-50 border border-slate-200 rounded p-2">
              {art.reasoning}
            </p>
          )}
          {art.citations?.length > 0 && (
            <div className="space-y-1">
              <p className="text-xs font-semibold text-slate-500">Citações:</p>
              {art.citations.map((c, i) => (
                <blockquote key={i} className="text-xs text-slate-600 border-l-2 border-lutz-300 pl-2 italic">
                  {c.text}
                </blockquote>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function CitationsDetail({ name, onBack }: { name: string; onBack: () => void }) {
  const { t, lang } = useLanguage()
  const locale = LANG_LOCALES[lang]
  const [report, setReport] = useState<CitationsReport | null>(null)
  const [tab, setTab] = useState<'relevant' | 'not_relevant'>('relevant')

  useEffect(() => { getRawReport(name).then((d) => setReport(d as unknown as CitationsReport)) }, [name])

  if (!report) return <div className="text-slate-400 animate-pulse text-sm">{t('reports.detail.loading')}</div>

  const { metadata } = report
  const relevant = report.relevant_articles ?? []
  const notRelevant = report.not_relevant_articles ?? []
  const shown = tab === 'relevant' ? relevant : notRelevant

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button className="text-sm text-sky-600 hover:underline" onClick={onBack}>{t('reports.back')}</button>
        <button className="btn-ghost text-xs" onClick={() => window.open(`/api/reports/${encodeURIComponent(name)}/pdf`, '_blank')}>
          {t('reports.exportPdf')}
        </button>
      </div>

      <div className="card bg-slate-800 text-white space-y-2">
        <h3 className="font-bold text-sky-400">{t('nav.citations')}</h3>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-300">
          <span>{t('reports.col.model')}: <strong>{metadata.llm?.model}</strong></span>
          <span>{t('reports.col.tokens')}: <strong>{fmtNum(metadata.llm?.total_tokens ?? 0, locale)}</strong></span>
          <span>{t('reports.col.duration')}: <strong>{metadata.elapsed_seconds?.toFixed(1)}s</strong></span>
          <span>{new Date(metadata.generated_at).toLocaleString(locale)}</span>
        </div>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setTab('relevant')}
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${tab === 'relevant' ? 'bg-slate-800 text-white border-slate-800' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
        >
          Relevantes ({relevant.length})
        </button>
        <button
          onClick={() => setTab('not_relevant')}
          className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${tab === 'not_relevant' ? 'bg-slate-800 text-white border-slate-800' : 'bg-white border-slate-200 text-slate-600 hover:bg-slate-50'}`}
        >
          Não relevantes ({notRelevant.length})
        </button>
      </div>

      <div className="space-y-2">
        {shown.map((a) => <CitationArticleCard key={a.filename} art={a} />)}
        {shown.length === 0 && <div className="text-slate-400 text-sm py-6 text-center">{t('reports.noArticles')}</div>}
      </div>
    </div>
  )
}

// ── Dispatcher ────────────────────────────────────────────────────────────────

function ReportDetail({ name, reportType, onBack }: { name: string; reportType: string; onBack: () => void }) {
  if (reportType === 'reading_roadmap') return <RoadmapDetail name={name} onBack={onBack} />
  if (reportType === 'citations') return <CitationsDetail name={name} onBack={onBack} />
  return <AnalysisDetail name={name} onBack={onBack} />
}

// ── List view ─────────────────────────────────────────────────────────────────

export default function Reports() {
  const { t, lang } = useLanguage()
  const locale = LANG_LOCALES[lang]
  const [reports, setReports] = useState<ReportMeta[]>([])
  const [selected, setSelected] = useState<{ name: string; reportType: string } | null>(null)
  const [loading, setLoading] = useState(true)
  const [confirmDelete, setConfirmDelete] = useState<ReportMeta | null>(null)
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false)

  const load = () => {
    setLoading(true)
    listReports('all').then((r) => setReports(r.reports ?? [])).finally(() => setLoading(false))
  }
  useEffect(() => { load() }, [])

  async function handleDelete(alsoVectorStore: boolean) {
    if (!confirmDelete) return
    await deleteReport(confirmDelete.name)
    if (alsoVectorStore) await deleteAllReports(true)  // drop vector store only
    setConfirmDelete(null)
    load()
  }

  async function handleDeleteAll(alsoVectorStore: boolean) {
    await deleteAllReports(alsoVectorStore)
    setConfirmDeleteAll(false)
    load()
  }

  function handleExportPdf(name: string, e: React.MouseEvent) {
    e.stopPropagation()
    window.open(`/api/reports/${encodeURIComponent(name)}/pdf`, '_blank')
  }

  if (selected) {
    return <ReportDetail name={selected.name} reportType={selected.reportType} onBack={() => setSelected(null)} />
  }

  return (
    <div className="space-y-6">
      {confirmDelete && (
        <DeleteReportDialog
          title={t('reports.delete.title')}
          body={`"${confirmDelete.name}" — ${t('reports.delete.body')}`}
          onCancel={() => setConfirmDelete(null)}
          onConfirm={handleDelete}
        />
      )}
      {confirmDeleteAll && (
        <DeleteReportDialog
          title={t('reports.deleteAll.title')}
          body={t('reports.deleteAll.body')}
          onCancel={() => setConfirmDeleteAll(false)}
          onConfirm={handleDeleteAll}
        />
      )}

      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800">{t('reports.title')}</h2>
        <div className="flex items-center gap-3">
          {reports.length > 0 && (
            <button
              className="text-xs text-red-400 hover:text-red-600 transition-colors"
              onClick={() => setConfirmDeleteAll(true)}
            >
              {t('reports.deleteAll')}
            </button>
          )}
          <button className="btn-ghost text-xs" onClick={load}>{t('reports.refresh')}</button>
        </div>
      </div>

      {loading && <div className="text-slate-400 animate-pulse text-sm">{t('reports.loading')}</div>}

      {!loading && reports.length === 0 && (
        <div className="text-slate-400 text-sm py-8 text-center">{t('reports.empty')}</div>
      )}

      <div className="space-y-3">
        {reports.map((r) => {
          const typeLabel = r.report_type === 'reading_roadmap'
            ? t('nav.roadmap')
            : r.report_type === 'citations'
            ? t('nav.citations')
            : r.mode || 'análise'
          return (
            <div
              key={r.name}
              className="card cursor-pointer hover:shadow-md transition-shadow"
              onClick={() => setSelected({ name: r.name, reportType: r.report_type || '' })}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <p className="font-semibold text-slate-800 text-sm truncate">{r.name}</p>
                    <span className="text-xs px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 whitespace-nowrap">{typeLabel}</span>
                  </div>
                  <p className="text-xs text-slate-400 mt-0.5">
                    {r.started_at ? new Date(r.started_at).toLocaleString(locale) : '—'} · {r.articles} artigos · {fmtNum(r.tokens, locale)} tokens · {r.elapsed.toFixed(1)}s
                  </p>
                </div>
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={(e) => handleExportPdf(r.name, e)}
                    className="text-lutz-500 hover:text-lutz-700 text-xs"
                    title={t('reports.exportPdf')}
                  >
                    ⬇ PDF
                  </button>
                  <button
                    onClick={(e) => { e.stopPropagation(); setConfirmDelete(r) }}
                    className="text-red-300 hover:text-red-600 text-xs"
                  >
                    🗑
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
