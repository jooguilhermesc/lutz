import { useState } from 'react'
import { Download, FileText, RefreshCw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api, esperarJob, url } from '../api'
import { useApp } from '../app-context'
import { ExecucaoSelect } from '../components/ExecucaoSelect'
import { Cabecalho, Carregando, Nota, Vazio, baixar, useCarregar, useFmt } from '../components/ui'

const PARTES = [
  ['1. Identificação da execução', '1. Run identification'],
  ['2. Processo', '2. Process'],
  ['3. Confiabilidade por campo', '3. Reliability by field'],
  ['4. Calibração dos níveis', '4. Level calibration'],
  ['5. Adjudicação', '5. Adjudication'],
  ['6. Texto para Métodos', '6. Methods text'],
  ['7. PRISMA 2020 e anexos', '7. PRISMA 2020 and annexes'],
]

export function Relatorio() {
  const { tr, avisar, recarregarJobs } = useApp()
  const fmt = useFmt()
  const [eid, setEid] = useState<number | null>(null)
  const [idioma, setIdioma] = useState<'pt' | 'en'>('pt')
  const [idiomas, setIdiomas] = useState<Set<string>>(new Set(['pt', 'en']))
  const [formatos, setFormatos] = useState<Set<string>>(new Set(['md', 'pdf']))
  const [gerando, setGerando] = useState(false)
  const previa = useCarregar(() => (eid ? api.get<{ markdown: string }>(`/relatorios/${eid}/previa?idioma=${idioma}`) : Promise.resolve(null)), [eid, idioma])
  const lista = useCarregar(() => api.get<{ execucao_id: number; arquivos: string[]; gerado_em: string }[]>('/relatorios'), [])
  const arquivos = lista.dados?.find((r) => r.execucao_id === eid)

  async function gerar() {
    if (!eid) return
    setGerando(true)
    try {
      const { job_id } = await api.post<{ job_id: string }>('/relatorios', { execucao_id: eid, idiomas: [...idiomas], formatos: [...formatos] })
      recarregarJobs()
      await esperarJob(job_id)
      avisar(tr('Relatório gerado.', 'Report generated.'))
      lista.recarregar(true)
      previa.recarregar(true)
    } catch (e) {
      avisar((e as Error).message, true)
    } finally {
      setGerando(false)
      recarregarJobs()
    }
  }

  const alterna = (s: Set<string>, v: string) => {
    const n = new Set(s)
    if (n.has(v)) n.delete(v)
    else n.add(v)
    return n
  }

  return (
    <>
      <Cabecalho titulo={tr('Relatório de confiabilidade', 'Reliability report')}
        sub={tr('Pronto para a seção de Métodos, o material suplementar e o checklist PRISMA. Sete partes, sempre na mesma ordem.',
          'Ready for the Methods section, the supplementary material and the PRISMA checklist. Seven parts, always in the same order.')}>
        <ExecucaoSelect valor={eid} onValor={setEid} />
        {['md', 'pdf'].map((f) => <button key={f} className={`chipb${formatos.has(f) ? ' on' : ''}`} onClick={() => setFormatos((s) => alterna(s, f))}>{f.toUpperCase()}</button>)}
        {['pt', 'en'].map((l) => <button key={l} className={`chipb${idiomas.has(l) ? ' on' : ''}`} onClick={() => setIdiomas((s) => alterna(s, l))}>{l}</button>)}
        <button className="btn btn-p" disabled={!eid || gerando || !formatos.size || !idiomas.size} onClick={gerar}>
          <RefreshCw size={15} className={gerando ? 'spin' : undefined} />{arquivos ? tr('Gerar de novo', 'Generate again') : tr('Gerar', 'Generate')}
        </button>
      </Cabecalho>

      {!eid ? (
        <section className="card"><Vazio titulo={tr('Nenhuma execução concluída', 'No completed run')}>{tr('O relatório exige uma execução concluída.', 'The report requires a completed run.')}</Vazio></section>
      ) : (
        <section className="row">
          <div className="card" style={{ flex: '1 1 220px', maxWidth: 300 }}>
            <h2 className="h2">{tr('Partes', 'Parts')}</h2>
            {PARTES.map(([pt, en]) => <div key={pt} className="small">{tr(pt, en)}</div>)}
            <div style={{ height: 1, background: 'var(--border)' }} />
            <h2 className="h2">{tr('Arquivos', 'Files')}</h2>
            {arquivos ? (
              <>
                <div className="small faint">{tr('Gerado', 'Generated')} {fmt.data(arquivos.gerado_em)}</div>
                {arquivos.arquivos.map((a) => (
                  <button key={a} className="btn btn-s" style={{ justifyContent: 'flex-start', overflow: 'hidden' }}
                    onClick={() => baixar(url(`/relatorios/${eid}/arquivos/${encodeURIComponent(a)}`))}>
                    {a.endsWith('.pdf') || a.endsWith('.md') ? <FileText size={13} /> : <Download size={13} />}{a}
                  </button>
                ))}
              </>
            ) : <div className="small faint">{tr('Ainda não gerado. A prévia ao lado é calculada na hora.', 'Not generated yet. The preview is computed on the fly.')}</div>}
          </div>
          <div className="card" style={{ flex: '3 1 520px' }}>
            <div className="card-h">
              <h2 className="h2">{tr('Prévia', 'Preview')}</h2>
              <span style={{ flex: 1 }} />
              {(['pt', 'en'] as const).map((l) => <button key={l} className={`chipb${idioma === l ? ' on' : ''}`} onClick={() => setIdioma(l)}>{l}</button>)}
            </div>
            {previa.carregando && !previa.dados ? <Carregando /> : previa.erro ? <Nota tipo="erro">{previa.erro}</Nota> : previa.dados ? (
              <div className="md"><ReactMarkdown remarkPlugins={[remarkGfm]}>{previa.dados.markdown}</ReactMarkdown></div>
            ) : null}
          </div>
        </section>
      )}
    </>
  )
}
