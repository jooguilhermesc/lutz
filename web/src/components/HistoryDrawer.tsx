import type { ReportMeta } from '../api/client'

interface Props {
  reports: ReportMeta[]
  projectName: string
  onClose: () => void
  onOpenRelatorios: () => void
}


export default function HistoryDrawer({ reports, projectName, onClose, onOpenRelatorios }: Props) {
  return (
    <>
      <div onClick={onClose}
        style={{ position: 'fixed', inset: 0, background: 'rgba(20,25,40,.28)', zIndex: 40, animation: 'vfade .15s ease' }} />
      <div style={{
        position: 'fixed', top: 0, right: 0, bottom: 0, width: 420, background: '#fff',
        zIndex: 41, boxShadow: '-14px 0 40px rgba(20,25,40,.14)',
        display: 'flex', flexDirection: 'column', animation: 'vfade .2s ease',
      }}>
        <div style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '18px 20px', borderBottom: '1px solid #e4e6eb',
        }}>
          <div>
            <div style={{ fontSize: 15, fontWeight: 700 }}>Histórico de análises</div>
            <div style={{ fontSize: 12, color: '#8a92a0' }}>Log de execuções · {projectName}</div>
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <button onClick={onOpenRelatorios} style={{
              fontSize: 12, fontWeight: 500, padding: '5px 10px', border: '1px solid #e4e6eb',
              borderRadius: 7, background: 'none', cursor: 'pointer', color: '#1A9494',
            }}>
              Ver todos →
            </button>
            <button onClick={onClose} style={{
              width: 30, height: 30, border: '1px solid #e4e6eb', borderRadius: 7, background: 'none',
              cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#5b6472',
            }}>
              <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
                <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
              </svg>
            </button>
          </div>
        </div>

        <div style={{ flex: 1, overflowY: 'auto', padding: '14px 20px' }}>
          {reports.length === 0 ? (
            <p style={{ color: '#8a92a0', fontSize: 13, textAlign: 'center', marginTop: 40 }}>
              Nenhuma análise realizada ainda.
            </p>
          ) : reports.map(r => {
            const date = r.started_at ? new Date(r.started_at).toLocaleString('pt-BR') : '—'
            return (
              <div key={r.name} style={{
                border: '1px solid #e4e6eb', borderRadius: 10, padding: '13px 14px', marginBottom: 10,
              }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 7 }}>
                  <span style={{ fontSize: 12, color: '#8a92a0', fontFamily: 'IBM Plex Mono, monospace' }}>{date}</span>
                  <span style={{
                    fontSize: 11, fontWeight: 600, padding: '3px 9px', borderRadius: 11,
                    background: '#e8f8f8', color: '#1A9494',
                  }}>
                    {r.articles} artigos
                  </span>
                </div>
                <div style={{ fontSize: 13, fontWeight: 500, color: '#1a1d23', marginBottom: 8, fontFamily: 'IBM Plex Mono, monospace', wordBreak: 'break-all' }}>
                  {r.name}
                </div>
                <div style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  fontSize: 11.5, color: '#8a92a0', fontFamily: 'IBM Plex Mono, monospace',
                }}>
                  <span>{r.model || '—'}</span>
                  <span>·</span>
                  <span>{r.tokens?.toLocaleString() ?? 0} tokens</span>
                  <span>·</span>
                  <span>{r.elapsed?.toFixed(1) ?? '?'}s</span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </>
  )
}
