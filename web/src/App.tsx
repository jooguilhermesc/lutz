import { useState, type ReactNode } from 'react'
import { BookOpen, ClipboardList, FileText, FlaskConical, Gavel, Library, Plug, Settings, Sparkles, Table2 } from 'lucide-react'
import { useApp } from './app-context'
import { JobsMenu } from './components/JobsMenu'
import { SettingsModal } from './components/SettingsModal'
import { Nota, useFmt } from './components/ui'
import { Adjudicacao } from './screens/Adjudicacao'
import { Biblioteca } from './screens/Biblioteca'
import { Codebook } from './screens/Codebook'
import { Extracao } from './screens/Extracao'
import { Integracao } from './screens/Integracao'
import { Piloto } from './screens/Piloto'
import { Relatorio } from './screens/Relatorio'
import { Resultados } from './screens/Resultados'

interface Item { id: string; pt: string; en: string; icone: ReactNode }
const GRUPOS: { pt: string; en: string; itens: Item[] }[] = [
  { pt: 'Preparar', en: 'Prepare', itens: [
    { id: 'biblioteca', pt: 'Biblioteca', en: 'Library', icone: <Library size={16} /> },
    { id: 'codebook', pt: 'Codebook', en: 'Codebook', icone: <BookOpen size={16} /> },
  ] },
  { pt: 'Validar', en: 'Validate', itens: [
    { id: 'piloto', pt: 'Piloto', en: 'Pilot', icone: <FlaskConical size={16} /> },
    { id: 'extracao', pt: 'Extração', en: 'Extraction', icone: <Sparkles size={16} /> },
  ] },
  { pt: 'Revisar', en: 'Review', itens: [
    { id: 'resultados', pt: 'Resultados', en: 'Results', icone: <Table2 size={16} /> },
    { id: 'adjudicacao', pt: 'Adjudicação', en: 'Adjudication', icone: <Gavel size={16} /> },
  ] },
  { pt: 'Relatar', en: 'Report', itens: [
    { id: 'relatorio', pt: 'Relatório', en: 'Report', icone: <FileText size={16} /> },
  ] },
  { pt: 'Integrar', en: 'Integrate', itens: [
    { id: 'api', pt: 'API e MCP', en: 'API and MCP', icone: <Plug size={16} /> },
  ] },
]

export default function App() {
  const { projeto, erroProjeto, tr, rota, ir } = useApp()
  const fmt = useFmt()
  const [config, setConfig] = useState(false)
  const tela = rota.split('/')[0]

  let conteudo: ReactNode
  switch (tela) {
    case 'codebook': conteudo = <Codebook />; break
    case 'piloto': conteudo = <Piloto />; break
    case 'extracao': conteudo = <Extracao />; break
    case 'resultados': conteudo = <Resultados />; break
    case 'adjudicacao': conteudo = <Adjudicacao />; break
    case 'relatorio': conteudo = <Relatorio />; break
    case 'api': conteudo = <Integracao />; break
    default: conteudo = <Biblioteca />
  }

  return (
    <div>
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark"><ClipboardList size={16} /></div>
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            <span className="brand-name">lutz</span>
            <span className="brand-sub">RESEARCH</span>
          </div>
        </div>
        {projeto ? <span className="chip" title={projeto.raiz}>{projeto.raiz}</span> : null}
        {projeto?.codebook ? (
          <span className="chip chip-brand">codebook v{projeto.codebook.versao} · {projeto.codebook.hash.slice(0, 8)}
            {projeto.codebook.congelado ? '' : ` · ${tr('rascunho', 'draft')}`}</span>
        ) : projeto ? <span className="chip">{tr('sem codebook', 'no codebook')}</span> : null}
        <div style={{ flex: 1 }} />
        {projeto ? (
          <span className="chip chip-cost">{fmt.usd(projeto.consumo.custo_usd)} · {fmt.tokens(projeto.consumo.tokens)} tokens</span>
        ) : null}
        <JobsMenu />
        <button className="btn btn-icon" onClick={() => setConfig(true)} aria-label={tr('Configurações', 'Settings')}
          title={tr('Configurações', 'Settings')}>
          <Settings size={16} />
        </button>
      </header>
      <div className="shell">
        <nav className="sidenav" aria-label={tr('Navegação principal', 'Main navigation')}>
          {GRUPOS.map((g, gi) => (
            <div key={g.pt} style={{ display: 'contents' }}>
              <span className="lbl" style={{ padding: gi === 0 ? '6px 10px 4px' : '14px 10px 4px' }}>{tr(g.pt, g.en)}</span>
              {g.itens.map((it) => (
                <button key={it.id} className={`nav${tela === it.id || (tela === '' && it.id === 'biblioteca') ? ' on' : ''}`}
                  aria-current={tela === it.id ? 'page' : undefined} onClick={() => ir(it.id)}>
                  {it.icone}
                  {tr(it.pt, it.en)}
                  {it.id === 'adjudicacao' && projeto?.fila_adjudicacao ? (
                    <span className="badge-count" aria-label={tr('células na fila', 'cells in queue')}>{projeto.fila_adjudicacao}</span>
                  ) : null}
                </button>
              ))}
            </div>
          ))}
        </nav>
        <main className="main">
          {erroProjeto ? <Nota tipo="erro">{tr('Não foi possível falar com o servidor do Lutz', 'Could not reach the Lutz server')}: {erroProjeto}</Nota> : null}
          {conteudo}
        </main>
      </div>
      {config ? <SettingsModal onFechar={() => setConfig(false)} /> : null}
    </div>
  )
}
