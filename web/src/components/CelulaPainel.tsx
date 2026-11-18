import { useApp } from '../app-context'
import type { Bruta, CelulaDetalhe } from '../api'
import { NivelPill, useFmt } from './ui'

export function RespostaBruta({ b }: { b: Bruta }) {
  const { tr } = useApp()
  if (b.status !== 'ok') return <span style={{ color: 'var(--danger-fg)' }}>{tr('falha', 'failed')}: {b.erro}</span>
  if (b.nao_reportado) return <span className="tag tag-g">{tr('não reportado', 'not reported')}</span>
  return (
    <span>
      <strong>{b.valor ?? '—'}</strong>{' '}
      {b.e !== null ? <span className={`tag ${b.e >= 1 ? 'tag-s' : b.e > 0 ? 'tag-w' : 'tag-d'}`} title={b.e_detalhe}>e={b.e}</span> : null}
      {b.pagina ? <span className="faint small"> p.{b.pagina}</span> : null}
    </span>
  )
}

/** Everything about one cell: three extractors, quote, checks, verifier, history. */
export function CelulaPainel({ c }: { c: CelulaDetalhe }) {
  const { tr } = useApp()
  const fmt = useFmt()
  const valor = c.nao_reportado ? tr('não reportado', 'not reported') : c.valor_final ?? tr('sem valor (empate)', 'no value (tie)')
  return (
    <>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
        <NivelPill nivel={c.nivel} />
        <strong style={{ fontSize: 16 }}>{valor}</strong>
        {c.origem === 'adjudicacao' ? <span className="tag">{tr('adjudicada', 'adjudicated')}</span> : null}
        {c.enviada_manual ? <span className="tag tag-w">{tr('enviada à adjudicação', 'sent to adjudication')}</span> : null}
      </div>
      {c.trecho ? (
        <blockquote className="quote">“…{c.trecho}…” <span className="faint small">p.{c.pagina ?? '?'}{c.unidades.length ? ` · ${c.unidades.join(' ')}` : ''}</span></blockquote>
      ) : null}
      <div className="card" style={{ padding: '12px 14px' }}>
        <div className="lbl">{tr('Extratores', 'Extractors')}</div>
        {c.brutas.map((b) => (
          <div key={b.rotulo} style={{ display: 'grid', gridTemplateColumns: '36px minmax(0,1fr)', gap: 8, padding: '4px 0', borderTop: '1px solid var(--border)' }}>
            <span className="tag">{b.rotulo}</span>
            <div style={{ minWidth: 0 }}>
              <RespostaBruta b={b} />
              {b.status === 'ok' && b.trecho && b.trecho !== c.trecho ? <div className="small muted" style={{ overflowWrap: 'anywhere' }}>“{b.trecho}”</div> : null}
              {b.e_detalhe ? <div className="small faint">{b.e_detalhe}</div> : null}
              {b.regras_ok === 0 && b.regras_detalhe ? <div className="small" style={{ color: 'var(--danger-fg)' }}>{b.regras_detalhe}</div> : null}
            </div>
          </div>
        ))}
      </div>
      <dl className="kvr">
        <dt>{tr('Concordância a', 'Agreement a')}</dt><dd className="mono">{fmt.num(c.a)}</dd>
        <dt>{tr('Evidência e', 'Evidence e')}</dt><dd className="mono">{c.e ?? '—'}</dd>
        <dt>{tr('Verificador v', 'Verifier v')}</dt><dd className="mono">{c.v ?? tr('declarado 1 (sem verificador)', 'assumed 1 (no verifier)')}</dd>
        <dt>{tr('Escore s', 'Score s')}</dt><dd className="mono">{c.escore === null ? tr('— (empate)', '— (tie)') : fmt.num(c.escore)}</dd>
        <dt>{tr('Regras', 'Rules')}</dt><dd>{c.regras_ok === 0 ? <span style={{ color: 'var(--danger-fg)' }}>{tr('violadas', 'violated')}</span> : 'OK'}</dd>
        {c.v_justificativa?.veredito ? (<><dt>{tr('Veredito do verificador', 'Verifier verdict')}</dt>
          <dd>{c.v_justificativa.veredito} · <span className="muted">{c.v_justificativa.justificativa}</span></dd></>) : null}
        {c.v_justificativa?.nota ? (<><dt>{tr('Nota', 'Note')}</dt><dd className="muted">{c.v_justificativa.nota}</dd></>) : null}
      </dl>
      {c.motivos.length ? (
        <div className="info" style={{ flexDirection: 'column', gap: 2 }}>
          {c.motivos.map((m, i) => <div key={i}>· {m}</div>)}
        </div>
      ) : null}
      {c.adjudicacoes.length ? (
        <div className="card" style={{ padding: '12px 14px' }}>
          <div className="lbl">{tr('Decisões', 'Decisions')}</div>
          {c.adjudicacoes.map((a) => (
            <div key={a.id} className="small" style={{ borderTop: '1px solid var(--border)', padding: '4px 0' }}>
              {fmt.data(a.decidido_em)} · {a.motivo} · {a.valor_anterior ?? '∅'} → <strong>{a.nao_reportado ? tr('não reportado', 'not reported') : a.valor_decidido}</strong>
              {a.justificativa ? <span className="muted"> · {a.justificativa}</span> : null}
            </div>
          ))}
        </div>
      ) : null}
    </>
  )
}
