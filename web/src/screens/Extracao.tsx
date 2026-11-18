import { useEffect, useState } from 'react'
import { Pause, Play, Plus, RefreshCw } from 'lucide-react'
import { api, type Checagens, type CodebookPayload, type Estimativa, type ExecucaoDetalhe, type LogItem, type MetricasExecucao, type Resumo } from '../api'
import { useApp } from '../app-context'
import { ConfirmarExecucao } from '../components/Estimativa'
import { BarraNiveis, Cabecalho, Carregando, Modal, NivelPill, Nota, StatusPill, Vazio, useCarregar, useFmt, useIntervalo } from '../components/ui'

const DIVERSIDADE: Record<string, [string, string, string]> = {
  fornecedores_diferentes: ['tag-s', 'Diversidade forte', 'Strong diversity'],
  modelos_diferentes: ['tag', 'Modelos diferentes', 'Different models'],
  instrucoes_reescritas: ['tag-w', 'Só instruções reescritas', 'Rewritten instructions only'],
  nenhuma: ['tag-d', 'Sem diversidade', 'No diversity'],
}

export function Extracao() {
  const { tr, projeto, recarregarProjeto } = useApp()
  const fmt = useFmt()
  const lista = useCarregar(() => api.get<Resumo[]>('/execucoes'), [])
  const [selId, setSelId] = useState<number | null>(null)
  const [nova, setNova] = useState(false)
  const [confirmar, setConfirmar] = useState<Estimativa | null>(null)
  const execs = (lista.dados ?? []).filter((r) => r.tipo !== 'teste')

  useEffect(() => {
    if (selId === null && execs.length) setSelId(execs[0].id)
  }, [execs, selId])

  const det = useCarregar(() => (selId ? api.get<ExecucaoDetalhe>(`/execucoes/${selId}`) : Promise.resolve(null)), [selId])
  const rodando = det.dados?.status === 'rodando'
  useIntervalo(() => { det.recarregar(true); lista.recarregar(true); recarregarProjeto() }, 2500, rodando)

  return (
    <>
      <Cabecalho titulo={tr('Extração', 'Extraction')}
        sub={tr('Modo Autônomo: três extratores independentes por célula, evidência conferida no texto da página, verificador e regras do codebook.',
          'Autonomous mode: three independent extractors per cell, evidence checked in the page text, verifier and codebook rules.')}>
        <select className="sel-in" style={{ width: 280 }} value={selId ?? ''} onChange={(e) => setSelId(Number(e.target.value) || null)}
          aria-label={tr('Execuções anteriores', 'Previous runs')}>
          {execs.length === 0 ? <option value="">{tr('Nenhuma execução', 'No runs')}</option> : null}
          {execs.map((r) => <option key={r.id} value={r.id}>{tr('Execução', 'Run')} {r.id} · {r.tipo}{r.conjunto ? ` (${r.conjunto})` : ''} · {r.status}</option>)}
        </select>
        <button className="btn btn-p" onClick={() => setNova(true)} disabled={!projeto?.codebook_congelado}><Plus size={15} />{tr('Nova execução', 'New run')}</button>
      </Cabecalho>

      {!projeto?.codebook_congelado ? <Nota>{tr('Congele uma versão do codebook antes de extrair.', 'Freeze a codebook version before extracting.')}</Nota> : null}
      {lista.carregando && !lista.dados ? <Carregando /> : execs.length === 0 ? (
        <section className="card"><Vazio titulo={tr('Nenhuma execução ainda', 'No runs yet')}>{tr('Comece com "Nova execução". O custo é estimado e confirmado antes de rodar.', 'Start with "New run". The cost is estimated and confirmed before running.')}</Vazio></section>
      ) : det.erro ? <Nota tipo="erro">{det.erro}</Nota> : det.dados ? (
        <Detalhe d={det.dados} onConfirmar={setConfirmar} onAtualizar={() => { det.recarregar(true); lista.recarregar(true) }} />
      ) : <Carregando />}

      {execs.length ? (
        <section className="card">
          <h2 className="h2">{tr('Execuções anteriores', 'Previous runs')}</h2>
          <div className="tablewrap">
            <table className="t">
              <thead><tr><th>ID</th><th>{tr('Tipo', 'Type')}</th><th>Status</th><th className="num">{tr('Células', 'Cells')}</th><th>{tr('Níveis', 'Levels')}</th><th className="num">US$</th><th>{tr('Criada', 'Created')}</th></tr></thead>
              <tbody>
                {execs.map((r) => (
                  <tr key={r.id} className={`click${r.id === selId ? ' sel' : ''}`} onClick={() => setSelId(r.id)}>
                    <td className="mono">{r.id}</td><td>{r.tipo}{r.conjunto ? ` (${r.conjunto})` : ''}</td><td><StatusPill status={r.status} /></td>
                    <td className="num">{r.celulas_prontas}/{r.celulas}</td>
                    <td><BarraNiveis a={r.niveis.alta ?? 0} m={r.niveis.media ?? 0} b={r.niveis.baixa ?? 0} /></td>
                    <td className="num">{fmt.num(r.custo_usd, 4)}</td><td className="small">{fmt.data(r.criada_em)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}

      {nova ? <NovaExecucao onFechar={() => setNova(false)} onEstimativa={(e) => { setNova(false); setConfirmar(e); lista.recarregar(true); setSelId(e.execucao_id) }} /> : null}
      {confirmar ? <ConfirmarExecucao est={confirmar} onFechar={() => { setConfirmar(null); det.recarregar(true); lista.recarregar(true) }}
        onIniciada={(id) => { setConfirmar(null); setSelId(id); det.recarregar(true); lista.recarregar(true) }} /> : null}
    </>
  )
}

function NovaExecucao({ onFechar, onEstimativa }: { onFechar: () => void; onEstimativa: (e: Estimativa) => void }) {
  const { tr, projeto } = useApp()
  const cb = useCarregar(() => (projeto?.codebook_congelado ? api.get<CodebookPayload>(`/codebooks/${projeto.codebook_congelado.versao}`) : Promise.resolve(null)), [projeto?.codebook_congelado?.versao])
  const [campos, setCampos] = useState<Set<string>>(new Set())
  const [artigos, setArtigos] = useState('')
  const [erro, setErro] = useState('')
  const [ocupado, setOcupado] = useState(false)
  return (
    <Modal titulo={tr('Nova execução autônoma', 'New autonomous run')}
      sub={projeto?.codebook_congelado ? `codebook v${projeto.codebook_congelado.versao} · ${projeto.codebook_congelado.hash}` : ''}
      onFechar={onFechar}
      rodape={<button className="btn btn-p" disabled={ocupado} onClick={async () => {
        setOcupado(true)
        setErro('')
        try {
          const body: Record<string, unknown> = {}
          if (campos.size) body.campos = [...campos]
          const a = artigos.split(',').map((x) => x.trim()).filter(Boolean)
          if (a.length) body.artigos = a
          onEstimativa(await api.post<Estimativa>('/execucoes/estimativa', body))
        } catch (e) {
          setErro((e as Error).message)
        } finally {
          setOcupado(false)
        }
      }}>{ocupado ? tr('Estimando…', 'Estimating…') : tr('Planejar e estimar custo', 'Plan and estimate cost')}</button>}>
      <div className="modal-b">
        {erro ? <Nota tipo="erro">{erro}</Nota> : null}
        <p className="sub">{tr('Padrão: todos os campos do codebook congelado em todos os artigos prontos. Restrinja só se precisar.', 'Default: every field of the frozen codebook on every ready article. Restrict only if you need to.')}</p>
        <div className="field"><span>{tr('Campos (nenhum marcado = todos)', 'Fields (none checked = all)')}</span>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            {(cb.dados?.campos ?? []).map((c) => (
              <button key={c.nome} className={`chipb${campos.has(c.nome) ? ' on' : ''}`} onClick={() => setCampos((s) => {
                const n = new Set(s)
                if (n.has(c.nome)) n.delete(c.nome)
                else n.add(c.nome)
                return n
              })}>{c.nome}</button>
            ))}
          </div>
        </div>
        <label className="field"><span>{tr('Artigos (chaves separadas por vírgula; vazio = todos)', 'Articles (keys separated by commas; empty = all)')}</span>
          <input className="in mono" value={artigos} onChange={(e) => setArtigos(e.target.value)} /></label>
      </div>
    </Modal>
  )
}

function Detalhe({ d, onConfirmar, onAtualizar }: { d: ExecucaoDetalhe; onConfirmar: (e: Estimativa) => void; onAtualizar: () => void }) {
  const { tr, avisar } = useApp()
  const fmt = useFmt()
  const rodando = d.status === 'rodando'
  const chec = useCarregar(() => api.get<Checagens>(`/execucoes/${d.id}/checagens`), [d.id])
  const met = useCarregar(() => api.get<MetricasExecucao>(`/execucoes/${d.id}/metricas`), [d.id, d.status])
  const log = useCarregar(() => api.get<LogItem[]>(`/execucoes/${d.id}/log?limite=40`), [d.id])
  useIntervalo(() => { chec.recarregar(true); log.recarregar(true) }, 2500, rodando)
  const pct = d.celulas ? d.celulas_prontas / d.celulas : 0
  const div = DIVERSIDADE[d.estrategia_diversidade] ?? ['tag-g', d.estrategia_diversidade, d.estrategia_diversidade]
  const extratores = d.extratores.filter((e) => e.papel === 'extrator')
  const outros = d.extratores.filter((e) => e.papel !== 'extrator')

  async function iniciar() {
    try {
      onConfirmar(await api.get<Estimativa>(`/execucoes/${d.id}/estimativa`))
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }
  async function pausar() {
    try {
      await api.post(`/execucoes/${d.id}/pausar`)
      avisar(tr('Pausa solicitada; as células em andamento terminam primeiro.', 'Pause requested; cells in progress finish first.'))
      onAtualizar()
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }
  async function recalcular() {
    if (!window.confirm(tr('Recalcular evidência, regras, níveis e métricas com os limiares atuais do lutz.yaml? Não chama modelos.', 'Recompute evidence, rules, levels and metrics with the current lutz.yaml thresholds? No model calls.'))) return
    try {
      await api.post(`/execucoes/${d.id}/recalcular`, { limiares_atuais: true })
      avisar(tr('Recálculo iniciado.', 'Recompute started.'))
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }

  return (
    <>
      <section className="card">
        <div className="card-h">
          <h2 className="h2">{tr('Execução', 'Run')} {d.id} · {d.tipo}{d.conjunto ? ` (${d.conjunto})` : ''}</h2>
          <StatusPill status={d.status} />
          <span className="mono small faint">codebook v{d.codebook?.versao} · {d.codebook?.hash}</span>
          <span style={{ flex: 1 }} />
          {rodando ? <button className="btn btn-s" onClick={pausar}><Pause size={14} />{tr('Pausar', 'Pause')}</button> : null}
          {d.status === 'planejada' || d.status === 'pausada' || d.status === 'falhou' ? (
            <button className="btn btn-s btn-p" onClick={iniciar}><Play size={14} />{d.status === 'planejada' ? tr('Iniciar', 'Start') : tr('Retomar', 'Resume')}</button>
          ) : null}
          {d.status === 'concluida' ? <button className="btn btn-s" onClick={recalcular}><RefreshCw size={14} />{tr('Recalcular', 'Recompute')}</button> : null}
        </div>
        {d.motivo ? <Nota>{d.motivo}</Nota> : null}
        <div className="kpis">
          <div className="kpi"><div className="lbl">{tr('Artigos', 'Articles')}</div><div className="kv">{d.artigos_prontos} / {d.artigos}</div></div>
          <div className="kpi"><div className="lbl">{tr('Células prontas', 'Cells ready')}</div><div className="kv">{d.celulas_prontas} / {d.celulas}</div>
            <div className="bar" style={{ marginTop: 6 }}><span style={{ width: `${pct * 100}%`, background: 'var(--lutz-500)' }} /></div></div>
          <div className="kpi"><div className="lbl">{tr('Custo', 'Cost')}</div><div className="kv">{fmt.usd(d.custo_usd)}</div>
            <div className="kv-sub">{d.chamadas} {tr('chamadas', 'calls')} · {d.chamadas_cache} cache{d.orcamento_usd != null ? ` · ${tr('orçamento', 'budget')} ${fmt.usd(d.orcamento_usd)}` : ''}</div></div>
          <div className="kpi"><div className="lbl">{tr('Retomada', 'Resume')}</div><div className="small" style={{ marginTop: 6 }}>{tr('Retomável por célula: uma falha de API não perde trabalho.', 'Resumable per cell: an API failure does not lose work.')}</div></div>
        </div>
      </section>

      <section className="card">
        <div className="card-h">
          <h2 className="h2">{tr('Extratores', 'Extractors')}</h2>
          <span className={`tag ${div[0]}`}>{tr(div[1], div[2])}</span>
        </div>
        <p className="sub">{tr('Nenhum extrator vê a resposta dos outros. Modelos de fornecedores diferentes descorrelacionam os erros; com um único modelo isso vira limitação no relatório.',
          'No extractor sees the others\' answers. Models from different vendors decorrelate errors; with a single model this becomes a limitation in the report.')}</p>
        <div className="grid2">
          {[...extratores, ...outros].map((e) => (
            <div key={e.rotulo} className="step">
              <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}><span className="tag">{e.rotulo}</span><strong>{e.provedor}</strong></span>
              <span className="mono small">{e.modelo}{e.temperatura != null ? ` · temp ${e.temperatura}` : ''}</span>
              <span className="faint small">{tr('observado', 'observed')}: <span className="mono">{e.modelo_observado || '—'}</span></span>
              {e.papel !== 'extrator' ? <span className="faint small">{e.papel === 'verificador' ? tr('verificador · sem o artigo', 'verifier · without the article') : e.papel}</span> : null}
            </div>
          ))}
          {!outros.some((e) => e.papel === 'verificador') ? <div className="step"><span className="tag tag-w">V</span><span className="small">{tr('Sem verificador: v = 1 declarado.', 'No verifier: v = 1 assumed.')}</span></div> : null}
        </div>
      </section>

      {chec.dados && chec.dados.celulas ? (
        <section className="card">
          <h2 className="h2">{tr('Checagens das células prontas', 'Checks of the ready cells')} ({chec.dados.celulas})</h2>
          <div className="kpis">
            <div className="kpi"><div className="lbl">{tr('Concordância (a)', 'Agreement (a)')}</div>
              <div className="small" style={{ marginTop: 6 }}>{chec.dados.concordancia.unanimes} {tr('unânimes', 'unanimous')} · {chec.dados.concordancia.dois_de_tres} {tr('com 2 de 3', '2 of 3')} · {chec.dados.concordancia.empates} {tr('empates 1-1-1', '1-1-1 ties')}</div></div>
            <div className="kpi"><div className="lbl">{tr('Evidência (e)', 'Evidence (e)')}</div><div className="kv">{fmt.pct(chec.dados.evidencia.exata)}</div>
              <div className="kv-sub">{tr('exata', 'exact')} · {fmt.pct(chec.dados.evidencia.parcial)} {tr('parcial', 'partial')} · {fmt.pct(chec.dados.evidencia.nao_encontrada)} {tr('não encontrada', 'not found')}</div></div>
            <div className="kpi"><div className="lbl">{tr('Verificador (v)', 'Verifier (v)')}</div><div className="kv">{chec.dados.verificador.n ? fmt.pct(chec.dados.verificador.sustenta) : '—'}</div>
              <div className="kv-sub">{tr('sustenta', 'supports')} · {fmt.pct(chec.dados.verificador.parcial)} {tr('em parte', 'partly')} · {fmt.pct(chec.dados.verificador.nao_sustenta)} {tr('não sustenta', 'does not')}</div></div>
            <div className="kpi"><div className="lbl">{tr('Regras', 'Rules')}</div><div className="kv">{chec.dados.regras_barradas}</div><div className="kv-sub">{tr('células barradas', 'cells blocked')}</div></div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="lbl">{tr('Escore s = a × e × v', 'Score s = a × e × v')}</span>
            <NivelPill nivel="alta" /> {chec.dados.niveis.alta}
            <NivelPill nivel="media" /> {chec.dados.niveis.media}
            <NivelPill nivel="baixa" /> {chec.dados.niveis.baixa}
          </div>
        </section>
      ) : null}

      <section className="card">
        <div className="card-h">
          <h2 className="h2">{tr('Confiabilidade por campo', 'Reliability by field')}</h2>
          <span className="small muted">{tr('α de Krippendorff entre E1, E2 e E3 · IC95% por bootstrap', "Krippendorff's α among E1, E2 and E3 · 95% bootstrap CI")}</span>
        </div>
        {met.dados && met.dados.campos.some((c) => Object.keys(c.metricas).length) ? (
          <div className="tablewrap">
            <table className="t">
              <thead><tr><th>{tr('Campo', 'Field')}</th><th>{tr('Tipo', 'Type')}</th><th className="num">α</th><th className="num">IC95%</th><th className="num">{tr('Unânimes', 'Unanimous')}</th>
                <th>{tr('Níveis', 'Levels')}</th><th className="num">{tr('Evidência exata', 'Exact evidence')}</th><th className="num">{tr('Não reportado', 'Not reported')}</th></tr></thead>
              <tbody>
                {met.dados.campos.map((c) => {
                  const m = c.metricas
                  const alfa = m.alfa
                  const nr = m.pct_nao_reportado
                  return (
                    <tr key={c.chave}>
                      <td><strong>{c.chave}</strong></td><td className="small">{c.tipo}</td>
                      <td className="num">{c.tipo === 'texto' ? '—' : fmt.num(alfa?.valor)}
                        {alfa?.valor != null && alfa.valor < 0.667 ? <div className="small" style={{ color: 'var(--danger-fg)' }}>{tr('abaixo de 0,667', 'below 0.667')}</div> : null}</td>
                      <td className="num">{c.tipo === 'texto' ? '—' : fmt.ic(alfa?.ic_inf, alfa?.ic_sup)}</td>
                      <td className="num">{fmt.pct(m.unanimes?.valor)}</td>
                      <td className="small">A {fmt.pct(m.pct_alta?.valor)} · M {fmt.pct(m.pct_media?.valor)} · B {fmt.pct(m.pct_baixa?.valor)}</td>
                      <td className="num">{fmt.pct(m.pct_evidencia_exata?.valor)}</td>
                      <td className="num">{fmt.pct(nr?.valor)}{nr?.nota ? <div className="small" style={{ color: 'var(--warning-fg)' }}>{tr('possível falha de leitura', 'possible reading failure')}</div> : null}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : <div className="faint small">{tr('As métricas aparecem quando a execução termina.', 'Metrics appear when the run completes.')}</div>}
        <Nota tipo="info">{tr('Isto mede consistência, não acerto: três extratores podem errar do mesmo jeito. O acerto vem do piloto ou da auditoria. Em texto livre, a % de células unânimes substitui o α.',
          'This measures consistency, not accuracy: three extractors can make the same mistake. Accuracy comes from the pilot or the audit. For free text, % unanimous cells replaces α.')}</Nota>
      </section>

      <section className="card">
        <div className="card-h"><h2 className="h2">Log</h2><span className="small muted">{tr('célula a célula; vira o anexo C do relatório', 'cell by cell; becomes annex C of the report')}</span></div>
        {log.dados?.length ? (
          <div className="log">
            {log.dados.map((l) => (
              <div key={l.id} style={{ color: l.nivel === 'baixa' ? 'var(--danger-fg)' : l.nivel === 'alta' ? 'var(--success-fg)' : undefined }}>
                {l.nivel === 'alta' ? '✓' : l.nivel === 'baixa' ? '✗' : l.nivel ? '•' : '→'} {l.chave} · {l.campo_chave} · {l.nao_reportado ? tr('não reportado', 'not reported') : (l.valor_final ?? tr('sem valor', 'no value'))}
                {l.pagina ? ` · p.${l.pagina}` : ''}{l.a != null ? ` · a=${fmt.num(l.a)} e=${l.e ?? '—'} v=${l.v ?? '—'}` : ''} · {l.nivel ?? l.estado}
                {l.motivos.length ? ` · ${l.motivos[0]}` : ''}
              </div>
            ))}
          </div>
        ) : <div className="faint small">{tr('Sem células processadas ainda.', 'No processed cells yet.')}</div>}
      </section>
    </>
  )
}
