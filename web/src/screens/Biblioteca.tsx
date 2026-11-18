import { useRef, useState } from 'react'
import { FileUp, Loader2, Search } from 'lucide-react'
import { api, esperarJob, type Artigo, type Evento } from '../api'
import { useApp } from '../app-context'
import { PageViewer } from '../components/PageViewer'
import { Cabecalho, Carregando, Kpi, Nota, StatusPill, Vazio, useCarregar, useFmt } from '../components/ui'

type Filtro = 'todos' | 'pronto' | 'duas' | 'sem_texto' | 'erro'

export function Biblioteca() {
  const { tr, avisar, recarregarProjeto, recarregarJobs } = useApp()
  const fmt = useFmt()
  const artigos = useCarregar(() => api.get<Artigo[]>('/artigos'), [])
  const [filtro, setFiltro] = useState<Filtro>('todos')
  const [busca, setBusca] = useState('')
  const [sobre, setSobre] = useState(false)
  const [enviando, setEnviando] = useState<{ total: number; feitos: Evento[] } | null>(null)
  const [aberto, setAberto] = useState<string | null>(null)
  const input = useRef<HTMLInputElement>(null)

  async function enviar(arquivos: FileList | File[]) {
    const pdfs = Array.from(arquivos).filter((f) => f.name.toLowerCase().endsWith('.pdf'))
    if (!pdfs.length) {
      avisar(tr('Nenhum arquivo .pdf selecionado.', 'No .pdf file selected.'), true)
      return
    }
    const fd = new FormData()
    pdfs.forEach((f) => fd.append('arquivos', f))
    setEnviando({ total: pdfs.length, feitos: [] })
    try {
      const { job_id } = await api.form<{ job_id: string }>('/artigos', fd)
      recarregarJobs()
      await esperarJob(job_id, (ev) => {
        if (ev.tipo === 'artigo') setEnviando((s) => (s ? { ...s, feitos: [...s.feitos, ev] } : s))
      })
      avisar(tr('Importação concluída.', 'Import finished.'))
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      artigos.recarregar(true)
      recarregarProjeto()
      recarregarJobs()
    }
  }

  const lista = (artigos.dados ?? []).filter((a) => {
    if (filtro === 'pronto' && a.status !== 'pronto') return false
    if (filtro === 'duas' && !a.duas_colunas) return false
    if (filtro === 'sem_texto' && a.status !== 'sem_texto') return false
    if (filtro === 'erro' && a.status !== 'erro') return false
    const q = busca.trim().toLowerCase()
    return !q || `${a.chave} ${a.titulo} ${a.autores}`.toLowerCase().includes(q)
  })
  const todos = artigos.dados ?? []
  const n = {
    total: todos.length,
    prontos: todos.filter((a) => a.status === 'pronto').length,
    duas: todos.filter((a) => a.duas_colunas).length,
    sem: todos.filter((a) => a.status !== 'pronto').length,
    paginas: todos.reduce((s, a) => s + a.n_paginas, 0),
    ocultos: todos.filter((a) => a.frac_oculto > 0.02).length,
  }

  return (
    <>
      <Cabecalho titulo={tr('Biblioteca', 'Library')}
        sub={tr('Todo artigo entra por PDF e é guardado página a página, para que cada valor extraído possa ser conferido no texto.',
          'Every article enters as a PDF and is stored page by page, so every extracted value can be checked against the text.')}>
        <button className="btn btn-p" onClick={() => input.current?.click()}>
          <FileUp size={16} />{tr('Enviar PDFs', 'Upload PDFs')}
        </button>
        <input ref={input} type="file" accept="application/pdf,.pdf" multiple hidden
          onChange={(e) => e.target.files && enviar(e.target.files)} aria-label={tr('Escolher PDFs', 'Choose PDFs')} />
      </Cabecalho>

      <section className="kpis" aria-label={tr('Resumo do corpus', 'Corpus summary')}>
        <Kpi rotulo={tr('Artigos', 'Articles')} valor={fmt.int(n.total)} />
        <Kpi rotulo={tr('Prontos', 'Ready')} valor={fmt.int(n.prontos)} cor="var(--success-fg)" />
        <Kpi rotulo={tr('Duas colunas', 'Two columns')} valor={fmt.int(n.duas)} cor="var(--warning-fg)" />
        <Kpi rotulo={tr('Sem texto / erro', 'No text / error')} valor={fmt.int(n.sem)} cor={n.sem ? 'var(--danger-fg)' : undefined} />
        <Kpi rotulo={tr('Páginas', 'Pages')} valor={fmt.int(n.paginas)} />
      </section>

      {n.duas ? (
        <Nota>
          <strong>{n.duas} {tr('artigo(s) em duas colunas.', 'two-column article(s).')}</strong>{' '}
          {tr('A ordem de leitura foi corrigida por colunas; se um trecho atravessar colunas, a verificação literal pode falhar. Confira as páginas antes de extrair.',
            'Reading order was fixed by columns; a passage that crosses columns may fail the literal check. Review the pages before extracting.')}
        </Nota>
      ) : null}
      {n.ocultos ? (
        <Nota>{n.ocultos} {tr('artigo(s) com texto oculto (branco, minúsculo ou invisível). Esse texto foi descartado e não chega aos extratores.',
          'article(s) with hidden text (white, tiny or invisible). That text was discarded and never reaches the extractors.')}</Nota>
      ) : null}

      <section className="row" style={{ alignItems: 'stretch' }}>
        <div className={`drop grow${sobre ? ' over' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setSobre(true) }}
          onDragLeave={() => setSobre(false)}
          onDrop={(e) => { e.preventDefault(); setSobre(false); enviar(e.dataTransfer.files) }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{tr('Arraste PDFs para cá', 'Drag PDFs here')}</div>
          <div className="muted">
            {tr('O Lutz calcula o hash de cada arquivo para barrar duplicatas, extrai o texto visível de cada página, corrige a ordem de leitura em duas colunas, marca as seções e cria unidades citáveis (frases e linhas de tabela) com página.',
              'Lutz hashes each file to block duplicates, extracts the visible text of each page, fixes two-column reading order, marks sections and creates citable units (sentences and table rows) with their page.')}
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <span className="tag">PDF</span><span className="tag">SHA-256</span><span className="tag tag-g">{tr('sem OCR', 'no OCR')}</span>
          </div>
        </div>
        {enviando ? (
          <div className="card grow">
            <div className="card-h">
              {enviando.feitos.length < enviando.total ? <Loader2 size={16} className="spin" /> : null}
              <h2 className="h2">{tr('Processando', 'Processing')} {enviando.feitos.length}/{enviando.total} PDF(s)</h2>
              <span style={{ flex: 1 }} />
              {enviando.feitos.length >= enviando.total ? <button className="btn btn-s" onClick={() => setEnviando(null)}>{tr('Fechar', 'Close')}</button> : null}
            </div>
            <div className="log">
              {enviando.feitos.map((ev, i) => (
                <div key={i} style={{ color: ev.status === 'importado' ? 'var(--success-fg)' : ev.status === 'duplicado' ? 'var(--text-muted)' : 'var(--danger-fg)' }}>
                  {ev.status === 'importado' ? '✓' : ev.status === 'duplicado' ? '=' : '✗'} {String(ev.arquivo)} · {String(ev.status)}
                  {ev.chave ? ` · ${String(ev.chave)}` : ''}{ev.mensagem ? ` · ${String(ev.mensagem)}` : ''}
                </div>
              ))}
            </div>
          </div>
        ) : null}
      </section>

      <section className="card" aria-label={tr('Artigos', 'Articles')}>
        <div className="card-h">
          <div style={{ position: 'relative', flex: '1 1 260px' }}>
            <Search size={14} style={{ position: 'absolute', left: 10, top: 11, color: 'var(--text-faint)' }} />
            <input className="in" style={{ paddingLeft: 30 }} placeholder={tr('Buscar na biblioteca', 'Search the library')}
              value={busca} onChange={(e) => setBusca(e.target.value)} aria-label={tr('Buscar', 'Search')} />
          </div>
          {(['todos', 'pronto', 'duas', 'sem_texto', 'erro'] as Filtro[]).map((f) => (
            <button key={f} className={`chipb${filtro === f ? ' on' : ''}`} onClick={() => setFiltro(f)}>
              {{ todos: tr('Todos', 'All'), pronto: tr('Prontos', 'Ready'), duas: tr('Duas colunas', 'Two columns'),
                sem_texto: tr('Sem texto', 'No text'), erro: tr('Erro', 'Error') }[f]}
            </button>
          ))}
        </div>
        {artigos.carregando && !artigos.dados ? <Carregando /> : artigos.erro ? <Nota tipo="erro">{artigos.erro}</Nota> :
          todos.length === 0 ? (
            <Vazio titulo={tr('Nenhum artigo ainda', 'No articles yet')}>
              {tr('Envie PDFs acima ou use', 'Upload PDFs above or run')} <span className="mono">lutz load pasta/</span>.
            </Vazio>
          ) : (
            <div className="tablewrap">
              <table className="t">
                <thead>
                  <tr>
                    <th>{tr('Artigo', 'Article')}</th><th className="num">{tr('Ano', 'Year')}</th><th className="num">{tr('Págs', 'Pages')}</th>
                    <th>Layout</th><th>{tr('Seções detectadas', 'Detected sections')}</th><th className="num">{tr('Tabelas', 'Tables')}</th>
                    <th className="num">{tr('Oculto', 'Hidden')}</th><th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {lista.map((a) => (
                    <tr key={a.id} className="click" onClick={() => a.status !== 'erro' && setAberto(a.chave)} tabIndex={0}
                      onKeyDown={(e) => e.key === 'Enter' && setAberto(a.chave)}>
                      <td style={{ maxWidth: 420 }}>
                        <div style={{ fontWeight: 600 }}>{a.titulo}</div>
                        <div className="small muted"><span className="mono">{a.chave}</span>{a.autores ? ` · ${a.autores}` : ''}</div>
                      </td>
                      <td className="num">{a.ano ?? '—'}</td>
                      <td className="num">{a.n_paginas}</td>
                      <td>{a.duas_colunas ? <span className="tag tag-w">2 col</span> : <span className="tag tag-g">1 col</span>}</td>
                      <td className="small">{a.secoes.length ? a.secoes.join(' · ') : <span className="faint">{tr('não detectadas', 'not detected')}</span>}</td>
                      <td className="num">{a.n_tabelas}</td>
                      <td className="num">{a.frac_oculto ? fmt.pct(a.frac_oculto, 1) : '—'}</td>
                      <td>
                        <StatusPill status={a.status} />
                        {a.erro ? <div className="small faint" style={{ maxWidth: 220 }}>{a.erro}</div> : null}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              {lista.length === 0 ? <Vazio titulo={tr('Nada com esse filtro', 'Nothing matches this filter')} /> : null}
            </div>
          )}
      </section>
      {aberto ? <PageViewer chave={aberto} onFechar={() => setAberto(null)} /> : null}
    </>
  )
}
