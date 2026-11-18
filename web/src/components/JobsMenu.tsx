import { useState } from 'react'
import { api, type JobCompleto } from '../api'
import { useApp } from '../app-context'
import { StatusPill, useFmt } from './ui'

export function JobsMenu() {
  const { jobs, tr } = useApp()
  const fmt = useFmt()
  const [aberto, setAberto] = useState(false)
  const [detalhe, setDetalhe] = useState<JobCompleto | null>(null)
  const rodando = jobs.filter((j) => j.status === 'rodando').length
  return (
    <div style={{ position: 'relative' }}>
      <button className="btn" onClick={() => setAberto((a) => !a)} aria-expanded={aberto} aria-haspopup="true">
        <span className="dot" style={{ background: rodando ? 'var(--lutz-500)' : 'var(--border-2)' }} />
        Jobs ({rodando})
      </button>
      {aberto ? (
        <div className="popover" role="menu">
          {jobs.length === 0 ? <div className="faint small" style={{ padding: 8 }}>{tr('Nenhum job nesta sessão.', 'No jobs in this session.')}</div> : null}
          {jobs.slice(0, 20).map((j) => (
            <button key={j.id} className="nav" style={{ flexDirection: 'column', alignItems: 'stretch', gap: 2 }}
              onClick={async () => setDetalhe(await api.get<JobCompleto>(`/jobs/${j.id}`))}>
              <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis' }}>{j.descricao}</span>
                <StatusPill status={j.status} />
              </span>
              <span className="faint small mono">{j.tipo} · {fmt.data(new Date(j.criado * 1000).toISOString())} · {j.n_eventos} {tr('eventos', 'events')}</span>
              {j.erro ? <span className="small" style={{ color: 'var(--danger-fg)' }}>{j.erro}</span> : null}
            </button>
          ))}
          {detalhe ? (
            <pre className="con" style={{ maxHeight: 220, whiteSpace: 'pre-wrap' }}>
              {detalhe.eventos.slice(-30).map((e) => JSON.stringify(e)).join('\n')}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
