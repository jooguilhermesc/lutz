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
      background: '#fff',
      border: `1px solid ${expanded ? '#9ecfcf' : '#e4e6eb'}`,
      borderRadius: 11,
      transition: 'border-color .15s',
    }}>
      <div onClick={onToggle}
        className="flex items-center gap-4 px-4 py-3 cursor-pointer">
        <div style={{
          flexShrink: 0, width: 44, height: 30, borderRadius: 6, background: '#f0fafa',
          color: '#1A9494', display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: 10.5, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '.3px',
        }}>PDF</div>
        <div className="flex-1 min-w-0">
          <div className="text-sm font-semibold text-[#1a1d23] truncate font-mono">{art.filename}</div>
          <div className="text-xs text-[#8a92a0] mt-0.5 truncate">
            {art.analysis ? art.analysis.slice(0, 80) + (art.analysis.length > 80 ? '…' : '') : 'Aguardando análise'}
          </div>
        </div>
        {art.relevance && (
          <div className="text-right flex-shrink-0">
            <div className="text-xs font-bold font-mono text-[#1a1d23]">
              {art.chunks_used ?? '—'} chunks
            </div>
            <div className="text-[10px] text-[#b6bcc7] tracking-wide">USADOS</div>
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
          <path d="m4 6 4 4 4-4" stroke="#b6bcc7" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
        </svg>
      </div>

      {expanded && art.analysis && (
        <div style={{ padding: '0 16px 16px', animation: 'vfade .18s ease' }}>
          <div className="border-t border-[#eef0f3] pt-3">
            <div className="section-label mb-2">Análise do LLM</div>
            <pre className="text-xs text-[#3a4150] leading-relaxed bg-[#f7f8fa] border border-[#eef0f3] rounded-lg p-3 whitespace-pre-wrap max-h-64 overflow-y-auto font-mono">
              {art.analysis}
            </pre>
            {art.error && (
              <p className="text-xs text-red-500 mt-2">Erro: {art.error}</p>
            )}
            <div className="flex gap-2 mt-3 text-xs text-[#8a92a0] font-mono">
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

  // Show stream log while running
  if (analysisRunning) {
    return (
      <div className="flex-1 flex flex-col min-h-0 px-6 py-4 gap-4">
        <div className="flex items-center gap-3 flex-none">
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none"
            style={{ animation: 'vspin .8s linear infinite', flexShrink: 0 }}>
            <circle cx="8" cy="8" r="6.4" stroke="#dfe2e8" strokeWidth="2"/>
            <path d="M8 1.6a6.4 6.4 0 0 1 6.4 6.4" stroke="#1A9494" strokeWidth="2" strokeLinecap="round"/>
          </svg>
          <span className="text-sm font-semibold text-[#1a1d23]">Analisando artigos…</span>
          <span className="text-xs text-[#8a92a0] bg-lutz-50 px-2.5 py-1 rounded-full border border-lutz-200">
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
        <div className="text-center text-[#8a92a0]">
          {analysisDone === false ? (
            <p className="text-sm text-red-500">Análise encerrada com erro. Verifique o painel de jobs.</p>
          ) : (
            <>
              <svg width="44" height="44" viewBox="0 0 24 24" fill="none" className="mx-auto mb-3 opacity-30">
                <circle cx="11" cy="11" r="8" stroke="currentColor" strokeWidth="1.5"/>
                <path d="m21 21-4.35-4.35" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
              <p className="text-sm">Configure o critério de triagem e clique em <strong>Analisar</strong> para ver os resultados aqui.</p>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <>
      {/* Filter bar + export */}
      <div className="flex-none flex items-center gap-3 px-6 py-4">
        <div className="flex gap-0.5 bg-[#e8eaee] p-0.5 rounded-[9px]">
          {filterDefs.map(fd => {
            const active = filter === fd.id
            return (
              <button key={fd.id} onClick={() => setFilter(fd.id)} style={{
                display: 'flex', alignItems: 'center', gap: 7,
                fontSize: 13, fontWeight: 600, padding: '6px 12px', border: 'none', borderRadius: 7,
                cursor: 'pointer', background: active ? '#fff' : 'transparent',
                color: active ? '#1a1d23' : '#5b6472',
                boxShadow: active ? '0 1px 2px rgba(20,25,40,.1)' : 'none',
              }}>
                {fd.label}
                <span style={{
                  fontSize: 11, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace',
                  padding: '1px 6px', borderRadius: 9,
                  background: active ? '#e8f8f8' : '#e0e3e8',
                  color: active ? '#1A9494' : '#8a92a0',
                }}>
                  {counts[fd.id === 'all' ? 'all' : fd.id]}
                </span>
              </button>
            )
          })}
        </div>
        <div className="flex-1" />
        <div className="text-xs text-[#8a92a0] font-mono">
          {report.metadata.llm?.model} · {report.metadata.llm?.total_tokens?.toLocaleString()} tokens · {report.metadata.elapsed_seconds?.toFixed(1)}s
        </div>
        <button className="shell-btn text-xs"
          onClick={() => window.open(`/api/reports/${encodeURIComponent('')}/pdf`, '_blank')}>
          ⬇ PDF
        </button>
      </div>

      {/* Summary cards */}
      <div className="flex-none flex gap-3 px-6 pb-4">
        {[
          { label: 'Incluir',  count: counts.INCLUDE,   dotColor: '#1f9d6b' },
          { label: 'Excluir',  count: counts.EXCLUDE,   dotColor: '#9aa3b0' },
          { label: 'Incerto',  count: counts.UNCERTAIN, dotColor: '#d69a2d' },
        ].map(s => (
          <div key={s.label} className="flex-1 bg-white border border-[#e4e6eb] rounded-[11px] p-3 flex items-center gap-3">
            {dot(s.dotColor, 12)}
            <div>
              <div className="text-xl font-bold font-mono text-[#1a1d23] leading-none">{s.count}</div>
              <div className="text-xs text-[#8a92a0] mt-0.5">{s.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Results list */}
      <div className="flex-1 overflow-y-auto px-6 pb-6 flex flex-col gap-2">
        {visible.length === 0 ? (
          <div className="text-center py-12 text-[#8a92a0] text-sm">Nenhum resultado neste filtro.</div>
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
