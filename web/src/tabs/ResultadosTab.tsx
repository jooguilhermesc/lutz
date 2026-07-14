import { useState } from 'react'
import StreamLog from '../components/StreamLog'
import type { Report, ReportArticle } from '../api/client'

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

function ArticleResultCard({ art, expanded, onToggle }: {
  art: ReportArticle; expanded: boolean; onToggle: () => void
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
          </div>
        </div>
      )}
    </div>
  )
}

interface Props {
  report: Report | null
  analysisRunning: boolean
  logs: string[]
  analysisDone: boolean | null
}

export default function ResultadosTab({ report, analysisRunning, logs, analysisDone }: Props) {
  const [filter, setFilter] = useState<Filter>('all')
  const [expandedId, setExpandedId] = useState<string | null>(null)

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
          />
        ))}
      </div>
    </>
  )
}
