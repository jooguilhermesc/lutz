import { useState } from 'react'
import { ExternalLink } from 'lucide-react'
import { api, type McpInfo } from '../api'
import { useApp } from '../app-context'
import { Cabecalho, Carregando, Copiar, Nota, useCarregar } from '../components/ui'

const ENDPOINTS: [string, string, string, string][] = [
  ['GET', '/api/v1/projeto', 'projeto, contagens, codebook e custo', 'project, counts, codebook and cost'],
  ['GET', '/api/v1/codebooks/{versao}', 'codebook e hash', 'codebook and hash'],
  ['POST', '/api/v1/execucoes/estimativa', 'planeja uma execução e estima o custo', 'plans a run and estimates its cost'],
  ['POST', '/api/v1/execucoes/{id}/iniciar', 'assíncrona: devolve 202 e o id do job (exige confirmar: true)', 'asynchronous: returns 202 and the job id (requires confirmar: true)'],
  ['GET', '/api/v1/execucoes/{id}', 'status, progresso e custo', 'status, progress and cost'],
  ['GET', '/api/v1/execucoes/{id}/tabela', 'valor + nível + página por célula', 'value + level + page per cell'],
  ['GET', '/api/v1/celulas/{id}', 'extratores, trecho e checagens de uma célula', 'extractors, passage and checks of one cell'],
  ['POST', '/api/v1/adjudicacoes', 'grava uma decisão com justificativa', 'stores a decision with justification'],
  ['GET', '/api/v1/relatorios/{id}/previa', 'relatório em Markdown', 'report in Markdown'],
  ['GET', '/api/v1/jobs/{id}/eventos', 'progresso por Server-Sent Events', 'progress via Server-Sent Events'],
]

export function Integracao() {
  const { tr } = useApp()
  const info = useCarregar(() => api.get<McpInfo>('/mcp'), [])
  const [cliente, setCliente] = useState<'claude' | 'cursor' | 'vscode'>('claude')
  const cfg = info.dados ? JSON.stringify(cliente === 'vscode' ? info.dados.config_vscode : cliente === 'cursor' ? info.dados.config_cursor : info.dados.config_claude_desktop, null, 2) : ''
  return (
    <>
      <Cabecalho titulo={tr('API e MCP', 'API and MCP')}
        sub={tr('Leve codebook, células validadas e relatório para o cliente que você já usa: Claude, Cursor, VS Code, Jupyter, R. Sem chat dentro do app.',
          'Bring the codebook, validated cells and report to the client you already use: Claude, Cursor, VS Code, Jupyter, R. No chat inside the app.')}>
        <a className="btn" href="/api/docs" target="_blank" rel="noreferrer"><ExternalLink size={15} />{tr('Documentação OpenAPI', 'OpenAPI docs')}</a>
      </Cabecalho>
      {info.carregando && !info.dados ? <Carregando /> : info.erro ? <Nota tipo="erro">{info.erro}</Nota> : info.dados ? (
        <section className="row">
          <div className="card grow">
            <div className="card-h">
              <h2 className="h2">{tr('Servidor MCP', 'MCP server')}</h2>
              <span className="tag tag-s">{info.dados.transporte}</span>
              <span className="tag">{tr('somente leitura', 'read-only')}</span>
            </div>
            <p className="sub">{tr('O cliente abre o servidor com este comando; não é preciso deixar nada rodando.', 'The client starts the server with this command; nothing needs to stay running.')}</p>
            <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
              <pre className="con" style={{ flex: 1 }}>{info.dados.comando}</pre>
              <Copiar texto={info.dados.comando} />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {([['claude', 'Claude Desktop'], ['cursor', 'Cursor'], ['vscode', 'VS Code']] as const).map(([id, rot]) => (
                <button key={id} className={`chipb${cliente === id ? ' on' : ''}`} onClick={() => setCliente(id)}>{rot}</button>
              ))}
            </div>
            <pre className="con">{cfg}</pre>
            <div><Copiar texto={cfg} /></div>
            <h2 className="h2">{tr('Ferramentas expostas', 'Exposed tools')}</h2>
            {info.dados.ferramentas.map((f) => (
              <div key={f.nome} className="tl"><span className="mono" style={{ fontWeight: 600 }}>{f.nome}</span><span className="muted">{f.descricao}</span></div>
            ))}
            <Nota tipo="info">{tr('Nenhuma ferramenta escreve no projeto, roda extração ou altera células. Execução, adjudicação e relatório ficam na CLI e nesta interface. Células do piloto cego continuam ocultas.',
              'No tool writes to the project, runs an extraction or changes cells. Runs, adjudication and reports stay in the CLI and in this interface. Blind-pilot cells stay hidden.')}</Nota>
          </div>
          <div className="card grow">
            <h2 className="h2">{tr('Endpoints REST', 'REST endpoints')}</h2>
            <p className="sub">{tr('Os mesmos recursos da CLI, só em 127.0.0.1 (sem autenticação: uso local). Execuções longas respondem 202; acompanhe pelo id do job.',
              'The same resources as the CLI, on 127.0.0.1 only (no authentication: local use). Long runs answer 202; follow them by job id.')}</p>
            {ENDPOINTS.map(([m, p, pt, en]) => (
              <div key={p} className="ep">
                <span className={`m ${m === 'GET' ? 'get' : 'post'}`}>{m}</span>
                <div><div className="mono small" style={{ overflowWrap: 'anywhere' }}>{p}</div><div className="small muted">{tr(pt, en)}</div></div>
              </div>
            ))}
          </div>
        </section>
      ) : null}
    </>
  )
}
