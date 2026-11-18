// Configuration mechanism kept from Lutz 0.5: the modal reads and writes the project .env through /config.
// Models, thresholds and budget live in lutz.yaml and are shown read-only.
import { useState } from 'react'
import { Download } from 'lucide-react'
import { api, url, type Config, type Consumo } from '../api'
import { useApp, type Lang } from '../app-context'
import { Carregando, Modal, Nota, baixar, useCarregar, useFmt } from './ui'

type Aba = 'chaves' | 'modelos' | 'idioma' | 'consumo'

const ORIGEM: Record<string, [string, string, string]> = {
  processo: ['tag-w', 'terminal', 'shell'],
  '.env': ['tag-s', '.env', '.env'],
  padrao: ['tag-g', 'padrão', 'default'],
  ausente: ['tag-d', 'ausente', 'missing'],
}

export function SettingsModal({ onFechar, inicial = 'chaves' }: { onFechar: () => void; inicial?: Aba }) {
  const { tr, lang, setLang, avisar } = useApp()
  const fmt = useFmt()
  const [aba, setAba] = useState<Aba>(inicial)
  const cfg = useCarregar(() => api.get<Config>('/config'), [])
  const cons = useCarregar(() => (aba === 'consumo' ? api.get<Consumo>('/consumo?limite=100') : Promise.resolve(null)), [aba])
  const [form, setForm] = useState<Record<string, string>>({})
  const [limpar, setLimpar] = useState<Set<string>>(new Set())
  const [salvando, setSalvando] = useState(false)
  const [erro, setErro] = useState('')

  async function salvar() {
    setSalvando(true)
    setErro('')
    try {
      const body: Record<string, string | null> = {}
      for (const [k, v] of Object.entries(form)) if (v.trim()) body[k] = v.trim()
      for (const k of limpar) body[k] = null
      if (Object.keys(body).length === 0) {
        onFechar()
        return
      }
      const r = await api.put<{ ok: boolean; sombreadas: string[] }>('/config', body)
      if (r.sombreadas.length)
        avisar(tr(`Gravado no .env, mas ${r.sombreadas.join(', ')} também está definida no terminal, que tem precedência.`,
          `Saved to .env, but ${r.sombreadas.join(', ')} is also set in the shell, which takes precedence.`), true)
      else avisar(tr('Configuração salva no .env.', 'Settings saved to .env.'))
      setForm({})
      setLimpar(new Set())
      cfg.recarregar(true)
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setSalvando(false)
    }
  }

  const aba_ = (id: Aba, rot: string) => (
    <button className={`tab${aba === id ? ' on' : ''}`} onClick={() => setAba(id)} role="tab" aria-selected={aba === id}>
      {rot}
    </button>
  )
  const y = cfg.dados?.lutz_yaml

  return (
    <Modal titulo={tr('Configurações', 'Settings')}
      sub={tr('Segredos e URLs ficam no .env do projeto; modelos e limiares no lutz.yaml.',
        'Secrets and URLs live in the project .env; models and thresholds in lutz.yaml.')}
      onFechar={onFechar}
      rodape={aba === 'chaves' ? (
        <>
          <button className="btn btn-p" onClick={salvar} disabled={salvando}>{salvando ? tr('Salvando…', 'Saving…') : tr('Salvar', 'Save')}</button>
          {erro ? <span style={{ color: 'var(--danger-fg)' }}>{erro}</span> : null}
        </>
      ) : undefined}>
      <div className="tabs" role="tablist">
        {aba_('chaves', tr('Chaves e URLs', 'Keys and URLs'))}
        {aba_('modelos', tr('Modelos (lutz.yaml)', 'Models (lutz.yaml)'))}
        {aba_('idioma', tr('Idioma', 'Language'))}
        {aba_('consumo', tr('Consumo', 'Usage'))}
      </div>
      <div className="modal-b">
        {cfg.carregando && !cfg.dados ? <Carregando /> : cfg.erro ? <Nota tipo="erro">{cfg.erro}</Nota> : null}

        {aba === 'chaves' && cfg.dados ? (
          <>
            <p className="sub">{tr('Variáveis exportadas no terminal têm precedência sobre o .env. Valores secretos aparecem mascarados.',
              'Variables exported in the shell take precedence over .env. Secret values are masked.')}</p>
            {cfg.dados.env.map((v) => {
              const [cls, pt, en] = ORIGEM[v.origem] ?? ['tag-g', v.origem, v.origem]
              const vaiLimpar = limpar.has(v.nome)
              return (
                <div key={v.nome} className="field">
                  <span style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    {v.rotulo} <span className="mono faint">{v.nome}</span>
                    <span className={`tag ${cls}`}>{tr(pt, en)}</span>
                  </span>
                  <div style={{ display: 'flex', gap: 8 }}>
                    <input className="in" type={v.segredo ? 'password' : 'text'} autoComplete="off"
                      aria-label={v.nome}
                      placeholder={vaiLimpar ? tr('será removida', 'will be removed') : v.valor || (v.segredo ? 'sk-…' : '')}
                      value={form[v.nome] ?? ''} disabled={vaiLimpar}
                      onChange={(e) => setForm((f) => ({ ...f, [v.nome]: e.target.value }))} />
                    {v.origem === '.env' ? (
                      <button className={`btn btn-s${vaiLimpar ? ' btn-d' : ''}`} onClick={() => setLimpar((s) => {
                        const n = new Set(s)
                        if (n.has(v.nome)) n.delete(v.nome)
                        else n.add(v.nome)
                        return n
                      })}>{vaiLimpar ? tr('Manter', 'Keep') : tr('Limpar', 'Clear')}</button>
                    ) : null}
                  </div>
                  {v.origem === 'processo' ? (
                    <span className="small" style={{ color: 'var(--warning-fg)' }}>
                      {tr('Definida no ambiente do terminal: editar o .env não muda o valor usado.',
                        'Set in the shell environment: editing .env does not change the value in use.')}
                    </span>
                  ) : null}
                </div>
              )
            })}
          </>
        ) : null}

        {aba === 'modelos' && y ? (
          <>
            <Nota tipo="info">
              {tr('Somente leitura. Edite no seu editor', 'Read-only. Edit it in your editor')}: <span className="mono">{y.caminho}</span>.{' '}
              {tr('A configuração resolvida e o hash entram em cada execução e no relatório.',
                'The resolved settings and their hash are stored with every run and cited in the report.')}
            </Nota>
            {!y.valido ? <Nota tipo="erro">{y.erro}</Nota> : (
              <>
                <div className="card">
                  <div className="card-h">
                    <h2 className="h2">{tr('Papéis', 'Roles')}</h2>
                    <span className="tag">{y.estrategia}</span>
                    <span className="mono faint small">hash {y.hash}</span>
                    <span style={{ flex: 1 }} />
                    <span className="small muted">{tr('Orçamento', 'Budget')}: {y.orcamento_usd == null ? '—' : fmt.usd(y.orcamento_usd)}</span>
                  </div>
                  <div className="tablewrap">
                    <table className="t">
                      <thead><tr><th>{tr('Papel', 'Role')}</th><th>{tr('Provedor', 'Provider')}</th><th>{tr('Modelo', 'Model')}</th><th>Temp.</th><th>Prompt</th><th>max_tokens</th></tr></thead>
                      <tbody>
                        {(y.papeis ?? []).map((p) => (
                          <tr key={p.rotulo}>
                            <td><span className="tag">{p.rotulo}</span></td><td>{p.provedor}</td><td className="mono small">{p.modelo}</td>
                            <td className="num">{p.temperatura == null ? 'n/a' : p.temperatura}</td><td className="small">{p.variante_prompt}</td>
                            <td className="num">{p.max_tokens}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                  {(y.avisos ?? []).map((a) => <Nota key={a}>{a}</Nota>)}
                </div>
              </>
            )}
            <pre className="con" style={{ maxHeight: 320 }}>{y.texto}</pre>
          </>
        ) : null}

        {aba === 'idioma' ? (
          <div className="grid2">
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
          </div>
        ) : null}

        {aba === 'consumo' ? (
          cons.carregando && !cons.dados ? <Carregando /> : cons.erro ? <Nota tipo="erro">{cons.erro}</Nota> : cons.dados ? (
            <>
              <div className="kpis">
                <div className="kpi"><div className="lbl">{tr('Chamadas', 'Calls')}</div><div className="kv">{fmt.int(cons.dados.total.chamadas)}</div>
                  <div className="kv-sub">{fmt.int(cons.dados.total.em_cache ?? 0)} {tr('em cache', 'cached')}</div></div>
                <div className="kpi"><div className="lbl">Tokens</div><div className="kv">{fmt.tokens((cons.dados.total.tokens_entrada || 0) + (cons.dados.total.tokens_saida || 0))}</div></div>
                <div className="kpi"><div className="lbl">{tr('Custo', 'Cost')}</div><div className="kv">{fmt.usd(cons.dados.total.custo_usd ?? 0)}</div>
                  {cons.dados.total.sem_preco ? <div className="kv-sub">{cons.dados.total.sem_preco} {tr('sem preço', 'unpriced')}</div> : null}</div>
              </div>
              <div className="card">
                <h2 className="h2">{tr('Por papel e modelo', 'By role and model')}</h2>
                <div className="tablewrap">
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
              </div>
              <div className="card">
                <div className="card-h"><h2 className="h2">{tr('Chamadas recentes', 'Recent calls')}</h2><span style={{ flex: 1 }} />
                  <button className="btn btn-s" onClick={() => baixar(url('/consumo.csv'))}><Download size={14} />CSV</button></div>
                <div className="tablewrap scroll">
                  <table className="t">
                    <thead><tr><th>{tr('Quando', 'When')}</th><th>{tr('Exec.', 'Run')}</th><th>{tr('Papel', 'Role')}</th><th>{tr('Artigo', 'Article')}</th>
                      <th>{tr('Modelo', 'Model')}</th><th className="num">Tokens</th><th className="num">US$</th><th>Status</th></tr></thead>
                    <tbody>
                      {cons.dados.chamadas.map((c) => (
                        <tr key={c.id}><td className="small mono">{fmt.data(c.criado_em)}</td><td className="num">{c.execucao_id ?? '—'}</td>
                          <td>{c.rotulo}{c.cache ? <span className="tag tag-g" style={{ marginLeft: 4 }}>cache</span> : null}</td>
                          <td className="mono small">{c.artigo ?? '—'}</td><td className="mono small">{c.modelo_pedido}</td>
                          <td className="num">{fmt.tokens(c.tokens_entrada + c.tokens_saida)}</td>
                          <td className="num">{c.custo_usd == null ? '?' : fmt.num(c.custo_usd, 4)}</td>
                          <td><span className={`tag ${c.status === 'ok' ? 'tag-s' : 'tag-d'}`}>{c.status}</span></td></tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : null
        ) : null}
      </div>
    </Modal>
  )
}
