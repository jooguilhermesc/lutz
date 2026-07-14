import { useState } from 'react'
import {
  getReport, deleteReport, deleteAllReports,
  type ReportMeta, type Report, type ReportArticle,
} from '../api/client'
import Badge from '../components/Badge'
import { useLanguage } from '../contexts/LanguageContext'

function fmtNum(n: number) { return n.toLocaleString('pt-BR') }

// ── Delete dialog ─────────────────────────────────────────────────────────────

function DeleteDialog({ title, body, onCancel, onConfirm }: {
  title: string; body: string; onCancel: () => void; onConfirm: (alsoVs: boolean) => void
}) {
  const { t } = useLanguage()
  const [alsoVs, setAlsoVs] = useState(false)
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4">
        <h3 className="text-base font-semibold text-[#1a1d23]">{title}</h3>
        <p className="text-sm text-[#5b6472]">{body}</p>
        <label className="flex items-start gap-3 cursor-pointer p-3 rounded-xl border border-amber-200 bg-amber-50">
          <input type="checkbox" className="rounded border-amber-400 text-amber-500 mt-0.5 flex-shrink-0"
            checked={alsoVs} onChange={e => setAlsoVs(e.target.checked)} />
          <div>
            <p className="text-sm font-medium text-amber-800">{t('reports.delete.alsoVectorStore')}</p>
            <p className="text-xs text-amber-600 mt-0.5">{t('reports.delete.alsoVectorStore.hint')}</p>
          </div>
        </label>
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost text-sm px-4" onClick={onCancel}>{t('dialog.cancel')}</button>
          <button className="text-sm px-4 py-1.5 rounded-lg font-medium bg-red-500 hover:bg-red-600 text-white"
            onClick={() => onConfirm(alsoVs)}>{t('dialog.delete')}</button>
        </div>
      </div>
    </div>
  )
}

// ── Report detail ─────────────────────────────────────────────────────────────

function ArticleCard({ art }: { art: ReportArticle }) {
  const [open, setOpen] = useState(false)
  const { t } = useLanguage()
  return (
    <div className="border border-[#e4e6eb] rounded-lg p-3 hover:bg-[#f4f5f7] transition-colors">
      <div className="flex items-center gap-2 justify-between">
        <span className="font-medium text-sm text-[#1a1d23] break-all font-mono">{art.filename}</span>
        <div className="flex items-center gap-2 flex-shrink-0">
          <span className="text-xs text-[#8a92a0] font-mono">{art.llm_total_tokens} tok</span>
          <Badge label={art.relevance ?? 'UNKNOWN'} />
        </div>
      </div>
      {art.analysis && (
        <button className="text-xs text-[#8a92a0] hover:text-[#5b6472] mt-1 underline"
          onClick={() => setOpen(v => !v)}>
          {open ? t('reports.analysis.hide') : t('reports.analysis.show')}
        </button>
      )}
      {art.error && <p className="text-xs text-red-500 mt-1">Erro: {art.error}</p>}
      {open && art.analysis && (
        <pre className="mt-2 text-xs bg-[#f7f8fa] border border-[#eef0f3] rounded p-3 whitespace-pre-wrap max-h-64 overflow-y-auto font-mono">
          {art.analysis}
        </pre>
      )}
    </div>
  )
}

function ReportDetail({ meta, onBack }: { meta: ReportMeta; onBack: () => void }) {
  const { t } = useLanguage()
  const [report, setReport] = useState<Report | null>(null)
  const [filter, setFilter] = useState('all')

  useState(() => { getReport(meta.name).then(setReport) })

  if (!report) return (
    <div className="flex-1 flex items-center justify-center">
      <p className="text-sm text-[#8a92a0] animate-pulse">{t('reports.detail.loading')}</p>
    </div>
  )

  const arts = report.articles ?? []
  const counts: Record<string, number> = {}
  for (const a of arts) {
    const k = (a.relevance ?? 'UNKNOWN').toUpperCase()
    counts[k] = (counts[k] ?? 0) + 1
  }
  const visible = filter === 'all' ? arts : arts.filter(a => (a.relevance ?? 'UNKNOWN').toUpperCase() === filter)

  return (
    <>
      <div className="flex-none flex items-center justify-between px-6 py-4">
        <button className="text-sm text-lutz-600 hover:underline flex items-center gap-1.5"
          onClick={onBack}>
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
            <path d="m10 12-4-4 4-4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
          </svg>
          {t('reports.back')}
        </button>
        <button className="shell-btn text-xs"
          onClick={() => window.open(`/api/reports/${encodeURIComponent(meta.name)}/pdf`, '_blank')}>
          ⬇ {t('reports.exportPdf')}
        </button>
      </div>

      <div className="flex-none mx-6 mb-4 bg-[#1a1d23] text-white rounded-[11px] p-4">
        <p className="font-bold text-lutz-400 font-mono text-sm mb-2 truncate">{meta.name}</p>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs text-slate-300 font-mono">
          <span>Modo: <strong>{report.metadata.mode}</strong></span>
          <span>Modelo: <strong>{report.metadata.llm?.model}</strong></span>
          <span>Tokens: <strong>{fmtNum(report.metadata.llm?.total_tokens ?? 0)}</strong></span>
          <span>Duração: <strong>{report.metadata.elapsed_seconds?.toFixed(1)}s</strong></span>
        </div>
      </div>

      <div className="flex-none flex gap-2 flex-wrap px-6 mb-4">
        {['all', ...Object.keys(counts)].map(k => (
          <button key={k}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              filter === k ? 'bg-[#1a1d23] text-white border-[#1a1d23]' : 'bg-white border-[#e4e6eb] text-[#5b6472] hover:bg-[#f4f5f7]'
            }`}
            onClick={() => setFilter(k)}>
            {k === 'all' ? `${t('reports.filter.all')} (${arts.length})` : `${k} (${counts[k]})`}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-2">
        {visible.map(a => <ArticleCard key={a.filename} art={a} />)}
        {visible.length === 0 && (
          <div className="text-[#8a92a0] text-sm py-6 text-center">{t('reports.noArticles')}</div>
        )}
      </div>
    </>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  reports: ReportMeta[]
  onRefresh: () => void
}

export default function RelatoriosTab({ reports, onRefresh }: Props) {
  const { t } = useLanguage()
  const [selected, setSelected] = useState<ReportMeta | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<ReportMeta | null>(null)
  const [confirmDeleteAll, setConfirmDeleteAll] = useState(false)

  async function handleDelete(alsoVs: boolean) {
    if (!confirmDelete) return
    await deleteReport(confirmDelete.name)
    if (alsoVs) await deleteAllReports(true)
    setConfirmDelete(null)
    onRefresh()
  }

  async function handleDeleteAll(alsoVs: boolean) {
    await deleteAllReports(alsoVs)
    setConfirmDeleteAll(false)
    onRefresh()
  }

  if (selected) {
    return (
      <>
        {confirmDelete && (
          <DeleteDialog title={t('reports.delete.title')} body={`"${confirmDelete.name}"`}
            onCancel={() => setConfirmDelete(null)} onConfirm={handleDelete} />
        )}
        <ReportDetail meta={selected} onBack={() => setSelected(null)} />
      </>
    )
  }

  return (
    <>
      {confirmDelete && (
        <DeleteDialog title={t('reports.delete.title')} body={`"${confirmDelete.name}"`}
          onCancel={() => setConfirmDelete(null)} onConfirm={handleDelete} />
      )}
      {confirmDeleteAll && (
        <DeleteDialog title={t('reports.deleteAll.title')} body={t('reports.deleteAll.body')}
          onCancel={() => setConfirmDeleteAll(false)} onConfirm={handleDeleteAll} />
      )}

      <div className="flex-none flex items-center gap-3 px-6 py-4">
        <span className="text-sm text-[#5b6472]">{reports.length} relatórios gerados</span>
        <div className="flex-1" />
        {reports.length > 0 && (
          <button className="text-xs text-red-400 hover:text-red-600 px-2"
            onClick={() => setConfirmDeleteAll(true)}>
            {t('reports.deleteAll')}
          </button>
        )}
        <button className="shell-btn text-xs" onClick={onRefresh}>↺ Atualizar</button>
      </div>

      <div className="flex-1 overflow-y-auto px-6 pb-6 space-y-3">
        {reports.length === 0 ? (
          <div className="text-center py-16 text-[#8a92a0] text-sm">
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" className="mx-auto mb-3 opacity-30">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"
                stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <polyline points="14,2 14,8 20,8" stroke="currentColor" strokeWidth="1.5" strokeLinejoin="round"/>
              <line x1="8" y1="13" x2="16" y2="13" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              <line x1="8" y1="17" x2="12" y2="17" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
            {t('reports.empty')}
          </div>
        ) : reports.map(r => (
          <div key={r.name}
            className="bg-white border border-[#e4e6eb] rounded-[11px] p-4 cursor-pointer hover:shadow-md transition-shadow"
            onClick={() => setSelected(r)}>
            <div className="flex items-start gap-4">
              <div className="flex-none w-10 h-10 rounded-[9px] bg-[#f0fafa] flex items-center justify-center">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M5 2.5h7l4 4v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1Z"
                    stroke="#1A9494" strokeWidth="1.4" strokeLinejoin="round"/>
                  <path d="M12 2.5V7h4.5" stroke="#1A9494" strokeWidth="1.4" strokeLinejoin="round"/>
                  <path d="M7 10.5h6M7 13.5h4" stroke="#1A9494" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <div className="text-sm font-semibold font-mono text-[#1a1d23] mb-1 truncate">{r.name}</div>
                <div className="text-xs text-[#8a92a0]">
                  {r.started_at ? new Date(r.started_at).toLocaleString('pt-BR') : '—'} · {r.articles} artigos · {fmtNum(r.tokens)} tokens · {r.elapsed.toFixed(1)}s
                </div>
              </div>
              <div className="flex gap-2 flex-shrink-0" onClick={e => e.stopPropagation()}>
                <button className="shell-btn text-xs"
                  onClick={() => window.open(`/api/reports/${encodeURIComponent(r.name)}/pdf`, '_blank')}>
                  ⬇ PDF
                </button>
                <button className="text-red-300 hover:text-red-500 text-xs px-1"
                  onClick={() => setConfirmDelete(r)}>🗑</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
