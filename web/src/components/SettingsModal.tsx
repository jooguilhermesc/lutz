import { useEffect, useState } from 'react'
import { getConfig, saveConfig, type Config } from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import { LANG_NAMES, type Lang } from '../i18n'

const LLM_PROVIDERS = [
  { value: 'openai',               label: 'OpenAI / OpenRouter' },
  { value: 'anthropic',            label: 'Anthropic' },
  { value: 'docker_model_runner',  label: 'Docker Model Runner' },
]

const EMBEDDING_PROVIDERS = [
  { value: 'openai',                label: 'OpenAI' },
  { value: 'sentence_transformers', label: 'Sentence Transformers (local)' },
  { value: 'docker_model_runner',   label: 'Docker Model Runner' },
]

const LANGS: Array<{ value: Lang; label: string }> = [
  { value: 'pt', label: LANG_NAMES.pt },
  { value: 'en', label: LANG_NAMES.en },
  { value: 'es', label: LANG_NAMES.es },
]

const TEXT_FIELDS: Array<{ key: keyof Config; label: string; type?: string; placeholder?: string }> = [
  { key: 'LLM_MODEL',         label: 'LLM Model',         placeholder: 'google/gemini-2.5-flash-lite' },
  { key: 'LLM_MAX_TOKENS',    label: 'Max output tokens', type: 'number', placeholder: '2048' },
  { key: 'LLM_TEMPERATURE',   label: 'Temperature',       placeholder: '0.2' },
  { key: 'EMBEDDING_MODEL',   label: 'Embedding model',   placeholder: 'openai/text-embedding-3-small' },
  { key: 'OPENAI_BASE_URL',   label: 'OpenAI base URL',   placeholder: 'https://openrouter.ai/api/v1' },
  { key: 'DOCKER_MODEL_HOST', label: 'Docker model host', placeholder: 'http://localhost:11434' },
]

const KEY_FIELDS: Array<{ envKey: string; label: string; hasKey: 'has_openai_key' | 'has_anthropic_key' }> = [
  { envKey: 'OPENAI_API_KEY',    label: 'OpenAI / OpenRouter API Key', hasKey: 'has_openai_key' },
  { envKey: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key',          hasKey: 'has_anthropic_key' },
]

interface Props { onClose: () => void }

export default function SettingsModal({ onClose }: Props) {
  const { t, lang, setLang, reportLang, setReportLang } = useLanguage()
  const [cfg, setCfg] = useState<Config | null>(null)
  const [llmProvider, setLlmProvider] = useState('openai')
  const [embProvider, setEmbProvider] = useState('openai')
  const [form, setForm] = useState<Record<string, string>>({})
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({})
  const [localReportLang, setLocalReportLang] = useState(reportLang)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')
  const [activeSection, setActiveSection] = useState<'llm' | 'keys' | 'language'>('llm')

  useEffect(() => {
    getConfig().then(c => {
      setCfg(c)
      setLlmProvider(c.LLM_PROVIDER || 'openai')
      setEmbProvider(c.EMBEDDING_PROVIDER || 'openai')
      const initial: Record<string, string> = {}
      for (const f of TEXT_FIELDS) {
        initial[f.key as string] = (c[f.key] as string) || ''
      }
      setForm(initial)
      if (c.REPORT_LANGUAGE) setLocalReportLang(c.REPORT_LANGUAGE)
    })
  }, [])

  async function handleSave() {
    setSaving(true); setSaved(false); setError('')
    try {
      const payload: Record<string, string> = {
        ...form, LLM_PROVIDER: llmProvider, EMBEDDING_PROVIDER: embProvider,
        REPORT_LANGUAGE: localReportLang,
      }
      for (const { envKey } of KEY_FIELDS) {
        if (apiKeys[envKey]) payload[envKey] = apiKeys[envKey]
      }
      await saveConfig(payload)
      setReportLang(localReportLang)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const sectionTab = (id: typeof activeSection, label: string) => (
    <button onClick={() => setActiveSection(id)}
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
      <div onClick={e => e.stopPropagation()}
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
            <div style={{ fontSize: 16, fontWeight: 700, color: 'var(--text)' }}>Configurações</div>
            <div style={{ fontSize: 12.5, color: 'var(--text-faint)' }}>Provedores LLM, chaves de API e preferências</div>
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
          {sectionTab('llm', 'LLM & Embedding')}
          {sectionTab('keys', 'Chaves de API')}
          {sectionTab('language', 'Idioma')}
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '20px 24px 24px', background: 'var(--surface-2)' }}>
          {!cfg ? (
            <p style={{ color: '#8a92a0', fontSize: 13, textAlign: 'center', padding: '40px 0' }}>
              {t('settings.loading')}
            </p>
          ) : activeSection === 'llm' ? (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label className="label">LLM Provider</label>
                <select className="select" value={llmProvider} onChange={e => setLlmProvider(e.target.value)}>
                  {LLM_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              <div>
                <label className="label">Embedding Provider</label>
                <select className="select" value={embProvider} onChange={e => setEmbProvider(e.target.value)}>
                  {EMBEDDING_PROVIDERS.map(p => <option key={p.value} value={p.value}>{p.label}</option>)}
                </select>
              </div>
              {TEXT_FIELDS.map(f => (
                <div key={f.key as string}>
                  <label className="label">{f.label}</label>
                  <input type={f.type ?? 'text'} className="input" placeholder={f.placeholder}
                    value={form[f.key as string] ?? ''}
                    onChange={e => setForm(prev => ({ ...prev, [f.key as string]: e.target.value }))} />
                </div>
              ))}
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
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label className="label">{t('settings.lang.ui')}</label>
                <select className="select" value={lang} onChange={e => setLang(e.target.value as Lang)}>
                  {LANGS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
                <p className="text-xs text-[#8a92a0] mt-1">Aplica imediatamente.</p>
              </div>
              <div>
                <label className="label">{t('settings.lang.report')}</label>
                <select className="select" value={localReportLang} onChange={e => setLocalReportLang(e.target.value)}>
                  {LANGS.map(l => <option key={l.value} value={l.value}>{l.label}</option>)}
                </select>
                <p className="text-xs text-[#8a92a0] mt-1">{t('settings.lang.report.hint')}</p>
              </div>
            </div>
          )}
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
