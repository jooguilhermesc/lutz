import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, type JobPublico, type Projeto } from './api'

export type Lang = 'pt' | 'en'

function lerLang(): Lang {
  try {
    const v = localStorage.getItem('lutz_lang')
    return v === 'en' ? 'en' : 'pt'
  } catch {
    return 'pt'
  }
}

interface Toast { id: number; texto: string; ruim: boolean }

interface Ctx {
  lang: Lang
  setLang: (l: Lang) => void
  /** Inline translation: tr('Biblioteca', 'Library'). */
  tr: (pt: string, en: string) => string
  projeto: Projeto | null
  erroProjeto: string
  recarregarProjeto: () => Promise<void>
  jobs: JobPublico[]
  recarregarJobs: () => Promise<void>
  avisar: (texto: string, ruim?: boolean) => void
  rota: string
  ir: (r: string) => void
}

const AppCtx = createContext<Ctx | null>(null)

export function useApp(): Ctx {
  const c = useContext(AppCtx)
  if (!c) throw new Error('AppCtx ausente')
  return c
}

function rotaAtual(): string {
  const h = window.location.hash.replace(/^#\/?/, '')
  return h || 'biblioteca'
}

export function AppProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(lerLang)
  const [projeto, setProjeto] = useState<Projeto | null>(null)
  const [erroProjeto, setErroProjeto] = useState('')
  const [jobs, setJobs] = useState<JobPublico[]>([])
  const [toasts, setToasts] = useState<Toast[]>([])
  const [rota, setRota] = useState(rotaAtual)
  const seq = useRef(0)

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem('lutz_lang', l)
    } catch {
      /* private mode */
    }
    document.documentElement.lang = l === 'pt' ? 'pt-BR' : 'en'
  }, [])

  const tr = useCallback((pt: string, en: string) => (lang === 'en' ? en : pt), [lang])

  const recarregarProjeto = useCallback(async () => {
    try {
      setProjeto(await api.get<Projeto>('/projeto'))
      setErroProjeto('')
    } catch (e) {
      setErroProjeto((e as Error).message)
    }
  }, [])

  const recarregarJobs = useCallback(async () => {
    try {
      setJobs(await api.get<JobPublico[]>('/jobs'))
    } catch {
      /* ignore */
    }
  }, [])

  const avisar = useCallback((texto: string, ruim = false) => {
    const id = ++seq.current
    setToasts((t) => [...t, { id, texto, ruim }])
    window.setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), ruim ? 8000 : 4000)
  }, [])

  const ir = useCallback((r: string) => {
    window.location.hash = `/${r}`
  }, [])

  useEffect(() => {
    const f = () => setRota(rotaAtual())
    window.addEventListener('hashchange', f)
    return () => window.removeEventListener('hashchange', f)
  }, [])

  useEffect(() => {
    recarregarProjeto()
    recarregarJobs()
    const t = window.setInterval(() => {
      recarregarProjeto()
      recarregarJobs()
    }, 5000)
    return () => window.clearInterval(t)
  }, [recarregarProjeto, recarregarJobs])

  const valor = useMemo<Ctx>(
    () => ({ lang, setLang, tr, projeto, erroProjeto, recarregarProjeto, jobs, recarregarJobs, avisar, rota, ir }),
    [lang, setLang, tr, projeto, erroProjeto, recarregarProjeto, jobs, recarregarJobs, avisar, rota, ir],
  )

  return (
    <AppCtx.Provider value={valor}>
      {children}
      <div className="toast" role="status" aria-live="polite">
        {toasts.map((t) => (
          <div key={t.id} className={t.ruim ? 'bad' : ''}>
            {t.texto}
          </div>
        ))}
      </div>
    </AppCtx.Provider>
  )
}
