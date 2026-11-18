import { useEffect } from 'react'
import { api, type Resumo } from '../api'
import { useApp } from '../app-context'
import { useCarregar } from './ui'

/** Choose a run. Default: the latest completed non-test run. */
export function ExecucaoSelect({ valor, onValor, filtro = (r) => r.tipo !== 'teste' && r.status === 'concluida' }: {
  valor: number | null; onValor: (id: number | null) => void; filtro?: (r: Resumo) => boolean
}) {
  const { tr } = useApp()
  const ex = useCarregar(() => api.get<Resumo[]>('/execucoes'), [])
  const opcoes = (ex.dados ?? []).filter(filtro)
  useEffect(() => {
    if (valor === null && opcoes.length) onValor(opcoes[0].id)
  }, [valor, opcoes, onValor])
  if (!opcoes.length) return null
  return (
    <label className="field" style={{ minWidth: 240 }}>
      <span className="sr-only" style={{ display: 'none' }}>{tr('Execução', 'Run')}</span>
      <select className="sel-in" value={valor ?? ''} aria-label={tr('Execução', 'Run')}
        onChange={(e) => onValor(e.target.value ? Number(e.target.value) : null)}>
        {opcoes.map((r) => (
          <option key={r.id} value={r.id}>
            {tr('Execução', 'Run')} {r.id} · {r.tipo}{r.conjunto ? ` (${r.conjunto})` : ''} · {r.status}
          </option>
        ))}
      </select>
    </label>
  )
}
