import { useState } from 'react'
import { Play } from 'lucide-react'
import { api, type Estimativa } from '../api'
import { useApp } from '../app-context'
import { Modal, Nota, useFmt } from './ui'

export function TabelaEstimativa({ est }: { est: Estimativa }) {
  const { tr } = useApp()
  const fmt = useFmt()
  return (
    <>
      <div className="kpis">
        <div className="kpi"><div className="lbl">{tr('Artigos × campos', 'Articles × fields')}</div><div className="kv">{est.artigos} × {est.campos}</div></div>
        <div className="kpi"><div className="lbl">{tr('Chamadas novas', 'New calls')}</div><div className="kv">{fmt.int(est.chamadas)}</div>
          <div className="kv-sub">{est.em_cache} {tr('em cache (custo zero)', 'cached (no cost)')}</div></div>
        <div className="kpi"><div className="lbl">{tr('Custo estimado', 'Estimated cost')}</div>
          <div className="kv">{est.custo_usd === null ? '?' : fmt.usd(est.custo_usd)}</div>
          <div className="kv-sub">{tr('teto; inclui o verificador', 'upper bound; includes the verifier')}</div></div>
        <div className="kpi"><div className="lbl">{tr('Gasto do projeto', 'Project spend')}</div><div className="kv">{fmt.usd(est.gasto_projeto_usd)}</div>
          <div className="kv-sub">{est.orcamento_usd === null ? tr('sem orçamento', 'no budget') : `${tr('de', 'of')} ${fmt.usd(est.orcamento_usd)}`}</div></div>
      </div>
      <div className="tablewrap">
        <table className="t">
          <thead><tr><th>{tr('Papel', 'Role')}</th><th>{tr('Provedor', 'Provider')}</th><th>{tr('Modelo', 'Model')}</th>
            <th className="num">{tr('Chamadas', 'Calls')}</th><th className="num">{tr('Tokens entrada', 'Input tokens')}</th>
            <th className="num">{tr('Tokens saída', 'Output tokens')}</th><th className="num">{tr('Custo', 'Cost')}</th></tr></thead>
          <tbody>
            {est.por_papel.map((p) => (
              <tr key={p.rotulo}><td><span className="tag">{p.rotulo}</span></td><td>{p.provedor}</td><td className="mono small">{p.modelo}</td>
                <td className="num">{fmt.int(p.chamadas)}</td><td className="num">{fmt.int(p.tokens_entrada)}</td><td className="num">{fmt.int(p.tokens_saida)}</td>
                <td className="num">{p.custo_usd === null ? '?' : fmt.usd(p.custo_usd)}</td></tr>
            ))}
          </tbody>
        </table>
      </div>
      {est.sem_preco.length ? <Nota>{tr('Preço desconhecido para', 'Unknown price for')} {est.sem_preco.join(', ')}. {tr('Defina em "precos" no lutz.yaml para estimar o custo.', 'Set it under "precos" in lutz.yaml to estimate the cost.')}</Nota> : null}
      {est.excedem_contexto.length ? <Nota>{tr('Excedem a janela de contexto de algum extrator', 'Exceed the context window of some extractor')}: <span className="mono">{est.excedem_contexto.join(', ')}</span></Nota> : null}
      {!est.cabe_no_orcamento ? <Nota tipo="erro">{tr('A estimativa ultrapassa o orçamento: a execução pausa quando o gasto do projeto atingir o limite.', 'The estimate exceeds the budget: the run pauses when project spend reaches the limit.')}</Nota> : null}
    </>
  )
}

/** Confirm an estimate and start (or resume) a planned run. */
export function ConfirmarExecucao({ est, onFechar, onIniciada }: {
  est: Estimativa; onFechar: () => void; onIniciada: (execucaoId: number, jobId: string) => void
}) {
  const { tr, avisar, recarregarJobs } = useApp()
  const [ocupado, setOcupado] = useState(false)
  return (
    <Modal titulo={`${tr('Execução', 'Run')} ${est.execucao_id} · ${tr('estimativa de custo', 'cost estimate')}`}
      sub={tr('Nada roda antes da sua confirmação.', 'Nothing runs before you confirm.')} onFechar={onFechar}
      rodape={<>
        <button className="btn btn-p" disabled={ocupado} onClick={async () => {
          setOcupado(true)
          try {
            const r = await api.post<{ job_id: string }>(`/execucoes/${est.execucao_id}/iniciar`, { confirmar: true })
            recarregarJobs()
            onIniciada(est.execucao_id, r.job_id)
          } catch (e) {
            avisar((e as Error).message, true)
          } finally {
            setOcupado(false)
          }
        }}><Play size={15} />{tr('Confirmar e iniciar', 'Confirm and start')}</button>
        <button className="btn" onClick={onFechar}>{tr('Agora não', 'Not now')}</button>
        <span className="small faint">{tr('A execução fica planejada e pode ser iniciada depois.', 'The run stays planned and can be started later.')}</span>
      </>}>
      <div className="modal-b"><TabelaEstimativa est={est} /></div>
    </Modal>
  )
}
