import { useEffect, useRef, useState } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import {
  streamAgentMessage,
  type AgentMessage,
  type AgentPlan,
  type AgentStep,
} from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import './AgentChat.css'

// ── Tier colour helper ────────────────────────────────────────────────────────

// ── Step status icon ──────────────────────────────────────────────────────────

function stepIconChar(status: AgentStep['status']): string {
  switch (status) {
    case 'running': return '◉'
    case 'done': return '✓'
    case 'error': return '✗'
    default: return '○'
  }
}

// ── Plan panel ────────────────────────────────────────────────────────────────

function PlanPanel({
  plan,
  onClose,
}: {
  plan: AgentPlan | null
  onClose: () => void
}) {
  const { t } = useLanguage()

  return (
    <aside className="agent-plan-panel">
      <div className="agent-panel-header">
        <span>{t('agent.plan.title')}</span>
        <button className="agent-panel-toggle" onClick={onClose} title="Fechar painel">✕</button>
      </div>

      {!plan ? (
        <div className="agent-plan-empty">{t('agent.plan.empty')}</div>
      ) : (
        <>
          {plan.goal && (
            <div className="agent-plan-goal">"{plan.goal}"</div>
          )}
          <div className="agent-step-list">
            {plan.steps.map((step, i) => {
              const status = step.status ?? 'pending'
              const isRunning = status === 'running'
              const isDone = status === 'done'
              const isError = status === 'error'
              const stepClass = [
                'agent-step',
                isRunning ? 'running' : '',
                isDone ? 'done' : '',
                isError ? 'error' : '',
              ].filter(Boolean).join(' ')

              return (
                <div key={i} className={stepClass}>
                  <div className={`agent-step-icon ${status}`}>
                    {stepIconChar(status)}
                  </div>
                  <div className="agent-step-label">
                    <div className="agent-step-tool">
                      {i + 1}. {step.tool}
                    </div>
                    <div className="agent-step-rationale">{step.rationale}</div>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </aside>
  )
}

// ── Detail panel (step result) ────────────────────────────────────────────────

function DetailPanel({
  stepResult,
  onClose,
}: {
  stepResult: Record<string, unknown> | null
  onClose: () => void
}) {
  const { t } = useLanguage()

  return (
    <aside className="agent-detail-panel">
      <div className="agent-panel-header">
        <span>{t('agent.detail.title')}</span>
        <button className="agent-panel-toggle" onClick={onClose} title="Fechar painel">✕</button>
      </div>
      {!stepResult ? (
        <div className="agent-detail-empty">{t('agent.detail.empty')}</div>
      ) : (
        <div className="agent-detail-section">
          <h3>Resultado do passo</h3>
          {Object.entries(stepResult).map(([k, v]) => (
            <div key={k} className="agent-detail-stat">
              <span className="label">{k}</span>
              <span className="value">{String(v)}</span>
            </div>
          ))}
        </div>
      )}
    </aside>
  )
}

// ── Markdown bubble ───────────────────────────────────────────────────────────

function AgentMarkdown({ content }: { content: string }) {
  return (
    <div className="agent-msg-bubble">
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

function MessageRow({ msg }: { msg: AgentMessage }) {
  const isUser = msg.role === 'user'
  const now = new Date()
  const timeStr = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0')

  return (
    <div className={`agent-msg ${msg.role}`}>
      <div className="agent-msg-avatar">
        {isUser ? '👤' : '🧠'}
      </div>
      <div className="agent-msg-body">
        {isUser ? (
          <div className="agent-msg-bubble">
            <p style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{msg.content}</p>
          </div>
        ) : (
          <AgentMarkdown content={msg.content} />
        )}
        <div className="agent-msg-time">{timeStr}</div>
      </div>
    </div>
  )
}

// ── Sidebar (sessions) ────────────────────────────────────────────────────────

interface AgentSession {
  id: string
  title: string
  state: string
}

function AgentSidebar({
  sessions,
  activeId,
  onSelect,
  onNew,
}: {
  sessions: AgentSession[]
  activeId: string | null
  onSelect: (id: string) => void
  onNew: () => void
}) {
  const { t } = useLanguage()

  function stateLabel(state: string): string {
    const key = `agent.state.${state}`
    return t(key) !== key ? t(key) : state
  }

  return (
    <aside className="agent-sidebar">
      <div className="agent-sidebar-header">
        <span className="agent-sidebar-title">{t('agent.sessions.title')}</span>
        <button className="agent-new-btn" onClick={onNew} title={t('agent.sessions.new')}>+</button>
      </div>
      <div className="agent-session-list">
        {sessions.length === 0 && (
          <div className="agent-sidebar-empty">{t('agent.sessions.empty')}</div>
        )}
        {sessions.map((s) => (
          <div
            key={s.id}
            className={`agent-session-item${s.id === activeId ? ' active' : ''}`}
            onClick={() => onSelect(s.id)}
          >
            <span className="agent-session-icon">🤖</span>
            <div className="agent-session-info">
              <div className="agent-session-name">{s.title}</div>
              <div className="agent-session-meta">Sessão agentiva</div>
            </div>
            <span className={`agent-state-badge ${s.state}`}>
              {stateLabel(s.state)}
            </span>
          </div>
        ))}
      </div>
    </aside>
  )
}

// ── State indicator ───────────────────────────────────────────────────────────

function StateIndicator({ state, plan }: { state: string; plan: AgentPlan | null }) {
  const { t } = useLanguage()

  function label(): string {
    if (state === 'executing' && plan) {
      const currentIdx = plan.current_step
      const total = plan.steps.length
      return `${t('agent.state.executing')} passo ${currentIdx + 1}/${total}`
    }
    const key = `agent.state.${state}`
    const translated = t(key)
    return translated !== key ? translated : state
  }

  return (
    <div className="agent-state-indicator">
      <div className={`agent-state-dot ${state}`} />
      <span>{label()}</span>
    </div>
  )
}

// ── Suggestions ───────────────────────────────────────────────────────────────

const SUGGESTIONS_PT = [
  'Revisão sistemática sobre IA na educação',
  'Análise de metodologias dos artigos',
  'Quais seções estão disponíveis no corpus?',
]

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AgentChat() {
  const { t } = useLanguage()

  const [sessions, setSessions] = useState<AgentSession[]>([])
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AgentMessage[]>([])
  const [currentPlan, setCurrentPlan] = useState<AgentPlan | null>(null)
  const [lastStepResult, setLastStepResult] = useState<Record<string, unknown> | null>(null)
  const [agentState, setAgentState] = useState('idle')
  const [awaitingConfirmation, setAwaitingConfirmation] = useState(false)
  const [streaming, setStreaming] = useState(false)
  const [showPlanPanel, setShowPlanPanel] = useState(true)
  const [showDetailPanel, setShowDetailPanel] = useState(true)
  const [input, setInput] = useState('')

  const bottomRef = useRef<HTMLDivElement>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  const hasStarted = messages.length > 0

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streaming])

  // ── Send message ──

  async function handleSend(text: string) {
    const trimmed = text.trim()
    if (!trimmed || streaming) return

    setInput('')
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
    }

    const userMsg: AgentMessage = { role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userMsg])

    // Optimistic assistant placeholder
    setMessages((prev) => [...prev, { role: 'assistant', content: '' }])
    setStreaming(true)

    let assistantContent = ''

    try {
      for await (const event of streamAgentMessage(sessionId, trimmed)) {
        if (event.type === 'session') {
          const sid = event.session_id as string
          setSessionId(sid)
          // Register in local sessions list if new
          setSessions((prev) => {
            if (prev.find((s) => s.id === sid)) return prev
            return [{ id: sid, title: trimmed.slice(0, 40) || 'Sessão agentiva', state: 'idle' }, ...prev]
          })
        }

        if (event.type === 'token') {
          assistantContent += event.content as string
          setMessages((prev) => {
            const copy = [...prev]
            copy[copy.length - 1] = { ...copy[copy.length - 1], content: assistantContent }
            return copy
          })
        }

        if (event.type === 'state') {
          const newState = event.state as string
          setAgentState(newState)
          setSessions((prev) =>
            prev.map((s) => s.id === sessionId ? { ...s, state: newState } : s),
          )
        }

        if (event.type === 'plan') {
          setCurrentPlan(event.plan as AgentPlan)
          setShowPlanPanel(true)
        }

        if (event.type === 'step_result') {
          setLastStepResult(event.result as Record<string, unknown>)
          setShowDetailPanel(true)
          // Update plan step statuses
          if (currentPlan && event.step_index !== undefined) {
            setCurrentPlan((prev) => {
              if (!prev) return prev
              const steps = prev.steps.map((step, idx) =>
                idx === (event.step_index as number)
                  ? { ...step, status: event.status as AgentStep['status'] }
                  : step,
              )
              return { ...prev, steps, current_step: event.step_index as number }
            })
          }
        }

        if (event.type === 'done') {
          const newState = event.state as string
          setAgentState(newState)
          setCurrentPlan((event.plan as AgentPlan) ?? null)
          setAwaitingConfirmation((event.awaiting_confirmation as boolean) ?? false)
          setSessions((prev) =>
            prev.map((s) => (s.id === sessionId ? { ...s, state: newState } : s)),
          )
        }
      }
    } catch {
      setMessages((prev) => {
        const copy = [...prev]
        const last = copy[copy.length - 1]
        if (last.role === 'assistant' && !last.content) {
          copy[copy.length - 1] = { ...last, content: 'Erro ao conectar com o agente.' }
        }
        return copy
      })
    } finally {
      setStreaming(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend(input)
    }
  }

  function handleConfirm() {
    setAwaitingConfirmation(false)
    handleSend('sim')
  }

  function handleCancel() {
    setAwaitingConfirmation(false)
    handleSend('cancelar')
  }

  function handleNewSession() {
    setSessionId(null)
    setMessages([])
    setCurrentPlan(null)
    setLastStepResult(null)
    setAgentState('idle')
    setAwaitingConfirmation(false)
    setInput('')
  }

  function handleSelectSession(id: string) {
    if (id === sessionId) return
    // In a real implementation this would fetch the session from the API
    setSessionId(id)
    setMessages([])
    setCurrentPlan(null)
    setLastStepResult(null)
    setAgentState('idle')
    setAwaitingConfirmation(false)
  }

  return (
    <div
      className="agent-root flex overflow-hidden"
      style={{ height: 'calc(100vh - 3.5rem)' }}
    >
      <div className="agent-layout" style={{ width: '100%' }}>

        {/* ── Sidebar ── */}
        <AgentSidebar
          sessions={sessions}
          activeId={sessionId}
          onSelect={handleSelectSession}
          onNew={handleNewSession}
        />

        {/* ── Plan panel ── */}
        {showPlanPanel && (
          <PlanPanel
            plan={currentPlan}
            onClose={() => setShowPlanPanel(false)}
          />
        )}

        {/* ── Chat main ── */}
        <main className="agent-chat-main">

          {/* Topbar */}
          <div className="agent-topbar">
            <span className="agent-topbar-title">{t('agent.title')}</span>
            <span className="agent-topbar-badge">{t('agent.badge')}</span>
            <div className="agent-topbar-spacer" />
            <StateIndicator state={agentState} plan={currentPlan} />
            <button
              className={`agent-icon-btn${showPlanPanel ? ' active' : ''}`}
              onClick={() => setShowPlanPanel((v) => !v)}
              title={t('agent.plan.title')}
            >
              ☰
            </button>
            <button
              className={`agent-icon-btn${showDetailPanel ? ' active' : ''}`}
              onClick={() => setShowDetailPanel((v) => !v)}
              title={t('agent.detail.title')}
            >
              ⧉
            </button>
          </div>

          {/* Messages */}
          <div className="agent-messages">
            {!hasStarted ? (
              <div className="agent-welcome">
                <div className="agent-welcome-inner">
                  <h1>{t('agent.welcome.title')}</h1>
                  <p>{t('agent.welcome')}</p>
                  <div className="agent-suggestions">
                    {SUGGESTIONS_PT.map((s) => (
                      <span
                        key={s}
                        className="agent-suggestion-chip"
                        onClick={() => handleSend(s)}
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              </div>
            ) : (
              <>
                {messages.map((msg, i) => (
                  <MessageRow key={i} msg={msg} />
                ))}
                {streaming && messages[messages.length - 1]?.content === '' && (
                  <div className="agent-msg assistant">
                    <div className="agent-msg-avatar">🧠</div>
                    <div className="agent-msg-body">
                      <div className="agent-typing">
                        <span /><span /><span />
                      </div>
                    </div>
                  </div>
                )}
              </>
            )}
            <div ref={bottomRef} />
          </div>

          {/* Confirmation bar */}
          {awaitingConfirmation && (
            <div className="agent-confirm-bar">
              <span>{t('agent.state.awaiting_confirmation')}</span>
              <button className="agent-confirm-btn primary" onClick={handleConfirm}>
                {t('agent.confirm')}
              </button>
              <button className="agent-confirm-btn secondary" onClick={handleCancel}>
                {t('agent.cancel')}
              </button>
            </div>
          )}

          {/* Input */}
          <div className="agent-input-area">
            <textarea
              ref={textareaRef}
              className="agent-textarea"
              rows={1}
              placeholder={t('agent.input.placeholder')}
              value={input}
              disabled={streaming}
              onChange={(e) => {
                setInput(e.target.value)
                e.target.style.height = 'auto'
                e.target.style.height = Math.min(e.target.scrollHeight, 120) + 'px'
              }}
              onKeyDown={handleKeyDown}
            />
            <button
              className="agent-send-btn"
              disabled={!input.trim() || streaming}
              onClick={() => handleSend(input)}
              title="Enviar"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z" />
              </svg>
            </button>
          </div>
        </main>

        {/* ── Detail panel ── */}
        {showDetailPanel && (
          <DetailPanel
            stepResult={lastStepResult}
            onClose={() => setShowDetailPanel(false)}
          />
        )}

      </div>
    </div>
  )
}
