import { useState } from 'react'
import type { VectorStoreInfo } from '../api/client'

interface Props {
  vectorStore: VectorStoreInfo | null
  pendingCount: number
  vectorizeRunning: boolean
  onVectorize: () => void
  onReset: () => void
  onClose: () => void
}

function fmt(iso: string | null) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('pt-BR', { dateStyle: 'short', timeStyle: 'short' })
}

function fmtSize(chunks: number) {
  return chunks === 1 ? '1 chunk' : `${chunks} chunks`
}

export default function VectorStoreModal({ vectorStore, pendingCount, vectorizeRunning, onVectorize, onReset, onClose }: Props) {
  const [confirmReset, setConfirmReset] = useState(false)

  const stats = [
    { label: 'Registros totais', value: String(vectorStore?.total_records ?? 0) },
    { label: 'Documentos únicos', value: String(vectorStore?.unique_documents ?? 0) },
    { label: 'Atualizado em', value: fmt(vectorStore?.last_updated ?? null) },
    { label: 'Modelo', value: vectorStore?.embedding_model ?? '—' },
  ]

  const articles = vectorStore?.articles ?? []

  return (
    <div onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(20,25,40,.32)', zIndex: 50,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32,
        animation: 'vfade .15s ease',
      }}>
      <div onClick={e => e.stopPropagation()}
        style={{
          width: 680, maxWidth: '100%', maxHeight: '88vh', background: 'var(--surface)',
          borderRadius: 16, boxShadow: '0 24px 60px rgba(20,25,40,.4)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>

        {/* Header */}
        <div style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px', borderBottom: '1px solid var(--border)',
        }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>Vector Store</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Índice semântico dos artigos vetorizados</div>
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

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 24px', background: 'var(--surface-2)' }}>

          {/* Stats grid */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 10, marginBottom: 20 }}>
            {stats.map(s => (
              <div key={s.label} style={{
                background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10,
                padding: '12px 14px',
              }}>
                <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 5, fontWeight: 500 }}>{s.label}</div>
                <div style={{
                  fontSize: 13, fontWeight: 700, color: 'var(--text)',
                  fontFamily: s.label === 'Modelo' ? 'IBM Plex Mono, monospace' : undefined,
                  wordBreak: 'break-all', lineHeight: 1.3,
                }}>{s.value}</div>
              </div>
            ))}
          </div>

          {/* Pending notice */}
          {pendingCount > 0 && (
            <div style={{
              display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px',
              marginBottom: 16, borderRadius: 9, background: '#fffbeb', border: '1px solid #fde68a',
            }}>
              <svg width="15" height="15" viewBox="0 0 16 16" fill="none" style={{ flexShrink: 0 }}>
                <path d="M8 1.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM8 5v3.5M8 10.5v.5" stroke="#b45309" strokeWidth="1.4" strokeLinecap="round"/>
              </svg>
              <span style={{ fontSize: 13, color: '#92400e' }}>
                <strong>{pendingCount}</strong> {pendingCount === 1 ? 'artigo pendente' : 'artigos pendentes'} — ainda não vetorizado{pendingCount !== 1 ? 's' : ''}
              </span>
            </div>
          )}

          {/* Articles table */}
          <div style={{ background: 'var(--surface)', border: '1px solid var(--border)', borderRadius: 10, overflow: 'hidden' }}>
            <div style={{
              display: 'grid', gridTemplateColumns: '1fr auto auto',
              padding: '9px 14px', borderBottom: '1px solid var(--border)',
              background: 'var(--surface-2)',
            }}>
              {['Arquivo', 'Vetorizado em', 'Chunks'].map(h => (
                <span key={h} style={{ fontSize: 11, fontWeight: 600, color: 'var(--text-faint)', textTransform: 'uppercase', letterSpacing: '.4px' }}>{h}</span>
              ))}
            </div>
            {articles.length === 0 ? (
              <div style={{ padding: '28px', textAlign: 'center', color: 'var(--text-faint)', fontSize: 13 }}>
                Nenhum artigo vetorizado ainda
              </div>
            ) : (
              <div style={{ maxHeight: 300, overflowY: 'auto' }}>
                {articles.map((a, i) => (
                  <div key={a.filename} style={{
                    display: 'grid', gridTemplateColumns: '1fr auto auto',
                    padding: '10px 14px', alignItems: 'center',
                    borderTop: i > 0 ? '1px solid var(--border)' : undefined,
                  }}>
                    <span style={{
                      fontSize: 12.5, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', paddingRight: 16,
                    }} title={a.filename}>{a.filename}</span>
                    <span style={{ fontSize: 11.5, color: 'var(--text-faint)', paddingRight: 20, whiteSpace: 'nowrap' }}>
                      {fmt(a.vectorized_at)}
                    </span>
                    <span style={{
                      fontSize: 11.5, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text-muted)',
                      textAlign: 'right', whiteSpace: 'nowrap',
                    }}>{fmtSize(a.chunk_count)}</span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
        <div style={{
          flexShrink: 0, padding: '14px 24px', borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 10, background: 'var(--surface)',
        }}>
          {confirmReset ? (
            <>
              <span style={{ fontSize: 13, color: '#92400e', flex: 1 }}>
                Tem certeza? Todos os vetores serão apagados e será necessário re-vetorizar.
              </span>
              <button onClick={() => setConfirmReset(false)} style={{
                padding: '8px 16px', border: '1px solid var(--border)', borderRadius: 8,
                background: 'none', cursor: 'pointer', fontSize: 13, color: 'var(--text)',
              }}>Cancelar</button>
              <button onClick={() => { setConfirmReset(false); onReset() }} style={{
                padding: '8px 16px', border: 'none', borderRadius: 8,
                background: '#ef4444', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: '#fff',
              }}>Limpar mesmo assim</button>
            </>
          ) : (
            <>
              <button
                onClick={() => { onVectorize(); onClose() }}
                disabled={vectorizeRunning || pendingCount === 0}
                style={{
                  padding: '9px 20px', border: 'none', borderRadius: 9, cursor: vectorizeRunning || pendingCount === 0 ? 'default' : 'pointer',
                  fontSize: 14, fontWeight: 600, background: vectorizeRunning || pendingCount === 0 ? 'var(--surface-3)' : '#1A9494',
                  color: vectorizeRunning || pendingCount === 0 ? 'var(--text-faint)' : '#fff',
                  opacity: vectorizeRunning || pendingCount === 0 ? 0.6 : 1,
                }}>
                {vectorizeRunning ? 'Vetorizando…' : pendingCount > 0 ? `Vetorizar (${pendingCount} pendentes)` : 'Tudo vetorizado'}
              </button>
              <div style={{ flex: 1 }} />
              <button
                onClick={() => setConfirmReset(true)}
                disabled={articles.length === 0}
                style={{
                  padding: '9px 16px', border: '1px solid #fca5a5', borderRadius: 9,
                  background: 'none', cursor: articles.length === 0 ? 'default' : 'pointer',
                  fontSize: 13, fontWeight: 500, color: articles.length === 0 ? 'var(--text-faint)' : '#dc2626',
                  opacity: articles.length === 0 ? 0.4 : 1,
                }}>
                Limpar vector store
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
