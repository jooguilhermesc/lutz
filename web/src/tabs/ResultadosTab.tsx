import { useState, useEffect } from 'react'
import StreamLog from '../components/StreamLog'
import { useNotifications } from '../contexts/NotificationsContext'
import { useLanguage } from '../contexts/LanguageContext'
import {
  getRawReport, listReports, getReportPdfUrl,
  type Report, type ReportArticle,
  type CitationsReport, type CitationsArticleEntry,
  type RoadmapReport,
} from '../api/client'

// ── Constants ─────────────────────────────────────────────────────────────────

const DEFAULT_ROADMAP_STAGES = [
  { name: 'Leituras fundacionais', criteria: 'Artigos que servem de base para compreender os demais — conceitos fundamentais, revisões abrangentes e metodologias centrais.' },
  { name: 'Casos específicos', criteria: 'Artigos bem elaborados sobre tópicos que se fecham em si mesmos e têm pouca relação com os demais.' },
  { name: 'Evolução do conteúdo', criteria: 'Artigos que apresentam conceitos mais elaborados, refinamentos metodológicos ou aplicações avançadas sobre o tema central.' },
]

// ── Helpers ───────────────────────────────────────────────────────────────────

function getRoadmapStages(): Array<{ name: string; criteria: string }> {
  try {
    const stored = localStorage.getItem('lutz_roadmap_stages')
    if (stored) return JSON.parse(stored)
  } catch { /* ignore */ }
  return DEFAULT_ROADMAP_STAGES
}

function buildUserInstructions(stages: Array<{ name: string; criteria: string }>): string {
  const lines = stages
    .filter(s => s.name.trim())
    .map((s, i) => `${i + 1}. "${s.name}": ${s.criteria}`)
  return `Organize os artigos nos seguintes estágios (use exatamente estes nomes e critérios):\n${lines.join('\n')}`
}

function downloadPdf(reportName: string) {
  const url = getReportPdfUrl(reportName)
  const a = document.createElement('a')
  a.href = url
  a.download = `${reportName}.pdf`
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
}

function extractRoadmapContent(rm: RoadmapReport['roadmap']) {
  let overview = rm?.overview ?? ''
  let stages = rm?.stages ?? []
  // Fallback: backend JSON parsing failed → overview holds the raw LLM response
  if (overview.trim().startsWith('{') && stages.length === 0) {
    try {
      const parsed = JSON.parse(overview)
      if (parsed?.overview) overview = parsed.overview
      if (Array.isArray(parsed?.stages)) stages = parsed.stages
    } catch { /* not parseable, render as text */ }
  }
  return { overview, stages }
}

// ── Status meta ───────────────────────────────────────────────────────────────

type Filter = 'all' | 'INCLUDE' | 'EXCLUDE' | 'UNCERTAIN'

const STATUS_META: Record<string, { label: string; dot: string; chipBg: string; chipFg: string }> = {
  INCLUDE:   { label: 'Incluir',  dot: '#1f9d6b', chipBg: '#e6f5ee', chipFg: '#0f6b47' },
  EXCLUDE:   { label: 'Excluir',  dot: '#9aa3b0', chipBg: '#eef0f3', chipFg: '#5b6472' },
  UNCERTAIN: { label: 'Incerto',  dot: '#d69a2d', chipBg: '#fbf1dd', chipFg: '#8a6414' },
  UNKNOWN:   { label: 'Aguard.',  dot: '#cfd4dc', chipBg: '#f4f5f7', chipFg: '#9aa3b0' },
}

function dot(c: string, sz = 8) {
  return (
    <span style={{ display: 'inline-block', width: sz, height: sz, borderRadius: '50%', background: c, flexShrink: 0 }} />
  )
}

function Spinner() {
  return (
    <svg width="12" height="12" viewBox="0 0 16 16" fill="none" style={{ animation: 'vspin .8s linear infinite', flexShrink: 0 }}>
      <circle cx="8" cy="8" r="6.4" stroke="currentColor" strokeOpacity=".3" strokeWidth="2"/>
      <path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" stroke="currentColor" strokeWidth="2" strokeLinecap="round"/>
    </svg>
  )
}

// ── Article card ──────────────────────────────────────────────────────────────

function ArticleResultCard({ art, expanded, onToggle, citationsEntry }: {
  art: ReportArticle
  expanded: boolean
  onToggle: () => void
  citationsEntry?: CitationsArticleEntry | null
}) {
  const key = (art.relevance ?? 'UNKNOWN').toUpperCase()
  const s = STATUS_META[key] ?? STATUS_META.UNKNOWN
  return (
    <div style={{
      background: 'var(--surface)',
      border: `1px solid ${expanded ? '#9ecfcf' : 'var(--border)'}`,
      borderRadius: 11,
      transition: 'border-color .15s',
    }}>
      <div onClick={onToggle}
        style={{ display: 'flex', alignItems: 'center', gap: 16, padding: '12px 16px', cursor: 'pointer' }}>
        <div style={{
          flexShrink: 0, width: 44, height: 30, borderRadius: 6, background: '#f0fafa',
          color: '#1A9494', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10.5, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '.3px',
        }}>PDF</div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontFamily: 'IBM Plex Mono, monospace' }}>
            {art.filename}
          </div>
          <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {art.analysis ? art.analysis.slice(0, 80) + (art.analysis.length > 80 ? '…' : '') : 'Aguardando análise'}
          </div>
        </div>
        {art.relevance && (
          <div style={{ textAlign: 'right', flexShrink: 0 }}>
            <div style={{ fontSize: 12, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)' }}>
              {art.chunks_used ?? '—'} chunks
            </div>
            <div style={{ fontSize: 10, color: 'var(--text-chip)', letterSpacing: '.05em' }}>USADOS</div>
          </div>
        )}
        <span style={{
          flexShrink: 0, display: 'inline-flex', alignItems: 'center', gap: 6,
          fontSize: 11.5, fontWeight: 600, padding: '5px 11px', borderRadius: 20,
          background: s.chipBg, color: s.chipFg,
        }}>
          {dot(s.dot, 7)}
          {s.label}
        </span>
        <svg width="14" height="14" viewBox="0 0 16 16" fill="none"
          style={{ flexShrink: 0, transition: 'transform .18s', transform: `rotate(${expanded ? 180 : 0}deg)` }}>
          <path d="m4 6 4 4 4-4" stroke="var(--text-chip)" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      {expanded && art.analysis && (
        <div style={{ padding: '0 16px 16px', animation: 'vfade .18s ease' }}>
          <div style={{ borderTop: '1px solid var(--border)', paddingTop: 12 }}>
            <div className="section-label" style={{ marginBottom: 8 }}>Análise do LLM</div>
            <pre style={{
              fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.6,
              background: 'var(--surface-2)', border: '1px solid var(--border)',
              borderRadius: 9, padding: 12, whiteSpace: 'pre-wrap', maxHeight: 256,
              overflowY: 'auto', fontFamily: 'IBM Plex Mono, monospace', margin: 0,
            }}>
              {art.analysis}
            </pre>
            {art.error && (
              <p style={{ fontSize: 12, color: '#ef4444', marginTop: 8 }}>Erro: {art.error}</p>
            )}
            <div style={{ display: 'flex', gap: 8, marginTop: 12, fontSize: 12, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace' }}>
              <span>{art.llm_total_tokens} tokens</span>
              <span>·</span>
              <span>{art.chunks_used ?? 0} chunks</span>
            </div>

            {citationsEntry && (citationsEntry.citations?.length ?? 0) > 0 && (
              <div style={{ marginTop: 16 }}>
                <div className="section-label" style={{ marginBottom: 8 }}>Citações de suporte</div>
                {citationsEntry.reasoning && (
                  <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 10, fontStyle: 'italic', lineHeight: 1.5 }}>
                    {citationsEntry.reasoning}
                  </p>
                )}
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {citationsEntry.citations.map((c, i) => (
                    <div key={i} style={{
                      background: 'var(--surface-2)', border: '1px solid var(--border)',
                      borderLeft: '3px solid #1A9494', borderRadius: '0 8px 8px 0',
                      padding: '8px 12px',
                    }}>
                      <p style={{ fontSize: 12, color: 'var(--text)', margin: 0, lineHeight: 1.6 }}>
                        "{c.text}"
                      </p>
                      {c.page != null && (
                        <p style={{ fontSize: 11, color: 'var(--text-faint)', margin: '4px 0 0', fontFamily: 'IBM Plex Mono, monospace' }}>
                          p. {c.page}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
                {citationsEntry.confidence != null && (
                  <p style={{ fontSize: 11, color: 'var(--text-faint)', marginTop: 6, fontFamily: 'IBM Plex Mono, monospace' }}>
                    Confiança: {citationsEntry.confidence}%
                  </p>
                )}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Roadmap modal ─────────────────────────────────────────────────────────────

function RoadmapModal({ data, reportName, onClose }: {
  data: RoadmapReport
  reportName: string | null
  onClose: () => void
}) {
  const { metadata } = data
  const { overview, stages } = extractRoadmapContent(data.roadmap)

  return (
    <div style={{
      position: 'fixed', inset: 0, background: 'rgba(20,25,40,.5)', zIndex: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32,
      animation: 'vfade .15s ease',
    }}>
      <div style={{
        width: 700, maxWidth: '100%', maxHeight: '88vh', background: 'var(--surface)',
        borderRadius: 16, boxShadow: '0 24px 60px rgba(20,25,40,.4)',
        display: 'flex', flexDirection: 'column', overflow: 'hidden',
      }}>
        <div style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 24px', borderBottom: '1px solid var(--border)',
        }}>
          <div>
            <span style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Roteiro de leitura</span>
            <span style={{ marginLeft: 10, fontSize: 12, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace' }}>
              {metadata.llm?.model} · {metadata.llm?.total_tokens?.toLocaleString()} tokens · {metadata.elapsed_seconds?.toFixed(1)}s
            </span>
          </div>
          <button onClick={onClose} style={{
            width: 32, height: 32, border: '1px solid var(--border)', borderRadius: 8,
            background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
            justifyContent: 'center', color: 'var(--text-muted)',
          }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
          {overview && (
            <p style={{ fontSize: 13, color: 'var(--text-muted)', lineHeight: 1.7, margin: 0, background: 'var(--surface-2)', borderRadius: 9, padding: '10px 14px', border: '1px solid var(--border)' }}>
              {overview}
            </p>
          )}
          {stages.map((stage, i) => (
            <div key={i} style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: 11, overflow: 'hidden' }}>
              <div style={{ padding: '12px 16px', background: 'var(--surface)', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'flex-start', gap: 10 }}>
                <span style={{ flexShrink: 0, width: 24, height: 24, borderRadius: 6, background: '#1A9494', color: '#fff', fontSize: 11, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>{stage.stage_number ?? i + 1}</span>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>{stage.stage_name}</div>
                  {stage.description && <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 3 }}>{stage.description}</div>}
                </div>
              </div>
              <div style={{ padding: '12px 16px', display: 'flex', flexDirection: 'column', gap: 10 }}>
                {(stage.articles ?? []).map((a, j) => (
                  <div key={j} style={{ display: 'flex', gap: 10 }}>
                    <div style={{ flexShrink: 0, width: 20, height: 20, borderRadius: 4, background: '#e8f8f8', color: '#1A9494', fontSize: 10, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', display: 'flex', alignItems: 'center', justifyContent: 'center', marginTop: 1 }}>{j + 1}</div>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{a.filename}</div>
                      {a.reading_note && <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 3, lineHeight: 1.5 }}>{a.reading_note}</div>}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div style={{ flexShrink: 0, padding: '14px 24px', borderTop: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
          {reportName && (
            <button
              onClick={() => downloadPdf(reportName)}
              style={{ padding: '8px 16px', border: 'none', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 600, background: '#1A9494', color: '#fff', display: 'flex', alignItems: 'center', gap: 6 }}
            >
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="M8 2v8M5 7l3 3 3-3" stroke="#fff" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                <path d="M3 12h10" stroke="#fff" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              Exportar PDF
            </button>
          )}
          <button onClick={onClose} style={{ padding: '8px 16px', border: '1px solid var(--border)', borderRadius: 9, cursor: 'pointer', fontSize: 13, fontWeight: 600, background: 'var(--surface)', color: 'var(--text-muted)' }}>
            Fechar
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────

interface Props {
  report: Report | null
  activeReportName: string | null
  analysisRunning: boolean
  logs: string[]
  analysisDone: boolean | null
}

export default function ResultadosTab({ report, activeReportName, analysisRunning, logs, analysisDone }: Props) {
  const { dispatchJob, jobs } = useNotifications()
  const { reportLang } = useLanguage()
  const [filter, setFilter] = useState<Filter>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)

  // Citations
  const [citJobId, setCitJobId] = useState<string | null>(null)
  const [citData, setCitData] = useState<CitationsReport | null>(null)
  const [citReportName, setCitReportName] = useState<string | null>(null)

  // Roadmap
  const [rmJobId, setRmJobId] = useState<string | null>(null)
  const [rmData, setRmData] = useState<RoadmapReport | null>(null)
  const [rmReportName, setRmReportName] = useState<string | null>(null)
  const [showRmModal, setShowRmModal] = useState(false)

  // Auto-load existing reports when the analysis report changes
  useEffect(() => {
    if (!activeReportName) return
    listReports('all').then(r => {
      const reps = r.reports ?? []
      const citName = reps.filter(m => m.report_type === 'citations')[0]?.name
      if (citName) {
        setCitReportName(citName)
        getRawReport(citName).then(raw => setCitData(raw as unknown as CitationsReport)).catch(() => {})
      }
      const rmName = reps.filter(m => m.report_type === 'reading_roadmap')[0]?.name
      if (rmName) {
        setRmReportName(rmName)
        getRawReport(rmName).then(raw => setRmData(raw as unknown as RoadmapReport)).catch(() => {})
      }
    }).catch(() => {})
  }, [activeReportName])

  // Watch citations job completion
  useEffect(() => {
    if (!citJobId) return
    const job = jobs.find(j => j.id === citJobId)
    if (!job) return
    if (job.status === 'done') {
      setCitJobId(null)
      listReports('all').then(r => {
        const name = (r.reports ?? []).filter(m => m.report_type === 'citations')[0]?.name ?? null
        if (name) {
          setCitReportName(name)
          getRawReport(name).then(raw => setCitData(raw as unknown as CitationsReport)).catch(() => {})
        }
      }).catch(() => {})
    } else if (job.status === 'error' || job.status === 'cancelled') {
      setCitJobId(null)
    }
  }, [jobs, citJobId])

  // Watch roadmap job completion
  useEffect(() => {
    if (!rmJobId) return
    const job = jobs.find(j => j.id === rmJobId)
    if (!job) return
    if (job.status === 'done') {
      setRmJobId(null)
      listReports('all').then(r => {
        const name = (r.reports ?? []).filter(m => m.report_type === 'reading_roadmap')[0]?.name ?? null
        if (name) {
          setRmReportName(name)
          getRawReport(name).then(raw => {
            setRmData(raw as unknown as RoadmapReport)
            setShowRmModal(true)
          }).catch(() => {})
        }
      }).catch(() => {})
    } else if (job.status === 'error' || job.status === 'cancelled') {
      setRmJobId(null)
    }
  }, [jobs, rmJobId])

  const citJob = citJobId ? jobs.find(j => j.id === citJobId) : null
  const citRunning = citJob?.status === 'queued' || citJob?.status === 'running'
  const rmJob = rmJobId ? jobs.find(j => j.id === rmJobId) : null
  const rmRunning = rmJob?.status === 'queued' || rmJob?.status === 'running'

  const arts = report?.articles ?? []
  const counts = { all: arts.length, INCLUDE: 0, EXCLUDE: 0, UNCERTAIN: 0 }
  for (const a of arts) {
    const k = (a.relevance ?? 'UNKNOWN').toUpperCase()
    if (k === 'INCLUDE') counts.INCLUDE++
    else if (k === 'EXCLUDE') counts.EXCLUDE++
    else counts.UNCERTAIN++
  }

  const visible = filter === 'all' ? arts : arts.filter(a =>
    (a.relevance ?? 'UNKNOWN').toUpperCase() === filter
  )

  const filterDefs: Array<{ id: Filter; label: string }> = [
    { id: 'all',       label: 'Todos'  },
    { id: 'INCLUDE',   label: 'Incluir' },
    { id: 'EXCLUDE',   label: 'Excluir' },
    { id: 'UNCERTAIN', label: 'Incerto' },
  ]

  function getCitationsEntry(filename: string): CitationsArticleEntry | null {
    return citData?.relevant_articles?.find(a => a.filename === filename) ?? null
  }

  async function handleExtractCitations() {
    if (!activeReportName || citRunning) return
    setCitData(null)
    setCitReportName(null)
    const job = await dispatchJob('citations', { report: activeReportName, language: reportLang })
    setCitJobId(job.id)
  }

  async function handleRoadmap() {
    if (!activeReportName || rmRunning) return
    const stages = getRoadmapStages()
    const user_instructions = buildUserInstructions(stages)
    setRmData(null)
    setRmReportName(null)
    const job = await dispatchJob('roadmap', { report: activeReportName, user_instructions, language: reportLang })
    setRmJobId(job.id)
  }

  const showActions = !!report && counts.INCLUDE > 0 && !!activeReportName

  if (analysisRunning) {
    return (
      <div className="flex-1 flex flex-col min-h-0 px-6 py-4 gap-4">
        <div className="flex items-center gap-3 flex-none">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
            style={{ animation: 'vspin .8s linear infinite', flexShrink: 0 }}>
            <circle cx="8" cy="8" r="6.4" stroke="var(--border-2)" strokeWidth="2"/>
            <path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" stroke="#1A9494" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--text)' }}>Analisando artigos…</span>
          <span className="text-xs text-lutz-500 bg-lutz-50 px-2.5 py-1 rounded-full border border-lutz-200">
            rodando em segundo plano
          </span>
        </div>
        <StreamLog lines={logs} running={analysisRunning} className="flex-1" />
      </div>
    )
  }

  if (!report) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div style={{ textAlign: 'center', color: 'var(--text-faint)' }}>
          {analysisDone === false ? (
            <p style={{ fontSize: 13.5, color: '#ef4444' }}>Análise encerrada com erro. Verifique o painel de jobs.</p>
          ) : (
            <>
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" style={{ margin: '0 auto 12px', opacity: 0.3, color: 'var(--text-faint)', display: 'block' }}>
                <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5"/>
                <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <p style={{ fontSize: 13.5, color: 'var(--text-faint)' }}>Configure o critério de triagem e clique em <strong style={{ color: 'var(--text-muted)' }}>Analisar</strong> para ver os resultados aqui.</p>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Filter bar */}
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 12, padding: '16px 24px' }}>
        <div style={{ display: 'flex', gap: 2, background: 'var(--surface-3)', padding: 2, borderRadius: 9 }}>
          {filterDefs.map(fd => {
            const active = filter === fd.id
            return (
              <button key={fd.id} onClick={() => setFilter(fd.id)} style={{
                display: 'flex', alignItems: 'center', gap: 7,
                fontSize: 13, fontWeight: 600, padding: '6px 12px', border: 'none', borderRadius: 7,
                cursor: 'pointer',
                background: active ? 'var(--surface)' : 'transparent',
                color: active ? 'var(--text)' : 'var(--text-faint)',
                boxShadow: active ? '0 1px 2px rgba(20,25,40,.1)' : 'none',
              }}>
                {fd.label}
                <span style={{
                  fontSize: 11, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace',
                  padding: '1px 6px', borderRadius: 9,
                  background: active ? '#e8f8f8' : 'var(--border)',
                  color: active ? '#1A9494' : 'var(--text-faint)',
                }}>
                  {counts[fd.id === 'all' ? 'all' : fd.id]}
                </span>
              </button>
            )
          })}
        </div>
        <div style={{ flex: 1 }} />

        {showActions && (
          <div style={{ display: 'flex', gap: 8 }}>
            {/* Citations button */}
            <button
              onClick={() => {
                if (citRunning) return
                if (citData && citReportName) {
                  // Already have data — offer PDF download
                  downloadPdf(citReportName)
                } else {
                  handleExtractCitations()
                }
              }}
              disabled={citRunning}
              title={citData ? 'Baixar PDF das citações' : 'Extrair citações dos artigos incluídos'}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', border: '1px solid var(--border)', borderRadius: 8,
                background: citData ? '#e6f5ee' : 'var(--surface)',
                color: citData ? '#0f6b47' : 'var(--text-muted)',
                cursor: citRunning ? 'not-allowed' : 'pointer',
                fontSize: 12.5, fontWeight: 600, opacity: citRunning ? 0.6 : 1,
                transition: 'background .15s, color .15s',
              }}
            >
              {citRunning ? <Spinner /> : (
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                  <path d="M3 4h2v8H3V4ZM11 4h2v8h-2V4ZM5 7h6" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              )}
              {citRunning ? 'Extraindo…' : citData ? 'Citações ⬇' : 'Extrair citações'}
            </button>

            {/* Roadmap button */}
            <button
              onClick={() => {
                if (rmRunning) return
                if (rmData) { setShowRmModal(true) } else { handleRoadmap() }
              }}
              disabled={rmRunning}
              title={rmData ? 'Ver roteiro de leitura' : 'Gerar roteiro de leitura'}
              style={{
                display: 'flex', alignItems: 'center', gap: 6,
                padding: '6px 12px', border: '1px solid var(--border)', borderRadius: 8,
                background: rmData ? '#e8f8f8' : 'var(--surface)',
                color: rmData ? '#1A9494' : 'var(--text-muted)',
                cursor: rmRunning ? 'not-allowed' : 'pointer',
                fontSize: 12.5, fontWeight: 600, opacity: rmRunning ? 0.6 : 1,
                transition: 'background .15s, color .15s',
              }}
            >
              {rmRunning ? <Spinner /> : (
                <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                  <rect x="2" y="3" width="12" height="10" rx="2" stroke="currentColor" strokeWidth="1.4"/>
                  <path d="M5 6h6M5 9h4" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round"/>
                </svg>
              )}
              {rmRunning ? 'Gerando…' : rmData ? 'Ver roteiro' : 'Roteiro de leitura'}
            </button>
          </div>
        )}

        <div style={{ fontSize: 12, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace' }}>
          {report.metadata.llm?.model} · {report.metadata.llm?.total_tokens?.toLocaleString()} tokens · {report.metadata.elapsed_seconds?.toFixed(1)}s
        </div>
      </div>

      {/* Summary cards */}
      <div style={{ flexShrink: 0, display: 'flex', gap: 12, padding: '0 24px 16px' }}>
        {[
          { label: 'Incluir',  count: counts.INCLUDE,   dotColor: '#1f9d6b' },
          { label: 'Excluir',  count: counts.EXCLUDE,   dotColor: '#9aa3b0' },
          { label: 'Incerto',  count: counts.UNCERTAIN, dotColor: '#d69a2d' },
        ].map(s => (
          <div key={s.label} style={{
            flex: 1, background: 'var(--surface)', border: '1px solid var(--border)',
            borderRadius: 11, padding: 12, display: 'flex', alignItems: 'center', gap: 12,
          }}>
            {dot(s.dotColor, 12)}
            <div>
              <div style={{ fontSize: 20, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)', lineHeight: 1 }}>{s.count}</div>
              <div style={{ fontSize: 12, color: 'var(--text-faint)', marginTop: 2 }}>{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Results list */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '0 24px 24px', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {visible.length === 0 ? (
          <div style={{ textAlign: 'center', padding: '48px 0', color: 'var(--text-faint)', fontSize: 13.5 }}>
            Nenhum resultado neste filtro.
          </div>
        ) : visible.map(a => (
          <ArticleResultCard
            key={a.filename}
            art={a}
            expanded={expandedId === a.filename}
            onToggle={() => setExpandedId(v => v === a.filename ? null : a.filename)}
            citationsEntry={getCitationsEntry(a.filename)}
          />
        ))}
      </div>

      {/* Roadmap modal */}
      {showRmModal && rmData && (
        <RoadmapModal
          data={rmData}
          reportName={rmReportName}
          onClose={() => setShowRmModal(false)}
        />
      )}
    </>
  )
}
