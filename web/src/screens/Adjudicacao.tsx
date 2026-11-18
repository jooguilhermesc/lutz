import { useEffect, useRef, useState } from 'react'
import { Check, Download, FileSearch, SkipForward, Upload } from 'lucide-react'
import { api, url, type AuditoriaResposta, type CelulaDetalhe, type EstatAdj, type ItemFila, type Pagina } from '../api'
import { useApp } from '../app-context'
import { RespostaBruta } from '../components/CelulaPainel'
import { ExecucaoSelect } from '../components/ExecucaoSelect'
import { PageViewer } from '../components/PageViewer'
import { Cabecalho, Carregando, Destacar, Kpi, NivelPill, Nota, Vazio, baixar, useCarregar, useFmt } from '../components/ui'

export function Adjudicacao() {
  const { tr, avisar, recarregarProjeto } = useApp()
  const fmt = useFmt()
  const [eid, setEid] = useState<number | null>(null)
  const fila = useCarregar(() => (eid ? api.get<ItemFila[]>(`/execucoes/${eid}/fila`) : Promise.resolve(null)), [eid])
  const est = useCarregar(() => (eid ? api.get<EstatAdj>(`/execucoes/${eid}/adjudicacao/estatisticas`) : Promise.resolve(null)), [eid])
  const [selId, setSelId] = useState<number | null>(null)
  const [pulados, setPulados] = useState<Set<number>>(new Set())
  const arquivo = useRef<HTMLInputElement>(null)

  const itens = fila.dados ?? []
  useEffect(() => {
    if (fila.dados && (selId === null || !fila.dados.some((i) => i.id === selId))) {
      const prox = fila.dados.find((i) => !pulados.has(i.id)) ?? fila.dados[0]
      setSelId(prox ? prox.id : null)
    }
  }, [fila.dados, selId, pulados])

  const proximo = (atual: number) => {
    const resto = itens.filter((i) => i.id !== atual && !pulados.has(i.id))
    setSelId(resto[0]?.id ?? null)
  }

  async function importar(f: File) {
    const fd = new FormData()
    fd.append('arquivo', f)
    try {
      const r = await api.form<{ aplicadas: number; ignoradas: number; erros: { linha: number; erro: string }[] }>('/adjudicacao/importar', fd)
      avisar(tr(`${r.aplicadas} decisão(ões) aplicada(s); ${r.erros.length} erro(s).`, `${r.aplicadas} decision(s) applied; ${r.erros.length} error(s).`), r.erros.length > 0)
      r.erros.slice(0, 5).forEach((e) => avisar(`${tr('linha', 'line')} ${e.linha}: ${e.erro}`, true))
      fila.recarregar(true)
      est.recarregar(true)
      recarregarProjeto()
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }

  const t = est.dados?.total
  const nBaixa = itens.filter((i) => i.nivel === 'baixa').length
  const nMedia = itens.filter((i) => i.nivel === 'media').length
  const aud = est.dados?.auditoria

  return (
    <>
      <Cabecalho titulo={tr('Adjudicação', 'Adjudication')}
        sub={tr('A decisão final sobre cada célula duvidosa é sua. A fila vem ordenada pelo escore, da pior para a melhor.',
          'The final decision on every doubtful cell is yours. The queue is ordered by score, worst first.')}>
        <ExecucaoSelect valor={eid} onValor={setEid} />
        <button className="btn" disabled={!eid} onClick={() => baixar(url(`/execucoes/${eid}/adjudicacao.csv`))}><Download size={15} />{tr('Exportar CSV', 'Export CSV')}</button>
        <button className="btn" disabled={!eid} onClick={() => arquivo.current?.click()}><Upload size={15} />{tr('Importar CSV', 'Import CSV')}</button>
        <input ref={arquivo} type="file" accept=".csv,text/csv" hidden aria-label={tr('CSV de decisões', 'Decisions CSV')}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) importar(f); e.target.value = '' }} />
      </Cabecalho>

      {!eid ? (
        <section className="card"><Vazio titulo={tr('Nenhuma execução concluída', 'No completed run')} /></section>
      ) : (
        <>
          <section className="kpis">
            <Kpi rotulo={tr('Na fila', 'In queue')} valor={itens.length} sub={`${nBaixa} ${tr('Baixa', 'Low')} · ${nMedia} ${tr('Média de campos fracos', 'Medium of weak fields')}`} />
            <Kpi rotulo={tr('Decididas', 'Decided')} valor={t?.decididas ?? '—'} />
            <Kpi rotulo={tr('Valor alterado', 'Value changed')} valor={t?.alteradas ?? '—'} sub={t?.decididas ? `${fmt.pct((t.alteradas ?? 0) / t.decididas)} ${tr('das decididas', 'of decided')}` : undefined} />
            <Kpi rotulo={tr('Auditoria de Alta', 'High audit')} valor={aud ? `${aud.conferidas}/${aud.n_amostra}` : '—'}
              sub={aud && aud.conferidas ? `${fmt.pct(aud.taxa, 1)} ${tr('de acerto', 'accuracy')}` : tr('não iniciada', 'not started')} />
          </section>

          <section className="row">
            <div className="card" style={{ flex: '1 1 300px', maxWidth: 420 }}>
              <div className="card-h"><h2 className="h2">{tr('Fila', 'Queue')}</h2><span className="small muted">{tr('ordem: escore ↑', 'order: score ↑')}</span></div>
              {fila.carregando && !fila.dados ? <Carregando /> : fila.erro ? <Nota tipo="erro">{fila.erro}</Nota> : itens.length === 0 ? (
                <Vazio titulo={tr('Fila vazia', 'Queue empty')}>{tr('Nenhuma célula aguarda decisão.', 'No cell awaits a decision.')}</Vazio>
              ) : (
                <div className="scroll" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {itens.map((i) => (
                    <button key={i.id} className={`fcard${i.id === selId ? ' on' : ''}`} onClick={() => setSelId(i.id)}
                      style={{ textAlign: 'left', opacity: pulados.has(i.id) ? 0.6 : 1 }}>
                      <span style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                        <NivelPill nivel={i.nivel} /><span className="mono small">s {i.escore === null ? '—' : fmt.num(i.escore)}</span>
                        {i.motivo_fila !== 'baixa' ? <span className="tag tag-g">{i.motivo_fila}</span> : null}
                      </span>
                      <strong className="small">{i.campo_chave}</strong>
                      <span className="small muted">{i.chave} · {i.motivos[0] ?? ''}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <div style={{ flex: '2 1 480px', display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
              {selId ? <Item key={selId} id={selId} onDecidido={() => {
                fila.recarregar(true)
                est.recarregar(true)
                recarregarProjeto()
                proximo(selId)
              }} onPular={() => { setPulados((s) => new Set(s).add(selId)); proximo(selId) }} /> : (
                <section className="card"><Vazio titulo={tr('Selecione uma célula da fila', 'Select a cell from the queue')} /></section>
              )}
              {eid ? <Auditoria eid={eid} onMudou={() => { est.recarregar(true); fila.recarregar(true) }} /> : null}
            </div>
          </section>
        </>
      )}
    </>
  )
}

function Item({ id, onDecidido, onPular }: { id: number; onDecidido: () => void; onPular: () => void }) {
  const { tr, avisar } = useApp()
  const fmt = useFmt()
  const c = useCarregar(() => api.get<CelulaDetalhe>(`/celulas/${id}`), [id])
  const pag = useCarregar(() => (c.dados?.pagina ? api.get<Pagina>(`/artigos/${encodeURIComponent(c.dados.chave)}/paginas/${c.dados.pagina}`) : Promise.resolve(null)), [c.dados?.chave, c.dados?.pagina])
  const [valor, setValor] = useState('')
  const [justificativa, setJustificativa] = useState('')
  const [ocupado, setOcupado] = useState(false)
  const [pdf, setPdf] = useState(false)

  async function decidir(v: string | null, nr: boolean) {
    setOcupado(true)
    try {
      await api.post('/adjudicacoes', { celula_id: id, valor: v, nao_reportado: nr, justificativa })
      avisar(tr('Decisão gravada.', 'Decision saved.'))
      onDecidido()
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado(false)
    }
  }

  if (c.carregando && !c.dados) return <section className="card"><Carregando /></section>
  if (c.erro) return <Nota tipo="erro">{c.erro}</Nota>
  if (!c.dados) return null
  const d = c.dados
  const valores = d.definicao.valores ?? []
  const trechoUnidades = new Set(d.unidades)
  return (
    <>
      <section className="card">
        <div className="card-h">
          <div style={{ minWidth: 0, flex: 1 }}>
            <div style={{ fontWeight: 700 }}>{d.titulo}</div>
            <div className="small muted"><span className="mono">{d.chave}</span> · {tr('pág.', 'p.')} {d.pagina ?? '—'}</div>
          </div>
          <button className="btn btn-s" onClick={() => setPdf(true)}><FileSearch size={14} />{tr('Abrir no PDF', 'Open in PDF')}</button>
        </div>
        {pag.dados ? (
          <div className="pagetext" style={{ maxHeight: 280, whiteSpace: 'normal' }}>
            {pag.dados.unidades.map((u) => (
              <div key={u.uid} className={`unit${trechoUnidades.has(u.uid) ? ' hl' : ''}`}>
                <span className="mono faint">{u.uid}</span>
                <span><Destacar texto={u.texto} trecho={trechoUnidades.size ? null : d.trecho} /></span>
              </div>
            ))}
            <div className="faint small" style={{ marginTop: 6 }}>{tr('Página reconstruída do texto extraído. O trecho citado aparece destacado.', 'Page rebuilt from the extracted text. The quoted passage is highlighted.')}</div>
          </div>
        ) : (
          <Nota tipo="info">{tr('Nenhum extrator citou trecho. Confira o artigo no PDF.', 'No extractor quoted a passage. Check the article in the PDF.')}</Nota>
        )}
      </section>

      <section className="card">
        <div className="card-h">
          <h2 className="h2">{d.chave} · {d.campo_rotulo || d.campo_chave}</h2>
          <NivelPill nivel={d.nivel} />
          <span className="tag tag-g">{d.campo_tipo}</span>
        </div>
        <div className="small muted">{d.definicao.instrucao}</div>
        <div className="lbl">{tr('Respostas', 'Answers')}</div>
        {d.brutas.map((b) => (
          <div key={b.rotulo} style={{ display: 'grid', gridTemplateColumns: '36px minmax(0,1fr) auto', gap: 8, alignItems: 'start' }}>
            <span className="tag">{b.rotulo}</span>
            <div style={{ minWidth: 0 }}>
              <RespostaBruta b={b} />
              {b.status === 'ok' && b.trecho ? <div className="small muted" style={{ overflowWrap: 'anywhere' }}>“{b.trecho}”</div> : null}
              {b.e_detalhe ? <div className="small faint">{b.e_detalhe}</div> : null}
            </div>
            {b.status === 'ok' && (b.valor_normalizado || b.nao_reportado) ? (
              <button className="btn btn-s" disabled={ocupado} onClick={() => decidir(b.nao_reportado ? null : b.valor_normalizado, !!b.nao_reportado)}>
                {tr('Usar', 'Use')} {b.rotulo}
              </button>
            ) : <span />}
          </div>
        ))}
        <dl className="kvr">
          <dt>a · e · v</dt><dd className="mono">{fmt.num(d.a)} · {d.e ?? '—'} · {d.v ?? '—'}</dd>
          <dt>{tr('Motivo', 'Reason')}</dt><dd>{d.motivos.join('; ') || '—'}</dd>
        </dl>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button className="btn btn-p" disabled={ocupado || (d.valor_final === null && !d.nao_reportado)}
            onClick={() => decidir(d.valor_final, !!d.nao_reportado)}><Check size={15} />{tr('Aceitar maioria', 'Accept majority')}</button>
          <button className="btn" disabled={ocupado} onClick={() => decidir(null, true)}>{tr('Não reportado', 'Not reported')}</button>
          <button className="btn" onClick={onPular}><SkipForward size={15} />{tr('Pular', 'Skip')}</button>
        </div>
        <div className="grid2">
          <label className="field"><span>{tr('Valor final', 'Final value')}</span>
            {valores.length ? (
              <select className="sel-in" value={valor} onChange={(e) => setValor(e.target.value)}>
                <option value="">—</option>
                {valores.map((v) => <option key={v} value={v}>{v}</option>)}
              </select>
            ) : <input className="in" value={valor} onChange={(e) => setValor(e.target.value)} />}
          </label>
          <label className="field"><span>{tr('Justificativa', 'Justification')}</span>
            <input className="in" value={justificativa} onChange={(e) => setJustificativa(e.target.value)} /></label>
        </div>
        <div><button className="btn btn-p" disabled={ocupado || !valor.trim()} onClick={() => decidir(valor.trim(), false)}>{tr('Salvar e próxima', 'Save and next')}</button></div>
        <div className="small faint">{tr('Valor anterior, novo, justificativa e data vão para o log (anexo C).', 'Previous value, new value, justification and date go to the log (annex C).')}</div>
      </section>
      {pdf ? <PageViewer chave={d.chave} pagina={d.pagina ?? 1} trecho={d.trecho} unidades={d.unidades} onFechar={() => setPdf(false)} /> : null}
    </>
  )
}

function Auditoria({ eid, onMudou }: { eid: number; onMudou: () => void }) {
  const { tr, avisar } = useApp()
  const fmt = useFmt()
  const a = useCarregar(() => api.get<AuditoriaResposta>(`/execucoes/${eid}/auditoria`), [eid])
  const [valores, setValores] = useState<Record<number, string>>({})

  async function criar() {
    try {
      await api.post(`/execucoes/${eid}/auditoria`, {})
      a.recarregar(true)
      onMudou()
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }
  async function registrar(itemId: number, correto: boolean) {
    const v = valores[itemId]?.trim()
    if (!correto && !v) {
      avisar(tr('Informe o valor correto (ou "não reportado").', 'Enter the correct value (or "not reported").'), true)
      return
    }
    const nr = !correto && /^n(ã|a)o reportado$|^not reported$/i.test(v ?? '')
    try {
      await api.post(`/auditoria/itens/${itemId}`, { correto, valor_correto: correto || nr ? null : v, nao_reportado_correto: nr })
      a.recarregar(true)
      onMudou()
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }

  return (
    <section className="card">
      <div className="card-h">
        <h2 className="h2">{tr('Auditoria das células Alta', 'Audit of High cells')}</h2>
        <span className="small muted">{tr('amostra aleatória conferida à mão; é o número Lutz × humano quando não há piloto', 'random sample checked by hand; the Lutz × human number when there is no pilot')}</span>
      </div>
      {a.carregando && !a.dados ? <Carregando /> : a.erro ? <Nota tipo="erro">{a.erro}</Nota> : !a.dados?.auditoria ? (
        <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
          <span className="small">{tr(`${a.dados?.n_alta ?? 0} células Alta; amostra sugerida: ${a.dados?.n_sugerido ?? 0} (IC de Wilson com meia-largura alvo).`,
            `${a.dados?.n_alta ?? 0} High cells; suggested sample: ${a.dados?.n_sugerido ?? 0} (Wilson CI with target half-width).`)}</span>
          <button className="btn btn-p btn-s" disabled={!a.dados?.n_alta} onClick={criar}>{tr('Sortear amostra', 'Draw sample')}</button>
        </div>
      ) : (
        <>
          {a.dados.resultado ? (
            <div className="small">{a.dados.resultado.conferidas}/{a.dados.resultado.n_amostra} {tr('conferidas', 'checked')} · {a.dados.resultado.acertos} {tr('corretas', 'correct')}
              {a.dados.resultado.conferidas ? ` · ${fmt.pct(a.dados.resultado.taxa, 1)} (IC95% ${fmt.pct(a.dados.resultado.ic_inf, 1)}–${fmt.pct(a.dados.resultado.ic_sup, 1)})` : ''}
              {' · '}{tr('semente', 'seed')} {a.dados.resultado.semente}</div>
          ) : null}
          <div className="tablewrap scroll">
            <table className="t">
              <thead><tr><th>{tr('Artigo', 'Article')}</th><th>{tr('Campo', 'Field')}</th><th>{tr('Valor do Lutz', 'Lutz value')}</th><th>{tr('Trecho', 'Passage')}</th><th>{tr('Conferência', 'Check')}</th></tr></thead>
              <tbody>
                {(a.dados.itens ?? []).map((i) => (
                  <tr key={i.id}>
                    <td className="mono small">{i.chave}</td><td className="small">{i.campo_chave}</td>
                    <td>{i.nao_reportado ? tr('não reportado', 'not reported') : i.valor_final}</td>
                    <td className="small" style={{ maxWidth: 300 }}>{i.trecho ? `“${i.trecho}” p.${i.pagina ?? '?'}` : '—'}</td>
                    <td style={{ minWidth: 220 }}>
                      {i.correto !== null ? (
                        <span className={`tag ${i.correto ? 'tag-s' : 'tag-d'}`}>{i.correto ? tr('correto', 'correct') : `${tr('errado', 'wrong')} → ${i.valor_correto ?? tr('não reportado', 'not reported')}`}</span>
                      ) : (
                        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          <button className="btn btn-s" onClick={() => registrar(i.id, true)}>{tr('Correto', 'Correct')}</button>
                          <input className="in" style={{ height: 30, width: 120 }} placeholder={tr('valor certo', 'right value')} aria-label={tr('valor certo', 'right value')}
                            value={valores[i.id] ?? ''} onChange={(e) => setValores((v) => ({ ...v, [i.id]: e.target.value }))} />
                          <button className="btn btn-s btn-d" onClick={() => registrar(i.id, false)}>{tr('Errado', 'Wrong')}</button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  )
}
