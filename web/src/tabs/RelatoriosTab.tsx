import { useState } from 'react'
import {
  getReport, deleteReport, deleteAllReports, resetVectorStore,
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
    <div style={{ position: 'fixed', inset: 0, zIndex: 50, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,.4)' }} onClick={onCancel} />
      <div style={{
        position: 'relative', background: 'var(--surface)', borderRadius: 16,
        boxShadow: '0 24px 60px rgba(20,25,40,.4)', padding: 24, width: '100%', maxWidth: 360, margin: '0 16px',
        display: 'flex', flexDirection: 'column', gap: 16,
      }}>
        <h3 style={{ fontSize: 15, fontWeight: 600, color: 'var(--text)', margin: 0 }}>{title}</h3>
        <p style={{ fontSize: 13.5, color: 'var(--text-muted)', margin: 0 }}>{body}</p>
        <label style={{
          display: 'flex', alignItems: 'flex-start', gap: 12, cursor: 'pointer',
          padding: 12, borderRadius: 11, border: '1px solid #fde68a', background: '#fffbeb',
        }}>
          <input type="checkbox" style={{ marginTop: 2, flexShrink: 0, accentColor: '#d97706' }}
            checked={alsoVs} onChange={e => setAlsoVs(e.target.checked)} />
          <div>
            <p style={{ fontSize: 13.5, fontWeight: 500, color: '#92400e', margin: 0 }}>{t('reports.delete.alsoVectorStore')}</p>
            <p style={{ fontSize: 12, color: '#b45309', marginTop: 3 }}>{t('reports.delete.alsoVectorStore.hint')}</p>
          </div>
        </label>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8, paddingTop: 4 }}>
          <button className="btn-ghost text-sm px-4" onClick={onCancel}>{t('dialog.cancel')}</button>
          <button style={{
            fontSize: 13.5, padding: '6px 16px', borderRadius: 8, border: 'none',
            fontWeight: 500, background: '#ef4444', color: '#fff', cursor: 'pointer',
          }} onClick={() => onConfirm(alsoVs)}>{t('dialog.delete')}</button>
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
    <div style={{
      border: '1px solid var(--border)', borderRadius: 9, padding: 12,
      background: 'var(--surface)', transition: 'background .15s',
    }}
      onMouseEnter={e => (e.currentTarget.style.background = 'var(--surface-2)')}
      onMouseLeave={e => (e.currentTarget.style.background = 'var(--surface)')}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, justifyContent: 'space-between' }}>
        <span style={{ fontWeight: 500, fontSize: 13.5, color: 'var(--text)', wordBreak: 'break-all', fontFamily: 'IBM Plex Mono, monospace' }}>
          {art.filename}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <span style={{ fontSize: 12, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace' }}>
            {art.llm_total_tokens} tok
          </span>
          <Badge label={art.relevance ?? 'UNKNOWN'} />
        </div>
      </div>
      {art.analysis && (
        <button style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 4, background: 'none', border: 'none', cursor: 'pointer', padding: 0, textDecoration: 'underline' }}
          onClick={() => setOpen(v => !v)}>
          {open ? t('reports.analysis.hide') : t('reports.analysis.show')}
        </button>
      )}
      {art.error && <p style={{ fontSize: 12, color: '#ef4444', marginTop: 4 }}>Erro: {art.error}</p>}
      {open && art.analysis && (
        <pre style={{
          marginTop: 8, fontSize: 12, background: 'var(--surface-2)', border: '1px solid var(--border)',
          borderRadius: 7, padding: 12, whiteSpace: 'pre-wrap', maxHeight: 256,
          overflowY: 'auto', fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text-muted)',
        }}>
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
      <p style={{ fontSize: 13.5, color: 'var(--text-faint)' }} className="animate-pulse">{t('reports.detail.loading')}</p>
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
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 24px' }}>
        <button style={{ fontSize: 13.5, color: '#1A9494', background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6 }}
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

      <div style={{
        flexShrink: 0, margin: '0 24px 16px', background: '#0f1117', color: '#e8eaf0',
        borderRadius: 11, padding: 16,
      }}>
        <p style={{ fontWeight: 700, color: '#1A9494', fontFamily: 'IBM Plex Mono, monospace', fontSize: 13.5, marginBottom: 8, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {meta.name}
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, fontSize: 12, color: '#9ca3af', fontFamily: 'IBM Plex Mono, monospace' }}>
          <span>Modo: <strong style={{ color: '#e8eaf0' }}>{report.metadata.mode}</strong></span>
          <span>Modelo: <strong style={{ color: '#e8eaf0' }}>{report.metadata.llm?.model}</strong></span>
          <span>Tokens: <strong style={{ color: '#e8eaf0' }}>{fmtNum(report.metadata.llm?.total_tokens ?? 0)}</strong></span>
          <span>Duração: <strong style={{ color: '#e8eaf0' }}>{report.metadata.elapsed_seconds?.toFixed(1)}s</strong></span>
        </div>
      </div>

      <div style={{ flexShrink: 0, display: 'flex', gap: 8, flexWrap: 'wrap', padding: '0 24px 16px' }}>
        {['all', ...Object.keys(counts)].map(k => (
          <button key={k}
            style={{
              padding: '4px 12px', borderRadius: 20, fontSize: 12.5, fontWeight: 500,
              border: `1px solid ${filter === k ? 'var(--text)' : 'var(--border)'}`,
              background: filter === k ? 'var(--text)' : 'var(--surface)',
              color: filter === k ? 'var(--surface)' : 'var(--text-muted)',
              cursor: 'pointer', transition: 'all .15s',
            }}
            onClick={() => setFilter(k)}>
            {k === 'all' ? `${t('reports.filter.all')} (${arts.length})` : `${k} (${counts[k]})`}
          </button>
        ))}
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {visible.map(a => <ArticleCard key={a.filename} art={a} />)}
        {visible.length === 0 && (
          <div style={{ color: 'var(--text-faint)', fontSize: 13.5, padding: '24px 0', textAlign: 'center' }}>
            {t('reports.noArticles')}
          </div>
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
    if (alsoVs) await resetVectorStore()
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

      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px' }}>
        <span style={{ fontSize: 13.5, color: 'var(--text-muted)' }}>{reports.length} relatórios gerados</span>
        <div style={{ flex: 1 }} />
        {reports.length > 0 && (
          <button style={{ fontSize: 12.5, color: '#f87171', background: 'none', border: 'none', cursor: 'pointer', padding: '0 8px' }}
            onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
            onMouseLeave={e => (e.currentTarget.style.color = '#f87171')}
            onClick={() => setConfirmDeleteAll(true)}>
            {t('reports.deleteAll')}
          </button>
        )}
        <button className="shell-btn text-xs" onClick={onRefresh}>↺ Atualizar</button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: 12 }}>
        {reports.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '64px 0', color: 'var(--text-faint)', fontSize: 13.5 }}>
            <svg width="40" height="40" viewBox="0 0 24 24" fill="none" style={{ margin: '0 auto 12px', opacity: 0.3, display: 'block', color: 'var(--text-faint)' }}>
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
            style={{
              background: 'var(--surface)', border: '1px solid var(--border)',
              borderRadius: 11, padding: 16, cursor: 'pointer', transition: 'box-shadow .15s',
            }}
            onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 16px rgba(20,25,40,.12)')}
            onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
            onClick={() => setSelected(r)}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 16 }}>
              <div style={{
                flexShrink: 0, width: 40, height: 40, borderRadius: 9,
                background: '#f0fafa', display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M5 2.5h7l4 4v11a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1v-14a1 1 0 0 1 1-1Z"
                    stroke="#1A9494" strokeWidth="1.4" strokeLinejoin="round"/>
                  <path d="M12 2.5V7h4.5" stroke="#1A9494" strokeWidth="1.4" strokeLinejoin="round"/>
                  <path d="M7 10.5h6M7 13.5h4" stroke="#1A9494" strokeWidth="1.3" strokeLinecap="round"/>
                </svg>
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)', marginBottom: 4, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {r.name}
                </div>
                <div style={{ fontSize: 12, color: 'var(--text-faint)' }}>
                  {r.started_at ? new Date(r.started_at).toLocaleString('pt-BR') : '—'} · {r.articles} artigos · {fmtNum(r.tokens)} tokens · {r.elapsed.toFixed(1)}s
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8, flexShrink: 0 }} onClick={e => e.stopPropagation()}>
                <button className="shell-btn text-xs"
                  onClick={() => window.open(`/api/reports/${encodeURIComponent(r.name)}/pdf`, '_blank')}>
                  ⬇ PDF
                </button>
                <button style={{ color: '#f87171', background: 'none', border: 'none', cursor: 'pointer', fontSize: 13.5, padding: '0 4px' }}
                  onMouseEnter={e => (e.currentTarget.style.color = '#ef4444')}
                  onMouseLeave={e => (e.currentTarget.style.color = '#f87171')}
                  onClick={() => setConfirmDelete(r)}>🗑</button>
              </div>
            </div>
          </div>
        ))}
      </div>
    </>
  )
}
