// Typed client for the Lutz 1.0 local REST API (lutz/server/app.py). Every route lives under /api/v1.

export const BASE = '/api/v1'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function mensagemDeErro(status: number, corpo: unknown): string {
  if (corpo && typeof corpo === 'object') {
    const c = corpo as Record<string, unknown>
    if (typeof c.erro === 'string') return c.erro
    if (typeof c.detail === 'string') return c.detail
    if (Array.isArray(c.detail)) {
      return c.detail
        .map((d) => {
          const x = d as { loc?: unknown[]; msg?: string }
          return `${(x.loc ?? []).join('.')}: ${x.msg ?? ''}`
        })
        .join('\n')
    }
  }
  return `Erro ${status}`
}

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, headers: {} }
  if (body instanceof FormData) {
    init.body = body
  } else if (body !== undefined) {
    init.body = JSON.stringify(body)
    ;(init.headers as Record<string, string>)['Content-Type'] = 'application/json'
  }
  const r = await fetch(BASE + path, init)
  const texto = await r.text()
  let corpo: unknown = null
  try {
    corpo = texto ? JSON.parse(texto) : null
  } catch {
    corpo = texto
  }
  if (!r.ok) throw new ApiError(r.status, mensagemDeErro(r.status, corpo))
  return corpo as T
}

export const api = {
  get: <T>(p: string) => req<T>('GET', p),
  post: <T>(p: string, b?: unknown) => req<T>('POST', p, b ?? {}),
  put: <T>(p: string, b?: unknown) => req<T>('PUT', p, b ?? {}),
  form: <T>(p: string, f: FormData) => req<T>('POST', p, f),
}

export const url = (p: string) => BASE + p

// ── types ──────────────────────────────────────────────────────────────────

export type Nivel = 'alta' | 'media' | 'baixa'
export type TipoCampo = 'categorico' | 'ordinal' | 'numerico' | 'texto'

export interface Resumo {
  id: number
  tipo: 'autonoma' | 'piloto' | 'teste'
  status: 'planejada' | 'rodando' | 'pausada' | 'concluida' | 'falhou'
  motivo: string
  codebook_id: number
  piloto_id: number | null
  conjunto: 'ajuste' | 'validacao' | null
  estrategia_diversidade: string
  celulas: number
  celulas_prontas: number
  estados: Record<string, number>
  niveis: Partial<Record<Nivel, number>>
  artigos: number
  artigos_prontos: number
  custo_usd: number
  tokens: number
  chamadas: number
  chamadas_cache: number
  chamadas_sem_preco: number
  criada_em: string
  iniciada_em: string | null
  concluida_em: string | null
  atualizada_em: string | null
}

export interface Projeto {
  nome: string
  pergunta: string
  tipo_revisao: string
  raiz: string
  versao_lutz: string
  artigos: { total: number; prontos: number; sem_texto: number; erro: number; duas_colunas: number }
  codebook: { versao: number; hash: string; congelado: number } | null
  codebook_congelado: { versao: number; hash: string } | null
  ultima_execucao: Resumo | null
  ultima_concluida: number | null
  fila_adjudicacao: number
  piloto: { id: number; sorteado: boolean; cegamento_aberto: boolean } | null
  consumo: { chamadas: number; custo_usd: number; tokens: number }
}

export interface Artigo {
  id: number
  chave: string
  titulo: string
  autores: string
  ano: number | null
  revista: string
  caminho_pdf: string
  nome_original: string
  n_paginas: number
  n_chars: number
  tokens_estimados: number
  duas_colunas: number
  frac_oculto: number
  n_tabelas: number
  secoes: string[]
  status: 'pronto' | 'sem_texto' | 'erro'
  erro: string | null
  importado_em: string
  legibilidade: number
}

export interface PaginaInfo { numero: number; rotulo: string; n_chars: number; frac_oculto: number; secao: string }
export interface ArtigoDetalhe extends Artigo { paginas: PaginaInfo[] }
export interface Unidade { uid: string; tipo: string; secao: string; texto: string }
export interface Pagina extends PaginaInfo { texto: string; texto_oculto: string; unidades: Unidade[] }

export interface Regra {
  tipo: 'soma_igual' | 'menor_ou_igual' | 'maior_ou_igual' | 'requer' | 'valor_implica'
  campos?: string[]
  campo?: string | null
  se?: string | null
  entao?: string[]
  tolerancia_relativa?: number
}
export interface Exemplo { trecho: string; valor: string; positivo?: boolean }
export interface Campo {
  nome: string
  rotulo?: string
  tipo: TipoCampo
  instrucao: string
  valores?: string[]
  definicoes?: Record<string, string>
  exemplos?: Exemplo[]
  secoes?: string[]
  se_ausente?: string
  tolerancia_relativa?: number
  faixa?: [number, number] | null
  unidade?: string
  papel?: 'dado' | 'triagem' | 'risco_vies' | 'criterio'
  motivo_exclusao?: boolean
  regras?: Regra[]
  origem?: 'manual' | 'assistente'
  hash?: string
  testado?: boolean
}
export interface Achado { campo: string | null; codigo: string; severidade: 'erro' | 'aviso' | 'sugestao'; mensagem: string }
export interface CodebookPayload {
  versao: number
  hash: string
  congelado: boolean
  origem: string
  nota: string
  criado_em: string
  descricao: string
  campos: Campo[]
  lint: Achado[]
  yaml: string
}
export interface VersaoCodebook {
  id: number
  versao: number
  hash: string
  origem: string
  congelado: number
  nota: string
  criado_em: string
  congelado_em: string | null
  n_campos: number
  n_assistente: number
  execucoes: number[]
}

export interface PorPapel {
  papel: string
  rotulo: string
  provedor: string
  modelo: string
  chamadas: number
  tokens_entrada: number
  tokens_saida: number
  custo_usd: number | null
}
export interface Estimativa {
  execucao_id: number
  chamadas: number
  tokens_entrada: number
  tokens_saida: number
  custo_usd: number | null
  custo_conhecido_usd: number
  por_papel: PorPapel[]
  sem_preco: string[]
  em_cache: number
  excedem_contexto: string[]
  gasto_projeto_usd: number
  orcamento_usd: number | null
  cabe_no_orcamento: boolean
  artigos: number
  campos: number
}

export interface Extrator {
  rotulo: string
  papel: string
  provedor: string
  modelo: string
  modelo_observado: string
  temperatura: number | null
  variante_prompt: string
}
export interface JobPublico {
  id: string
  tipo: string
  descricao: string
  status: 'rodando' | 'concluido' | 'falhou'
  erro: string
  criado: number
  terminado: number | null
  execucao_id: number | null
  n_eventos: number
}
export interface ExecucaoDetalhe extends Resumo {
  extratores: Extrator[]
  campos: string[]
  hash_config: string
  hash_prompts: string
  versao_lutz: string
  codebook: { versao: number; hash: string }
  orcamento_usd: number | null
  job: JobPublico | null
}

export interface Metrica { nome: string; valor: number | null; ic_inf: number | null; ic_sup: number | null; n: number | null; nota: string }
export interface MetricasExecucao {
  campos: { chave: string; rotulo: string; tipo: TipoCampo; metricas: Record<string, Metrica> }[]
  geral: Record<string, Metrica>
}
export interface Checagens {
  celulas: number
  concordancia: { unanimes: number; dois_de_tres: number; empates: number }
  evidencia: { exata: number; parcial: number; nao_encontrada: number }
  verificador: { sustenta: number; parcial: number; nao_sustenta: number; n: number }
  regras_barradas: number
  niveis: Record<Nivel, number>
  pct_niveis: Record<Nivel, number>
}
export interface LogItem {
  id: number
  chave: string
  campo_chave: string
  valor_final: string | null
  nao_reportado: number
  nivel: Nivel | null
  a: number | null
  e: number | null
  v: number | null
  pagina: number | null
  estado: string
  motivos: string[]
  atualizada_em: string
}

export interface CelulaTabela {
  id: number
  valor: string | null
  nao_reportado: boolean
  nivel: Nivel | null
  origem: string
  pagina: number | null
  escore: number | null
  estado: string
}
export interface Tabela {
  campos: { chave: string; rotulo: string; tipo: TipoCampo }[]
  linhas: { artigo: string; titulo: string; autores: string; ano: number | null; celulas: Record<string, CelulaTabela> }[]
  ocultos_piloto: number
}

export interface Bruta {
  rotulo: string
  status: 'ok' | 'falha'
  valor: string | null
  valor_normalizado: string | null
  nao_reportado: number
  trecho: string | null
  pagina: number | null
  unidades?: string[]
  e: number | null
  e_detalhe: string
  regras_ok?: number | null
  regras_detalhe?: string
  erro: string
}
export interface Adjudicacao {
  id: number
  motivo: string
  valor_anterior: string | null
  valor_decidido: string | null
  nao_reportado: number
  alterou: number
  justificativa: string
  decidido_em: string
}
export interface CelulaDetalhe {
  id: number
  execucao_id: number
  artigo_id: number
  campo_chave: string
  chave: string
  titulo: string
  campo_rotulo: string
  campo_tipo: TipoCampo
  definicao: Campo
  estado: string
  valor_final: string | null
  nao_reportado: number
  a: number | null
  e: number | null
  v: number | null
  escore: number | null
  nivel: Nivel | null
  motivos: string[]
  regras_ok: number | null
  extrator_vencedor: string | null
  trecho: string | null
  pagina: number | null
  unidades: string[]
  v_justificativa: { papel?: string; rotulo?: string; veredito?: string; justificativa?: string; nota?: string }
  origem: string
  brutas: Bruta[]
  adjudicacoes: Adjudicacao[]
  enviada_manual: boolean
  unidades_texto?: { uid: string; pagina: number; tipo: string; texto: string }[]
}
export interface ItemFila extends Omit<CelulaDetalhe, 'definicao' | 'v_justificativa' | 'adjudicacoes' | 'enviada_manual' | 'unidades'> {
  motivo_fila: string
  unidades: string
}

export interface ResultadoAuditoria {
  auditoria_id: number
  n_amostra: number
  n_alta: number
  conferidas: number
  acertos: number
  taxa: number | null
  ic_inf: number | null
  ic_sup: number | null
  completa: boolean
  semente: number
  meia_largura_alvo: number
}
export interface ItemAuditoria {
  id: number
  celula_id: number
  correto: number | null
  valor_correto: string | null
  nota: string
  valor_final: string | null
  nao_reportado: number
  trecho: string | null
  pagina: number | null
  campo_chave: string
  chave: string
}
export interface AuditoriaResposta {
  auditoria: null | { id: number; n_amostra: number; n_alta: number; semente: number }
  n_alta?: number
  n_sugerido?: number
  resultado?: ResultadoAuditoria
  itens?: ItemAuditoria[]
}
export interface EstatAdj {
  total: { enviadas: number; decididas: number; alteradas: number }
  por_nivel: Record<string, { enviadas: number; decididas: number; alteradas: number }>
  por_campo_nivel: { campo: string; nivel: string; enviadas: number; decididas: number; alteradas: number }[]
  auditoria: ResultadoAuditoria | null
}

export interface LinhaTamanho { n: number; erro_padrao: number; meia_largura: number }
export interface EstadoPiloto {
  piloto: {
    id: number
    n_total: number
    n_ajuste: number
    n_validacao: number
    n_reserva: number
    estratos: string
    semente: number
    avaliadores: string[]
    plano: Record<string, unknown>
    hash_plano: string
    sorteado_em: string | null
    cegamento_aberto: number
    criado_em: string
  }
  amostra: Record<string, number>
  cobertura: Record<string, { feito: number; esperado: number } | null>
  consenso: boolean
  rodadas: { id: number; conjunto_piloto: string; status: string; criada_em: string; versao: number; hash: string;
    mudancas: { adicionados: string[]; removidos: string[]; alterados: string[] } | null }[]
  validacao: Record<string, unknown> | null
  decisoes: { campo_chave: string; metrica: string; valor: number | null; ic_inf: number | null; ic_sup: number | null; decisao: string; nota: string }[]
  tamanho: LinhaTamanho[]
}
export interface PilotoResposta { estado: EstadoPiloto | null; n_corpus: number; tamanho: LinhaTamanho[]; avisos: string[] }
export interface MetricaPar {
  n: number
  pct_concordancia: number | null
  metrica: string
  valor: number | null
  ic: [number | null, number | null]
  notas: string[]
  pabak?: number
  pct_exato?: number
  erros?: { mediano: number | null; maximo: number | null }
}
export interface Comparacao {
  piloto_id: number
  execucao_id: number
  conjunto: string
  padrao_ouro: string
  campos: { campo: string; tipo: TipoCampo; lutz_ouro: MetricaPar; humano_humano: MetricaPar | null; decisao: string | null; nota: string }[]
  niveis: { nivel: Nivel; n: number; acertos: number; taxa: number | null; ic_inf: number | null; ic_sup: number | null }[]
  avisos: string[]
}
export interface Formulario {
  campos: Campo[]
  artigos: { chave: string; titulo: string; conjunto: string;
    respostas: Record<string, { valor: string | null; nao_reportado: boolean; pagina: number | null } | null> }[]
  cobertura: { feito: number; esperado: number }
}

export interface EnvItem { nome: string; rotulo: string; segredo: boolean; definido: boolean; valor: string; origem: string; sombreado: boolean }
export interface Config {
  env: EnvItem[]
  lutz_yaml: {
    caminho: string
    texto: string
    valido: boolean
    erro: string
    papeis?: (Extrator & { max_tokens: number; janela_tokens: number | null; esforco: string | null })[]
    estrategia?: string
    avisos?: string[]
    hash?: string
    orcamento_usd?: number | null
    idiomas?: string[]
    formatos?: string[]
    limiares?: Record<string, number | boolean>
  }
}
export interface ModeloOR {
  id: string; nome: string; fornecedor: string; contexto: number | null
  entrada: number | null; saida: number | null; parametros: string[]; criado: number | null
}
export interface CatalogoOR { modelos: ModeloOR[]; atualizado_em: string | null; origem: 'rede' | 'cache' | 'vazio'; erro: string }
export interface ContaOR {
  rotulo: string; uso_usd: number | null; uso_dia_usd: number | null; uso_semana_usd: number | null; uso_mes_usd: number | null
  limite_usd: number | null; limite_restante_usd: number | null; gratuito: boolean
  creditos_usd: number | null; creditos_usados_usd: number | null; saldo_usd: number | null
}
export interface Consumo {
  total: { chamadas: number; tokens_entrada: number; tokens_saida: number; custo_usd: number | null; em_cache: number | null;
    falhas: number | null; sem_preco: number | null }
  por_papel: { papel: string; rotulo: string; provedor: string; modelo_pedido: string; modelo_observado: string; chamadas: number;
    tokens_entrada: number; tokens_saida: number; custo_usd: number | null; latencia_media_ms: number | null; falhas: number }[]
  chamadas: { id: number; execucao_id: number | null; papel: string; rotulo: string; artigo: string | null; provedor: string;
    modelo_pedido: string; modelo_observado: string; tokens_entrada: number; tokens_saida: number; custo_usd: number | null;
    latencia_ms: number; status: string; cache: number; criado_em: string }[]
  por_execucao: { execucao_id: number | null; chamadas: number; tokens: number; custo_usd: number | null }[]
}
export interface McpInfo {
  comando: string
  transporte: string
  somente_leitura: boolean
  config_claude_desktop: unknown
  config_cursor: unknown
  config_vscode: unknown
  ferramentas: { nome: string; descricao: string }[]
  openapi: string
}
export interface Evento { t: number; tipo: string; [k: string]: unknown }
export interface JobCompleto extends JobPublico { resultado: unknown; eventos: Evento[] }

// ── jobs (SSE) ─────────────────────────────────────────────────────────────

export function seguirJob(jobId: string, onEvento: (e: Evento) => void): () => void {
  const es = new EventSource(url(`/jobs/${jobId}/eventos`))
  es.onmessage = (m) => {
    try {
      const ev = JSON.parse(m.data) as Evento
      onEvento(ev)
      if (ev.tipo === 'job_fim') es.close()
    } catch {
      /* ignore malformed event */
    }
  }
  es.onerror = () => es.close()
  return () => es.close()
}

/** Resolves with the full job once it ends (SSE for progress, then one GET for the result). */
export function esperarJob(jobId: string, onEvento?: (e: Evento) => void): Promise<JobCompleto> {
  return new Promise((resolve, reject) => {
    let terminou = false
    const fim = async () => {
      if (terminou) return
      terminou = true
      try {
        const j = await api.get<JobCompleto>(`/jobs/${jobId}`)
        if (j.status === 'falhou') reject(new ApiError(409, j.erro || 'O job falhou.'))
        else resolve(j)
      } catch (e) {
        reject(e)
      }
    }
    const parar = seguirJob(jobId, (ev) => {
      onEvento?.(ev)
      if (ev.tipo === 'job_fim') fim()
    })
    // Fallback polling in case the event stream is interrupted.
    const timer = window.setInterval(async () => {
      try {
        const j = await api.get<JobPublico>(`/jobs/${jobId}`)
        if (j.status !== 'rodando') {
          window.clearInterval(timer)
          parar()
          fim()
        }
      } catch {
        /* keep polling */
      }
    }, 3000)
  })
}
