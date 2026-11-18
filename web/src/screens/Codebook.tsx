import { useEffect, useMemo, useState } from 'react'
import { Check, Download, FlaskConical, Lock, Plus, Sparkles, Trash2, Upload, Wand2 } from 'lucide-react'
import { api, esperarJob, type Achado, type Campo, type CodebookPayload, type TipoCampo, type VersaoCodebook } from '../api'
import { useApp } from '../app-context'
import { Cabecalho, Carregando, Modal, Nota, Vazio, useCarregar, useFmt } from '../components/ui'

const TIPOS: TipoCampo[] = ['categorico', 'ordinal', 'numerico', 'texto']

function limparCampo(c: Campo): Campo {
  // Only the attributes the backend schema accepts.
  const out: Campo = { nome: c.nome, tipo: c.tipo, instrucao: c.instrucao }
  if (c.rotulo) out.rotulo = c.rotulo
  if (c.valores?.length) out.valores = c.valores
  if (c.definicoes && Object.keys(c.definicoes).length) out.definicoes = c.definicoes
  if (c.exemplos?.length) out.exemplos = c.exemplos
  if (c.secoes?.length) out.secoes = c.secoes
  if (c.se_ausente) out.se_ausente = c.se_ausente
  if (c.tolerancia_relativa) out.tolerancia_relativa = c.tolerancia_relativa
  if (c.faixa) out.faixa = c.faixa
  if (c.unidade) out.unidade = c.unidade
  if (c.papel) out.papel = c.papel
  if (c.motivo_exclusao) out.motivo_exclusao = c.motivo_exclusao
  if (c.regras?.length) out.regras = c.regras
  out.origem = c.origem ?? 'manual'
  return out
}

function baixarTexto(nome: string, texto: string, tipo = 'text/yaml') {
  const url = URL.createObjectURL(new Blob([texto], { type: tipo }))
  const a = document.createElement('a')
  a.href = url
  a.download = nome
  a.click()
  URL.revokeObjectURL(url)
}

interface ResultadoTeste {
  chave: string; campo_chave: string; valor_final: string | null; nao_reportado: number; trecho: string | null
  pagina: number | null; e: number | null; e_detalhe: string | null; erro: string | null; regras_detalhe: string | null
}

export function Codebook() {
  const { tr, avisar, recarregarProjeto, recarregarJobs, projeto } = useApp()
  const fmt = useFmt()
  const atual = useCarregar(() => api.get<CodebookPayload | null>('/codebooks/atual'), [])
  const versoes = useCarregar(() => api.get<VersaoCodebook[]>('/codebooks'), [])
  const [campos, setCampos] = useState<Campo[]>([])
  const [descricao, setDescricao] = useState('')
  const [nota, setNota] = useState('')
  const [sujo, setSujo] = useState(false)
  const [sel, setSel] = useState<number | null>(null)
  const [achados, setAchados] = useState<Achado[]>([])
  const [semanticos, setSemanticos] = useState<Achado[]>([])
  const [sugestoes, setSugestoes] = useState<Campo[]>([])
  const [ocupado, setOcupado] = useState('')
  const [importar, setImportar] = useState(false)
  const [verVersao, setVerVersao] = useState<number | null>(null)
  const [teste, setTeste] = useState<{ campo: string; rodando: boolean; res: ResultadoTeste[]; custo?: number | null; erro?: string } | null>(null)

  useEffect(() => {
    if (atual.dados && !sujo) {
      setCampos(atual.dados.campos.map(limparCampo))
      setDescricao(atual.dados.descricao ?? '')
      setAchados(atual.dados.lint)
      setSel((s) => (s === null && atual.dados && atual.dados.campos.length ? 0 : s))
    }
  }, [atual.dados, sujo])

  // Live deterministic lint (no tokens).
  useEffect(() => {
    if (!sujo) return
    const t = window.setTimeout(async () => {
      try {
        const r = await api.post<{ achados: Achado[] }>('/codebooks/lint', { campos: campos.map(limparCampo), descricao })
        setAchados(r.achados)
      } catch (e) {
        setAchados([{ campo: null, codigo: 'API', severidade: 'erro', mensagem: (e as Error).message }])
      }
    }, 500)
    return () => window.clearTimeout(t)
  }, [campos, descricao, sujo])

  const mudar = (i: number, patch: Partial<Campo>) => {
    setCampos((cs) => cs.map((c, j) => (j === i ? { ...c, ...patch } : c)))
    setSujo(true)
  }

  async function salvar() {
    setOcupado('salvar')
    try {
      const r = await api.put<CodebookPayload>('/codebooks/rascunho', { campos: campos.map(limparCampo), descricao, nota })
      setSujo(false)
      atual.setDados(r)
      setAchados(r.lint)
      versoes.recarregar(true)
      recarregarProjeto()
      avisar(tr(`Rascunho v${r.versao} salvo · ${r.hash}`, `Draft v${r.versao} saved · ${r.hash}`))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado('')
    }
  }

  async function congelar() {
    if (!window.confirm(tr('Congelar esta versão? Ela passa a valer para extração e piloto e não pode mais ser editada.',
      'Freeze this version? It becomes the version used by extraction and the pilot and can no longer be edited.'))) return
    setOcupado('congelar')
    try {
      const r = await api.post<CodebookPayload>('/codebooks/congelar', {})
      atual.setDados(r)
      versoes.recarregar(true)
      recarregarProjeto()
      avisar(tr(`Codebook v${r.versao} congelado · ${r.hash}`, `Codebook v${r.versao} frozen · ${r.hash}`))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado('')
    }
  }

  async function lintSemantico() {
    if (!window.confirm(tr('O lint semântico chama um modelo e gasta tokens. Continuar?', 'Semantic lint calls a model and spends tokens. Continue?'))) return
    setOcupado('semantico')
    try {
      const r = await api.post<{ achados: Achado[] }>('/codebooks/lint?semantico=true', { campos: campos.map(limparCampo), descricao })
      setSemanticos(r.achados.filter((a) => a.codigo.startsWith('S')))
      setAchados(r.achados.filter((a) => !a.codigo.startsWith('S')))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado('')
    }
  }

  async function testar(campo: string) {
    setTeste({ campo, rodando: true, res: [] })
    try {
      const { job_id } = await api.post<{ job_id: string }>('/codebooks/teste', { campos: [campo], n: 3 })
      recarregarJobs()
      const j = await esperarJob(job_id)
      const r = j.resultado as { resultados: ResultadoTeste[]; estimativa: { custo_usd: number | null } }
      setTeste({ campo, rodando: false, res: r.resultados, custo: r.estimativa?.custo_usd })
      atual.recarregar(true)
      recarregarProjeto()
    } catch (e) {
      setTeste({ campo, rodando: false, res: [], erro: (e as Error).message })
    } finally {
      recarregarJobs()
    }
  }

  const porCampo = useMemo(() => {
    const m: Record<string, Achado[]> = {}
    for (const a of [...achados, ...semanticos]) (m[a.campo ?? '-'] ??= []).push(a)
    return m
  }, [achados, semanticos])
  const nErros = achados.filter((a) => a.severidade === 'erro').length
  const congelado = !!atual.dados?.congelado && !sujo
  const campo = sel !== null ? campos[sel] : null

  return (
    <>
      <Cabecalho titulo="Codebook"
        sub={tr('O formulário de extração. Cada campo vira uma coluna, e o tipo do campo decide a estatística de concordância.',
          'The extraction form. Each field becomes a column, and the field type decides the agreement statistic.')}>
        <button className="btn" onClick={() => setImportar(true)}><Upload size={15} />{tr('Importar YAML', 'Import YAML')}</button>
        <button className="btn" disabled={!atual.dados} onClick={() => atual.dados && baixarTexto(`codebook_v${atual.dados.versao}.yaml`, atual.dados.yaml)}>
          <Download size={15} />{tr('Exportar YAML', 'Export YAML')}
        </button>
        <button className="btn" onClick={salvar} disabled={!sujo || ocupado !== '' || nErros > 0}>
          {ocupado === 'salvar' ? tr('Salvando…', 'Saving…') : tr('Salvar rascunho', 'Save draft')}
        </button>
        <button className="btn btn-p" onClick={congelar} disabled={sujo || !atual.dados || !!atual.dados?.congelado || ocupado !== ''}>
          <Lock size={15} />{atual.dados && !atual.dados.congelado ? `${tr('Congelar', 'Freeze')} v${atual.dados.versao}` : tr('Congelar', 'Freeze')}
        </button>
      </Cabecalho>

      {atual.erro ? <Nota tipo="erro">{atual.erro}</Nota> : null}
      {congelado ? (
        <Nota tipo="info">{tr(`A versão v${atual.dados?.versao} está congelada (hash ${atual.dados?.hash}). Editar e salvar cria uma versão nova; execuções e piloto continuam ligados à versão exata.`,
          `Version v${atual.dados?.versao} is frozen (hash ${atual.dados?.hash}). Editing and saving creates a new version; runs and the pilot stay tied to the exact version.`)}</Nota>
      ) : null}

      <Assistente existentes={campos.map((c) => c.nome)} perguntaInicial={projeto?.pergunta ?? ''}
        onSugestoes={(s) => setSugestoes((x) => [...x, ...s.filter((c) => !campos.some((y) => y.nome === c.nome) && !x.some((y) => y.nome === c.nome))])} />

      {sugestoes.length ? (
        <section className="card">
          <div className="card-h">
            <Sparkles size={16} color="var(--lutz-600)" />
            <h2 className="h2">{tr('Sugestões do Assistente', 'Assistant suggestions')}</h2>
            <span className="small muted">{tr('sugere · você decide. Nada entra no codebook sem confirmação.', 'suggests · you decide. Nothing enters the codebook without confirmation.')}</span>
            <span style={{ flex: 1 }} />
            <button className="btn btn-s" onClick={() => setSugestoes([])}>{tr('Descartar todas', 'Discard all')}</button>
          </div>
          <div className="grid2">
            {sugestoes.map((s) => (
              <div key={s.nome} className="fcard sug" style={{ cursor: 'default' }}>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                  <strong>{s.rotulo || s.nome}</strong><span className="tag tag-g">{s.tipo}</span><span className="tag">Assistente</span>
                </div>
                <div className="mono small faint">{s.nome}</div>
                <div className="small">{s.instrucao}</div>
                {s.valores?.length ? <div className="small muted">{s.valores.join(' · ')}</div> : null}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-s btn-p" onClick={() => {
                    setCampos((cs) => [...cs, { ...s, origem: 'assistente' }])
                    setSel(campos.length)
                    setSujo(true)
                    setSugestoes((x) => x.filter((y) => y.nome !== s.nome))
                  }}><Check size={14} />{tr('Aceitar', 'Accept')}</button>
                  <button className="btn btn-s" onClick={() => {
                    setCampos((cs) => [...cs, { ...s, origem: 'assistente' }])
                    setSel(campos.length)
                    setSujo(true)
                    setSugestoes((x) => x.filter((y) => y.nome !== s.nome))
                  }}>{tr('Aceitar e editar', 'Accept and edit')}</button>
                  <button className="btn btn-s" onClick={() => setSugestoes((x) => x.filter((y) => y.nome !== s.nome))}>{tr('Descartar', 'Discard')}</button>
                </div>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <section className="row">
        <div className="card" style={{ flex: '1 1 340px' }}>
          <div className="card-h">
            <h2 className="h2">{tr('Campos', 'Fields')}{atual.dados ? ` · ${atual.dados.congelado && !sujo ? '' : tr('rascunho', 'draft') + ' '}v${atual.dados.versao}` : ''}</h2>
            <span className="small muted">{campos.length} {tr('campos', 'fields')}{sujo ? ` · ${tr('não salvo', 'unsaved')}` : ''}</span>
            <span style={{ flex: 1 }} />
            <button className="btn btn-s" onClick={() => {
              setCampos((cs) => [...cs, { nome: `campo_${cs.length + 1}`, tipo: 'categorico', instrucao: '', valores: [], origem: 'manual' }])
              setSel(campos.length)
              setSujo(true)
            }}><Plus size={14} />{tr('Novo campo', 'New field')}</button>
          </div>
          <label className="field">
            <span>{tr('Descrição', 'Description')}</span>
            <input className="in" value={descricao} onChange={(e) => { setDescricao(e.target.value); setSujo(true) }} />
          </label>
          {atual.carregando && !atual.dados ? <Carregando /> : campos.length === 0 ? (
            <Vazio titulo={tr('Nenhum campo ainda', 'No fields yet')}>
              {tr('Use o Assistente acima, importe um YAML ou crie um campo.', 'Use the Assistant above, import a YAML or create a field.')}
            </Vazio>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {campos.map((c, i) => {
                const ach = porCampo[c.nome] ?? []
                const pior = ach.some((a) => a.severidade === 'erro') ? 'erro' : ach.some((a) => a.severidade === 'aviso') ? 'aviso' : ach.length ? 'sugestao' : ''
                return (
                  <div key={i} className={`fcard${sel === i ? ' on' : ''}`} role="button" tabIndex={0}
                    onClick={() => setSel(i)} onKeyDown={(e) => e.key === 'Enter' && setSel(i)}>
                    <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                      <strong>{c.rotulo || c.nome}</strong>
                      <span className="tag tag-g">{c.tipo}</span>
                      {c.origem === 'assistente' ? <span className="tag">Assistente</span> : <span className="tag tag-g">{tr('manual', 'manual')}</span>}
                      {pior ? <span className={`tag ${pior === 'erro' ? 'tag-d' : pior === 'aviso' ? 'tag-w' : 'tag-g'}`}>lint: {ach.length}</span> : null}
                      {atual.dados?.campos.find((x) => x.nome === c.nome)?.testado ? <span className="tag tag-s">{tr('testado', 'tested')}</span> : null}
                    </div>
                    <div className="mono small faint">{c.nome}</div>
                    <div className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.instrucao || <span className="faint">{tr('sem instrução', 'no instruction')}</span>}</div>
                  </div>
                )
              })}
            </div>
          )}
          <div className={`small ${nErros ? '' : 'muted'}`} style={nErros ? { color: 'var(--danger-fg)' } : undefined}>
            {tr('Lint do codebook inteiro', 'Whole-codebook lint')}: {nErros} {tr('erro(s)', 'error(s)')} · {achados.filter((a) => a.severidade === 'aviso').length} {tr('aviso(s)', 'warning(s)')} · {achados.filter((a) => a.severidade === 'sugestao').length} {tr('sugestão(ões)', 'suggestion(s)')}
            {porCampo['-']?.length ? ` · ${porCampo['-'].map((a) => a.mensagem).join('; ')}` : ''}
          </div>
          <button className="btn btn-s" onClick={lintSemantico} disabled={!campos.length || ocupado !== ''}>
            <Wand2 size={14} />{ocupado === 'semantico' ? tr('Analisando…', 'Analysing…') : tr('Lint semântico (LLM, gasta tokens)', 'Semantic lint (LLM, spends tokens)')}
          </button>
        </div>

        <div style={{ flex: '2 1 460px', display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          {campo && sel !== null ? (
            <>
              <EditorCampo campo={campo} achados={porCampo[campo.nome] ?? []} todos={campos.map((c) => c.nome)}
                onMudar={(p) => mudar(sel, p)}
                onRemover={() => { setCampos((cs) => cs.filter((_, j) => j !== sel)); setSel(null); setSujo(true) }} />
              <section className="card">
                <div className="card-h">
                  <FlaskConical size={16} color="var(--lutz-600)" />
                  <h2 className="h2">{tr('Teste rápido', 'Quick test')}</h2>
                  <span style={{ flex: 1 }} />
                  <button className="btn btn-s btn-p" disabled={sujo || !atual.dados || teste?.rodando || !(projeto?.artigos.prontos)}
                    onClick={() => testar(campo.nome)}>{tr('Rodar em 3 artigos', 'Run on 3 articles')}</button>
                </div>
                <p className="sub">{tr('Roda só este campo com E1 e mostra valor, trecho e página. Serve para ajustar a instrução; não conta como piloto e não entra no relatório. Os artigos usados ficam fora do sorteio do piloto.',
                  'Runs only this field with E1 and shows value, passage and page. It is for tuning the instruction; it does not count as a pilot and is not in the report. The articles used are excluded from the pilot draw.')}</p>
                {sujo ? <Nota>{tr('Salve o rascunho antes de testar: o teste usa a versão salva.', 'Save the draft before testing: the test uses the saved version.')}</Nota> : null}
                {!projeto?.artigos.prontos ? <Nota>{tr('Importe PDFs na Biblioteca para poder testar.', 'Import PDFs in the Library to test.')}</Nota> : null}
                {teste && teste.campo === campo.nome ? (
                  teste.rodando ? <Carregando texto={tr('Extraindo…', 'Extracting…')} /> : teste.erro ? <Nota tipo="erro">{teste.erro}</Nota> : (
                    <div className="tablewrap">
                      <table className="t">
                        <thead><tr><th>{tr('Artigo', 'Article')}</th><th>{tr('Valor', 'Value')}</th><th>{tr('Trecho', 'Passage')}</th><th className="num">{tr('Pág.', 'p.')}</th><th>{tr('Evidência', 'Evidence')}</th></tr></thead>
                        <tbody>
                          {teste.res.map((r, i) => (
                            <tr key={i}>
                              <td className="mono small">{r.chave}</td>
                              <td>{r.nao_reportado ? <span className="tag tag-g">{tr('não reportado', 'not reported')}</span> : r.valor_final ?? <span style={{ color: 'var(--danger-fg)' }}>{r.erro || r.regras_detalhe}</span>}</td>
                              <td className="small" style={{ maxWidth: 360 }}>{r.trecho ? <q>{r.trecho}</q> : '—'}</td>
                              <td className="num">{r.pagina ?? '—'}</td>
                              <td className="small">{r.e === null ? '—' : <><span className={`tag ${r.e >= 1 ? 'tag-s' : r.e > 0 ? 'tag-w' : 'tag-d'}`}>e={r.e}</span> {r.e_detalhe}</>}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {teste.custo !== undefined ? <div className="small faint">{tr('estimativa', 'estimate')}: {fmt.usd(teste.custo)}</div> : null}
                    </div>
                  )
                ) : null}
              </section>
            </>
          ) : (
            <section className="card"><Vazio titulo={tr('Selecione um campo', 'Select a field')} /></section>
          )}

          <section className="card">
            <div className="card-h"><h2 className="h2">{tr('Versões', 'Versions')}</h2></div>
            {versoes.dados?.length ? (
              <div className="tablewrap">
                <table className="t">
                  <thead><tr><th>{tr('Versão', 'Version')}</th><th>{tr('Estado', 'State')}</th><th>Hash</th><th className="num">{tr('Campos', 'Fields')}</th><th>{tr('Execuções', 'Runs')}</th><th>{tr('Nota', 'Note')}</th></tr></thead>
                  <tbody>
                    {[...versoes.dados].reverse().map((v) => (
                      <tr key={v.id} className="click" onClick={() => setVerVersao(v.versao)}>
                        <td className="mono">v{v.versao}</td>
                        <td>{v.congelado ? <span className="tag tag-s">{tr('congelada', 'frozen')}</span> : <span className="tag tag-w">{tr('rascunho', 'draft')}</span>}</td>
                        <td className="mono small">{v.hash}</td>
                        <td className="num">{v.n_campos}{v.n_assistente ? ` (${v.n_assistente} A)` : ''}</td>
                        <td className="small">{v.execucoes.join(', ') || '—'}</td>
                        <td className="small">{v.nota}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : <div className="faint small">{tr('Nenhuma versão salva.', 'No saved version.')}</div>}
            <label className="field">
              <span>{tr('Nota da próxima versão (o que mudou)', 'Note for the next version (what changed)')}</span>
              <input className="in" value={nota} onChange={(e) => { setNota(e.target.value) }} />
            </label>
          </section>
        </div>
      </section>

      {importar ? <ImportarYaml onFechar={() => setImportar(false)} onOk={(r) => { setSujo(false); atual.setDados(r); versoes.recarregar(true); recarregarProjeto() }} /> : null}
      {verVersao !== null ? <VerVersao versao={verVersao} onFechar={() => setVerVersao(null)} /> : null}
    </>
  )
}

function linhasDef(d: Record<string, string> | undefined) {
  return Object.entries(d ?? {}).map(([k, v]) => `${k}: ${v}`).join('\n')
}

function EditorCampo({ campo, achados, todos, onMudar, onRemover }: {
  campo: Campo; achados: Achado[]; todos: string[]; onMudar: (p: Partial<Campo>) => void; onRemover: () => void
}) {
  const { tr } = useApp()
  const [regrasTxt, setRegrasTxt] = useState(JSON.stringify(campo.regras ?? [], null, 1))
  const [exemplosTxt, setExemplosTxt] = useState((campo.exemplos ?? []).map((e) => `${e.trecho} => ${e.valor}`).join('\n'))
  const [defs, setDefs] = useState(linhasDef(campo.definicoes))
  const [erroRegras, setErroRegras] = useState('')
  const [valoresTxt, setValoresTxt] = useState((campo.valores ?? []).join(', '))
  const [secoesTxt, setSecoesTxt] = useState((campo.secoes ?? []).join(', '))
  useEffect(() => {
    setRegrasTxt(JSON.stringify(campo.regras ?? [], null, 1))
    setExemplosTxt((campo.exemplos ?? []).map((e) => `${e.trecho} => ${e.valor}`).join('\n'))
    setDefs(linhasDef(campo.definicoes))
    setValoresTxt((campo.valores ?? []).join(', '))
    setSecoesTxt((campo.secoes ?? []).join(', '))
    setErroRegras('')
    // reset local text buffers when switching fields
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campo.nome])
  const cat = campo.tipo === 'categorico' || campo.tipo === 'ordinal'
  const lista = (s: string) => s.split(',').map((x) => x.trim()).filter(Boolean)
  return (
    <section className="card">
      <div className="card-h">
        <h2 className="h2">{campo.rotulo || campo.nome}</h2>
        {campo.origem === 'assistente' ? <span className="tag">Assistente</span> : null}
        <span style={{ flex: 1 }} />
        <button className="btn btn-s btn-d" onClick={onRemover}><Trash2 size={14} />{tr('Remover', 'Remove')}</button>
      </div>
      {achados.map((a, i) => (
        <div key={i} className={a.severidade === 'erro' ? 'err' : a.severidade === 'aviso' ? 'note' : 'info'} style={{ padding: '6px 10px' }}>
          <span className="mono small">{a.codigo}</span> {a.mensagem}
        </div>
      ))}
      <div className="grid2">
        <label className="field"><span>{tr('Nome (identificador)', 'Name (identifier)')}</span>
          <input className="in mono" value={campo.nome} onChange={(e) => onMudar({ nome: e.target.value })} /></label>
        <label className="field"><span>{tr('Rótulo', 'Label')}</span>
          <input className="in" value={campo.rotulo ?? ''} onChange={(e) => onMudar({ rotulo: e.target.value })} /></label>
        <label className="field"><span>{tr('Tipo', 'Type')}</span>
          <select className="sel-in" value={campo.tipo} onChange={(e) => onMudar({ tipo: e.target.value as TipoCampo })}>
            {TIPOS.map((t) => <option key={t} value={t}>{t}</option>)}
          </select></label>
        <label className="field"><span>{tr('Papel no PRISMA', 'PRISMA role')}</span>
          <select className="sel-in" value={campo.papel ?? 'dado'} onChange={(e) => onMudar({ papel: e.target.value as Campo['papel'] })}>
            <option value="dado">{tr('dado', 'data item')}</option><option value="triagem">{tr('triagem', 'screening')}</option>
            <option value="criterio">{tr('critério', 'criterion')}</option><option value="risco_vies">{tr('risco de viés', 'risk of bias')}</option>
          </select></label>
      </div>
      <label className="field"><span>{tr('Instrução (o que extrair, em linguagem de quem pesquisa)', 'Instruction (what to extract)')}</span>
        <textarea className="ta" rows={3} value={campo.instrucao} onChange={(e) => onMudar({ instrucao: e.target.value })} /></label>
      {cat ? (
        <>
          <label className="field"><span>{campo.tipo === 'ordinal' ? tr('Valores em ordem (vírgulas)', 'Values in order (commas)') : tr('Valores aceitos (vírgulas)', 'Allowed values (commas)')}</span>
            <input className="in" value={valoresTxt} onChange={(e) => { setValoresTxt(e.target.value); onMudar({ valores: lista(e.target.value) }) }} /></label>
          <label className="field"><span>{tr('Definições (uma por linha: valor: definição)', 'Definitions (one per line: value: definition)')}</span>
            <textarea className="ta" rows={3} value={defs} onChange={(e) => {
              setDefs(e.target.value)
              const d: Record<string, string> = {}
              for (const l of e.target.value.split('\n')) {
                const i = l.indexOf(':')
                if (i > 0) d[l.slice(0, i).trim()] = l.slice(i + 1).trim()
              }
              onMudar({ definicoes: d })
            }} /></label>
        </>
      ) : null}
      {campo.tipo === 'numerico' ? (
        <div className="grid2">
          <label className="field"><span>{tr('Unidade', 'Unit')}</span>
            <input className="in" value={campo.unidade ?? ''} onChange={(e) => onMudar({ unidade: e.target.value })} /></label>
          <label className="field"><span>{tr('Faixa mínima', 'Range min')}</span>
            <input className="in" type="number" value={campo.faixa?.[0] ?? ''} onChange={(e) => onMudar({ faixa: e.target.value === '' ? null : [Number(e.target.value), campo.faixa?.[1] ?? Number(e.target.value)] })} /></label>
          <label className="field"><span>{tr('Faixa máxima', 'Range max')}</span>
            <input className="in" type="number" value={campo.faixa?.[1] ?? ''} onChange={(e) => onMudar({ faixa: e.target.value === '' ? null : [campo.faixa?.[0] ?? 0, Number(e.target.value)] })} /></label>
          <label className="field"><span>{tr('Tolerância relativa (0 = iguais)', 'Relative tolerance (0 = equal)')}</span>
            <input className="in" type="number" step="0.01" min="0" max="1" value={campo.tolerancia_relativa ?? 0} onChange={(e) => onMudar({ tolerancia_relativa: Number(e.target.value) })} /></label>
        </div>
      ) : null}
      <div className="grid2">
        <label className="field"><span>{tr('Onde procurar (seções, vírgulas)', 'Where to look (sections, commas)')}</span>
          <input className="in" value={secoesTxt} placeholder="Methods, Results" onChange={(e) => { setSecoesTxt(e.target.value); onMudar({ secoes: lista(e.target.value) }) }} /></label>
        <label className="field"><span>{tr('Se ausente', 'If absent')}</span>
          <input className="in mono" value={campo.se_ausente ?? 'nao_reportado'} onChange={(e) => onMudar({ se_ausente: e.target.value })} /></label>
      </div>
      <label className="field"><span>{tr('Exemplos (um por linha: trecho => valor)', 'Examples (one per line: passage => value)')}</span>
        <textarea className="ta" rows={2} value={exemplosTxt} onChange={(e) => {
          setExemplosTxt(e.target.value)
          onMudar({ exemplos: e.target.value.split('\n').filter((l) => l.includes('=>')).map((l) => {
            const [t, v] = l.split('=>')
            return { trecho: t.trim(), valor: v.trim() }
          }) })
        }} /></label>
      <label className="field"><span>{tr('Regras entre campos (JSON)', 'Cross-field rules (JSON)')} — soma_igual, menor_ou_igual, maior_ou_igual, requer, valor_implica</span>
        <textarea className="ta mono" rows={3} value={regrasTxt} onChange={(e) => {
          setRegrasTxt(e.target.value)
          try {
            const r = JSON.parse(e.target.value || '[]')
            if (!Array.isArray(r)) throw new Error(tr('use uma lista', 'use a list'))
            setErroRegras('')
            onMudar({ regras: r })
          } catch (err) {
            setErroRegras((err as Error).message)
          }
        }} /></label>
      {erroRegras ? <div className="small" style={{ color: 'var(--danger-fg)' }}>{erroRegras}</div> : null}
      <div className="small faint">{tr('Campos disponíveis para regras', 'Fields available for rules')}: <span className="mono">{todos.join(', ')}</span></div>
    </section>
  )
}

function Assistente({ existentes, perguntaInicial, onSugestoes }: {
  existentes: string[]; perguntaInicial: string; onSugestoes: (c: Campo[]) => void
}) {
  const { tr, avisar } = useApp()
  const modelos = useCarregar(() => api.get<{ id: string; rotulo: string; n_campos: number }[]>('/assistente/modelos'), [])
  const [aberto, setAberto] = useState(existentes.length === 0)
  const [pergunta, setPergunta] = useState(perguntaInicial)
  const [estrutura, setEstrutura] = useState<'PICO' | 'PCC'>('PICO')
  const [comp, setComp] = useState<Record<string, string>>({})
  const [variaveis, setVariaveis] = useState('')
  const [modelo, setModelo] = useState('')
  const [ocupado, setOcupado] = useState(false)
  useEffect(() => setPergunta((p) => p || perguntaInicial), [perguntaInicial])
  const nomes = estrutura === 'PICO' ? [['População', 'Population'], ['Intervenção', 'Intervention'], ['Comparação', 'Comparison'], ['Desfecho', 'Outcome']]
    : [['População', 'Population'], ['Conceito', 'Concept'], ['Contexto', 'Context']]

  async function partida(area: string) {
    setModelo(area)
    if (!area) return
    try {
      const r = await api.post<{ campos: Campo[] }>('/assistente/modelo', { area })
      onSugestoes(r.campos)
    } catch (e) {
      avisar((e as Error).message, true)
    }
  }
  async function sugerir() {
    setOcupado(true)
    try {
      const r = await api.post<{ campos: Campo[]; descartados: { campo: string; motivo: string }[] }>('/assistente/sugestoes', {
        pergunta, componentes: Object.fromEntries(nomes.map(([p]) => [p, comp[p] ?? ''])),
        variaveis: variaveis.split(',').map((x) => x.trim()).filter(Boolean), existentes,
      })
      onSugestoes(r.campos)
      if (r.descartados.length) avisar(tr(`${r.descartados.length} sugestão(ões) inválida(s) descartada(s).`, `${r.descartados.length} invalid suggestion(s) discarded.`), true)
      if (!r.campos.length) avisar(tr('O Assistente não sugeriu campos novos.', 'The Assistant suggested no new fields.'))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setOcupado(false)
    }
  }
  return (
    <section className="card">
      <div className="card-h">
        <Sparkles size={16} color="var(--lutz-600)" />
        <h2 className="h2">{tr('Assistente de Codebook', 'Codebook Assistant')}</h2>
        <span className="tag">{tr('sugere · você decide', 'suggests · you decide')}</span>
        <span style={{ flex: 1 }} />
        <button className="btn btn-s" onClick={() => setAberto((a) => !a)} aria-expanded={aberto}>{aberto ? tr('Recolher', 'Collapse') : tr('Abrir', 'Open')}</button>
      </div>
      {aberto ? (
        <>
          <label className="field"><span>{tr('Pergunta de pesquisa', 'Research question')}</span>
            <textarea className="ta" rows={2} value={pergunta} onChange={(e) => setPergunta(e.target.value)} /></label>
          <div style={{ display: 'flex', gap: 6 }}>
            {(['PICO', 'PCC'] as const).map((e) => <button key={e} className={`chipb${estrutura === e ? ' on' : ''}`} onClick={() => setEstrutura(e)}>{e}</button>)}
          </div>
          <div className="grid2">
            {nomes.map(([p, en]) => (
              <label key={p} className="field"><span>{tr(p, en)}</span>
                <input className="in" value={comp[p] ?? ''} onChange={(e) => setComp((c) => ({ ...c, [p]: e.target.value }))} /></label>
            ))}
          </div>
          <label className="field"><span>{tr('Variáveis que você já tem em mente (vírgulas)', 'Variables you already have in mind (commas)')}</span>
            <input className="in" value={variaveis} onChange={(e) => setVariaveis(e.target.value)} /></label>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
            <span className="lbl">{tr('Modelo de partida', 'Starting template')}</span>
            {(modelos.dados ?? []).map((m) => (
              <button key={m.id} className={`chipb${modelo === m.id ? ' on' : ''}`} onClick={() => partida(m.id)}>{m.rotulo}</button>
            ))}
          </div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
            <button className="btn btn-p" disabled={!pergunta.trim() || ocupado} onClick={sugerir}>
              <Sparkles size={15} />{ocupado ? tr('Pedindo sugestões…', 'Asking for suggestions…') : tr('Sugerir campos (LLM)', 'Suggest fields (LLM)')}
            </button>
            <span className="small faint">{tr('Uma chamada ao modelo J (ou V, ou E1). Gasta tokens.', 'One call to model J (or V, or E1). Spends tokens.')}</span>
          </div>
        </>
      ) : null}
    </section>
  )
}

function ImportarYaml({ onFechar, onOk }: { onFechar: () => void; onOk: (r: CodebookPayload) => void }) {
  const { tr, avisar } = useApp()
  const [texto, setTexto] = useState('')
  const [nota, setNota] = useState('')
  const [erro, setErro] = useState('')
  return (
    <Modal titulo={tr('Importar codebook YAML', 'Import codebook YAML')} onFechar={onFechar}
      rodape={<>
        <button className="btn btn-p" disabled={!texto.trim()} onClick={async () => {
          try {
            const r = await api.post<CodebookPayload>('/codebooks/importar', { yaml: texto, nota })
            avisar(tr(`Rascunho v${r.versao} importado.`, `Draft v${r.versao} imported.`))
            onOk(r)
            onFechar()
          } catch (e) {
            setErro((e as Error).message)
          }
        }}>{tr('Importar como rascunho', 'Import as draft')}</button>
        <input type="file" accept=".yaml,.yml,text/yaml" aria-label={tr('Arquivo YAML', 'YAML file')}
          onChange={async (e) => { const f = e.target.files?.[0]; if (f) setTexto(await f.text()) }} />
      </>}>
      <div className="modal-b">
        {erro ? <Nota tipo="erro">{erro}</Nota> : null}
        <textarea className="ta mono" rows={16} value={texto} onChange={(e) => setTexto(e.target.value)} placeholder={'campos:\n  - nome: desenho_estudo\n    tipo: categorico\n    valores: [experimental, observacional, outro]\n    instrucao: Classifique o desenho do estudo.'} />
        <label className="field"><span>{tr('Nota (o que mudou)', 'Note (what changed)')}</span><input className="in" value={nota} onChange={(e) => setNota(e.target.value)} /></label>
      </div>
    </Modal>
  )
}

function VerVersao({ versao, onFechar }: { versao: number; onFechar: () => void }) {
  const { tr } = useApp()
  const v = useCarregar(() => api.get<CodebookPayload>(`/codebooks/${versao}`), [versao])
  const diff = useCarregar(() => (versao > 1 ? api.get<{ adicionados: string[]; removidos: string[]; alterados: { campo: string; diff: string }[] }>(`/codebooks/diff?v1=${versao - 1}&v2=${versao}`) : Promise.resolve(null)), [versao])
  return (
    <Modal titulo={`Codebook v${versao}`} sub={v.dados ? `${v.dados.hash} · ${v.dados.congelado ? tr('congelada', 'frozen') : tr('rascunho', 'draft')}` : ''} onFechar={onFechar}>
      <div className="modal-b">
        {v.carregando ? <Carregando /> : v.erro ? <Nota tipo="erro">{v.erro}</Nota> : null}
        {diff.dados ? (
          <div className="card">
            <h2 className="h2">{tr(`Mudanças desde v${versao - 1}`, `Changes since v${versao - 1}`)}</h2>
            <div className="small">{tr('Adicionados', 'Added')}: {diff.dados.adicionados.join(', ') || '—'} · {tr('Removidos', 'Removed')}: {diff.dados.removidos.join(', ') || '—'}</div>
            {diff.dados.alterados.map((a) => <pre key={a.campo} className="con">{a.diff}</pre>)}
          </div>
        ) : null}
        {v.dados ? <pre className="con">{v.dados.yaml}</pre> : null}
      </div>
    </Modal>
  )
}
