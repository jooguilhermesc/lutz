import { useEffect, useRef, useState } from 'react'
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
} from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import ConfirmDialog from '../components/ConfirmDialog'

const ACCEPTED = '.pdf,.docx,.xlsx,.xls,.pptx,.txt,.md,.csv'

// ── Source badges ─────────────────────────────────────────────────────────────

function SourceBadges({ sources }: { sources: ChatSource[] }) {
  if (!sources.length) return null
  const unique = [...new Map(sources.map((s) => [`${s.filename}:${s.page}`, s])).values()]
  return (
    <div className="flex flex-wrap gap-1 mt-2">
      {unique.map((s, i) => (
        <span key={i} className="text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-500 border border-slate-200">
          {s.filename}{s.page > 0 ? ` p.${s.page}` : ''}
        </span>
      ))}
    </div>
  )
}

// ── Markdown prose ────────────────────────────────────────────────────────────

function MarkdownContent({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        h1: ({ children }) => <h1 className="text-base font-bold mt-3 mb-1">{children}</h1>,
        h2: ({ children }) => <h2 className="text-sm font-bold mt-3 mb-1">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mt-2 mb-1">{children}</h3>,
        ul: ({ children }) => <ul className="list-disc pl-4 mb-2 space-y-0.5">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal pl-4 mb-2 space-y-0.5">{children}</ol>,
        li: ({ children }) => <li className="text-sm">{children}</li>,
        blockquote: ({ children }) => (
          <blockquote className="border-l-2 border-slate-300 pl-3 my-2 text-slate-500 italic">{children}</blockquote>
        ),
        code: ({ children, className }) => {
          const isBlock = className?.includes('language-')
          return isBlock ? (
            <pre className="bg-slate-100 rounded-md p-3 overflow-x-auto my-2 text-xs font-mono">
              <code>{children}</code>
            </pre>
          ) : (
            <code className="bg-slate-100 rounded px-1 py-0.5 text-xs font-mono">{children}</code>
          )
        },
        a: ({ href, children }) => (
          <a href={href} target="_blank" rel="noopener noreferrer" className="text-lutz-600 underline hover:text-lutz-700">
            {children}
          </a>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-2">
            <table className="text-xs border-collapse w-full">{children}</table>
          </div>
        ),
        th: ({ children }) => <th className="border border-slate-200 bg-slate-50 px-2 py-1 font-semibold text-left">{children}</th>,
        td: ({ children }) => <td className="border border-slate-200 px-2 py-1">{children}</td>,
        hr: () => <hr className="my-3 border-slate-200" />,
        strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
        em: ({ children }) => <em className="italic">{children}</em>,
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

// ── Message bubble ────────────────────────────────────────────────────────────

function MessageBubble({
  msg, sources, onSaveMemory,
}: {
  msg: ChatMessage
  sources?: ChatSource[]
  onSaveMemory?: (text: string) => void
}) {
  const isUser = msg.role === 'user'
  const [hover, setHover] = useState(false)
  const [copied, setCopied] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(msg.content).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 1500)
    })
  }

  return (
    <div
      className={`flex ${isUser ? 'justify-end' : 'justify-start'} group`}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
    >
      <div className={`relative max-w-[80%] rounded-2xl px-4 py-3 text-sm leading-relaxed ${
        isUser
          ? 'bg-lutz-500 text-white rounded-br-sm whitespace-pre-wrap'
          : 'bg-white border border-slate-200 text-slate-800 rounded-bl-sm shadow-sm'
      }`}>
        {isUser ? msg.content : <MarkdownContent content={msg.content} />}
        {!isUser && sources && <SourceBadges sources={sources} />}

        {/* Action buttons (assistant only) — bottom-right corner */}
        {!isUser && hover && (
          <div className="flex justify-end gap-1 mt-2">
            {onSaveMemory && (
              <button
                className="bg-lutz-50 text-lutz-600 border border-lutz-200 text-[10px] px-2 py-0.5 rounded-full hover:bg-lutz-100 transition-colors"
                title="Salvar na memória"
                onClick={() => onSaveMemory(msg.content)}
              >
                📌 salvar
              </button>
            )}
            <button
              className="bg-slate-100 text-slate-600 border border-slate-200 text-[10px] px-2 py-0.5 rounded-full hover:bg-slate-200 transition-colors"
              title="Copiar"
              onClick={handleCopy}
            >
              {copied ? '✓ copiado' : '⎘ copiar'}
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Sessions sidebar ──────────────────────────────────────────────────────────

function SessionsSidebar({
  sessions, activeId, onSelect, onNew, onDelete, onRename,
}: {
  sessions: ChatSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
  onDelete: (id: string) => void
  onRename: (id: string, title: string) => void
}) {
  const { t } = useLanguage()
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editTitle, setEditTitle] = useState('')

  function startEdit(s: ChatSession) {
    setEditingId(s.id)
    setEditTitle(s.title)
  }

  function commitEdit(id: string) {
    if (editTitle.trim()) onRename(id, editTitle.trim())
    setEditingId(null)
  }

  return (
    <div className="flex flex-col gap-2 h-full">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">{t('chat.sessions.title')}</span>
        <button
          className="text-xs px-2 py-0.5 rounded bg-lutz-500 text-white hover:bg-lutz-600 transition-colors"
          onClick={onNew}
        >
          + {t('chat.sessions.new')}
        </button>
      </div>

      <div className="flex-1 overflow-y-auto space-y-1 min-h-0">
        {sessions.length === 0 && (
          <p className="text-xs text-slate-400 text-center py-4">{t('chat.sessions.empty')}</p>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`group rounded-lg px-2 py-2 cursor-pointer transition-colors flex items-start gap-1 ${
              s.id === activeId ? 'bg-lutz-50 border border-lutz-200' : 'hover:bg-slate-50'
            }`}
            onClick={() => onSelect(s.id)}
          >
            <div className="flex-1 min-w-0">
              {editingId === s.id ? (
                <input
                  className="input text-xs py-0.5 w-full"
                  value={editTitle}
                  autoFocus
                  onChange={(e) => setEditTitle(e.target.value)}
                  onBlur={() => commitEdit(s.id)}
                  onKeyDown={(e) => { if (e.key === 'Enter') commitEdit(s.id); if (e.key === 'Escape') setEditingId(null) }}
                  onClick={(e) => e.stopPropagation()}
                />
              ) : (
                <>
                  <p className="text-xs font-medium text-slate-700 truncate">{s.title}</p>
                  <p className="text-[10px] text-slate-400">{s.message_count} msgs</p>
                </>
              )}
            </div>
            <div className="flex-shrink-0 flex gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                className="text-slate-400 hover:text-slate-600 text-[10px]"
                title="Renomear"
                onClick={(e) => { e.stopPropagation(); startEdit(s) }}
              >✎</button>
              <button
                className="text-slate-300 hover:text-red-500 text-[10px]"
                title="Excluir"
                onClick={(e) => { e.stopPropagation(); onDelete(s.id) }}
              >✕</button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Memory panel ──────────────────────────────────────────────────────────────

function MemoryPanel({
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
    <div className="border border-amber-200 bg-amber-50 rounded-xl p-3 space-y-2">
      <div className="flex items-center gap-2">
        <span className="text-xs font-semibold text-amber-700">📌 {t('chat.memory.title')}</span>
        <span className="text-[10px] text-amber-500">{t('chat.memory.hint')}</span>
      </div>
      <div className="space-y-1 max-h-36 overflow-y-auto">
        {memories.length === 0 && (
          <p className="text-xs text-amber-500 italic">{t('chat.memory.empty')}</p>
        )}
        {memories.map((m) => (
          <div key={m.id} className="flex items-start gap-1 group">
            <span className={`text-[9px] flex-shrink-0 mt-0.5 px-1 py-0.5 rounded font-medium ${
              m.source === 'auto'
                ? 'bg-blue-100 text-blue-500'
                : 'bg-amber-100 text-amber-600'
            }`}>
              {m.source === 'auto' ? 'auto' : '📌'}
            </span>
            <p className="text-xs text-slate-700 flex-1 leading-snug">{m.text}</p>
            <button
              className="text-slate-300 hover:text-red-500 text-[10px] flex-shrink-0 opacity-0 group-hover:opacity-100 transition-opacity"
              onClick={() => onDelete(m.id)}
            >✕</button>
          </div>
        ))}
      </div>
      <div className="flex gap-1">
        <input
          className="input text-xs flex-1 py-1"
          placeholder={t('chat.memory.add')}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') handleAdd() }}
        />
        <button className="btn-ghost text-xs px-2" onClick={handleAdd}>+</button>
      </div>
    </div>
  )
}

// ── Files section ─────────────────────────────────────────────────────────────

function FilesSection({
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
  const [open, setOpen] = useState(false)
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

  const totalCount = files.length + contextFiles.length

  return (
    <div className="border-t border-slate-100 pt-2 space-y-2">
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

      <button
        className="flex items-center justify-between w-full text-xs font-semibold text-slate-500 uppercase tracking-wide"
        onClick={() => setOpen((v) => !v)}
      >
        <span>{t('chat.files.title')} ({totalCount})</span>
        <span>{open ? '▲' : '▼'}</span>
      </button>

      {open && (
        <>
          {/* Tab switcher */}
          <div className="flex rounded-md overflow-hidden border border-slate-200 text-[10px]">
            <button
              className={`flex-1 py-1 font-medium transition-colors ${tab === 'chat' ? 'bg-lutz-500 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
              onClick={() => setTab('chat')}
            >
              Chat ({files.length})
            </button>
            <button
              className={`flex-1 py-1 font-medium transition-colors ${tab === 'context' ? 'bg-lutz-500 text-white' : 'bg-white text-slate-500 hover:bg-slate-50'}`}
              onClick={() => setTab('context')}
            >
              Contexto ({contextFiles.length})
            </button>
          </div>

          {tab === 'chat' && (
            <>
              <input ref={chatInputRef} type="file" accept={ACCEPTED} multiple className="hidden" onChange={handleUploadChat} />
              <button
                className="btn-ghost text-xs w-full"
                onClick={() => chatInputRef.current?.click()}
                disabled={uploadingChat}
              >
                {uploadingChat ? t('chat.files.uploading') : '+ ' + t('chat.files.upload')}
              </button>
              <div className="space-y-1 max-h-28 overflow-y-auto">
                {files.map((f) => (
                  <div key={f.name} className="flex items-center justify-between gap-1 group text-xs">
                    <span className="truncate text-slate-600">{f.name}</span>
                    <button
                      className="text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 flex-shrink-0"
                      onClick={async () => { await deleteChatFile(f.name); onRefreshChat() }}
                    >✕</button>
                  </div>
                ))}
                {files.length === 0 && <p className="text-xs text-slate-400">{t('chat.files.empty')}</p>}
              </div>
              {files.length > 0 && (
                <button className="text-xs text-red-400 hover:text-red-600" onClick={() => setConfirmReset(true)}>
                  {t('chat.files.reset')}
                </button>
              )}
            </>
          )}

          {tab === 'context' && (
            <>
              <input ref={ctxInputRef} type="file" accept={ACCEPTED} multiple className="hidden" onChange={handleUploadCtx} />
              <button
                className="btn-ghost text-xs w-full"
                onClick={() => ctxInputRef.current?.click()}
                disabled={uploadingCtx}
              >
                {uploadingCtx ? t('chat.files.uploading') : '+ Adicionar arquivo de contexto'}
              </button>
              <p className="text-[10px] text-slate-400 leading-tight">
                Compartilhados com toda a aplicação (aba Vetorização).
              </p>
              <div className="space-y-1 max-h-28 overflow-y-auto">
                {contextFiles.map((f) => (
                  <div key={f.name} className="flex items-center justify-between gap-1 group text-xs">
                    <span className="truncate text-slate-600">{f.name}</span>
                    <span className={`text-[9px] flex-shrink-0 ${f.vectorized ? 'text-green-500' : 'text-amber-400'}`}>
                      {f.vectorized ? '✓' : '⏳'}
                    </span>
                    <button
                      className="text-slate-300 hover:text-red-500 opacity-0 group-hover:opacity-100 flex-shrink-0"
                      onClick={async () => { await deleteContextFile(f.name); onRefreshContext() }}
                    >✕</button>
                  </div>
                ))}
                {contextFiles.length === 0 && (
                  <p className="text-xs text-slate-400">Nenhum arquivo de contexto.</p>
                )}
              </div>
            </>
          )}
        </>
      )}
    </div>
  )
}

// ── Options toggle ────────────────────────────────────────────────────────────

function OptionToggle({ id, label, hint, checked, onChange }: {
  id: string; label: string; hint: string; checked: boolean; onChange: (v: boolean) => void
}) {
  return (
    <label htmlFor={id} className="flex items-start gap-2 cursor-pointer">
      <input id={id} type="checkbox" className="rounded border-slate-300 text-lutz-500 focus:ring-lutz-400 mt-0.5 flex-shrink-0"
        checked={checked} onChange={(e) => onChange(e.target.checked)} />
      <div>
        <p className="text-sm font-medium text-slate-700">{label}</p>
        <p className="text-xs text-slate-400">{hint}</p>
      </div>
    </label>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Chat() {
  const { t, reportLang } = useLanguage()

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

  // Confirm delete session dialog
  const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null)

  // Input & options
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [optionsOpen, setOptionsOpen] = useState(false)
  const [options, setOptions] = useState<ChatOptions>({
    use_rag: true, use_model_knowledge: true, use_context_files: false, top_k: 5,
  })

  const bottomRef = useRef<HTMLDivElement>(null)

  // Load initial data
  useEffect(() => {
    listChatSessions().then((r) => setSessions(r.sessions ?? []))
    listChatMemory().then((r) => setMemories(r.memories ?? []))
    listChatFiles().then((r) => setFiles(r.files ?? []))
    listContextFiles().then((r) => setContextFiles(r.files ?? []))
  }, [])

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, loading])

  // ── Session actions ──

  async function handleNewSession() {
    const { session } = await createChatSession()
    setSessions((prev) => [session, ...prev])
    setActiveId(session.id)
    setMessages([])
    setSourcesMap({})
  }

  async function handleSelectSession(id: string) {
    if (id === activeId) return
    const { session } = await getChatSession(id)
    setActiveId(id)
    setMessages(session.messages)
    setSourcesMap({})
  }

  async function handleDeleteSession(id: string) {
    await deleteChatSession(id)
    setSessions((prev) => prev.filter((s) => s.id !== id))
    if (activeId === id) { setActiveId(null); setMessages([]); setSourcesMap({}) }
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

    // Auto-create session if none is active
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

    try {
      const result = await sendSessionMessage(sessionId, text, options, reportLang)
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

  const noSession = !activeId

  return (
    <div className="flex gap-4 h-[calc(100vh-10rem)]">

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

      {/* ── Left sidebar: sessions + files ── */}
      <div className="w-56 flex-shrink-0 flex flex-col gap-3">
        <div className="flex-1 min-h-0">
          <SessionsSidebar
            sessions={sessions}
            activeId={activeId}
            onSelect={handleSelectSession}
            onNew={handleNewSession}
            onDelete={(id) => setConfirmDeleteId(id)}
            onRename={handleRenameSession}
          />
        </div>
        <FilesSection
          files={files}
          contextFiles={contextFiles}
          onRefreshChat={() => listChatFiles().then((r) => setFiles(r.files ?? []))}
          onRefreshContext={() => listContextFiles().then((r) => setContextFiles(r.files ?? []))}
        />
      </div>

      {/* ── Main chat area ── */}
      <div className="flex-1 flex flex-col gap-3 min-w-0">

        {/* Header */}
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-xl font-bold text-slate-800">{t('chat.title')}</h2>
          <div className="flex items-center gap-2">
            <button
              className={`btn-ghost text-xs ${showMemory ? 'ring-1 ring-amber-400' : ''}`}
              onClick={() => setShowMemory((v) => !v)}
            >
              📌 {t('chat.memory.title')} ({memories.length})
            </button>
            <button className="btn-ghost text-xs" onClick={() => setOptionsOpen((v) => !v)}>
              ⚙ {t('chat.options')}
            </button>
          </div>
        </div>

        {/* Options */}
        {optionsOpen && (
          <div className="card space-y-3 py-3">
            <OptionToggle id="opt-rag" label={t('chat.opt.rag.label')} hint={t('chat.opt.rag.hint')}
              checked={options.use_rag} onChange={(v) => setOptions((o) => ({ ...o, use_rag: v }))} />
            <OptionToggle id="opt-knowledge" label={t('chat.opt.knowledge.label')} hint={t('chat.opt.knowledge.hint')}
              checked={options.use_model_knowledge} onChange={(v) => setOptions((o) => ({ ...o, use_model_knowledge: v }))} />
            <OptionToggle id="opt-context" label={t('chat.opt.context.label')} hint={t('chat.opt.context.hint')}
              checked={options.use_context_files} onChange={(v) => setOptions((o) => ({ ...o, use_context_files: v }))} />
            <div className="flex items-center gap-2 pt-1">
              <label htmlFor="top-k" className="text-sm text-slate-600 whitespace-nowrap">{t('chat.opt.topk.label')}</label>
              <input id="top-k" type="range" min={1} max={15} step={1} value={options.top_k}
                onChange={(e) => setOptions((o) => ({ ...o, top_k: Number(e.target.value) }))}
                className="flex-1 accent-lutz-500" />
              <span className="text-sm text-slate-600 w-5 text-right">{options.top_k}</span>
            </div>
          </div>
        )}

        {/* Memory panel */}
        {showMemory && (
          <MemoryPanel
            memories={memories}
            onDelete={handleDeleteMemory}
            onAdd={(text) => handleAddMemory(text, activeId ?? undefined)}
          />
        )}

        {/* Messages or welcome */}
        <div className="flex-1 overflow-y-auto space-y-3 pr-1">
          {noSession && messages.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-full gap-4 pb-4">
              <div className="w-14 h-14 bg-lutz-50 border-2 border-lutz-200 rounded-2xl flex items-center justify-center">
                <span className="text-2xl">💬</span>
              </div>
              <div className="text-center space-y-1">
                <p className="text-slate-700 font-semibold text-base">{t('chat.welcome.title')}</p>
                <p className="text-slate-400 text-xs leading-relaxed max-w-xs">{t('chat.welcome.desc')}</p>
              </div>
            </div>
          ) : messages.length === 0 && activeId ? (
            <div className="flex items-center justify-center h-full">
              <p className="text-slate-400 text-sm">{t('chat.empty')}</p>
            </div>
          ) : (
            messages.map((msg, i) => (
              <MessageBubble
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
            <div className="flex justify-start">
              <div className="bg-white border border-slate-200 rounded-2xl rounded-bl-sm px-4 py-3 shadow-sm">
                <div className="flex gap-1 items-center">
                  <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce [animation-delay:0ms]" />
                  <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce [animation-delay:150ms]" />
                  <span className="w-2 h-2 bg-slate-300 rounded-full animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        {/* Input — always visible; creates session on first send */}
        <div className="space-y-1">
          <div className="flex gap-2 items-end">
            <textarea
              className={`input flex-1 resize-none transition-all ${
                noSession
                  ? 'min-h-[96px] max-h-64 text-base'
                  : 'min-h-[44px] max-h-36'
              }`}
              placeholder={t('chat.input.placeholder')}
              rows={noSession ? 4 : 1}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              disabled={loading}
              autoFocus={noSession}
            />
            <button
              className="btn-primary px-4 py-2.5 flex-shrink-0"
              onClick={handleSend}
              disabled={loading || !input.trim()}
            >
              {t('chat.send')}
            </button>
          </div>
          <p className="text-xs text-slate-400">{t('chat.input.hint')}</p>
        </div>
      </div>
    </div>
  )
}
