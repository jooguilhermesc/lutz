// Settings (ADR-004): one screen for the OpenRouter key, the model of each role and usage.
// The key goes to the project .env through /config (mechanism kept from 0.5); the models are written
// into the 'modelos' block of lutz.yaml through /config/modelos; everything else in lutz.yaml is edited by hand.
import { useEffect, useMemo, useState } from 'react'
import { Download, ExternalLink, RefreshCw } from 'lucide-react'
import { api, url, type CatalogoOR, type Config, type Consumo, type ContaOR, type ModeloOR } from '../api'
import { useApp, type Lang } from '../app-context'
import { Carregando, Kpi, Modal, Nota, baixar, useCarregar, useFmt } from './ui'

const ORIGEM: Record<string, [string, string, string]> = {
  processo: ['tag-w', 'terminal', 'shell'],
  '.env': ['tag-s', '.env', '.env'],
  padrao: ['tag-g', 'padrão', 'default'],
  ausente: ['tag-d', 'ausente', 'missing'],
}

const PAPEIS: { rot: 'E1' | 'E2' | 'E3' | 'V'; pt: string; en: string }[] = [
  { rot: 'E1', pt: 'Extrator 1', en: 'Extractor 1' },
  { rot: 'E2', pt: 'Extrator 2', en: 'Extractor 2' },
  { rot: 'E3', pt: 'Extrator 3', en: 'Extractor 3' },
  { rot: 'V', pt: 'Verificador (opcional)', en: 'Verifier (optional)' },
]

const fornecedor = (id: string) => (id.includes('/') ? id.split('/')[0] : '')

export function SettingsModal({ onFechar }: { onFechar: () => void }) {
  const { tr, lang, setLang, avisar } = useApp()
  const fmt = useFmt()
  const cfg = useCarregar(() => api.get<Config>('/config'), [])
  const [atualizar, setAtualizar] = useState(0)
  const cat = useCarregar(() => api.get<CatalogoOR>(`/openrouter/modelos${atualizar ? '?atualizar=true' : ''}`), [atualizar])
  const [versaoChave, setVersaoChave] = useState(0)
  const conta = useCarregar(() => api.get<ContaOR>('/openrouter/conta'), [versaoChave])
  const cons = useCarregar(() => api.get<Consumo>('/consumo?limite=50'), [])

  // ── key ──
  const chave = cfg.dados?.env.find((v) => v.nome === 'OPENROUTER_API_KEY')
  const baseUrl = cfg.dados?.env.find((v) => v.nome === 'OPENROUTER_BASE_URL')
  const [novaChave, setNovaChave] = useState('')
  const [novaBase, setNovaBase] = useState('')
  const [salvandoChave, setSalvandoChave] = useState(false)

  async function gravarEnv(body: Record<string, string | null>) {
    setSalvandoChave(true)
    try {
      const r = await api.put<{ ok: boolean; sombreadas: string[] }>('/config', body)
      if (r.sombreadas.length)
        avisar(tr(`Gravado no .env, mas ${r.sombreadas.join(', ')} também está definida no terminal, que tem precedência.`,
          `Saved to .env, but ${r.sombreadas.join(', ')} is also set in the shell, which takes precedence.`), true)
      else avisar(tr('Chave salva no .env.', 'Key saved to .env.'))
      setNovaChave('')
      setNovaBase('')
      cfg.recarregar(true)
      setVersaoChave((v) => v + 1)
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setSalvandoChave(false)
    }
  }

  // ── models ──
  const y = cfg.dados?.lutz_yaml
  const atuais = useMemo(() => {
    const m: Record<string, string> = {}
    for (const p of y?.papeis ?? []) m[p.rotulo] = p.modelo
    return m
  }, [y])
  const [escolha, setEscolha] = useState<Record<string, string>>({})
  useEffect(() => setEscolha(atuais), [atuais])
  const porId = useMemo(() => new Map((cat.dados?.modelos ?? []).map((m) => [m.id, m])), [cat.dados])
  const mudou = PAPEIS.some((p) => (escolha[p.rot] ?? '') !== (atuais[p.rot] ?? ''))
  const [salvandoModelos, setSalvandoModelos] = useState(false)
  const vendors = new Set(['E1', 'E2', 'E3'].map((r) => fornecedor(escolha[r] ?? '')).filter(Boolean))

  async function salvarModelos() {
    setSalvandoModelos(true)
    try {
      const body: Record<string, string | null> = {}
      for (const p of PAPEIS) body[p.rot] = (escolha[p.rot] ?? '').trim() || null
      await api.put<Config>('/config/modelos', body)
      avisar(tr('Modelos gravados no lutz.yaml.', 'Models saved to lutz.yaml.'))
      cfg.recarregar(true)
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setSalvandoModelos(false)
    }
  }

  const precoTxt = (m: ModeloOR | undefined) =>
    !m ? '' : m.entrada == null || m.saida == null ? tr('preço variável', 'variable price')
      : m.entrada === 0 && m.saida === 0 ? tr('gratuito', 'free')
        : `US$ ${fmt.num(m.entrada, 2)} / ${fmt.num(m.saida, 2)} ${tr('por 1M tokens (entrada/saída)', 'per 1M tokens (in/out)')}`

  // ── usage ──
  const c = conta.dados
  const total = cons.dados?.total
  const orcamento = y?.orcamento_usd

  return (
    <Modal largo titulo={tr('Configurações', 'Settings')}
      sub={tr('Todos os modelos passam pelo OpenRouter: uma chave, o catálogo inteiro e o consumo num só lugar.',
        'Every model runs through OpenRouter: one key, the whole catalog and usage in one place.')}
      onFechar={onFechar}>
      <div className="modal-b">
        {cfg.carregando && !cfg.dados ? <Carregando /> : cfg.erro ? <Nota tipo="erro">{cfg.erro}</Nota> : null}

        {/* ── 1. key ── */}
        <section className="card" aria-labelledby="cfg-chave">
          <div className="card-h">
            <h2 className="h2" id="cfg-chave">{tr('Chave do OpenRouter', 'OpenRouter key')}</h2>
            {chave ? <span className={`tag ${ORIGEM[chave.origem]?.[0] ?? 'tag-g'}`}>{tr(ORIGEM[chave.origem]?.[1] ?? chave.origem, ORIGEM[chave.origem]?.[2] ?? chave.origem)}</span> : null}
            <span style={{ flex: 1 }} />
            <a className="small" href="https://openrouter.ai/keys" target="_blank" rel="noreferrer">
              {tr('Criar uma chave', 'Create a key')} <ExternalLink size={12} />
            </a>
          </div>
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <input className="in" style={{ flex: 1 }} type="password" autoComplete="off" aria-label="OPENROUTER_API_KEY"
              placeholder={chave?.valor || 'sk-or-…'} value={novaChave} onChange={(e) => setNovaChave(e.target.value)} />
            <button className="btn btn-p" disabled={!novaChave.trim() || salvandoChave}
              onClick={() => gravarEnv({ OPENROUTER_API_KEY: novaChave.trim() })}>
              {salvandoChave ? tr('Salvando…', 'Saving…') : tr('Salvar chave', 'Save key')}
            </button>
            {chave?.origem === '.env' ? (
              <button className="btn" disabled={salvandoChave} onClick={() => gravarEnv({ OPENROUTER_API_KEY: null })}>
                {tr('Remover', 'Remove')}
              </button>
            ) : null}
          </div>
          <p className="sub small" style={{ marginTop: 6 }}>
            {chave?.origem === 'processo'
              ? tr('Definida no ambiente do terminal: editar o .env não muda o valor usado.', 'Set in the shell environment: editing .env does not change the value in use.')
              : tr('Fica no .env do projeto, mascarada. Variáveis exportadas no terminal têm precedência.', 'Stored masked in the project .env. Variables exported in the shell take precedence.')}
          </p>
          <details style={{ marginTop: 6 }}>
            <summary className="small muted">{tr('Avançado: URL da API', 'Advanced: API URL')}</summary>
            <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
              <input className="in" style={{ flex: 1 }} aria-label="OPENROUTER_BASE_URL" placeholder={baseUrl?.valor}
                value={novaBase} onChange={(e) => setNovaBase(e.target.value)} />
              <button className="btn" disabled={!novaBase.trim() || salvandoChave}
                onClick={() => gravarEnv({ OPENROUTER_BASE_URL: novaBase.trim() })}>{tr('Salvar', 'Save')}</button>
              {baseUrl?.origem === '.env' ? (
                <button className="btn" onClick={() => gravarEnv({ OPENROUTER_BASE_URL: null })}>{tr('Padrão', 'Default')}</button>
              ) : null}
            </div>
          </details>
        </section>

        {/* ── 2. models ── */}
        <section className="card" aria-labelledby="cfg-modelos">
          <div className="card-h">
            <h2 className="h2" id="cfg-modelos">{tr('Modelos', 'Models')}</h2>
            {y?.estrategia ? <span className="tag">{y.estrategia}</span> : null}
            {y?.hash ? <span className="mono faint small">hash {y.hash}</span> : null}
            <span style={{ flex: 1 }} />
            <span className="small muted">
              {cat.dados?.atualizado_em ? `${tr('Catálogo de', 'Catalog from')} ${fmt.data(cat.dados.atualizado_em)} · ${fmt.int(cat.dados.modelos.length)} ${tr('modelos', 'models')}` : ''}
            </span>
            <button className="btn btn-s" onClick={() => setAtualizar((n) => n + 1)} disabled={cat.carregando}
              title={tr('Baixar o catálogo de novo', 'Download the catalog again')}>
              <RefreshCw size={13} />{tr('Atualizar', 'Refresh')}
            </button>
          </div>
          {cat.erro ? <Nota tipo="erro">{cat.erro}</Nota> : null}
          {cat.dados?.erro ? <Nota>{tr('Não deu para baixar o catálogo; usando a cópia salva.', 'Could not download the catalog; using the saved copy.')} {cat.dados.erro}</Nota> : null}
          {y && !y.valido ? (
            <Nota tipo="erro">{y.erro}<br />{tr('Escolha os quatro modelos abaixo e salve para corrigir.', 'Choose the four models below and save to fix it.')}</Nota>
          ) : null}
          <datalist id="catalogo-openrouter">
            {(cat.dados?.modelos ?? []).map((m) => <option key={m.id} value={m.id} label={`${m.nome} · ${precoTxt(m)}`} />)}
          </datalist>
          <div style={{ display: 'grid', gap: 10, marginTop: 10 }}>
            {PAPEIS.map((p) => {
              const id = (escolha[p.rot] ?? '').trim()
              const m = porId.get(id)
              const fora = id && cat.dados && cat.dados.modelos.length > 0 && !m
              return (
                <label key={p.rot} className="field">
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <span className="tag">{p.rot}</span>{tr(p.pt, p.en)}
                  </span>
                  <input className="in mono" list="catalogo-openrouter" autoComplete="off" spellCheck={false}
                    placeholder={p.rot === 'V' ? tr('vazio = sem verificador', 'empty = no verifier') : tr('busque por nome ou id, ex.: anthropic/', 'search by name or id, e.g. anthropic/')}
                    value={escolha[p.rot] ?? ''} onChange={(e) => setEscolha((s) => ({ ...s, [p.rot]: e.target.value }))} />
                  <span className="small" style={{ color: fora ? 'var(--danger-fg)' : 'var(--text-muted)' }}>
                    {fora ? tr('Não está no catálogo do OpenRouter.', 'Not in the OpenRouter catalog.')
                      : m ? `${m.nome} · ${precoTxt(m)}${m.contexto ? ` · ${fmt.tokens(m.contexto)} ${tr('de contexto', 'context')}` : ''}`
                        : p.rot === 'V' && !id ? tr('Sem verificador, v = 1 em todas as células (aparece no relatório).', 'Without a verifier, v = 1 in every cell (stated in the report).') : ''}
                  </span>
                </label>
              )
            })}
          </div>
          {vendors.size > 0 && vendors.size < 3 ? (
            <Nota tipo="info">{tr('Modelos de três fornecedores diferentes (anthropic/, openai/, google/…) erram de forma menos correlacionada.',
              'Models from three different vendors (anthropic/, openai/, google/…) make less correlated errors.')}</Nota>
          ) : null}
          {(y?.avisos ?? []).map((a) => <Nota key={a}>{a}</Nota>)}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', marginTop: 10 }}>
            <button className="btn btn-p" disabled={!mudou || salvandoModelos} onClick={salvarModelos}>
              {salvandoModelos ? tr('Salvando…', 'Saving…') : tr('Salvar modelos', 'Save models')}
            </button>
            {mudou ? <button className="btn" onClick={() => setEscolha(atuais)}>{tr('Desfazer', 'Undo')}</button> : null}
            <span className="small muted">
              {tr('Grava só o bloco modelos do', 'Writes only the modelos block of')} <span className="mono">{y?.caminho ?? 'lutz.yaml'}</span>.{' '}
              {tr('Execuções já iniciadas mantêm a configuração delas.', 'Runs already started keep their own settings.')}
            </span>
          </div>
        </section>

        {/* ── 3. usage ── */}
        <section className="card" aria-labelledby="cfg-consumo">
          <div className="card-h">
            <h2 className="h2" id="cfg-consumo">{tr('Consumo', 'Usage')}</h2>
            <span style={{ flex: 1 }} />
            <button className="btn btn-s" onClick={() => { conta.recarregar(); cons.recarregar() }}><RefreshCw size={13} />{tr('Atualizar', 'Refresh')}</button>
            <button className="btn btn-s" onClick={() => baixar(url('/consumo.csv'))}><Download size={14} />CSV</button>
          </div>

          <h3 className="small muted" style={{ margin: '12px 0 6px' }}>{tr('Conta no OpenRouter', 'OpenRouter account')}{c?.rotulo ? ` · ${c.rotulo}` : ''}</h3>
          {conta.carregando && !c ? <Carregando /> : conta.erro ? <Nota>{conta.erro}</Nota> : c ? (
            <div className="kpis">
              {c.saldo_usd != null ? <Kpi rotulo={tr('Saldo de créditos', 'Credit balance')} valor={fmt.usd(c.saldo_usd)}
                sub={`${fmt.usd(c.creditos_usados_usd)} ${tr('de', 'of')} ${fmt.usd(c.creditos_usd)} ${tr('usados', 'used')}`} /> : null}
              {c.limite_usd != null ? <Kpi rotulo={tr('Limite da chave', 'Key limit')} valor={fmt.usd(c.limite_restante_usd)}
                sub={`${tr('restam de', 'left of')} ${fmt.usd(c.limite_usd)}`} /> : null}
              <Kpi rotulo={tr('Gasto da chave', 'Key spend')} valor={fmt.usd(c.uso_usd)}
                sub={c.uso_mes_usd != null ? `${fmt.usd(c.uso_dia_usd)} ${tr('hoje', 'today')} · ${fmt.usd(c.uso_mes_usd)} ${tr('no mês', 'this month')}` : undefined} />
            </div>
          ) : null}

          <h3 className="small muted" style={{ margin: '14px 0 6px' }}>{tr('Este projeto', 'This project')}</h3>
          {cons.carregando && !cons.dados ? <Carregando /> : cons.erro ? <Nota tipo="erro">{cons.erro}</Nota> : total ? (
            <>
              <div className="kpis">
                <Kpi rotulo={tr('Custo', 'Cost')} valor={fmt.usd(total.custo_usd ?? 0)}
                  sub={orcamento != null ? `${tr('orçamento', 'budget')} ${fmt.usd(orcamento)}` : tr('sem orçamento', 'no budget')} />
                <Kpi rotulo={tr('Chamadas', 'Calls')} valor={fmt.int(total.chamadas)} sub={`${fmt.int(total.em_cache ?? 0)} ${tr('em cache', 'cached')}`} />
                <Kpi rotulo="Tokens" valor={fmt.tokens((total.tokens_entrada || 0) + (total.tokens_saida || 0))}
                  sub={total.sem_preco ? `${total.sem_preco} ${tr('chamadas sem preço', 'unpriced calls')}` : undefined} />
              </div>
              {cons.dados && cons.dados.por_papel.length ? (
                <div className="tablewrap" style={{ marginTop: 10 }}>
                  <table className="t">
                    <thead><tr><th>{tr('Papel', 'Role')}</th><th>{tr('Modelo pedido', 'Requested model')}</th><th>{tr('Observado', 'Observed')}</th>
                      <th className="num">{tr('Chamadas', 'Calls')}</th><th className="num">Tokens</th><th className="num">US$</th></tr></thead>
                    <tbody>
                      {cons.dados.por_papel.map((r, i) => (
                        <tr key={i}><td>{r.papel} <span className="tag">{r.rotulo}</span></td><td className="mono small">{r.modelo_pedido}</td>
                          <td className="mono small">{r.modelo_observado || '—'}</td><td className="num">{r.chamadas}</td>
                          <td className="num">{fmt.tokens((r.tokens_entrada || 0) + (r.tokens_saida || 0))}</td>
                          <td className="num">{r.custo_usd == null ? '?' : fmt.num(r.custo_usd, 4)}</td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : <p className="sub small">{tr('Nenhuma chamada ainda.', 'No calls yet.')}</p>}
              {cons.dados && cons.dados.chamadas.length ? (
                <details style={{ marginTop: 8 }}>
                  <summary className="small muted">{tr('Chamadas recentes', 'Recent calls')}</summary>
                  <div className="tablewrap scroll" style={{ marginTop: 8 }}>
                    <table className="t">
                      <thead><tr><th>{tr('Quando', 'When')}</th><th>{tr('Exec.', 'Run')}</th><th>{tr('Papel', 'Role')}</th><th>{tr('Artigo', 'Article')}</th>
                        <th>{tr('Modelo', 'Model')}</th><th className="num">Tokens</th><th className="num">US$</th><th>Status</th></tr></thead>
                      <tbody>
                        {cons.dados.chamadas.map((x) => (
                          <tr key={x.id}><td className="small mono">{fmt.data(x.criado_em)}</td><td className="num">{x.execucao_id ?? '—'}</td>
                            <td>{x.rotulo}{x.cache ? <span className="tag tag-g" style={{ marginLeft: 4 }}>cache</span> : null}</td>
                            <td className="mono small">{x.artigo ?? '—'}</td><td className="mono small">{x.modelo_pedido}</td>
                            <td className="num">{fmt.tokens(x.tokens_entrada + x.tokens_saida)}</td>
                            <td className="num">{x.custo_usd == null ? '?' : fmt.num(x.custo_usd, 4)}</td>
                            <td><span className={`tag ${x.status === 'ok' ? 'tag-s' : 'tag-d'}`}>{x.status}</span></td></tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ) : null}
            </>
          ) : null}
        </section>

        {/* ── language ── */}
        <section className="card grid2" aria-label={tr('Idioma', 'Language')}>
          <label className="field">
            <span>{tr('Idioma da interface', 'Interface language')}</span>
            <select className="sel-in" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              <option value="pt">Português</option>
              <option value="en">English</option>
            </select>
          </label>
          <div className="field">
            <span>{tr('Idiomas do relatório', 'Report languages')}</span>
            <div className="small muted">{(y?.idiomas ?? []).join(', ') || '—'} · {tr('definidos em relatorio.idiomas no lutz.yaml', 'set in relatorio.idiomas in lutz.yaml')}</div>
          </div>
        </section>
      </div>
    </Modal>
  )
}
