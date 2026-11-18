import { useRef, useState } from 'react'
import { Check, Download, EyeOff, Play, Shuffle, Upload } from 'lucide-react'
import { api, url, type Campo, type Comparacao, type Estimativa, type Formulario, type PilotoResposta } from '../api'
import { useApp } from '../app-context'
import { ConfirmarExecucao } from '../components/Estimativa'
import { PdfViewer } from '../components/PdfViewer'
import { Cabecalho, Carregando, Modal, NivelPill, Nota, Vazio, baixar, useCarregar, useFmt } from '../components/ui'

const DECISAO: Record<string, [string, string, string]> = {
  lutz_sozinho: ['pa', 'Lutz sozinho', 'Lutz alone'],
  revisar_media_baixa: ['pm', 'Revisar Média e Baixa', 'Review Medium and Low'],
  reescrever: ['pb', 'Reescrever campo', 'Rewrite field'],
  indefinida: ['pn', 'Decisão manual', 'Manual decision'],
}
const METRICA: Record<string, string> = { kappa: 'κ', kappa_ponderado: 'κw', icc: 'ICC', pct_equivalencia: '% equiv.' }

export function Piloto() {
  const { tr, avisar, projeto, recarregarProjeto } = useApp()
  const fmt = useFmt()
  const p = useCarregar(() => api.get<PilotoResposta>('/piloto'), [])
  const [plano, setPlano] = useState({ n_ajuste: 10, n_validacao: 20, n_reserva: 0, estratos: '', avaliadores: 'A,B' })
  const [novoPlano, setNovoPlano] = useState(false)
  const [form, setForm] = useState<string | null>(null)
  const [confirmar, setConfirmar] = useState<Estimativa | null>(null)
  const [comp, setComp] = useState<Comparacao | null>(null)
  const [conjComp, setConjComp] = useState<'ajuste' | 'validacao'>('validacao')
  const [ocupado, setOcupado] = useState('')
  const upload = useRef<HTMLInputElement>(null)
  const uploadAv = useRef<string>('')
  const consensoIn = useRef<HTMLInputElement>(null)

  const st = p.dados?.estado ?? null
  const pil = st?.piloto
  const avs = pil?.avaliadores ?? []
  const sorteado = !!pil?.sorteado_em
  const cobertos = avs.every((a) => { const c = st?.cobertura[a]; return c && c.feito >= c.esperado && c.esperado > 0 })
  const precisaConsenso = avs.length === 2
  const ajustes = (st?.rodadas ?? []).filter((r) => r.conjunto_piloto === 'ajuste')
  const validacao = st?.validacao

  async function acao(nome: string, fn: () => Promise<unknown>, ok?: string) {
    setOcupado(nome)
    try {
      await fn()
      if (ok) avisar(ok)
      p.recarregar(true)
      recarregarProjeto()
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado('')
    }
  }

  async function rodar(conjunto: 'ajuste' | 'validacao') {
    if (conjunto === 'validacao' && !window.confirm(tr('A validação roda uma única vez, com o codebook congelado. Só essas métricas vão para o relatório. Continuar?',
      'Validation runs only once, with the frozen codebook. Only these metrics go to the report. Continue?'))) return
    setOcupado(conjunto)
    try {
      setConfirmar(await api.post<Estimativa>('/execucoes/estimativa', { conjunto }))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado('')
    }
  }

  async function importarPlanilha(f: File) {
    const fd = new FormData()
    fd.append('avaliador', uploadAv.current)
    fd.append('arquivo', f)
    try {
      const r = await api.form<{ gravadas: number; erros: { linha: number | null; erro: string }[]; faltando: string[] }>('/piloto/importacao', fd)
      if (r.erros.length) {
        avisar(tr(`${r.erros.length} erro(s); nada foi importado.`, `${r.erros.length} error(s); nothing was imported.`), true)
        r.erros.slice(0, 6).forEach((e) => avisar(`${e.linha ? `${tr('linha', 'line')} ${e.linha}: ` : ''}${e.erro}`, true))
      } else avisar(tr(`${r.gravadas} células importadas do avaliador ${uploadAv.current}.`, `${r.gravadas} cells imported for rater ${uploadAv.current}.`))
      p.recarregar(true)
      recarregarProjeto()
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }

  async function importarConsenso(f: File) {
    const fd = new FormData()
    fd.append('arquivo', f)
    try {
      const r = await api.form<{ gravadas: number; erros: { erro: string }[] }>('/piloto/consenso', fd)
      if (r.erros.length) r.erros.slice(0, 6).forEach((e) => avisar(e.erro, true))
      else avisar(tr(`Consenso gravado (${r.gravadas} células): é o padrão-ouro.`, `Consensus saved (${r.gravadas} cells): it is the reference standard.`))
      p.recarregar(true)
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }

  const etapas = [
    { ok: !!pil, rot: tr('Planejar', 'Plan'), det: pil ? `${pil.n_ajuste + pil.n_validacao} ${tr('artigos', 'articles')}` : '—' },
    { ok: sorteado, rot: tr('Sortear', 'Draw'), det: pil ? `seed ${pil.semente} · ${pil.n_ajuste} + ${pil.n_validacao}${pil.n_reserva ? ` + ${pil.n_reserva}` : ''}` : '—' },
    { ok: sorteado && cobertos, rot: tr('Extração cega', 'Blind extraction'), det: avs.map((a) => `${a} ${st?.cobertura[a]?.feito ?? 0}/${st?.cobertura[a]?.esperado ?? 0}`).join(', ') || '—' },
    ...(precisaConsenso ? [{ ok: !!st?.consenso, rot: tr('Consenso', 'Consensus'), det: st?.consenso ? tr('padrão-ouro pronto', 'reference ready') : '—' }] : []),
    { ok: ajustes.length > 0, rot: tr('Ajuste', 'Adjustment'), det: `${ajustes.length} ${tr('rodada(s)', 'round(s)')}` },
    { ok: !!validacao && (st?.decisoes.length ?? 0) > 0, rot: tr('Validação final', 'Final validation'), det: validacao ? `${tr('execução', 'run')} ${String(validacao.id)}` : '—' },
  ]
  const atual = etapas.findIndex((e) => !e.ok)

  return (
    <>
      <Cabecalho titulo={tr('Piloto calibrado', 'Calibrated pilot')}
        sub={tr('Mede a validade: quanto o Lutz acerta contra humanos. É opcional e usa o mesmo codebook da extração.',
          'Measures validity: how often Lutz is right against humans. It is optional and uses the same codebook as the extraction.')}>
        {pil && sorteado ? avs.map((a) => (
          <button key={a} className="btn" onClick={() => baixar(url(`/piloto/planilha/${encodeURIComponent(a)}.csv`))}><Download size={15} />{tr('Planilha', 'Sheet')} {a}</button>
        )) : null}
      </Cabecalho>

      {p.carregando && !p.dados ? <Carregando /> : p.erro ? <Nota tipo="erro">{p.erro}</Nota> : (
        <>
          {pil ? (
            <section className="steps" aria-label={tr('Etapas do piloto', 'Pilot steps')}>
              {etapas.map((e, i) => (
                <div key={e.rot} className={`step${e.ok ? ' ok' : i === atual ? ' cur' : ''}`}>
                  <strong>{e.ok ? '✓ ' : ''}{e.rot}</strong><span className="muted">{e.det}</span>
                </div>
              ))}
            </section>
          ) : null}

          <section className="row">
            <div className="card grow">
              <h2 className="h2">{tr('Tamanho do piloto', 'Pilot size')}</h2>
              <p className="sub">{tr('Largura do IC95% do kappa por número de artigos, com p_o = 0,90 e p_e = 0,50.', 'Width of the kappa 95% CI by number of articles, with p_o = 0.90 and p_e = 0.50.')}</p>
              <table className="t">
                <thead><tr><th className="num">{tr('Artigos', 'Articles')}</th><th className="num">{tr('Erro padrão', 'Std. error')}</th><th className="num">{tr('Meia largura', 'Half-width')}</th></tr></thead>
                <tbody>
                  {(p.dados?.tamanho ?? []).map((r) => (
                    <tr key={r.n} className={pil && r.n === pil.n_validacao ? 'sel' : ''}>
                      <td className="num">{r.n}{pil && r.n === pil.n_validacao ? ` · ${tr('escolhido', 'chosen')}` : ''}</td>
                      <td className="num">{fmt.num(r.erro_padrao)}</td><td className="num">±{fmt.num(r.meia_largura)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="small muted">{tr('Seu corpus tem', 'Your corpus has')} <strong>{p.dados?.n_corpus ?? 0}</strong> {tr('artigos prontos.', 'ready articles.')}</div>
              {(p.dados?.avisos ?? []).map((a) => <Nota key={a}>{a}</Nota>)}
            </div>

            <div className="card grow">
              {!pil || novoPlano ? (
                <>
                  <h2 className="h2">{tr('Plano (pré-registrado com hash)', 'Plan (pre-registered with a hash)')}</h2>
                  {!projeto?.codebook ? <Nota>{tr('Crie o codebook antes de planejar o piloto.', 'Create the codebook before planning the pilot.')}</Nota> : null}
                  <div className="grid2">
                    <label className="field"><span>{tr('Conjunto de ajuste', 'Adjustment set')}</span>
                      <input className="in" type="number" min={0} value={plano.n_ajuste} onChange={(e) => setPlano({ ...plano, n_ajuste: Number(e.target.value) })} /></label>
                    <label className="field"><span>{tr('Conjunto de validação', 'Validation set')}</span>
                      <input className="in" type="number" min={5} value={plano.n_validacao} onChange={(e) => setPlano({ ...plano, n_validacao: Number(e.target.value) })} /></label>
                    <label className="field"><span>{tr('Bloco reserva', 'Reserve block')}</span>
                      <input className="in" type="number" min={0} value={plano.n_reserva} onChange={(e) => setPlano({ ...plano, n_reserva: Number(e.target.value) })} /></label>
                    <label className="field"><span>{tr('Estratos', 'Strata')}</span>
                      <select className="sel-in" value={plano.estratos} onChange={(e) => setPlano({ ...plano, estratos: e.target.value })}>
                        <option value="">{tr('nenhum', 'none')}</option><option value="ano">{tr('ano', 'year')}</option><option value="revista">{tr('revista', 'journal')}</option>
                      </select></label>
                    <label className="field"><span>{tr('Avaliadores (1 ou 2, vírgula)', 'Raters (1 or 2, comma)')}</span>
                      <input className="in" value={plano.avaliadores} onChange={(e) => setPlano({ ...plano, avaliadores: e.target.value })} /></label>
                  </div>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className="btn btn-p" disabled={ocupado !== '' || !projeto?.codebook} onClick={() => acao('plano', async () => {
                      await api.post('/piloto/plano', { ...plano, avaliadores: plano.avaliadores.split(',').map((x) => x.trim()).filter(Boolean) })
                      setNovoPlano(false)
                    }, tr('Plano registrado.', 'Plan registered.'))}>{tr('Registrar plano', 'Register plan')}</button>
                    {novoPlano ? <button className="btn" onClick={() => setNovoPlano(false)}>{tr('Cancelar', 'Cancel')}</button> : null}
                  </div>
                  <div className="small faint">{tr('O plano guarda limiares, regra de decisão, sementes e versão do codebook. O hash vai para o relatório.', 'The plan stores thresholds, decision rule, seeds and codebook version. Its hash goes to the report.')}</div>
                </>
              ) : (
                <>
                  <div className="card-h">
                    <h2 className="h2">{tr('Amostra e avaliadores', 'Sample and raters')}</h2>
                    <span className="tag"><EyeOff size={11} style={{ marginRight: 4 }} />{pil.cegamento_aberto ? tr('cegamento encerrado', 'blinding lifted') : tr('piloto cego', 'blind pilot')}</span>
                    <span style={{ flex: 1 }} />
                    {sorteado && !pil.cegamento_aberto ? null : <button className="btn btn-s" onClick={() => setNovoPlano(true)}>{tr('Novo plano', 'New plan')}</button>}
                  </div>
                  <dl className="kvr">
                    <dt>{tr('Plano', 'Plan')}</dt><dd className="mono">{pil.hash_plano}</dd>
                    <dt>{tr('Sorteio', 'Draw')}</dt><dd>seed {pil.semente}{pil.estratos ? ` · ${tr('estratos', 'strata')}: ${pil.estratos}` : ''}</dd>
                    <dt>{tr('Ajuste', 'Adjustment')}</dt><dd>{pil.n_ajuste} {tr('artigos · rodadas livres', 'articles · free rounds')}</dd>
                    <dt>{tr('Validação', 'Validation')}</dt><dd>{pil.n_validacao} {tr('artigos · uma rodada com codebook congelado', 'articles · one round with frozen codebook')}</dd>
                    {pil.n_reserva ? <><dt>{tr('Reserva', 'Reserve')}</dt><dd>{pil.n_reserva}</dd></> : null}
                  </dl>
                  {!sorteado ? (
                    <button className="btn btn-p" disabled={ocupado !== ''} onClick={() => acao('sorteio', () => api.post('/piloto/sorteio'), tr('Sorteio feito. As respostas do Lutz para esses artigos ficam ocultas.', 'Draw done. Lutz answers for these articles stay hidden.'))}>
                      <Shuffle size={15} />{tr('Sortear amostra', 'Draw sample')}
                    </button>
                  ) : (
                    <>
                      {avs.map((a) => {
                        const c = st?.cobertura[a]
                        return (
                          <div key={a} style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                            <strong style={{ minWidth: 90 }}>{tr('Avaliador', 'Rater')} {a}</strong>
                            <span className="mono small">{c?.feito ?? 0}/{c?.esperado ?? 0}</span>
                            <span style={{ flex: 1 }} />
                            <button className="btn btn-s" onClick={() => setForm(a)}>{tr('Formulário cego', 'Blind form')}</button>
                            <button className="btn btn-s" onClick={() => { uploadAv.current = a; upload.current?.click() }}><Upload size={13} />{tr('Importar planilha', 'Import sheet')}</button>
                          </div>
                        )
                      })}
                      <input ref={upload} type="file" accept=".csv,text/csv" hidden aria-label={tr('Planilha preenchida', 'Filled sheet')}
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) importarPlanilha(f); e.target.value = '' }} />
                      <Nota tipo="info">{pil.cegamento_aberto
                        ? tr('Todas as planilhas foram importadas: as respostas do Lutz para a amostra agora aparecem.', 'All sheets were imported: Lutz answers for the sample are now visible.')
                        : tr('As respostas do Lutz para a amostra ficam ocultas até todas as planilhas humanas serem importadas.', 'Lutz answers for the sample stay hidden until all human sheets are imported.')}</Nota>
                    </>
                  )}
                  {precisaConsenso && sorteado ? (
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <strong>{tr('Consenso', 'Consensus')}</strong>
                      {st?.consenso ? <span className="tag tag-s">{tr('padrão-ouro pronto', 'reference ready')}</span> : null}
                      <span style={{ flex: 1 }} />
                      <button className="btn btn-s" disabled={!cobertos} onClick={() => baixar(url('/piloto/consenso.csv'))}><Download size={13} />{tr('Divergências', 'Disagreements')}</button>
                      <button className="btn btn-s" disabled={!cobertos} onClick={() => consensoIn.current?.click()}><Upload size={13} />{tr('Importar consenso', 'Import consensus')}</button>
                      <input ref={consensoIn} type="file" accept=".csv,text/csv" hidden aria-label={tr('Consenso', 'Consensus')}
                        onChange={(e) => { const f = e.target.files?.[0]; if (f) importarConsenso(f); e.target.value = '' }} />
                    </div>
                  ) : null}
                </>
              )}
            </div>
          </section>

          {pil && sorteado ? (
            <section className="card">
              <div className="card-h">
                <h2 className="h2">{tr('Rodadas', 'Rounds')}</h2>
                <span style={{ flex: 1 }} />
                <button className="btn btn-s" disabled={ocupado !== '' || !projeto?.codebook_congelado} onClick={() => rodar('ajuste')}><Play size={13} />{tr('Rodar conjunto de ajuste', 'Run adjustment set')}</button>
                <button className="btn btn-s btn-p" disabled={ocupado !== '' || !!validacao || !projeto?.codebook_congelado} onClick={() => rodar('validacao')}><Check size={13} />{tr('Validação final', 'Final validation')}</button>
              </div>
              <p className="sub">{tr('No ajuste, reescreva as instruções dos campos que foram mal, congele uma nova versão e rode de novo. A validação roda uma vez, com o codebook congelado; só ela vai para o relatório.',
                'In adjustment, rewrite the instructions of fields that did poorly, freeze a new version and run again. Validation runs once with the frozen codebook; only it goes to the report.')}</p>
              {st?.rodadas.length ? (
                <table className="t">
                  <thead><tr><th>{tr('Execução', 'Run')}</th><th>{tr('Conjunto', 'Set')}</th><th>Codebook</th><th>Status</th><th>{tr('O que mudou', 'What changed')}</th></tr></thead>
                  <tbody>
                    {st.rodadas.map((r) => (
                      <tr key={r.id}><td className="mono">{r.id}</td><td>{r.conjunto_piloto}</td><td className="mono small">v{r.versao} · {r.hash}</td><td>{r.status}</td>
                        <td className="small">{r.mudancas ? [...r.mudancas.alterados, ...r.mudancas.adicionados.map((x) => `+${x}`), ...r.mudancas.removidos.map((x) => `−${x}`)].join(', ') || '—' : '—'}</td></tr>
                    ))}
                  </tbody>
                </table>
              ) : <div className="faint small">{tr('Nenhuma rodada ainda.', 'No rounds yet.')}</div>}
            </section>
          ) : null}

          {pil && sorteado ? (
            <section className="card">
              <div className="card-h">
                <h2 className="h2">{tr('Lutz × padrão-ouro', 'Lutz × reference standard')}</h2>
                {(['ajuste', 'validacao'] as const).map((c) => <button key={c} className={`chipb${conjComp === c ? ' on' : ''}`} onClick={() => setConjComp(c)}>{c === 'ajuste' ? tr('ajuste', 'adjustment') : tr('validação', 'validation')}</button>)}
                <span style={{ flex: 1 }} />
                <button className="btn btn-s btn-p" disabled={ocupado !== '' || !pil.cegamento_aberto} onClick={() => acao('comparar', async () => setComp(await api.post<Comparacao>('/piloto/comparacao', { conjunto: conjComp })))}>
                  {ocupado === 'comparar' ? tr('Calculando…', 'Computing…') : tr('Comparar', 'Compare')}
                </button>
              </div>
              {!pil.cegamento_aberto ? <Nota tipo="info">{tr('Importe todas as planilhas humanas antes de comparar.', 'Import all human sheets before comparing.')}</Nota> : null}
              {comp ? <ResultadoComparacao c={comp} /> : st?.decisoes.length ? (
                <>
                  <div className="small muted">{tr('Decisões registradas na validação:', 'Decisions recorded in validation:')}</div>
                  <table className="t">
                    <thead><tr><th>{tr('Campo', 'Field')}</th><th>{tr('Métrica', 'Metric')}</th><th className="num">{tr('Valor', 'Value')}</th><th className="num">IC95%</th><th>{tr('Decisão', 'Decision')}</th></tr></thead>
                    <tbody>
                      {st.decisoes.map((d) => {
                        const x = DECISAO[d.decisao] ?? ['pn', d.decisao, d.decisao]
                        return <tr key={d.campo_chave}><td>{d.campo_chave}</td><td>{METRICA[d.metrica] ?? d.metrica}</td><td className="num">{fmt.num(d.valor)}</td>
                          <td className="num">{fmt.ic(d.ic_inf, d.ic_sup)}</td><td><span className={`pill ${x[0]}`}>{tr(x[1], x[2])}</span></td></tr>
                      })}
                    </tbody>
                  </table>
                </>
              ) : <Vazio titulo={tr('Sem comparação ainda', 'No comparison yet')} />}
            </section>
          ) : null}
        </>
      )}

      {form ? <FormularioCego avaliador={form} onFechar={() => { setForm(null); p.recarregar(true); recarregarProjeto() }} /> : null}
      {confirmar ? <ConfirmarExecucao est={confirmar} onFechar={() => { setConfirmar(null); p.recarregar(true) }}
        onIniciada={() => { setConfirmar(null); avisar(tr('Execução do piloto iniciada. Acompanhe na tela Extração.', 'Pilot run started. Follow it in the Extraction screen.')); p.recarregar(true) }} /> : null}
    </>
  )
}

function ResultadoComparacao({ c }: { c: Comparacao }) {
  const { tr } = useApp()
  const fmt = useFmt()
  const alta = c.niveis.find((n) => n.nivel === 'alta')
  return (
    <>
      <div className="small muted">{tr('Execução', 'Run')} {c.execucao_id} · {tr('padrão-ouro', 'reference')}: {c.padrao_ouro} · {tr('IC95% por bootstrap sobre artigos', '95% CI by bootstrap over articles')}</div>
      {c.conjunto === 'ajuste' ? <Nota tipo="info">{tr('Métricas do ajuste servem para reescrever instruções; não vão para o relatório.', 'Adjustment metrics are for rewriting instructions; they do not go to the report.')}</Nota> : null}
      <div className="tablewrap">
        <table className="t">
          <thead><tr><th>{tr('Campo', 'Field')}</th><th>{tr('Tipo', 'Type')}</th><th>{tr('Métrica', 'Metric')}</th><th className="num">IC95%</th><th className="num">{tr('Humano × humano', 'Human × human')}</th>
            <th className="num">{tr('Concordância', 'Agreement')}</th><th>{tr('Decisão para o corpus', 'Decision for the corpus')}</th></tr></thead>
          <tbody>
            {c.campos.map((x) => {
              const m = x.lutz_ouro
              const d = x.decisao ? DECISAO[x.decisao] : null
              const pctEq = m.metrica === 'pct_equivalencia'
              return (
                <tr key={x.campo}>
                  <td><strong>{x.campo}</strong>{[x.nota, ...m.notas].filter(Boolean).map((n, i) => <div key={i} className="small muted">{n}</div>)}</td>
                  <td className="small">{x.tipo}</td>
                  <td className="num">{METRICA[m.metrica] ?? m.metrica} {pctEq ? fmt.pct(m.valor) : fmt.num(m.valor)}</td>
                  <td className="num">{pctEq ? `${fmt.pct(m.ic[0])}–${fmt.pct(m.ic[1])}` : fmt.ic(m.ic[0], m.ic[1])}</td>
                  <td className="num">{x.humano_humano ? (pctEq ? fmt.pct(x.humano_humano.valor) : fmt.num(x.humano_humano.valor)) : '—'}</td>
                  <td className="num">{fmt.pct(m.pct_concordancia)}</td>
                  <td>{d ? <span className={`pill ${d[0]}`}>{tr(d[1], d[2])}</span> : '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="small faint">{tr('Regra: κ ou ICC ≥ 0,80 com IC inferior ≥ 0,60 → Lutz sozinho; 0,60–0,79 → revisar Média e Baixa; abaixo de 0,60 → reescrever.',
        'Rule: κ or ICC ≥ 0.80 with lower CI ≥ 0.60 → Lutz alone; 0.60–0.79 → review Medium and Low; below 0.60 → rewrite.')}</div>
      <h2 className="h2">{tr('Calibração dos níveis de confiança', 'Calibration of the confidence levels')}</h2>
      <table className="t">
        <thead><tr><th>{tr('Nível', 'Level')}</th><th className="num">{tr('Células', 'Cells')}</th><th className="num">{tr('Acertos', 'Hits')}</th><th className="num">{tr('Taxa de acerto', 'Accuracy')}</th><th className="num">IC95% (Wilson)</th></tr></thead>
        <tbody>
          {c.niveis.map((n) => (
            <tr key={n.nivel}><td><NivelPill nivel={n.nivel} /></td><td className="num">{n.n}</td><td className="num">{n.acertos}</td>
              <td className="num">{fmt.pct(n.taxa, 1)}</td><td className="num">{n.n ? `${fmt.pct(n.ic_inf, 1)}–${fmt.pct(n.ic_sup, 1)}` : '—'}</td></tr>
          ))}
        </tbody>
      </table>
      {alta && alta.n && alta.taxa !== null && alta.taxa < 0.95 ? <Nota>{tr('Células Alta acertaram menos de 95%: os limiares do Modo Autônomo estão frouxos.', 'High cells were right less than 95% of the time: the autonomous thresholds are too loose.')}</Nota> : null}
      {c.avisos.map((a) => <Nota key={a}>{a}</Nota>)}
    </>
  )
}

function FormularioCego({ avaliador, onFechar }: { avaliador: string; onFechar: () => void }) {
  const { tr, avisar } = useApp()
  const f = useCarregar(() => api.get<Formulario>(`/piloto/formulario/${encodeURIComponent(avaliador)}`), [avaliador])
  const [idx, setIdx] = useState(0)
  const [pagina, setPagina] = useState(1)
  const art = f.dados?.artigos[idx]

  return (
    <Modal titulo={`${tr('Formulário cego', 'Blind form')} · ${tr('avaliador', 'rater')} ${avaliador}`}
      sub={f.dados ? `${f.dados.cobertura.feito}/${f.dados.cobertura.esperado} ${tr('células preenchidas', 'cells filled')} · ${tr('as respostas do Lutz não aparecem aqui', 'Lutz answers never appear here')}` : ''}
      onFechar={onFechar} largo>
      <div className="modal-b">
        {f.carregando && !f.dados ? <Carregando /> : f.erro ? <Nota tipo="erro">{f.erro}</Nota> : f.dados && art ? (
          <>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
              <select className="sel-in" style={{ maxWidth: 520 }} value={idx} onChange={(e) => { setIdx(Number(e.target.value)); setPagina(1) }} aria-label={tr('Artigo', 'Article')}>
                {f.dados.artigos.map((a, i) => {
                  const feitos = Object.values(a.respostas).filter(Boolean).length
                  return <option key={a.chave} value={i}>{a.chave} · {a.conjunto} · {feitos}/{f.dados!.campos.length} — {a.titulo.slice(0, 60)}</option>
                })}
              </select>
              <button className="btn btn-s" disabled={idx === 0} onClick={() => { setIdx(idx - 1); setPagina(1) }}>{tr('Anterior', 'Previous')}</button>
              <button className="btn btn-s" disabled={idx >= f.dados.artigos.length - 1} onClick={() => { setIdx(idx + 1); setPagina(1) }}>{tr('Próximo', 'Next')}</button>
            </div>
            <div className="row" style={{ alignItems: 'flex-start' }}>
              <div style={{ flex: '1 1 460px', minWidth: 0 }}><PdfViewer chave={art.chave} pagina={pagina} onPagina={setPagina} largura={500} /></div>
              <div style={{ flex: '1 1 380px', display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
                {f.dados.campos.map((c) => (
                  <CampoCego key={`${art.chave}-${c.nome}`} campo={c} inicial={art.respostas[c.nome]} pagina={pagina}
                    onSalvar={async (valor, nr, pag) => {
                      try {
                        await api.post('/piloto/respostas', { avaliador, artigo: art.chave, campo: c.nome, valor, nao_reportado: nr, pagina: pag })
                        f.recarregar(true)
                      } catch (e) {
                        avisar((e as Error).message, true)
                      }
                    }} />
                ))}
              </div>
            </div>
          </>
        ) : <Vazio titulo={tr('Sem artigos na amostra', 'No articles in the sample')} />}
      </div>
    </Modal>
  )
}

function CampoCego({ campo, inicial, pagina, onSalvar }: {
  campo: Campo; inicial: { valor: string | null; nao_reportado: boolean; pagina: number | null } | null; pagina: number
  onSalvar: (valor: string | null, nr: boolean, pagina: number | null) => Promise<void>
}) {
  const { tr } = useApp()
  const [valor, setValor] = useState(inicial?.valor ?? '')
  const [nr, setNr] = useState(inicial?.nao_reportado ?? false)
  const [pag, setPag] = useState<string>(inicial?.pagina ? String(inicial.pagina) : '')
  const salvo = !!inicial
  return (
    <div className="card" style={{ padding: '10px 12px', gap: 6 }}>
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        <strong className="small">{campo.rotulo || campo.nome}</strong><span className="tag tag-g">{campo.tipo}</span>
        {salvo ? <span className="tag tag-s">{tr('salvo', 'saved')}</span> : null}
      </div>
      <div className="small muted">{campo.instrucao}</div>
      <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
        {campo.valores?.length ? (
          <select className="sel-in" style={{ flex: '1 1 160px' }} value={valor} disabled={nr} onChange={(e) => setValor(e.target.value)} aria-label={campo.nome}>
            <option value="">—</option>
            {campo.valores.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        ) : (
          <input className="in" style={{ flex: '1 1 160px' }} value={valor} disabled={nr} onChange={(e) => setValor(e.target.value)} aria-label={campo.nome}
            placeholder={campo.unidade ? `${tr('número', 'number')} (${campo.unidade})` : ''} />
        )}
        <input className="in" style={{ width: 70 }} value={pag} placeholder={tr('pág.', 'p.')} aria-label={tr('página', 'page')} onChange={(e) => setPag(e.target.value.replace(/\D/g, ''))} />
        <button className="btn btn-s" onClick={() => setPag(String(pagina))} title={tr('usar a página aberta', 'use the open page')}>p.{pagina}</button>
        <label className="small" style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
          <input type="checkbox" checked={nr} onChange={(e) => setNr(e.target.checked)} />{tr('não reportado', 'not reported')}
        </label>
        <button className="btn btn-s btn-p" disabled={!nr && !valor.trim()} onClick={() => onSalvar(nr ? null : valor.trim(), nr, pag ? Number(pag) : null)}>{tr('Salvar', 'Save')}</button>
      </div>
    </div>
  )
}
