import { useEffect, useRef, useState } from 'react'
import { useLocation } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  listChatSessions, createChatSession, getChatSession,
  renameChatSession, deleteChatSession, sendSessionMessage,
  listChatMemory, addChatMemory, deleteChatMemory,
  listChatFiles, uploadChatFiles, deleteChatFile, resetChatStore,
  listContextFiles, uploadContextFiles, deleteContextFile,
  type ChatSession, type ChatMessage, type ChatOptions,
  type ChatSource, type ChatMemory, type ChatFile, type ContextFile,
  type DatasetContext,
} from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import ConfirmDialog from '../components/ConfirmDialog'
import './Chat.css'

const ACCEPTED = '.pdf,.docx,.xlsx,.xls,.pptx,.txt,.md,.csv'

// ── Source badges ─────────────────────────────────────────────────────────────

function SourceBadges({ sources }: { sources: ChatSource[] }) {
  if (!sources.length) return null
  const unique = [...new Map(sources.map((s) => [`${s.filename}:${s.page}`, s])).values()]
  return (
    <div className="source-badges">
      {unique.map((s, i) => (
        <span key={i} className="source-badge">
          {s.filename}{s.page > 0 ? ` p.${s.page}` : ''}
        </span>
      ))}
    </div>
  )
}

// ── Markdown prose ────────────────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <div className="message-body">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => <p>{children}</p>,
          h1: ({ children }) => <h1>{children}</h1>,
          h2: ({ children }) => <h2>{children}</h2>,
          h3: ({ children }) => <h3>{children}</h3>,
          ul: ({ children }) => <ul>{children}</ul>,
          ol: ({ children }) => <ol>{children}</ol>,
          li: ({ children }) => <li>{children}</li>,
          blockquote: ({ children }) => <blockquote>{children}</blockquote>,
          code: ({ children, className }) => {
            const isBlock = className?.includes('language-')
            return isBlock ? (
              <pre><code>{children}</code></pre>
            ) : (
              <code>{children}</code>
            )
          },
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">{children}</a>
          ),
          table: ({ children }) => <table>{children}</table>,
          th: ({ children }) => <th>{children}</th>,
          td: ({ children }) => <td>{children}</td>,
          hr: () => <hr />,
          strong: ({ children }) => <strong>{children}</strong>,
          em: ({ children }) => <em>{children}</em>,
        }}
      >
        {content}
      </ReactMarkdown>
    </div>
  )
}

// ── Message row ───────────────────────────────────────────────────────────────

function MessageRow({
  msg, sources, onSaveMemory,
}: {
  msg: ChatMessage
  sources?: ChatSource[]
  onSaveMemory?: (text: string) => void
}) {
  const isUser = msg.role === 'user'
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  const now = new Date()
  const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0')

  return (
    <div className={`message ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">{isUser ? '👤' : '✦'}</div>
      <div className="message-content">
        <div className="message-header">
          <span className="message-name">{isUser ? 'Você' : 'Lutz'}</span>
          <span className="message-time">{timeStr}</span>
        </div>
        {isUser ? (
          <div className="message-body"><p style={{ whiteSpace: 'pre-wrap' }}>{msg.content}</p></div>
        ) : (
          <MarkdownContent content={msg.content} />
        )}
        {!isUser && sources && <SourceBadges sources={sources} />}
        <div className="message-actions">
          <button
            className={`msg-action-btn${copied ? ' copied' : ''}`}
            title="Copiar"
            onClick={handleCopy}
          >
            {copied ? '✓' : '⎘'}
          </button>
          {onSaveMemory && (
            <button
              className="msg-action-btn"
              title="Salvar na memória"
              onClick={() => onSaveMemory(msg.content)}
            >
              📌
            </button>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Sessions sidebar ──────────────────────────────────────────────────────────

function SessionsSidebar({
  sessions, activeId, onSelect, onNew, onDelete, onRename,
  options, setOptions, optionsOpen, setOptionsOpen,
}: {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
  options: ChatOptions
  setOptions: React.Dispatch<React.SetStateAction<ChatOptions>>
  optionsOpen: boolean
  setOptionsOpen: React.Dispatch<React.SetStateAction<boolean>>
}) {
  const { t } = useLanguage()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')
  const [search, setSearch] = useState('')

  function startEdit(s: ChatSession, e: React.MouseEvent) {
    e.stopPropagation()
    setEditingId(s.id)
    setEditTitle(s.title)
  }

  function commitEdit(id: string) {
    if (editTitle.trim()) onRename(id, editTitle.trim())
    setEditingId(null)
  }

  function formatDate(iso: string) {
    const d = new Date(iso)
    const now = new Date()
    const diffDays = Math.floor((now.getTime() - d.getTime()) / 86400000)
    if (diffDays === 0) return d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0')
    if (diffDays === 1) return 'Ontem'
    if (diffDays < 7) return `${diffDays}d`
    return d.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' })
  }

  const filtered = sessions.filter((s) =>
    s.title.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <aside className="chat-sidebar">
      <div className="sidebar-header">
        <div className="sidebar-logo">
          <span>Chat</span>
        </div>
        <button className="new-chat-btn" title={t('chat.sessions.new')} onClick={onNew}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round">
            <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
          </svg>
        </button>
      </div>

      <div className="sidebar-search">
        <input
          type="text"
          placeholder="Buscar conversas..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
      </div>

      <div className="sidebar-section-title">Conversas</div>

      <div className="sidebar-list">
        {filtered.length === 0 && (
          <p style={{ textAlign: 'center', fontSize: 12, color: 'var(--chat-text-muted)', padding: '16px 0' }}>
            {sessions.length === 0 ? t('chat.sessions.empty') : 'Nenhum resultado'}
          </p>
        )}
        {filtered.map((s) => (
          <div
            key={s.id}
            className={`chat-item${s.id === activeId ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <div className="chat-item-icon">💬</div>
            <div className="chat-item-info">
              {editingId === s.id ? (
                <input
                  className="chat-item-rename-input"
                  value={editTitle}
                  autoFocus
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => commitEdit(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') commitEdit(s.id)
                    if (e.key === 'Escape') setEditingId(null)
                  }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <div className="chat-item-title">{s.title}</div>
                  <div className="chat-item-preview">{s.message_count} mensagens</div>
                </>
              )}
            </div>
            {editingId !== s.id && (
              <span className="chat-item-time">{formatDate(s.updated_at)}</span>
            )}
            <div className="chat-item-actions">
              <button
                className="chat-item-action-btn"
                title="Renomear"
                onClick={(e) => startEdit(s, e)}
              >✎</button>
              <button
                className="chat-item-action-btn danger"
                title="Excluir"
                onClick={(e) => { e.stopPropagation(); onDelete(s.id) }}
              >✕</button>
            </div>
          </div>
        ))}
      </div>

      <div className="sidebar-footer">
        <button className="rag-options-toggle" onClick={() => setOptionsOpen((v) => !v)}>
          <span>⚙</span>
          <span style={{ flex: 1 }}>Opções RAG</span>
          <span>{optionsOpen ? '▲' : '▼'}</span>
        </button>
        {optionsOpen && (
          <div className="rag-options-panel">
            <label className="rag-option-row">
              <input
                type="checkbox"
                checked={options.use_rag}
                onChange={(e) => setOptions((o) => ({ ...o, use_rag: e.target.checked }))}
              />
              <div>
                <div className="rag-option-label">{t('chat.opt.rag.label')}</div>
                <div className="rag-option-hint">{t('chat.opt.rag.hint')}</div>
              </div>
            </label>
            <label className="rag-option-row">
              <input
                type="checkbox"
                checked={options.use_model_knowledge}
                onChange={(e) => setOptions((o) => ({ ...o, use_model_knowledge: e.target.checked }))}
              />
              <div>
                <div className="rag-option-label">{t('chat.opt.knowledge.label')}</div>
                <div className="rag-option-hint">{t('chat.opt.knowledge.hint')}</div>
              </div>
            </label>
            <label className="rag-option-row">
              <input
                type="checkbox"
                checked={options.use_context_files}
                onChange={(e) => setOptions((o) => ({ ...o, use_context_files: e.target.checked }))}
              />
              <div>
                <div className="rag-option-label">{t('chat.opt.context.label')}</div>
                <div className="rag-option-hint">{t('chat.opt.context.hint')}</div>
              </div>
            </label>
            <div className="rag-topk-row">
              <span className="rag-topk-label">{t('chat.opt.topk.label')}</span>
              <input
                type="range"
                min={1}
                max={15}
                step={1}
                value={options.top_k}
                onChange={(e) => setOptions((o) => ({ ...o, top_k: Number(e.target.value) }))}
              />
              <span className="rag-topk-value">{options.top_k}</span>
            </div>
          </div>
        )}
      </div>
    </aside>
  )
}

// ── Memory panel (side panel content) ────────────────────────────────────────

function MemoryPanelContent({
  memories, onDelete, onAdd,
}: {
  memories: ChatMemory[]
  onDelete: (id: string) => void
  onAdd: (text: string) => void
}) {
  const { t } = useLanguage()
  const [text, setText] = useState('')

  function handleAdd() {
    if (!text.trim()) return
    onAdd(text.trim())
    setText('')
  }

  return (
    <>
      <div className="memory-list">
        {memories.length === 0 && (
          <p className="memory-empty">{t('chat.memory.empty')}</p>
        )}
        {memories.map((m) => (
          <div key={m.id} className="memory-item">
            <span className={`memory-badge ${m.source === 'auto' ? 'auto' : 'manual'}`}>
              {m.source === 'auto' ? 'auto' : '📌'}
            </span>
            <p className="memory-text">{m.text}</p>
            <button className="memory-delete" onClick={() => onDelete(m.id)}>✕</button>
          </div>
        ))}
      </div>
      <div className="memory-add-row">
        <input
          className="memory-add-input"
          placeholder={t('chat.memory.add')}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
        />
        <button className="memory-add-btn" onClick={handleAdd}>+</button>
      </div>
    </>
  )
}

// ── Files panel (side panel content) ─────────────────────────────────────────

function FilesPanelContent({
  files, contextFiles, onRefreshChat, onRefreshContext,
}: {
  files: ChatFile[]
  contextFiles: ContextFile[]
  onRefreshChat: () => void
  onRefreshContext: () => void
}) {
  const { t } = useLanguage()
  const chatInputRef = useRef<HTMLInputElement>(null)
  const ctxInputRef = useRef<HTMLInputElement>(null)
  const [uploadingChat, setUploadingChat] = useState(false)
  const [uploadingCtx, setUploadingCtx] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [tab, setTab] = useState<'chat' | 'context'>('chat')

  async function handleUploadChat(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    setUploadingChat(true)
    try { await uploadChatFiles(e.target.files); onRefreshChat() } finally {
      setUploadingChat(false)
      if (chatInputRef.current) chatInputRef.current.value = ''
    }
  }

  async function handleUploadCtx(e: React.ChangeEvent<HTMLInputElement>) {
    if (!e.target.files?.length) return
    setUploadingCtx(true)
    try { await uploadContextFiles(e.target.files); onRefreshContext() } finally {
      setUploadingCtx(false)
      if (ctxInputRef.current) ctxInputRef.current.value = ''
    }
  }

  return (
    <>
      {confirmReset && (
        <ConfirmDialog
          title={t('chat.files.resetConfirmTitle')}
          body={t('chat.files.resetConfirmBody')}
          confirmLabel={t('dialog.confirm')}
          danger
          onCancel={() => setConfirmReset(false)}
          onConfirm={async () => { setConfirmReset(false); await resetChatStore(); onRefreshChat() }}
        />
      )}

      <div className="files-tab-bar">
        <button
          className={`files-tab${tab === 'chat' ? ' active' : ''}`}
          onClick={() => setTab('chat')}
        >
          Chat ({files.length})
        </button>
        <button
          className={`files-tab${tab === 'context' ? ' active' : ''}`}
          onClick={() => setTab('context')}
        >
          Contexto ({contextFiles.length})
        </button>
      </div>

      {tab === 'chat' && (
        <>
          <input ref={chatInputRef} type="file" accept={ACCEPTED} multiple className="hidden" onChange={handleUploadChat} />
          <button
            className="files-upload-btn"
            onClick={() => chatInputRef.current?.click()}
            disabled={uploadingChat}
          >
            {uploadingChat ? t('chat.files.uploading') : '+ ' + t('chat.files.upload')}
          </button>
          <div className="files-list">
            {files.map((f) => (
              <div key={f.name} className="files-item">
                <span className="files-item-name">{f.name}</span>
                <button
                  className="files-item-del"
                  onClick={async () => { await deleteChatFile(f.name); onRefreshChat() }}
                >✕</button>
              </div>
            ))}
            {files.length === 0 && <p className="files-empty">{t('chat.files.empty')}</p>}
          </div>
          {files.length > 0 && (
            <button className="files-reset-btn" onClick={() => setConfirmReset(true)}>
              {t('chat.files.reset')}
            </button>
          )}
        </>
      )}

      {tab === 'context' && (
        <>
          <input ref={ctxInputRef} type="file" accept={ACCEPTED} multiple className="hidden" onChange={handleUploadCtx} />
          <button
            className="files-upload-btn"
            onClick={() => ctxInputRef.current?.click()}
            disabled={uploadingCtx}
          >
            {uploadingCtx ? t('chat.files.uploading') : '+ Adicionar arquivo de contexto'}
          </button>
          <p className="files-hint">Compartilhados com toda a aplicação (aba Vetorização).</p>
          <div className="files-list">
            {contextFiles.map((f) => (
              <div key={f.name} className="files-item">
                <span className="files-item-name">{f.name}</span>
                <span className={`files-item-status${f.vectorized ? '' : ''}`} style={{ color: f.vectorized ? '#4ade80' : '#fbbf24' }}>
                  {f.vectorized ? '✓' : '⏳'}
                </span>
                <button
                  className="files-item-del"
                  onClick={async () => { await deleteContextFile(f.name); onRefreshContext() }}
                >✕</button>
              </div>
            ))}
            {contextFiles.length === 0 && (
              <p className="files-empty">Nenhum arquivo de contexto.</p>
            )}
          </div>
        </>
      )}
    </>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Chat() {
  const { t, reportLang } = useLanguage()
  const location = useLocation()
  const incomingDataset = location.state?.datasetContext as DatasetContext | undefined

  // Sessions
  const [sessions, setSessions] = useState<ChatSession[]>([])
  const [activeId, setActiveId] = useState<string | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [sourcesMap, setSourcesMap] = useState<Record<number, ChatSource[]>>({})

  // Memory
  const [memories, setMemories] = useState<ChatMemory[]>([])
  const [showMemory, setShowMemory] = useState(false)

  // Files
  const [files, setFiles] = useState<ChatFile[]>([])
  const [contextFiles, setContextFiles] = useState<ContextFile[]>([])
  const [showFiles, setShowFiles] = useState(false)

  // Confirm delete session dialog
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  // Dataset context from navigation
  const [activeDataset, setActiveDataset] = useState<DatasetContext | undefined>(incomingDataset)

  // Input & options
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [options, setOptions] = useState<ChatOptions>({
    use_rag: true, use_model_knowledge: true, use_context_files: false, top_k: 5,
  })
  const [hasStarted, setHasStarted] = useState(!!incomingDataset)

  const bottomRef = useRef<HTMLDivElement>(null)
  const chatFileInputRef = useRef<HTMLInputElement>(null)

  // Load initial data
  useEffect(() => {
    listChatSessions().then((r) => setSessions(r.sessions ?? []))
    listChatMemory().then((r) => setMemories(r.memories ?? []))
    listChatFiles().then((r) => setFiles(r.files ?? []))
    listContextFiles().then((r) => setContextFiles(r.files ?? []))
  }, [])

  // Auto-create session when arriving with a dataset context and no active session
  useEffect(() => {
    if (incomingDataset && !activeId) {
      createChatSession().then(({ session }) => {
        setSessions((prev) => [session, ...prev])
        setActiveId(session.id)
        setMessages([])
        setSourcesMap({})
      })
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  // ── Session actions ──

  async function handleNewSession() {
    const { session } = await createChatSession()
    setSessions((prev) => [session, ...prev])
    setActiveId(session.id)
    setMessages([])
    setSourcesMap({})
    setHasStarted(false)
  }

  async function handleSelectSession(id: string) {
    if (id === activeId) return
    const { session } = await getChatSession(id)
    setActiveId(id)
    setMessages(session.messages)
    setSourcesMap({})
    if (session.messages.length > 0) setHasStarted(true)
  }

  async function handleDeleteSession(id: string) {
    await deleteChatSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
    if (activeId === id) { setActiveId(null); setMessages([]); setSourcesMap({}); setHasStarted(false) }
  }

  async function handleRenameSession(id: string, title: string) {
    await renameChatSession(id, title)
    setSessions((prev) => prev.map((s) => s.id === id ? { ...s, title } : s))
  }

  // ── Memory actions ──

  async function handleAddMemory(text: string, sessionId?: string) {
    const { memory } = await addChatMemory(text, sessionId)
    setMemories((prev) => [...prev, memory])
  }

  async function handleDeleteMemory(id: string) {
    await deleteChatMemory(id)
    setMemories((prev) => prev.filter((m) => m.id !== id))
  }

  // ── Send message ──

  async function handleSend() {
    const text = input.trim()
    if (!text || loading) return

    let sessionId = activeId
    if (!sessionId) {
      const { session } = await createChatSession()
      setSessions((prev) => [session, ...prev])
      setActiveId(session.id)
      setMessages([])
      setSourcesMap({})
      sessionId = session.id
    }

    const optimisticMsg: ChatMessage = { role: 'user', content: text }
    setMessages((prev) => [...prev, optimisticMsg])
    setInput('')
    setLoading(true)
    setHasStarted(true)

    try {
      const result = await sendSessionMessage(sessionId, text, options, reportLang, activeDataset)
      const assistantMsg: ChatMessage = { role: 'assistant', content: result.response }
      const idx = messages.length + 1
      setMessages((prev) => [...prev, assistantMsg])
      if (result.sources.length) setSourcesMap((prev) => ({ ...prev, [idx]: result.sources }))
      setSessions((prev) => prev.map((s) =>
        s.id === sessionId
          ? { ...s, title: result.title, message_count: s.message_count + 2, updated_at: new Date().toISOString() }
          : s
      ))
    } catch (err) {
      setMessages((prev) => [...prev, { role: 'assistant', content: `⚠ ${(err as Error).message}` }])
    } finally {
      setLoading(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() }
  }

  function useSuggestion(text: string) {
    setInput(text)
    setHasStarted(true)
    // Defer send so state update for input completes first
    setTimeout(() => {
      const trimmed = text.trim()
      if (!trimmed || loading) return
      setInput('')
      setLoading(true)

      const doSend = async () => {
        let sessionId = activeId
        if (!sessionId) {
          const { session } = await createChatSession()
          setSessions((prev) => [session, ...prev])
          setActiveId(session.id)
          setMessages([])
          setSourcesMap({})
          sessionId = session.id
        }
        const optimisticMsg: ChatMessage = { role: 'user', content: trimmed }
        setMessages((prev) => [...prev, optimisticMsg])
        try {
          const result = await sendSessionMessage(sessionId, trimmed, options, reportLang, activeDataset)
          const assistantMsg: ChatMessage = { role: 'assistant', content: result.response }
          const idx = messages.length + 1
          setMessages((prev) => [...prev, assistantMsg])
          if (result.sources.length) setSourcesMap((prev) => ({ ...prev, [idx]: result.sources }))
          setSessions((prev) => prev.map((s) =>
            s.id === sessionId
              ? { ...s, title: result.title, message_count: s.message_count + 2, updated_at: new Date().toISOString() }
              : s
          ))
        } catch (err) {
          setMessages((prev) => [...prev, { role: 'assistant', content: `⚠ ${(err as Error).message}` }])
        } finally {
          setLoading(false)
        }
      }
      doSend()
    }, 0)
  }

  // Derived: show welcome layout when nothing has started yet
  const showCentered = !hasStarted && messages.length === 0

  const activeTitle = activeId ? sessions.find((s) => s.id === activeId)?.title ?? t('chat.title') : t('chat.title')

  return (
    // Use negative margins to escape the Layout's px-4 py-8 padding, then full viewport height minus navbar
    <div
      className="chat-root flex overflow-hidden"
      style={{ height: 'calc(100vh - 3.5rem)' }}
    >
      {/* ── Confirm delete session dialog ── */}
      {confirmDeleteId && (
        <ConfirmDialog
          title={t('chat.sessions.deleteConfirm')}
          body={t('chat.sessions.deleteConfirmBody')}
          confirmLabel={t('dialog.delete')}
          danger
          onCancel={() => setConfirmDeleteId(null)}
          onConfirm={() => { handleDeleteSession(confirmDeleteId); setConfirmDeleteId(null) }}
        />
      )}

      {/* Hidden file input for attach button */}
      <input
        ref={chatFileInputRef}
        type="file"
        accept={ACCEPTED}
        multiple
        className="hidden"
        onChange={async (e) => {
          if (!e.target.files?.length) return
          await uploadChatFiles(e.target.files)
          listChatFiles().then((r) => setFiles(r.files ?? []))
          if (chatFileInputRef.current) chatFileInputRef.current.value = ''
        }}
      />

      {/* ── Sidebar ── */}
      <SessionsSidebar
        sessions={sessions}
        activeId={activeId}
        onSelect={handleSelectSession}
        onNew={handleNewSession}
        onDelete={(id) => setConfirmDeleteId(id)}
        onRename={handleRenameSession}
        options={options}
        setOptions={setOptions}
        optionsOpen={optionsOpen}
        setOptionsOpen={setOptionsOpen}
      />

      {/* ── Main area ── */}
      <main className="chat-main">

        {/* Topbar */}
        <div className="chat-topbar">
          <div className="topbar-left">
            <span className="topbar-title">{activeTitle}</span>
            <span className="topbar-model">Lutz RAG</span>
          </div>
          <div className="topbar-right">
            <button
              className={`topbar-btn${showMemory ? ' active' : ''}`}
              onClick={() => { setShowMemory((v) => !v); setShowFiles(false) }}
              title={t('chat.memory.title')}
            >
              📌
            </button>
          </div>
        </div>

        {/* Chat area */}
        <div className="chat-area">
          <div className="chat-messages">

            {showCentered ? (
              <div className="welcome">
                <h2>Como posso ajudar?</h2>
                <p>Pergunte sobre seus artigos científicos ou peça uma análise.</p>
                <div className="suggestions">
                  <div
                    className="suggestion-chip"
                    onClick={() => useSuggestion('Resuma os principais achados dos artigos vetorizados')}
                  >
                    <span className="chip-icon">🔬</span>
                    <span className="chip-text">
                      <strong>Resumo</strong>Principais achados dos artigos
                    </span>
                  </div>
                  <div
                    className="suggestion-chip"
                    onClick={() => useSuggestion('Quais metodologias são mais utilizadas?')}
                  >
                    <span className="chip-icon">📊</span>
                    <span className="chip-text">
                      <strong>Metodologia</strong>Técnicas mais recorrentes
                    </span>
                  </div>
                  <div
                    className="suggestion-chip"
                    onClick={() => useSuggestion('Identifique lacunas de pesquisa na literatura')}
                  >
                    <span className="chip-icon">🧠</span>
                    <span className="chip-text">
                      <strong>Lacunas</strong>Oportunidades de pesquisa
                    </span>
                  </div>
                  <div
                    className="suggestion-chip"
                    onClick={() => useSuggestion('Compare as abordagens dos diferentes autores')}
                  >
                    <span className="chip-icon">⚡</span>
                    <span className="chip-text">
                      <strong>Comparação</strong>Perspectivas dos autores
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <>
                {messages.length === 0 && activeId ? (
                  <div style={{ textAlign: 'center', padding: '40px 0', color: 'var(--chat-text-muted)', fontSize: 14 }}>
                    {t('chat.empty')}
                  </div>
                ) : (
                  messages.map((msg, i) => (
                    <MessageRow
                      key={i}
                      msg={msg}
                      sources={msg.role === 'assistant' ? sourcesMap[i] : undefined}
                      onSaveMemory={msg.role === 'assistant'
                        ? (text) => handleAddMemory(text.slice(0, 300), activeId ?? undefined)
                        : undefined}
                    />
                  ))
                )}
                {loading && (
                  <div className="message assistant">
                    <div className="message-avatar">✦</div>
                    <div className="message-content">
                      <div className="message-header">
                        <span className="message-name">Lutz</span>
                      </div>
                      <div className="typing-indicator">
                        <span /><span /><span />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>
        </div>

        {/* Input area */}
        <div className="chat-input-area">
          <div className="input-wrapper">
            {/* Dataset context banner */}
            {activeDataset && (
              <div className="dataset-banner">
                <span className="dataset-banner-icon">📊</span>
                <span className="dataset-banner-name">Contexto ativo: {activeDataset.name}</span>
                <span className="dataset-banner-meta">
                  {activeDataset.row_count} linhas · {activeDataset.columns.length} colunas
                </span>
                <button
                  className="dataset-banner-close"
                  title="Remover contexto"
                  onClick={() => setActiveDataset(undefined)}
                >
                  ✕
                </button>
              </div>
            )}

            <div className="input-box">
              <textarea
                rows={1}
                placeholder={t('chat.input.placeholder')}
                value={input}
                onChange={(e) => {
                  setInput(e.target.value)
                  // auto-resize
                  e.target.style.height = 'auto'
                  e.target.style.height = Math.min(e.target.scrollHeight, 160) + 'px'
                }}
                onKeyDown={handleKeyDown}
                disabled={loading}
                autoFocus={showCentered}
              />
              <div className="input-toolbar">
                <div className="input-tools">
                  <button
                    className="tool-btn"
                    title="Anexar arquivo"
                    onClick={() => chatFileInputRef.current?.click()}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                      <path d="M21.44 11.05l-9.19 9.19a6 6 0 01-8.49-8.49l9.19-9.19a4 4 0 015.66 5.66L9.41 17.41a2 2 0 01-2.83-2.83l8.49-8.49" />
                    </svg>
                  </button>
                  <button
                    className={`tool-btn${showFiles ? ' active' : ''}`}
                    title={t('chat.files.title')}
                    onClick={() => { setShowFiles((v) => !v); setShowMemory(false) }}
                  >
                    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
                      <polyline points="14 2 14 8 20 8" />
                    </svg>
                  </button>
                </div>
                <button
                  className={`send-btn${!input.trim() || loading ? ' disabled' : ''}`}
                  onClick={handleSend}
                  disabled={!input.trim() || loading}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                    <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
                  </svg>
                </button>
              </div>
            </div>
            <div className="input-footer">{t('chat.input.hint')}</div>
          </div>
        </div>

        {/* Memory side panel */}
        {showMemory && (
          <div className="chat-side-panel">
            <div className="side-panel-header">
              <span>📌 {t('chat.memory.title')} ({memories.length})</span>
              <button className="side-panel-close" onClick={() => setShowMemory(false)}>✕</button>
            </div>
            <div className="side-panel-body">
              <MemoryPanelContent
                memories={memories}
                onDelete={handleDeleteMemory}
                onAdd={(text) => handleAddMemory(text, activeId ?? undefined)}
              />
            </div>
          </div>
        )}

        {/* Files side panel */}
        {showFiles && (
          <div className="chat-side-panel">
            <div className="side-panel-header">
              <span>📎 {t('chat.files.title')}</span>
              <button className="side-panel-close" onClick={() => setShowFiles(false)}>✕</button>
            </div>
            <div className="side-panel-body">
              <FilesPanelContent
                files={files}
                contextFiles={contextFiles}
                onRefreshChat={() => listChatFiles().then((r) => setFiles(r.files ?? []))}
                onRefreshContext={() => listContextFiles().then((r) => setContextFiles(r.files ?? []))}
              />
            </div>
          </div>
        )}

      </main>
    </div>
  )
}
