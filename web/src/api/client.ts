const BASE = '/api'

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    throw new Error(err.error ?? res.statusText)
  }
  return res.json()
}

// ── Project ───────────────────────────────────────────────────────────────────
export interface ProjectInfo {
  root: string
  articles: number
  reports: number
}
export const getProject = () => request<ProjectInfo>('GET', '/project')

// ── Articles ──────────────────────────────────────────────────────────────────
export interface Article { name: string; size: number }
export const listArticles = () => request<{ articles: Article[] }>('GET', '/articles')

export async function uploadArticles(files: FileList): Promise<string[]> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const res = await fetch(`${BASE}/articles/upload`, { method: 'POST', body: form })
  const data = await res.json()
  return data.uploaded ?? []
}

export const deleteArticle = (name: string) =>
  request<{ ok: boolean }>('DELETE', `/articles/${encodeURIComponent(name)}`)

export const deleteAllArticles = () =>
  request<{ deleted: number }>('DELETE', '/articles')

export const getArticleFileUrl = (name: string) =>
  `${BASE}/articles/${encodeURIComponent(name)}/file`

export const suggestArticleRename = (name: string) =>
  request<{ original: string; suggested: string }>('POST', `/articles/${encodeURIComponent(name)}/suggest-rename`, {})

export const renameArticle = (name: string, new_name: string) =>
  request<{ ok: boolean; new_name: string }>('POST', `/articles/${encodeURIComponent(name)}/rename`, { new_name })

// ── Vector Store ──────────────────────────────────────────────────────────────
export interface VectorStoreInfo {
  total_records: number
  unique_documents: number
  last_updated: string | null
  embedding_model: string | null
  embedding_provider: string | null
  articles: Array<{ filename: string; chunk_count: number; vectorized_at: string; embedding_model: string }>
}
export const getVectorStore = () => request<VectorStoreInfo>('GET', '/vector-store')
export const resetVectorStore = () => request<{ ok: boolean }>('DELETE', '/vector-store')

export interface QueryResult {
  columns: string[]
  // Rows may contain arrays from UDF outputs (pca_project, embedding_normalize…)
  rows: (string | number | boolean | null | unknown[])[][]
  count: number
  elapsed_ms: number
  error?: string
}
export const queryVectorStore = (sql: string) =>
  request<QueryResult>('POST', '/vector-store/query', { sql })

export const queryVectorStoreAnalytics = (sql: string, includeEmbeddings = false) =>
  request<QueryResult>('POST', '/vector-store/query', {
    sql,
    include_embeddings: includeEmbeddings,
  })

export interface UDFInfo {
  name: string
  description: string
  vectorized: boolean
}
export const listUDFs = () =>
  request<{ udfs: UDFInfo[] }>('GET', '/vector-store/udfs')

// ── Prompts ───────────────────────────────────────────────────────────────────
export interface Prompt { name: string; path: string }
export const listPrompts = () => request<{ prompts: Prompt[] }>('GET', '/prompts')
export const getPrompt = (name: string) => request<{ name: string; content: string }>('GET', `/prompts/${name}`)
export const savePrompt = (name: string, content: string) =>
  request<{ ok: boolean }>('PUT', `/prompts/${name}`, { content })

// ── Reports ───────────────────────────────────────────────────────────────────
export interface ReportMeta {
  name: string
  mode: string
  report_type: string
  started_at: string
  articles: number
  tokens: number
  elapsed: number
  model: string
}
export interface ReportArticle {
  filename: string
  relevance: string
  analysis: string
  chunks_used: number
  llm_total_tokens: number
  error?: string
}
export interface Report {
  metadata: {
    mode: string
    started_at: string
    elapsed_seconds: number
    prompt_path: string
    llm: { model: string; total_tokens: number }
  }
  articles: ReportArticle[]
}
export const listReports = (mode = '') => request<{ reports: ReportMeta[] }>('GET', `/reports${mode ? `?mode=${mode}` : ''}`)
export const getReport = (name: string) => request<Report>('GET', `/reports/${name}`)
export const getRawReport = (name: string) => request<Record<string, unknown>>('GET', `/reports/${name}`)
export const deleteReport = (name: string) => request<{ ok: boolean }>('DELETE', `/reports/${name}`)
export const deleteAllReports = (alsoVectorStore = false) =>
  request<{ deleted: number; vector_store_dropped: number }>('DELETE', `/reports${alsoVectorStore ? '?also_vector_store=true' : ''}`)

// ── Typed report shapes ───────────────────────────────────────────────────────
export interface RoadmapArticleEntry { filename: string; reading_note: string }
export interface RoadmapStage { stage_number: number; stage_name: string; description: string; articles: RoadmapArticleEntry[] }
export interface RoadmapReport {
  metadata: { report_type: string; generated_at: string; elapsed_seconds: number; relevant: number; llm: { model: string; total_tokens: number } }
  roadmap: { overview: string; stages: RoadmapStage[] }
}

export interface CitationEntry { text: string }
export interface CitationsArticleEntry { filename: string; label: string; confidence: number; reasoning: string; citations: CitationEntry[]; llm_total_tokens: number }
export interface CitationsReport {
  metadata: { report_type: string; generated_at: string; elapsed_seconds: number; llm: { model: string; total_tokens: number } }
  relevant_articles: CitationsArticleEntry[]
  not_relevant_articles: CitationsArticleEntry[]
}

// ── Config ────────────────────────────────────────────────────────────────────
export interface Config {
  LLM_PROVIDER: string
  LLM_MODEL: string
  LLM_MAX_TOKENS: string
  LLM_TEMPERATURE: string
  EMBEDDING_PROVIDER: string
  EMBEDDING_MODEL: string
  OPENAI_BASE_URL: string
  DOCKER_MODEL_HOST: string
  REPORT_LANGUAGE: string
  has_openai_key: boolean
  has_anthropic_key: boolean
}
export const getConfig = () => request<Config>('GET', '/config')
export const saveConfig = (cfg: Partial<Config> & Record<string, string>) =>
  request<{ ok: boolean }>('PUT', '/config', cfg)

// ── Context files ─────────────────────────────────────────────────────────────
export interface ContextFile {
  name: string
  size: number
  vectorized: boolean
  chunks: number
}
export const listContextFiles = () => request<{ files: ContextFile[] }>('GET', '/context')

export async function uploadContextFiles(files: FileList): Promise<{ uploaded: string[]; errors: string[] }> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const res = await fetch(`${BASE}/context/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

export const deleteContextFile = (name: string) =>
  request<{ ok: boolean }>('DELETE', `/context/${encodeURIComponent(name)}`)

// ── Chat ──────────────────────────────────────────────────────────────────────
export interface ChatFile { name: string; chunks: number }
export interface ChatMessage { role: 'user' | 'assistant'; content: string }
export interface ChatOptions {
  use_rag: boolean
  use_model_knowledge: boolean
  use_context_files: boolean
  top_k: number
}
export interface ChatSource { filename: string; page: number }
export interface ChatResponse { response: string; usage: { prompt_tokens: number; completion_tokens: number; total_tokens: number }; sources: ChatSource[] }

// ── Chat sessions ─────────────────────────────────────────────────────────────
export interface ChatSession {
  id: string
  title: string
  created_at: string
  updated_at: string
  message_count: number
}
export interface ChatSessionDetail extends ChatSession {
  messages: ChatMessage[]
}
export interface ChatMemory { id: string; text: string; session_id: string; created_at: string; source?: 'auto' | 'manual' }

export const listChatSessions = () => request<{ sessions: ChatSession[] }>('GET', '/chat/sessions')
export const createChatSession = (title?: string) =>
  request<{ session: ChatSessionDetail }>('POST', '/chat/sessions', title ? { title } : {})
export const getChatSession = (id: string) =>
  request<{ session: ChatSessionDetail }>('GET', `/chat/sessions/${id}`)
export const renameChatSession = (id: string, title: string) =>
  request<{ ok: boolean }>('PUT', `/chat/sessions/${id}/title`, { title })
export const deleteChatSession = (id: string) =>
  request<{ ok: boolean }>('DELETE', `/chat/sessions/${id}`)

export interface DatasetContext {
  id?: string
  name: string
  source: 'vector_store' | 'analytics'
  query?: string | null
  columns: string[]
  rows: unknown[][]
  row_count: number
}

export const sendSessionMessage = (
  sessionId: string, content: string, options: ChatOptions, language: string,
  datasetContext?: DatasetContext,
) => request<ChatResponse & { title: string }>('POST', `/chat/sessions/${sessionId}/message`,
  { content, options, language, ...(datasetContext ? { dataset_context: datasetContext } : {}) })

export const listChatMemory = () => request<{ memories: ChatMemory[] }>('GET', '/chat/memory')
export const addChatMemory = (text: string, session_id?: string) =>
  request<{ memory: ChatMemory }>('POST', '/chat/memory', { text, session_id })
export const deleteChatMemory = (id: string) =>
  request<{ ok: boolean }>('DELETE', `/chat/memory/${id}`)

export const listChatFiles = () => request<{ files: ChatFile[] }>('GET', '/chat/files')

export async function uploadChatFiles(files: FileList): Promise<{ uploaded: string[]; errors: string[] }> {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  const res = await fetch(`${BASE}/chat/files/upload`, { method: 'POST', body: form })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail ?? res.statusText)
  }
  return res.json()
}

export const deleteChatFile = (name: string) =>
  request<{ ok: boolean }>('DELETE', `/chat/files/${encodeURIComponent(name)}`)

export const resetChatStore = () => request<{ ok: boolean }>('DELETE', '/chat/store')

export const sendChatMessage = (messages: ChatMessage[], options: ChatOptions, language: string) =>
  request<ChatResponse>('POST', '/chat/message', { messages, options, language })

// ── Projects ──────────────────────────────────────────────────────────────────
export interface Project {
  id: string
  name: string
  color: string
  icon: string
  article_count: number
  dataset_count: number
  created_at: string
  updated_at: string
}

export const listProjects = () => request<{ projects: Project[] }>('GET', '/projects')
export const createProject = (data: { name: string; color?: string; icon?: string }) =>
  request<{ project: Project }>('POST', '/projects', data)
export const updateProject = (id: string, data: Partial<Project>) =>
  request<{ project: Project }>('PUT', `/projects/${id}`, data)
export const deleteProject = (id: string) =>
  request<{ ok: boolean }>('DELETE', `/projects/${id}`)

export const listProjectArticles = (projectId: string) =>
  request<{ articles: string[] }>('GET', `/projects/${encodeURIComponent(projectId)}/articles`)

export const addArticlesToProject = (projectId: string, paths: string[]) =>
  request<{ ok: boolean }>('POST', `/projects/${encodeURIComponent(projectId)}/articles`, { paths })

export const removeArticleFromProject = (projectId: string, articlePath: string) =>
  request<{ ok: boolean }>('DELETE', `/projects/${encodeURIComponent(projectId)}/articles/${encodeURIComponent(articlePath)}`)

// ── Datasets ──────────────────────────────────────────────────────────────────
export interface Dataset {
  id: string
  name: string
  source: 'vector_store' | 'analytics'
  project_id: string | null
  query: string | null
  columns: string[]
  rows?: unknown[][]
  row_count: number
  metadata: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export const listDatasets = (projectId?: string) =>
  request<{ datasets: Dataset[] }>('GET', `/datasets${projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''}`)
export const createDataset = (data: Omit<Dataset, 'id' | 'created_at'>) =>
  request<{ dataset: Dataset }>('POST', '/datasets', data)
export const getDataset = (id: string) =>
  request<{ dataset: Dataset }>('GET', `/datasets/${id}`)
export const deleteDataset = (id: string) =>
  request<{ ok: boolean }>('DELETE', `/datasets/${id}`)

// ── Store Catalog ─────────────────────────────────────────────────────────────
export interface CatalogColumn {
  name: string
  type: string
  description?: string
}

export interface CatalogTable {
  name: string
  description?: string
  record_count: number
  last_updated: string | null
  columns: CatalogColumn[]
}

export const fetchStoreCatalog = () =>
  request<{ tables: CatalogTable[] }>('GET', '/store/catalog')

// ── SSE stream helper ─────────────────────────────────────────────────────────
export interface StreamCallbacks {
  onLine: (line: string) => void
  onDone: () => void
  onError: (code: number) => void
}

export function startStream(
  path: string,
  body: unknown,
  callbacks: StreamCallbacks,
): AbortController {
  const ctrl = new AbortController()

  fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: ctrl.signal,
  }).then(async (res) => {
    const reader = res.body!.getReader()
    const dec = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += dec.decode(value, { stream: true })
      const parts = buffer.split('\n\n')
      buffer = parts.pop() ?? ''
      for (const part of parts) {
        const line = part.replace(/^data: /, '').trim()
        if (!line) continue
        if (line === '__done__') {
          callbacks.onDone()
        } else if (line.startsWith('__error__:')) {
          callbacks.onError(parseInt(line.split(':')[1] ?? '1'))
        } else {
          callbacks.onLine(line)
        }
      }
    }
  }).catch((err) => {
    if (err.name !== 'AbortError') callbacks.onError(1)
  })

  return ctrl
}
