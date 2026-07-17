import { useEffect, useState } from 'react'
import { getConfig, saveConfig, getProviderModels, getUsage, getUsageExportUrl, type Config, type ModelInfo, type UsageSummary } from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import { LANG_NAMES, type Lang } from '../i18n'

const LLM_PROVIDERS = [
  { value: 'anthropic',           label: 'Anthropic' },
  { value: 'openai',              label: 'OpenAI' },
  { value: 'openrouter',          label: 'OpenRouter' },
  { value: 'docker_model_runner', label: 'Docker Model Runner' },
]

const LANGS: Array<{ value: Lang; label: string }> = [
  { value: 'pt', label: LANG_NAMES.pt },
  { value: 'en', label: LANG_NAMES.en },
  { value: 'es', label: LANG_NAMES.es },
]

const TEXT_FIELDS: Array<{ key: keyof Config; label: string; type?: string; placeholder?: string }> = [
  { key: 'LLM_MAX_TOKENS',    label: 'Max output tokens', type: 'number', placeholder: '2048' },
  { key: 'LLM_TEMPERATURE',   label: 'Temperature',       placeholder: '0.2' },
  { key: 'OPENAI_BASE_URL',   label: 'OpenAI base URL',   placeholder: 'https://openrouter.ai/api/v1' },
  { key: 'DOCKER_MODEL_HOST', label: 'Docker model host', placeholder: 'http://localhost:11434' },
]

const KEY_FIELDS: Array<{ envKey: string; label: string; hasKey: 'has_openai_key' | 'has_anthropic_key' | 'has_openrouter_key' }> = [
  { envKey: 'OPENAI_API_KEY',     label: 'OpenAI API Key',     hasKey: 'has_openai_key' },
  { envKey: 'ANTHROPIC_API_KEY',  label: 'Anthropic API Key',  hasKey: 'has_anthropic_key' },
  { envKey: 'OPENROUTER_API_KEY', label: 'OpenRouter API Key', hasKey: 'has_openrouter_key' },
]

const DEFAULT_ROADMAP_STAGES = [
  { name: 'Leituras fundacionais', criteria: 'Artigos que servem de base para compreender os demais — conceitos fundamentais, revisões abrangentes e metodologias centrais.' },
  { name: 'Casos específicos', criteria: 'Artigos bem elaborados sobre tópicos que se fecham em si mesmos e têm pouca relação com os demais.' },
  { name: 'Evolução do conteúdo', criteria: 'Artigos que apresentam conceitos mais elaborados, refinamentos metodológicos ou aplicações avançadas sobre o tema central.' },
]

export function deriveCode(label: string): string {
  return (
    label
      .normalize('NFD')
      .replace(/[̀-ͯ]/g, '')
      .toUpperCase()
      .replace(/[^A-Z0-9]+/g, '_')
      .replace(/^_|_$/g, '') || 'STATUS'
  )
}

export type VerdictCategory = { label: string; color: string; extractCitations: boolean }

export const VERDICT_COLOR_PALETTE = [
  '#1f9d6b', '#d69a2d', '#3b82f6', '#ef4444',
  '#9aa3b0', '#8b5cf6', '#0891b2', '#f97316',
]

export const DEFAULT_VERDICT_CATEGORIES: VerdictCategory[] = [
  { label: 'Include',   color: '#1f9d6b', extractCitations: true  },
  { label: 'Exclude',   color: '#9aa3b0', extractCitations: false },
  { label: 'Uncertain', color: '#d69a2d', extractCitations: false },
]

export const DEFAULT_ANALYSIS_CRITERIA = [
  { name: 'Relevância temática', criteria: 'O artigo aborda diretamente o tema ou questão central da pesquisa.' },
  { name: 'Tipo de estudo', criteria: 'O desenho metodológico é compatível com os objetivos da revisão.' },
  { name: 'Dados originais', criteria: 'O artigo apresenta dados ou análises originais (não é editorial, carta ou comentário).' },
]
export type AnalysisCriteria = typeof DEFAULT_ANALYSIS_CRITERIA

export const DEFAULT_CITATION_CRITERIA = 'Extract the 3 to 5 passages that most strongly support the relevance classification. Prefer exact quotes; always include the page number.'

interface Props { onClose: () => void; onSaved?: () => void; initialSection?: 'llm' | 'keys' | 'language' | 'results' | 'roadmap' | 'consumo' }

export default function SettingsModal({ onClose, onSaved, initialSection }: Props) {
  const { t, lang, setLang, reportLang, setReportLang } = useLanguage()
  const [cfg, setCfg] = useState<Config | null>(null)
  const [llmProvider, setLlmProvider] = useState('openai')
  const [form, setForm] = useState<Record<string, string>>({})
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({})
  const [localReportLang, setLocalReportLang] = useState(reportLang)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState<'llm' | 'keys' | 'language' | 'results' | 'roadmap' | 'consumo'>(initialSection ?? 'llm')
  const [usageData, setUsageData] = useState<UsageSummary | null>(null)
  const [usageLoading, setUsageLoading] = useState(false)
  const [roadmapStages, setRoadmapStages] = useState<Array<{ name: string; criteria: string }>>(() => {
    try {
      const stored = localStorage.getItem('lutz_roadmap_stages')
      if (stored) return JSON.parse(stored)
    } catch { /* ignore */ }
    return DEFAULT_ROADMAP_STAGES
  })
  const [analysisCriteria, setAnalysisCriteria] = useState<AnalysisCriteria>(() => {
    try {
      const stored = localStorage.getItem('lutz_analysis_criteria')
      if (stored) return JSON.parse(stored)
    } catch { /* ignore */ }
    return DEFAULT_ANALYSIS_CRITERIA
  })
  const [citationCriteria, setCitationCriteria] = useState<string>(() => {
    return localStorage.getItem('lutz_citation_criteria') ?? DEFAULT_CITATION_CRITERIA
  })
  const [verdictCategories, setVerdictCategories] = useState<VerdictCategory[]>(() => {
    try {
      const stored = localStorage.getItem('lutz_verdict_categories')
      if (stored) return JSON.parse(stored)
    } catch { /* ignore */ }
    return DEFAULT_VERDICT_CATEGORIES
  })
  const [llmModels, setLlmModels] = useState<ModelInfo[]>([])
  const [llmModelsLoading, setLlmModelsLoading] = useState(false)
  const [embModels, setEmbModels] = useState<ModelInfo[]>([])
  const [embModelsLoading, setEmbModelsLoading] = useState(false)
  const [showLlmDropdown, setShowLlmDropdown] = useState(false)
  const [showEmbDropdown, setShowEmbDropdown] = useState(false)

  useEffect(() => {
    localStorage.setItem('lutz_roadmap_stages', JSON.stringify(roadmapStages))
  }, [roadmapStages])

  useEffect(() => {
    localStorage.setItem('lutz_analysis_criteria', JSON.stringify(analysisCriteria))
  }, [analysisCriteria])

  useEffect(() => {
    localStorage.setItem('lutz_citation_criteria', citationCriteria)
  }, [citationCriteria])

  useEffect(() => {
    localStorage.setItem('lutz_verdict_categories', JSON.stringify(verdictCategories))
  }, [verdictCategories])

  useEffect(() => {
    getConfig().then(c => {
      setCfg(c)
      setLlmProvider(c.LLM_PROVIDER || 'openai')
      const initial: Record<string, string> = {
        LLM_MODEL: c.LLM_MODEL || '',
        EMBEDDING_MODEL: c.EMBEDDING_MODEL || '',
        ANALYSIS_WORKERS: c.ANALYSIS_WORKERS || '4',
      }
      for (const f of TEXT_FIELDS) {
        initial[f.key as string] = (c[f.key] as string) || ''
      }
      setForm(initial)
      if (c.REPORT_LANGUAGE) setLocalReportLang(c.REPORT_LANGUAGE)
    })
  }, [])

  useEffect(() => {
    if (!llmProvider) return
    setLlmModelsLoading(true)
    getProviderModels(llmProvider, 'llm').then(({ models }) => {
      setLlmModels(models)
      setLlmModelsLoading(false)
    }).catch(() => setLlmModelsLoading(false))
  }, [llmProvider])

  useEffect(() => {
    if (!llmProvider) return
    setEmbModelsLoading(true)
    getProviderModels(llmProvider, 'embedding').then(({ models }) => {
      setEmbModels(models)
      setEmbModelsLoading(false)
    }).catch(() => setEmbModelsLoading(false))
  }, [llmProvider])

  useEffect(() => {
    if (activeSection !== 'consumo' || usageData !== null || usageLoading) return
    setUsageLoading(true)
    getUsage().then(d => { setUsageData(d); setUsageLoading(false) }).catch(() => {
      setUsageData({ records: [], totals: { total_tokens: 0, total_cost_usd: null } })
      setUsageLoading(false)
    })
  }, [activeSection])

  async function handleSave() {
    setSaving(true); setSaved(false); setError('')
    try {
      const payload: Record<string, string> = {
        ...form, LLM_PROVIDER: llmProvider, EMBEDDING_PROVIDER: llmProvider,
        REPORT_LANGUAGE: localReportLang,
      }
      for (const { envKey } of KEY_FIELDS) {
        if (apiKeys[envKey]) payload[envKey] = apiKeys[envKey]
      }
      await saveConfig(payload)
      setReportLang(localReportLang)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
      onSaved?.()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const sectionTab = (id: typeof activeSection, label: string, tourId?: string) => (
    <button id={tourId} onClick={() => setActiveSection(id)}
      style={{
        padding: '7px 14px', border: 'none', background: 'none', cursor: 'pointer',
        fontSize: 13, fontWeight: activeSection === id ? 600 : 500,
        color: activeSection === id ? 'var(--text)' : 'var(--text-faint)',
        borderBottom: `2px solid ${activeSection === id ? '#1A9494' : 'transparent'}`,
        marginBottom: -1,
      }}>
      {label}
    </button>
  )

  return (
    <div onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(20,25,40,.32)', zIndex: 50,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 32,
        animation: 'vfade .15s ease',
      }}>
      <div id="tour-settings-modal" onClick={e => e.stopPropagation()}
        style={{
          width: 640, maxWidth: '100%', maxHeight: '90vh', background: 'var(--surface)',
          borderRadius: 16, boxShadow: '0 24px 60px rgba(20,25,40,.4)',
          display: 'flex', flexDirection: 'column', overflow: 'hidden',
        }}>
        {/* Header */}
        <div style={{
          flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px', borderBottom: '1px solid var(--border)',
        }}>
          <div>
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>{t('settings.title')}</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>{t('settings.subtitle')}</div>
          </div>
          <button onClick={onClose} style={{
            width: 32, height: 32, border: '1px solid var(--border)', borderRadius: 8,
            background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
            justifyContent: 'center', color: 'var(--text-muted)',
          }}>
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none">
              <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
            </svg>
          </button>
        </div>

        {/* Section tabs */}
        <div style={{ flexShrink: 0, display: 'flex', borderBottom: '1px solid var(--border)', paddingLeft: 24 }}>
          {sectionTab('llm', t('settings.section.llm'))}
          {sectionTab('keys', t('settings.section.keys'))}
          {sectionTab('language', t('settings.section.language'))}
          {sectionTab('results', t('settings.section.results'), 'tour-settings-results-tab')}
          {sectionTab('roadmap', t('settings.section.roadmap'), 'tour-settings-roadmap-tab')}
          {sectionTab('consumo', t('settings.section.consumo'))}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 24px', background: 'var(--surface-2)' }}>
          {!cfg ? (
            <p style={{ color: '#8a92a0', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>
              {t('settings.loading')}
            </p>
          ) : activeSection === 'llm' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="label">Model Provider</label>
                <select className="select" value={llmProvider} onChange={e => setLlmProvider(e.target.value)}>
                  {LLM_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              {/* LLM Model combobox */}
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="label">
                  LLM Model
                  {llmModelsLoading && <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-faint)' }}>{t('settings.llm.loadingModels')}</span>}
                </label>
                <input
                  type="text" className="input"
                  placeholder={llmModelsLoading ? t('settings.llm.loadingModelsList') : t('settings.llm.selectModel')}
                  value={form['LLM_MODEL'] ?? ''}
                  onChange={e => setForm(prev => ({ ...prev, LLM_MODEL: e.target.value }))}
                  onFocus={() => setShowLlmDropdown(true)}
                  onBlur={() => setTimeout(() => setShowLlmDropdown(false), 150)}
                />
                {showLlmDropdown && !llmModelsLoading && llmModels.length > 0 && (() => {
                  const q = (form['LLM_MODEL'] ?? '').toLowerCase()
                  const filtered = llmModels.filter(m => !q || m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q))
                  return filtered.length > 0 ? (
                    <div style={{
                      marginTop: 4, border: '1px solid var(--border-2)', borderRadius: 9,
                      background: 'var(--surface)', maxHeight: 220, overflowY: 'auto',
                      boxShadow: '0 6px 20px rgba(20,25,40,.15)',
                    }}>
                      {filtered.map(m => (
                        <button
                          key={m.id}
                          onMouseDown={e => { e.preventDefault(); setForm(prev => ({ ...prev, LLM_MODEL: m.id })); setShowLlmDropdown(false) }}
                          style={{
                            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '8px 12px', border: 'none', cursor: 'pointer', textAlign: 'left',
                            background: m.id === form['LLM_MODEL'] ? 'var(--surface-3)' : 'none',
                          }}
                        >
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</div>
                            {m.id !== m.name && <div style={{ fontSize: 11, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.id}</div>}
                          </div>
                          {m.price !== undefined && (
                            <span style={{ fontSize: 11, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', flexShrink: 0, marginLeft: 8 }}>
                              {m.price === 0 ? 'grátis' : `$${m.price}/M`}
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                  ) : null
                })()}
              </div>

              {/* Embedding Model combobox */}
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="label">
                  Embedding Model
                  {embModelsLoading && <span style={{ marginLeft: 6, fontSize: 11, color: 'var(--text-faint)' }}>{t('settings.llm.loadingModels')}</span>}
                </label>
                <input
                  type="text" className="input"
                  placeholder={embModelsLoading ? t('settings.llm.loadingModelsList') : t('settings.llm.selectModel')}
                  value={form['EMBEDDING_MODEL'] ?? ''}
                  onChange={e => setForm(prev => ({ ...prev, EMBEDDING_MODEL: e.target.value }))}
                  onFocus={() => setShowEmbDropdown(true)}
                  onBlur={() => setTimeout(() => setShowEmbDropdown(false), 150)}
                />
                {showEmbDropdown && !embModelsLoading && embModels.length > 0 && (() => {
                  const q = (form['EMBEDDING_MODEL'] ?? '').toLowerCase()
                  const filtered = embModels.filter(m => !q || m.name.toLowerCase().includes(q) || m.id.toLowerCase().includes(q))
                  return filtered.length > 0 ? (
                    <div style={{
                      marginTop: 4, border: '1px solid var(--border-2)', borderRadius: 9,
                      background: 'var(--surface)', maxHeight: 220, overflowY: 'auto',
                      boxShadow: '0 6px 20px rgba(20,25,40,.15)',
                    }}>
                      {filtered.map(m => (
                        <button
                          key={m.id}
                          onMouseDown={e => { e.preventDefault(); setForm(prev => ({ ...prev, EMBEDDING_MODEL: m.id })); setShowEmbDropdown(false) }}
                          style={{
                            width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                            padding: '8px 12px', border: 'none', cursor: 'pointer', textAlign: 'left',
                            background: m.id === form['EMBEDDING_MODEL'] ? 'var(--surface-3)' : 'none',
                          }}
                        >
                          <div style={{ minWidth: 0, flex: 1 }}>
                            <div style={{ fontSize: 12.5, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.name}</div>
                            {m.id !== m.name && <div style={{ fontSize: 11, color: 'var(--text-faint)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{m.id}</div>}
                          </div>
                        </button>
                      ))}
                    </div>
                  ) : null
                })()}
              </div>
              {TEXT_FIELDS.map(f => (
                <div key={f.key as string}>
                  <label className="label">{f.label}</label>
                  <input type={f.type ?? 'text'} className="input" placeholder={f.placeholder}
                    value={form[f.key as string] ?? ''}
                    onChange={e => setForm(prev => ({ ...prev, [f.key as string]: e.target.value }))} />
                </div>
              ))}

              {/* Workers stepper */}
              <div style={{ gridColumn: '1 / -1' }}>
                <label className="label">{t('settings.llm.workers')}</label>
                <div style={{ display: 'flex', alignItems: 'center', gap: 0 }}>
                  <button
                    type="button"
                    onClick={() => setForm(prev => {
                      const cur = Math.max(1, parseInt(prev['ANALYSIS_WORKERS'] || '4') - 1)
                      return { ...prev, ANALYSIS_WORKERS: String(cur) }
                    })}
                    style={{
                      width: 36, height: 36, border: '1px solid var(--border-2)',
                      borderRight: 'none', borderRadius: '7px 0 0 7px',
                      background: 'var(--surface)', color: 'var(--text-muted)',
                      cursor: 'pointer', fontSize: 18, lineHeight: 1, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                    }}
                  >−</button>
                  <div style={{
                    width: 52, height: 36, border: '1px solid var(--border-2)',
                    background: 'var(--surface-2)', display: 'flex',
                    alignItems: 'center', justifyContent: 'center',
                    fontSize: 14, fontWeight: 600, fontFamily: 'IBM Plex Mono, monospace',
                    color: 'var(--text)',
                  }}>
                    {form['ANALYSIS_WORKERS'] || '4'}
                  </div>
                  <button
                    type="button"
                    onClick={() => setForm(prev => {
                      const cur = Math.min(32, parseInt(prev['ANALYSIS_WORKERS'] || '4') + 1)
                      return { ...prev, ANALYSIS_WORKERS: String(cur) }
                    })}
                    style={{
                      width: 36, height: 36, border: '1px solid var(--border-2)',
                      borderLeft: 'none', borderRadius: '0 7px 7px 0',
                      background: 'var(--surface)', color: 'var(--text-muted)',
                      cursor: 'pointer', fontSize: 18, lineHeight: 1, display: 'flex',
                      alignItems: 'center', justifyContent: 'center',
                    }}
                  >+</button>
                </div>
                <p style={{ marginTop: 5, fontSize: 11.5, color: 'var(--text-faint)' }}>
                  {t('settings.llm.workers.hint')}
                </p>
              </div>
            </div>
          ) : activeSection === 'keys' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p className="text-xs text-[#8a92a0]">{t('settings.keys.hint')}</p>
              {KEY_FIELDS.map(({ envKey, label, hasKey }) => (
                <div key={envKey}>
                  <label className="label">
                    {label}
                    {cfg[hasKey] && (
                      <span className="ml-2 text-lutz-600 font-normal text-xs">{t('settings.key.configured')}</span>
                    )}
                  </label>
                  <input type="password" className="input"
                    placeholder={cfg[hasKey] ? '••••••••••••••••' : 'sk-...'}
                    value={apiKeys[envKey] ?? ''}
                    onChange={e => setApiKeys(prev => ({ ...prev, [envKey]: e.target.value }))}
                    autoComplete="off" />
                </div>
              ))}
            </div>
          ) : activeSection === 'language' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label className="label">{t('settings.lang.ui')}</label>
                <select className="select" value={lang} onChange={e => setLang(e.target.value as Lang)}>
                  {LANGS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
                <p className="text-xs text-[#8a92a0] mt-1">{t('settings.lang.applyNow')}</p>
              </div>
              <div>
                <label className="label">{t('settings.lang.report')}</label>
                <select className="select" value={localReportLang} onChange={e => setLocalReportLang(e.target.value)}>
                  {LANGS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
                <p className="text-xs text-[#8a92a0] mt-1">{t('settings.lang.report.hint')}</p>
              </div>
            </div>
          ) : activeSection === 'roadmap' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <p style={{ fontSize: 12.5, color: 'var(--text-faint)', margin: 0 }}>
                {t('settings.roadmap.desc')}
              </p>
              {roadmapStages.map((stage, i) => (
                <div key={i} style={{
                  background: 'var(--surface)', border: '1px solid var(--border)',
                  borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10,
                }}>
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '.05em' }}>
                      {t('settings.roadmap.stage')} {i + 1}
                    </span>
                    {roadmapStages.length > 1 && (
                      <button
                        type="button"
                        onClick={() => setRoadmapStages(prev => prev.filter((_, idx) => idx !== i))}
                        style={{
                          width: 26, height: 26, border: '1px solid var(--border)', borderRadius: 6,
                          background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
                          justifyContent: 'center', color: 'var(--text-faint)',
                        }}
                        title={t('settings.roadmap.remove')}
                      >
                        <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                          <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                        </svg>
                      </button>
                    )}
                  </div>
                  <div>
                    <label className="label" style={{ marginBottom: 4 }}>{t('settings.roadmap.name')}</label>
                    <input
                      type="text" className="input"
                      value={stage.name}
                      onChange={e => setRoadmapStages(prev => prev.map((s, idx) => idx === i ? { ...s, name: e.target.value } : s))}
                      placeholder="Ex: Leituras fundacionais"
                    />
                  </div>
                  <div>
                    <label className="label" style={{ marginBottom: 4 }}>{t('settings.roadmap.criteria')}</label>
                    <textarea
                      className="input"
                      rows={2}
                      value={stage.criteria}
                      onChange={e => setRoadmapStages(prev => prev.map((s, idx) => idx === i ? { ...s, criteria: e.target.value } : s))}
                      placeholder="Descreva quais artigos pertencem a este estágio..."
                      style={{ resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                    />
                  </div>
                </div>
              ))}
              <button
                type="button"
                onClick={() => setRoadmapStages(prev => [...prev, { name: '', criteria: '' }])}
                style={{
                  padding: '9px 16px', border: '1px dashed var(--border-2)', borderRadius: 9,
                  background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                  color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 6,
                }}
              >
                <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> {t('settings.roadmap.add')}
              </button>
              <button
                type="button"
                onClick={() => setRoadmapStages(DEFAULT_ROADMAP_STAGES)}
                style={{
                  padding: '7px 14px', border: '1px solid var(--border)', borderRadius: 9,
                  background: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-faint)',
                  alignSelf: 'flex-start',
                }}
              >
                {t('settings.roadmap.restore')}
              </button>
            </div>
          ) : activeSection === 'results' ? (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>

              {/* ── Categorias de resultado ── */}
              <div id="tour-verdict-categories" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>{t('settings.results.cat.title')}</div>
                  <p style={{ fontSize: 12.5, color: 'var(--text-faint)', margin: 0 }}
                    dangerouslySetInnerHTML={{ __html: t('settings.results.cat.desc') }} />
                </div>
                {verdictCategories.map((cat, i) => {
                  const code = deriveCode(cat.label)
                  return (
                    <div key={i} style={{
                      background: 'var(--surface)', border: '1px solid var(--border)',
                      borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10,
                    }}>
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '.05em' }}>
                            {t('settings.results.cat.header')} {i + 1}
                          </span>
                          {code && (
                            <span style={{
                              fontSize: 10, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace',
                              padding: '2px 7px', borderRadius: 5,
                              background: cat.color + '22', color: cat.color, letterSpacing: '.3px',
                            }}>
                              {code}
                            </span>
                          )}
                        </div>
                        {verdictCategories.length > 2 && (
                          <button
                            type="button"
                            onClick={() => setVerdictCategories(prev => prev.filter((_, idx) => idx !== i))}
                            style={{
                              width: 26, height: 26, border: '1px solid var(--border)', borderRadius: 6,
                              background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
                              justifyContent: 'center', color: 'var(--text-faint)',
                            }}
                            title={t('settings.results.cat.remove')}
                          >
                            <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                              <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                            </svg>
                          </button>
                        )}
                      </div>
                      <div>
                        <label className="label" style={{ marginBottom: 4 }}>{t('settings.results.cat.name')}</label>
                        <input
                          type="text" className="input"
                          value={cat.label}
                          onChange={e => setVerdictCategories(prev => prev.map((x, idx) => idx === i ? { ...x, label: e.target.value } : x))}
                          placeholder={t('settings.results.cat.namePlaceholder')}
                        />
                      </div>
                      <div>
                        <label className="label" style={{ marginBottom: 6 }}>{t('settings.results.cat.color')}</label>
                        <div style={{ display: 'flex', gap: 6 }}>
                          {VERDICT_COLOR_PALETTE.map(color => (
                            <button
                              key={color}
                              type="button"
                              onClick={() => setVerdictCategories(prev => prev.map((x, idx) => idx === i ? { ...x, color } : x))}
                              style={{
                                width: 24, height: 24, borderRadius: '50%', background: color, border: 'none',
                                cursor: 'pointer', flexShrink: 0,
                                outline: cat.color === color ? `2px solid ${color}` : 'none',
                                outlineOffset: 2,
                              }}
                              title={color}
                            />
                          ))}
                        </div>
                      </div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <button
                          type="button"
                          role="switch"
                          aria-checked={cat.extractCitations}
                          onClick={() => setVerdictCategories(prev => prev.map((x, idx) =>
                            idx === i
                              ? { ...x, extractCitations: true }
                              : { ...x, extractCitations: false }
                          ))}
                          style={{
                            width: 38, height: 20, borderRadius: 10, border: 'none', cursor: 'pointer', padding: 2,
                            background: cat.extractCitations ? '#1A9494' : 'var(--border-2)',
                            transition: 'background .18s', flexShrink: 0, position: 'relative',
                          }}
                        >
                          <span style={{
                            display: 'block', width: 16, height: 16, borderRadius: '50%', background: '#fff',
                            transition: 'transform .18s',
                            transform: `translateX(${cat.extractCitations ? 18 : 0}px)`,
                          }} />
                        </button>
                        <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                          {t('settings.results.cat.citations')}
                          {cat.extractCitations && (
                            <span style={{ marginLeft: 6, fontSize: 11, color: '#1A9494', fontWeight: 600 }}>{t('settings.results.cat.inclusion')}</span>
                          )}
                        </span>
                      </div>
                    </div>
                  )
                })}
                <button
                  type="button"
                  disabled={verdictCategories.length >= 8}
                  onClick={() => {
                    const usedColors = verdictCategories.map(c => c.color)
                    const nextColor = VERDICT_COLOR_PALETTE.find(c => !usedColors.includes(c)) ?? VERDICT_COLOR_PALETTE[0]
                    setVerdictCategories(prev => [...prev, { label: '', color: nextColor, extractCitations: false }])
                  }}
                  style={{
                    padding: '9px 16px', border: '1px dashed var(--border-2)', borderRadius: 9,
                    background: 'none', cursor: verdictCategories.length >= 8 ? 'not-allowed' : 'pointer',
                    fontSize: 13, fontWeight: 600,
                    color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 6,
                    opacity: verdictCategories.length >= 8 ? 0.4 : 1,
                  }}
                >
                  <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> {t('settings.results.cat.add')}
                </button>
                <button
                  type="button"
                  onClick={() => setVerdictCategories(DEFAULT_VERDICT_CATEGORIES)}
                  style={{
                    padding: '7px 14px', border: '1px solid var(--border)', borderRadius: 9,
                    background: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-faint)',
                    alignSelf: 'flex-start',
                  }}
                >
                  {t('settings.results.cat.restore')}
                </button>
              </div>

              {/* ── Critérios de classificação ── */}
              <div id="tour-analysis-criteria" style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                <p style={{ fontSize: 12.5, color: 'var(--text-faint)', margin: 0 }}>
                  {t('settings.results.crit.desc')}
                </p>
                {analysisCriteria.map((c, i) => (
                  <div key={i} style={{
                    background: 'var(--surface)', border: '1px solid var(--border)',
                    borderRadius: 10, padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: 10,
                  }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                      <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', letterSpacing: '.05em' }}>
                        {t('settings.results.crit.header')} {i + 1}
                      </span>
                      {analysisCriteria.length > 1 && (
                        <button
                          type="button"
                          onClick={() => setAnalysisCriteria(prev => prev.filter((_, idx) => idx !== i))}
                          style={{
                            width: 26, height: 26, border: '1px solid var(--border)', borderRadius: 6,
                            background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center',
                            justifyContent: 'center', color: 'var(--text-faint)',
                          }}
                          title={t('settings.results.crit.remove')}
                        >
                          <svg width="12" height="12" viewBox="0 0 16 16" fill="none">
                            <path d="m4 4 8 8M12 4l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"/>
                          </svg>
                        </button>
                      )}
                    </div>
                    <div>
                      <label className="label" style={{ marginBottom: 4 }}>{t('settings.results.crit.name')}</label>
                      <input
                        type="text" className="input"
                        value={c.name}
                        onChange={e => setAnalysisCriteria(prev => prev.map((x, idx) => idx === i ? { ...x, name: e.target.value } : x))}
                        placeholder={t('settings.results.crit.namePlaceholder')}
                      />
                    </div>
                    <div>
                      <label className="label" style={{ marginBottom: 4 }}>{t('settings.results.crit.criteria')}</label>
                      <textarea
                        className="input"
                        rows={2}
                        value={c.criteria}
                        onChange={e => setAnalysisCriteria(prev => prev.map((x, idx) => idx === i ? { ...x, criteria: e.target.value } : x))}
                        placeholder={t('settings.results.crit.placeholder')}
                        style={{ resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                      />
                    </div>
                  </div>
                ))}
                <button
                  type="button"
                  onClick={() => setAnalysisCriteria(prev => [...prev, { name: '', criteria: '' }])}
                  style={{
                    padding: '9px 16px', border: '1px dashed var(--border-2)', borderRadius: 9,
                    background: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600,
                    color: 'var(--text-faint)', display: 'flex', alignItems: 'center', gap: 6,
                  }}
                >
                  <span style={{ fontSize: 16, lineHeight: 1 }}>+</span> {t('settings.results.crit.add')}
                </button>
                <button
                  type="button"
                  onClick={() => setAnalysisCriteria(DEFAULT_ANALYSIS_CRITERIA)}
                  style={{
                    padding: '7px 14px', border: '1px solid var(--border)', borderRadius: 9,
                    background: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-faint)',
                    alignSelf: 'flex-start',
                  }}
                >
                  {t('settings.results.crit.restore')}
                </button>
              </div>

              {/* ── Critérios de extração de citações ── */}
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                <div>
                  <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)', marginBottom: 4 }}>{t('settings.results.cite.title')}</div>
                  <p style={{ fontSize: 12.5, color: 'var(--text-faint)', margin: 0 }}>
                    {t('settings.results.cite.desc')}
                  </p>
                </div>
                <div>
                  <textarea
                    className="input"
                    rows={4}
                    value={citationCriteria}
                    onChange={e => setCitationCriteria(e.target.value)}
                    placeholder={t('settings.results.cite.placeholder')}
                    style={{ resize: 'vertical', fontFamily: 'inherit', fontSize: 13 }}
                  />
                </div>
                <button
                  type="button"
                  onClick={() => setCitationCriteria(DEFAULT_CITATION_CRITERIA)}
                  style={{
                    padding: '7px 14px', border: '1px solid var(--border)', borderRadius: 9,
                    background: 'none', cursor: 'pointer', fontSize: 12, color: 'var(--text-faint)',
                    alignSelf: 'flex-start',
                  }}
                >
                  {t('settings.results.cite.restore')}
                </button>
              </div>
            </div>
          ) : (() => {
            /* ── Consumo ── */
            const fmtTokens = (n: number) => n >= 1_000_000 ? `${(n/1_000_000).toFixed(1)}M` : n >= 1_000 ? `${Math.round(n/1_000)}k` : String(n)
            const fmtCost = (v: number | null) => v === null ? '—' : v < 0.000001 ? '$0' : `$${v.toFixed(v < 0.01 ? 6 : 2)}`
            const fmtDate = (s: string) => {
              try {
                const locale = lang === 'en' ? 'en-US' : lang === 'es' ? 'es-ES' : 'pt-BR'
                const d = new Date(s)
                return `${d.toLocaleDateString(locale)} ${d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' })}`
              } catch { return s }
            }
            const TYPE_CHIP: Record<string, { label: string; bg: string; color: string }> = {
              analysis:       { label: t('settings.consumo.type.analysis'),  bg: '#e8f0fe', color: '#1a56db' },
              citations:      { label: t('settings.consumo.type.citations'), bg: '#e6f5ee', color: '#0f6b47' },
              reading_roadmap:{ label: t('settings.consumo.type.roadmap'),   bg: '#e8f8f8', color: '#1A9494' },
            }
            const records = usageData?.records ?? []
            const totals = usageData?.totals
            return (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Summary chips */}
                <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                  {[
                    { label: t('settings.consumo.analyses'), value: usageLoading ? '…' : String(records.length) },
                    { label: t('settings.consumo.totalTokens'), value: usageLoading ? '…' : fmtTokens(totals?.total_tokens ?? 0) },
                    { label: t('settings.consumo.estimatedCost'), value: usageLoading ? '…' : fmtCost(totals?.total_cost_usd ?? null) },
                  ].map(({ label, value }) => (
                    <div key={label} style={{
                      flex: 1, minWidth: 120, padding: '10px 14px', borderRadius: 10,
                      background: 'var(--surface)', border: '1px solid var(--border)',
                    }}>
                      <div style={{ fontSize: 11, color: 'var(--text-faint)', marginBottom: 4 }}>{label}</div>
                      <div style={{ fontSize: 18, fontWeight: 700, fontFamily: 'IBM Plex Mono, monospace', color: 'var(--text)' }}>{value}</div>
                    </div>
                  ))}
                </div>

                {/* Table */}
                {usageLoading ? (
                  <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-faint)', fontSize: 13 }}>{t('settings.consumo.loading')}</div>
                ) : records.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '32px 0', color: 'var(--text-faint)', fontSize: 13 }}>{t('settings.consumo.empty')}</div>
                ) : (
                  <div style={{ overflowX: 'auto', borderRadius: 10, border: '1px solid var(--border)' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12.5 }}>
                      <thead>
                        <tr style={{ background: 'var(--surface)', borderBottom: '1px solid var(--border)' }}>
                          {[t('settings.consumo.col.datetime'), t('settings.consumo.col.type'), t('settings.consumo.col.model'), t('settings.consumo.col.provider'), t('settings.consumo.col.tokens'), t('settings.consumo.col.cost')].map(h => (
                            <th key={h} style={{ padding: '9px 12px', textAlign: 'left', fontWeight: 600, color: 'var(--text-muted)', whiteSpace: 'nowrap' }}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {records.map((r, i) => {
                          const chip = TYPE_CHIP[r.report_type] ?? { label: r.report_type.toUpperCase(), bg: 'var(--surface-2)', color: 'var(--text-muted)' }
                          return (
                            <tr key={r.name} style={{ borderBottom: i < records.length - 1 ? '1px solid var(--border)' : 'none' }}>
                              <td style={{ padding: '8px 12px', color: 'var(--text-muted)', whiteSpace: 'nowrap', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11.5 }}>
                                {fmtDate(r.started_at)}
                              </td>
                              <td style={{ padding: '8px 12px' }}>
                                <span style={{ fontSize: 10.5, fontWeight: 700, padding: '2px 7px', borderRadius: 6, background: chip.bg, color: chip.color, letterSpacing: '.3px' }}>
                                  {chip.label}
                                </span>
                              </td>
                              <td style={{ padding: '8px 12px', color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11.5, maxWidth: 160, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                                {r.model || '—'}
                              </td>
                              <td style={{ padding: '8px 12px', color: 'var(--text-muted)', fontSize: 12 }}>
                                {r.provider || '—'}
                              </td>
                              <td style={{ padding: '8px 12px', color: 'var(--text)', fontFamily: 'IBM Plex Mono, monospace', fontSize: 11.5, whiteSpace: 'nowrap' }}>
                                {fmtTokens(r.total_tokens)}
                                {r.prompt_tokens > 0 && (
                                  <span style={{ color: 'var(--text-faint)', fontSize: 10.5, marginLeft: 4 }}>
                                    ({fmtTokens(r.prompt_tokens)}↑ {fmtTokens(r.completion_tokens)}↓)
                                  </span>
                                )}
                              </td>
                              <td style={{ padding: '8px 12px', color: r.estimated_cost_usd !== null ? 'var(--text)' : 'var(--text-faint)', fontFamily: 'IBM Plex Mono, monospace', fontSize: 12 }}>
                                {fmtCost(r.estimated_cost_usd)}
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}

                {/* Export */}
                <div>
                  <a href={getUsageExportUrl('csv')} download="lutz_usage.csv" style={{
                    display: 'inline-flex', alignItems: 'center', gap: 7,
                    padding: '8px 16px', borderRadius: 8, border: '1px solid #1A9494',
                    background: '#1A9494', color: '#fff', fontSize: 13, fontWeight: 600,
                    textDecoration: 'none',
                  }}>
                    <svg width="13" height="13" viewBox="0 0 16 16" fill="none">
                      <path d="M13.5 10v1.5A1.5 1.5 0 0 1 12 13H4a1.5 1.5 0 0 1-1.5-1.5V10" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round"/>
                      <path d="M8 2v7M5.5 11.5 8 14l2.5-2.5" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round"/>
                    </svg>
                    {t('settings.consumo.export')}
                  </a>
                </div>
              </div>
            )
          })()}
        </div>

        {/* Footer */}
        <div style={{
          flexShrink: 0, padding: '14px 24px', borderTop: '1px solid var(--border)',
          display: 'flex', alignItems: 'center', gap: 12, background: 'var(--surface)',
        }}>
          <button
            onClick={handleSave} disabled={saving || !cfg}
            style={{
              padding: '9px 20px', border: 'none', borderRadius: 9, cursor: 'pointer',
              fontSize: 14, fontWeight: 600, background: '#1A9494', color: '#fff',
              opacity: saving || !cfg ? 0.5 : 1,
            }}>
            {saving ? t('settings.saving') : t('settings.save')}
          </button>
          {saved && <span style={{ color: '#0f6b47', fontSize: 13, fontWeight: 500 }}>{t('settings.saved')}</span>}
          {error && <span style={{ color: '#e05252', fontSize: 13 }}>{error}</span>}
        </div>
      </div>
    </div>
  )
}
