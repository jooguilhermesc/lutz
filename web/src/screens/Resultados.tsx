import { useState } from 'react'
import { Columns3, Download, FileSearch, Send } from 'lucide-react'
import { api, url, type CelulaDetalhe, type Nivel, type Tabela } from '../api'
import { useApp } from '../app-context'
import { CelulaPainel } from '../components/CelulaPainel'
import { ExecucaoSelect } from '../components/ExecucaoSelect'
import { PageViewer } from '../components/PageViewer'
import { Cabecalho, Carregando, Drawer, NivelPill, Nota, Vazio, baixar, useCarregar } from '../components/ui'

export function Resultados() {
  const { tr, avisar, recarregarProjeto } = useApp()
  const [eid, setEid] = useState<number | null>(null)
  const [nivel, setNivel] = useState<Nivel | ''>('')
  const [ocultas, setOcultas] = useState<Set<string>>(new Set())
  const [colunas, setColunas] = useState(false)
  const [celId, setCelId] = useState<number | null>(null)
  const [pdf, setPdf] = useState<CelulaDetalhe | null>(null)
  const tab = useCarregar(() => (eid ? api.get<Tabela>(`/execucoes/${eid}/tabela`) : Promise.resolve(null)), [eid])
  const cel = useCarregar(() => (celId ? api.get<CelulaDetalhe>(`/celulas/${celId}`) : Promise.resolve(null)), [celId])

  const campos = (tab.dados?.campos ?? []).filter((c) => !ocultas.has(c.chave))
  const linhas = (tab.dados?.linhas ?? []).filter((l) => !nivel || Object.values(l.celulas).some((c) => c.nivel === nivel))
  const cont: Record<Nivel, number> = { alta: 0, media: 0, baixa: 0 }
  for (const l of tab.dados?.linhas ?? []) for (const c of Object.values(l.celulas)) if (c.nivel) cont[c.nivel]++

  return (
    <>
      <Cabecalho titulo={tr('Resultados', 'Results')}
        sub={tr('A tabela de extração validada. Cada célula traz o valor final, o nível de confiança e o trecho com a página de onde saiu.',
          'The validated extraction table. Each cell has the final value, the confidence level and the passage with its page.')}>
        <ExecucaoSelect valor={eid} onValor={setEid} />
        <button className="btn" onClick={() => setColunas((c) => !c)} aria-expanded={colunas}><Columns3 size={15} />{tr('Colunas', 'Columns')} ({campos.length})</button>
        <button className="btn" disabled={!eid} onClick={() => baixar(url(`/execucoes/${eid}/exportar.csv?formato=largo`))}><Download size={15} />CSV {tr('largo', 'wide')}</button>
        <button className="btn" disabled={!eid} onClick={() => baixar(url(`/execucoes/${eid}/exportar.csv?formato=longo`))}><Download size={15} />CSV {tr('longo', 'long')}</button>
      </Cabecalho>

      {colunas && tab.dados ? (
        <section className="card" style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
          {tab.dados.campos.map((c) => (
            <button key={c.chave} className={`chipb${ocultas.has(c.chave) ? '' : ' on'}`} onClick={() => setOcultas((s) => {
              const n = new Set(s)
              if (n.has(c.chave)) n.delete(c.chave)
              else n.add(c.chave)
              return n
            })}>{c.rotulo || c.chave}</button>
          ))}
        </section>
      ) : null}

      {!eid && !tab.carregando ? (
        <section className="card"><Vazio titulo={tr('Nenhuma execução concluída', 'No completed run')}>{tr('Rode uma extração na tela Extração.', 'Run an extraction in the Extraction screen.')}</Vazio></section>
      ) : tab.erro ? <Nota tipo="erro">{tab.erro}</Nota> : !tab.dados ? <Carregando /> : (
        <section className="card">
          <div className="card-h">
            <span className="lbl">{tr('Nível', 'Level')}</span>
            <button className={`chipb${nivel === '' ? ' on' : ''}`} onClick={() => setNivel('')}>{tr('Todos', 'All')}</button>
            {(['alta', 'media', 'baixa'] as Nivel[]).map((n) => (
              <button key={n} className={`chipb${nivel === n ? ' on' : ''}`} onClick={() => setNivel(n)}>
                {{ alta: tr('Alta', 'High'), media: tr('Média', 'Medium'), baixa: tr('Baixa', 'Low') }[n]} · {cont[n]}
              </button>
            ))}
            <span style={{ flex: 1 }} />
            <span className="small muted">{tr('execução', 'run')} {eid} · {linhas.length} {tr('artigos', 'articles')}</span>
          </div>
          {tab.dados.ocultos_piloto ? (
            <Nota tipo="info">{tab.dados.ocultos_piloto} {tr('células de artigos do piloto cego estão ocultas até a importação das planilhas humanas.', 'cells of blind-pilot articles are hidden until the human sheets are imported.')}</Nota>
          ) : null}
          {linhas.length === 0 ? <Vazio titulo={tr('Nenhuma linha', 'No rows')} /> : (
            <div className="tablewrap">
              <table className="t">
                <thead><tr><th>{tr('Artigo', 'Article')}</th>{campos.map((c) => <th key={c.chave}>{c.rotulo || c.chave}</th>)}</tr></thead>
                <tbody>
                  {linhas.map((l) => (
                    <tr key={l.artigo}>
                      <td style={{ minWidth: 200, maxWidth: 280 }}>
                        <div className="small" style={{ fontWeight: 600 }}>{l.titulo}</div>
                        <div className="mono small faint">{l.artigo}{l.ano ? ` · ${l.ano}` : ''}</div>
                      </td>
                      {campos.map((c) => {
                        const x = l.celulas[c.chave]
                        if (!x) return <td key={c.chave} className="faint">—</td>
                        const apagada = nivel && x.nivel !== nivel
                        return (
                          <td key={c.chave} style={{ minWidth: 130, maxWidth: 240, opacity: apagada ? 0.35 : 1 }}>
                            <button className="cellbtn" onClick={() => setCelId(x.id)} aria-label={`${l.artigo} ${c.chave}`}>
                              <span className="cellval">{x.nao_reportado ? <span className="faint">{tr('não reportado', 'not reported')}</span> : x.valor ?? <span className="faint">{tr('empate', 'tie')}</span>}</span>
                              <span style={{ display: 'flex', gap: 4, alignItems: 'center' }}>
                                <NivelPill nivel={x.nivel} />
                                {x.origem === 'adjudicacao' ? <span className="tag" title={tr('adjudicada', 'adjudicated')}>adj</span> : null}
                                {x.pagina ? <span className="faint small">p.{x.pagina}</span> : null}
                              </span>
                            </button>
                          </td>
                        )
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className="small muted" style={{ margin: 0 }}>
            {tr('Alta: unanimidade, trecho exato, verificador sustenta e regras OK; aceita com auditoria por amostragem. Média: 2 de 3 e checagens parciais; revisar nos campos fracos do piloto. Baixa: o resto, inclusive empate e regra violada; adjudicar sempre.',
              'High: unanimity, exact passage, verifier supports and rules OK; accepted with sample audit. Medium: 2 of 3 and partial checks; review in fields weak in the pilot. Low: everything else, including ties and rule violations; always adjudicate.')}
          </p>
        </section>
      )}

      {celId ? (
        <Drawer titulo={cel.dados ? <><div style={{ fontWeight: 700 }}>{cel.dados.chave} · {cel.dados.campo_rotulo || cel.dados.campo_chave}</div><div className="small muted">{cel.dados.titulo}</div></> : '…'}
          onFechar={() => setCelId(null)}>
          {cel.carregando && !cel.dados ? <Carregando /> : cel.erro ? <Nota tipo="erro">{cel.erro}</Nota> : cel.dados ? (
            <>
              <CelulaPainel c={cel.dados} />
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                <button className="btn" onClick={() => setPdf(cel.dados)}><FileSearch size={15} />{tr('Abrir no PDF', 'Open in PDF')}</button>
                <button className="btn btn-p" disabled={cel.dados.enviada_manual || cel.dados.estado === 'adjudicada'} onClick={async () => {
                  try {
                    await api.post(`/celulas/${celId}/enviar`, {})
                    avisar(tr('Célula enviada para a fila de adjudicação.', 'Cell sent to the adjudication queue.'))
                    cel.recarregar(true)
                    recarregarProjeto()
                  } catch (e) {
                    avisar((e as Error).message, true)
                  }
                }}><Send size={15} />{tr('Enviar para adjudicação', 'Send to adjudication')}</button>
              </div>
            </>
          ) : null}
        </Drawer>
      ) : null}
      {pdf ? <PageViewer chave={pdf.chave} pagina={pdf.pagina ?? 1} trecho={pdf.trecho} unidades={pdf.unidades} onFechar={() => setPdf(null)} /> : null}
    </>
  )
}
