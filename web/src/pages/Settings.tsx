import { useEffect, useState } from 'react'
import { getConfig, saveConfig, type Config } from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import { LANG_NAMES, type Lang } from '../i18n'

const LLM_PROVIDERS = [
  { value: 'openai',              label: 'OpenAI / OpenRouter' },
  { value: 'anthropic',          label: 'Anthropic' },
  { value: 'docker_model_runner', label: 'Docker Model Runner' },
]

const EMBEDDING_PROVIDERS = [
  { value: 'openai',                 label: 'OpenAI' },
  { value: 'sentence_transformers',  label: 'Sentence Transformers (local)' },
  { value: 'docker_model_runner',    label: 'Docker Model Runner' },
]

const DEFAULTS: Partial<Record<keyof Config, string>> = {
  LLM_PROVIDER:       'openai',
  LLM_MODEL:          'google/gemini-2.5-flash-lite',
  LLM_MAX_TOKENS:     '2048',
  LLM_TEMPERATURE:    '0.2',
  EMBEDDING_PROVIDER: 'openai',
  EMBEDDING_MODEL:    'openai/text-embedding-3-small',
  OPENAI_BASE_URL:    'https://openrouter.ai/api/v1',
}

type TextFieldKey = 'LLM_MODEL' | 'LLM_MAX_TOKENS' | 'LLM_TEMPERATURE' | 'EMBEDDING_MODEL' | 'OPENAI_BASE_URL' | 'DOCKER_MODEL_HOST'

const TEXT_FIELDS: Array<{ key: TextFieldKey; label: string; type?: 'text' | 'number' | 'password'; placeholder?: string }> = [
  { key: 'LLM_MODEL',         label: 'LLM Model',           placeholder: DEFAULTS.LLM_MODEL },
  { key: 'LLM_MAX_TOKENS',    label: 'Max output tokens',   type: 'number', placeholder: '2048' },
  { key: 'LLM_TEMPERATURE',   label: 'Temperature',         placeholder: '0.2' },
  { key: 'EMBEDDING_MODEL',   label: 'Embedding model',     placeholder: DEFAULTS.EMBEDDING_MODEL },
  { key: 'OPENAI_BASE_URL',   label: 'OpenAI base URL',     placeholder: DEFAULTS.OPENAI_BASE_URL },
  { key: 'DOCKER_MODEL_HOST', label: 'Docker model host',   placeholder: 'http://localhost:11434' },
]

const KEY_FIELDS: Array<{ envKey: string; label: string; hasKey: 'has_openai_key' | 'has_anthropic_key' }> = [
  { envKey: 'OPENAI_API_KEY',    label: 'OpenAI / OpenRouter API Key', hasKey: 'has_openai_key' },
  { envKey: 'ANTHROPIC_API_KEY', label: 'Anthropic API Key',          hasKey: 'has_anthropic_key' },
]

const LANGS: Array<{ value: Lang; label: string }> = [
  { value: 'pt', label: LANG_NAMES.pt },
  { value: 'en', label: LANG_NAMES.en },
  { value: 'es', label: LANG_NAMES.es },
]

export default function Settings() {
  const { t, lang, setLang, reportLang, setReportLang, showVectorStore, setShowVectorStore } = useLanguage()

  const [cfg, setCfg] = useState<Config | null>(null)
  const [llmProvider, setLlmProvider] = useState(DEFAULTS.LLM_PROVIDER ?? 'openai')
  const [embProvider, setEmbProvider] = useState(DEFAULTS.EMBEDDING_PROVIDER ?? 'openai')
  const [form, setForm] = useState<Record<string, string>>({})
  const [apiKeys, setApiKeys] = useState<Record<string, string>>({})
  const [localReportLang, setLocalReportLang] = useState(reportLang)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    getConfig().then((c) => {
      setCfg(c)
      setLlmProvider(c.LLM_PROVIDER || DEFAULTS.LLM_PROVIDER || 'openai')
      setEmbProvider(c.EMBEDDING_PROVIDER || DEFAULTS.EMBEDDING_PROVIDER || 'openai')
      const initial: Record<string, string> = {}
      for (const f of TEXT_FIELDS) {
        initial[f.key] = (c[f.key] as string) || (DEFAULTS[f.key] ?? '')
      }
      setForm(initial)
      if (c.REPORT_LANGUAGE) setLocalReportLang(c.REPORT_LANGUAGE)
    })
  }, [])

  useEffect(() => { setLocalReportLang(reportLang) }, [reportLang])

  async function handleSave() {
    setSaving(true)
    setSaved(false)
    setError('')
    try {
      const payload: Record<string, string> = {
        ...form,
        LLM_PROVIDER: llmProvider,
        EMBEDDING_PROVIDER: embProvider,
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

  if (!cfg) return <div className="text-slate-400 animate-pulse text-sm">{t('settings.loading')}</div>

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-800">{t('settings.title')}</h2>

      {/* Language */}
      <div className="card space-y-4">
        <h3 className="font-semibold text-slate-700 text-sm">{t('settings.section.language')}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <div>
            <label className="label">{t('settings.lang.ui')}</label>
            <select className="select" value={lang} onChange={(e) => setLang(e.target.value as Lang)}>
              {LANGS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <p className="text-xs text-slate-400 mt-1">Aplica imediatamente — sem necessidade de salvar.</p>
          </div>
          <div>
            <label className="label">{t('settings.lang.report')}</label>
            <select className="select" value={localReportLang} onChange={(e) => setLocalReportLang(e.target.value)}>
              {LANGS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
            <p className="text-xs text-slate-400 mt-1">{t('settings.lang.report.hint')}</p>
          </div>
        </div>
      </div>

      {/* LLM & Embedding */}
      <div className="card space-y-4">
        <h3 className="font-semibold text-slate-700 text-sm">{t('settings.section.llm')}</h3>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {/* Provider dropdowns */}
          <div>
            <label className="label">LLM Provider</label>
            <select className="select" value={llmProvider} onChange={(e) => setLlmProvider(e.target.value)}>
              {LLM_PROVIDERS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="label">Embedding Provider</label>
            <select className="select" value={embProvider} onChange={(e) => setEmbProvider(e.target.value)}>
              {EMBEDDING_PROVIDERS.map(({ value, label }) => (
                <option key={value} value={value}>{label}</option>
              ))}
            </select>
          </div>
          {/* Text fields */}
          {TEXT_FIELDS.map((f) => (
            <div key={f.key}>
              <label className="label">{f.label}</label>
              <input
                type={f.type ?? 'text'}
                className="input"
                placeholder={f.placeholder}
                value={form[f.key] ?? ''}
                onChange={(e) => setForm((prev) => ({ ...prev, [f.key]: e.target.value }))}
              />
            </div>
          ))}
        </div>
      </div>

      {/* API Keys */}
      <div className="card space-y-4">
        <h3 className="font-semibold text-slate-700 text-sm">{t('settings.section.keys')}</h3>
        <p className="text-xs text-slate-400">{t('settings.keys.hint')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          {KEY_FIELDS.map(({ envKey, label, hasKey }) => (
            <div key={envKey}>
              <label className="label">
                {label}
                {cfg[hasKey] && (
                  <span className="ml-2 text-green-600 font-normal text-xs">{t('settings.key.configured')}</span>
                )}
              </label>
              <input
                type="password"
                className="input"
                placeholder={cfg[hasKey] ? '••••••••••••••••' : 'sk-...'}
                value={apiKeys[envKey] ?? ''}
                onChange={(e) => setApiKeys((prev) => ({ ...prev, [envKey]: e.target.value }))}
                autoComplete="off"
              />
            </div>
          ))}
        </div>
      </div>

      {/* Interface */}
      <div className="card space-y-3">
        <h3 className="font-semibold text-slate-700 text-sm">{t('settings.section.ui')}</h3>
        <label className="flex items-start gap-3 cursor-pointer">
          <input
            type="checkbox"
            className="rounded border-slate-300 text-lutz-500 focus:ring-lutz-400 mt-0.5"
            checked={showVectorStore}
            onChange={(e) => setShowVectorStore(e.target.checked)}
          />
          <div>
            <p className="text-sm font-medium text-slate-700">{t('settings.showVectorStore')}</p>
            <p className="text-xs text-slate-400">{t('settings.showVectorStore.hint')}</p>
          </div>
        </label>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-4">
        <button className="btn-primary" onClick={handleSave} disabled={saving}>
          {saving ? t('settings.saving') : t('settings.save')}
        </button>
        {saved && <span className="text-green-600 text-sm font-medium">{t('settings.saved')}</span>}
        {error && <span className="text-red-600 text-sm">{error}</span>}
      </div>

      {/* Info box */}
      <div className="border border-slate-200 rounded-xl p-4 bg-slate-50 text-xs text-slate-500 space-y-1">
        <p className="font-semibold text-slate-600">{t('settings.info.title')}</p>
        <p>{t('settings.info.p1')}</p>
        <p>{t('settings.info.p2')}</p>
      </div>
    </div>
  )
}
