import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react'
import { AlertTriangle, Info, Loader2, X } from 'lucide-react'
import type { Nivel } from '../api'
import { useApp } from '../app-context'

// ── formatting ─────────────────────────────────────────────────────────────

export function useFmt() {
  const { lang } = useApp()
  const loc = lang === 'en' ? 'en-US' : 'pt-BR'
  return {
    num: (x: number | null | undefined, casas = 2) =>
      x === null || x === undefined || Number.isNaN(x)
        ? '—'
        : x.toLocaleString(loc, { minimumFractionDigits: casas, maximumFractionDigits: casas }),
    int: (x: number | null | undefined) => (x === null || x === undefined ? '—' : x.toLocaleString(loc)),
    pct: (x: number | null | undefined, casas = 0) =>
      x === null || x === undefined || Number.isNaN(x)
        ? '—'
        : (x * 100).toLocaleString(loc, { minimumFractionDigits: casas, maximumFractionDigits: casas }) + '%',
    usd: (x: number | null | undefined) =>
      x === null || x === undefined ? '?' : 'US$ ' + x.toLocaleString(loc, { minimumFractionDigits: 2, maximumFractionDigits: x < 0.1 && x > 0 ? 4 : 2 }),
    tokens: (x: number | null | undefined) => {
      if (!x) return '0'
      if (x >= 1_000_000) return (x / 1_000_000).toLocaleString(loc, { maximumFractionDigits: 1 }) + 'M'
      if (x >= 1000) return Math.round(x / 1000).toLocaleString(loc) + 'k'
      return String(x)
    },
    data: (s: string | null | undefined) => {
      if (!s) return '—'
      const d = new Date(s)
      return Number.isNaN(d.getTime()) ? s : d.toLocaleString(loc, { dateStyle: 'short', timeStyle: 'short' })
    },
    ic: (lo: number | null | undefined, hi: number | null | undefined, casas = 2) =>
      lo === null || lo === undefined || hi === null || hi === undefined
        ? '—'
        : `${lo.toLocaleString(loc, { minimumFractionDigits: casas, maximumFractionDigits: casas })}–${hi.toLocaleString(loc, { minimumFractionDigits: casas, maximumFractionDigits: casas })}`,
  }
}

// ── data loading ───────────────────────────────────────────────────────────

export function useCarregar<T>(fn: () => Promise<T>, deps: unknown[]) {
  const [dados, setDados] = useState<T | null>(null)
  const [erro, setErro] = useState('')
  const [carregando, setCarregando] = useState(true)
  const fnRef = useRef(fn)
  fnRef.current = fn
  const recarregar = useCallback(async (silencioso = false) => {
    if (!silencioso) setCarregando(true)
    try {
      setDados(await fnRef.current())
      setErro('')
    } catch (e) {
      setErro((e as Error).message)
    } finally {
      setCarregando(false)
    }
  }, [])
  useEffect(() => {
    recarregar()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
  return { dados, erro, carregando, recarregar, setDados }
}

export function useIntervalo(fn: () => void, ms: number, ativo: boolean) {
  const ref = useRef(fn)
  ref.current = fn
  useEffect(() => {
    if (!ativo) return
    const t = window.setInterval(() => ref.current(), ms)
    return () => window.clearInterval(t)
  }, [ms, ativo])
}

// ── visual primitives ──────────────────────────────────────────────────────

const NIVEL_CLS: Record<Nivel, [string, string]> = { alta: ['pa', 'da'], media: ['pm', 'dm'], baixa: ['pb', 'db'] }

export function NivelPill({ nivel }: { nivel: Nivel | null | undefined }) {
  const { tr } = useApp()
  if (!nivel) return <span className="pill pn">—</span>
  const rot = { alta: tr('Alta', 'High'), media: tr('Média', 'Medium'), baixa: tr('Baixa', 'Low') }[nivel]
  const [p, d] = NIVEL_CLS[nivel]
  return (
    <span className={`pill ${p}`}>
      <span className={`dot ${d}`} />
      {rot}
    </span>
  )
}

export function StatusPill({ status }: { status: string }) {
  const cls: Record<string, string> = {
    concluida: 'pa', concluido: 'pa', pronto: 'pa', rodando: 'pm', planejada: 'pn', pausada: 'pm', falhou: 'pb',
    sem_texto: 'pb', erro: 'pb',
  }
  return <span className={`pill ${cls[status] ?? 'pn'}`}>{status}</span>
}

export function Kpi({ rotulo, valor, sub, cor }: { rotulo: string; valor: ReactNode; sub?: ReactNode; cor?: string }) {
  return (
    <div className="kpi">
      <div className="lbl">{rotulo}</div>
      <div className="kv" style={cor ? { color: cor } : undefined}>
        {valor}
      </div>
      {sub ? <div className="kv-sub">{sub}</div> : null}
    </div>
  )
}

export function Nota({ children, tipo = 'aviso' }: { children: ReactNode; tipo?: 'aviso' | 'info' | 'erro' }) {
  if (tipo === 'info')
    return (
      <div className="info">
        <Info size={16} />
        <div>{children}</div>
      </div>
    )
  if (tipo === 'erro')
    return (
      <div className="err" role="alert">
        <AlertTriangle size={16} style={{ flex: 'none', marginTop: 2 }} />
        <div>{children}</div>
      </div>
    )
  return (
    <div className="note">
      <AlertTriangle size={16} />
      <div>{children}</div>
    </div>
  )
}

export function Carregando({ texto }: { texto?: string }) {
  const { tr } = useApp()
  return (
    <div className="empty" aria-busy="true">
      <Loader2 className="spin" size={18} />
      {texto ?? tr('Carregando…', 'Loading…')}
    </div>
  )
}

export function Vazio({ titulo, children }: { titulo: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong style={{ color: 'var(--text)' }}>{titulo}</strong>
      {children}
    </div>
  )
}

export function Cabecalho({ titulo, sub, children }: { titulo: string; sub?: ReactNode; children?: ReactNode }) {
  return (
    <section style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'flex-end', gap: 12 }}>
      <div style={{ flex: '1 1 320px', minWidth: 0 }}>
        <h1>{titulo}</h1>
        {sub ? <p style={{ margin: '2px 0 0', color: 'var(--text-muted)' }}>{sub}</p> : null}
      </div>
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>{children}</div>
    </section>
  )
}

export function Modal({ titulo, sub, onFechar, children, rodape, largo }: {
  titulo: string; sub?: ReactNode; onFechar: () => void; children: ReactNode; rodape?: ReactNode; largo?: boolean
}) {
  const { tr } = useApp()
  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === 'Escape' && onFechar()
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [onFechar])
  return (
    <div className="overlay" onClick={onFechar}>
      <div className={`modal${largo ? ' modal-wide' : ''}`} role="dialog" aria-modal="true" aria-label={titulo}
        onClick={(e) => e.stopPropagation()}>
        <div className="modal-h">
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 16, fontWeight: 700 }}>{titulo}</div>
            {sub ? <div className="muted small">{sub}</div> : null}
          </div>
          <button className="btn btn-icon" onClick={onFechar} aria-label={tr('Fechar', 'Close')}>
            <X size={14} />
          </button>
        </div>
        {children}
        {rodape ? <div className="modal-f">{rodape}</div> : null}
      </div>
    </div>
  )
}

export function Drawer({ titulo, onFechar, children }: { titulo: ReactNode; onFechar: () => void; children: ReactNode }) {
  const { tr } = useApp()
  useEffect(() => {
    const f = (e: KeyboardEvent) => e.key === 'Escape' && onFechar()
    window.addEventListener('keydown', f)
    return () => window.removeEventListener('keydown', f)
  }, [onFechar])
  return (
    <aside className="drawer" role="dialog" aria-modal="false">
      <div className="modal-h">
        <div style={{ flex: 1, minWidth: 0 }}>{titulo}</div>
        <button className="btn btn-icon" onClick={onFechar} aria-label={tr('Fechar', 'Close')}>
          <X size={14} />
        </button>
      </div>
      <div className="modal-b">{children}</div>
    </aside>
  )
}

/** Bar with the share of High / Medium / Low. */
export function BarraNiveis({ a, m, b }: { a: number; m: number; b: number }) {
  const tot = a + m + b || 1
  return (
    <div className="bar" aria-label={`A ${a} M ${m} B ${b}`}>
      <span style={{ width: `${(a / tot) * 100}%`, background: 'var(--success-dot)' }} />
      <span style={{ width: `${(m / tot) * 100}%`, background: 'var(--warning-dot)' }} />
      <span style={{ width: `${(b / tot) * 100}%`, background: 'var(--danger-dot)' }} />
    </div>
  )
}

export function baixar(caminho: string) {
  const a = document.createElement('a')
  a.href = caminho
  a.download = ''
  document.body.appendChild(a)
  a.click()
  a.remove()
}

export function Copiar({ texto }: { texto: string }) {
  const { tr } = useApp()
  const [ok, setOk] = useState(false)
  return (
    <button
      className="btn btn-s"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(texto)
          setOk(true)
          window.setTimeout(() => setOk(false), 1500)
        } catch {
          /* clipboard blocked */
        }
      }}
    >
      {ok ? tr('Copiado', 'Copied') : tr('Copiar', 'Copy')}
    </button>
  )
}

/** Highlight *trecho* inside *texto* (case-insensitive, whitespace-tolerant). */
export function Destacar({ texto, trecho }: { texto: string; trecho: string | null | undefined }) {
  if (!trecho || trecho.length < 3) return <>{texto}</>
  const alvo = trecho.trim().slice(0, 160)
  const esc = alvo.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/\s+/g, '\\s+')
  let re: RegExp
  try {
    re = new RegExp(esc, 'i')
  } catch {
    return <>{texto}</>
  }
  const m = re.exec(texto)
  if (!m) return <>{texto}</>
  return (
    <>
      {texto.slice(0, m.index)}
      <mark>{m[0]}</mark>
      {texto.slice(m.index + m[0].length)}
    </>
  )
}
