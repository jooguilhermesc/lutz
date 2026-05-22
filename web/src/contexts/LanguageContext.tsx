import { createContext, useCallback, useContext, useEffect, useState } from 'react'
import { translate, type Lang } from '../i18n'
import { getConfig } from '../api/client'

interface LangCtx {
  lang: Lang
  setLang: (l: Lang) => void
  reportLang: string
  setReportLang: (l: string) => void
  t: (key: string) => string
  showVectorStore: boolean
  setShowVectorStore: (v: boolean) => void
}

const LanguageContext = createContext<LangCtx>({
  lang: 'pt',
  setLang: () => {},
  reportLang: 'pt',
  setReportLang: () => {},
  t: (key) => key,
  showVectorStore: false,
  setShowVectorStore: () => {},
})

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [lang, setLangState] = useState<Lang>(() => {
    const stored = localStorage.getItem('lutz_ui_lang')
    return (stored as Lang) || 'pt'
  })
  const [reportLang, setReportLangState] = useState<string>('pt')
  const [showVectorStore, setShowVectorStoreState] = useState<boolean>(() => {
    return localStorage.getItem('lutz_show_vector_store') === 'true'
  })

  useEffect(() => {
    getConfig()
      .then((cfg) => {
        if (cfg.REPORT_LANGUAGE) setReportLangState(cfg.REPORT_LANGUAGE)
      })
      .catch(() => {})
  }, [])

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    localStorage.setItem('lutz_ui_lang', l)
  }, [])

  const setReportLang = useCallback((l: string) => {
    setReportLangState(l)
  }, [])

  const setShowVectorStore = useCallback((v: boolean) => {
    setShowVectorStoreState(v)
    localStorage.setItem('lutz_show_vector_store', String(v))
  }, [])

  const t = useCallback((key: string) => translate(lang, key), [lang])

  return (
    <LanguageContext.Provider value={{ lang, setLang, reportLang, setReportLang, t, showVectorStore, setShowVectorStore }}>
      {children}
    </LanguageContext.Provider>
  )
}

export function useLanguage() {
  return useContext(LanguageContext)
}
