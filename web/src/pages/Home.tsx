import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { getProject, type ProjectInfo } from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'

export default function Home() {
  const [info, setInfo] = useState<ProjectInfo | null>(null)
  const [error, setError] = useState('')
  const { t } = useLanguage()

  useEffect(() => {
    getProject()
      .then(setInfo)
      .catch((e) => setError(e.message))
  }, [])

  const CARDS = [
    { to: '/vectorize', n: '1', titleKey: 'home.card.vectorize.title', descKey: 'home.card.vectorize.desc', color: 'border-lutz-500' },
    { to: '/store',     n: '2', titleKey: 'home.card.store.title',     descKey: 'home.card.store.desc',     color: 'border-lutz-400' },
    { to: '/analysis',  n: '3', titleKey: 'home.card.analysis.title',  descKey: 'home.card.analysis.desc',  color: 'border-lutz-600' },
    { to: '/citations', n: '4', titleKey: 'home.card.citations.title', descKey: 'home.card.citations.desc', color: 'border-lutz-300' },
    { to: '/roadmap',   n: '5', titleKey: 'home.card.roadmap.title',   descKey: 'home.card.roadmap.desc',   color: 'border-lutz-200' },
    { to: '/reports',   n: '6', titleKey: 'home.card.reports.title',   descKey: 'home.card.reports.desc',   color: 'border-lutz-100' },
    { to: '/settings',  n: '⚙', titleKey: 'home.card.settings.title', descKey: 'home.card.settings.desc',  color: 'border-slate-300' },
  ]

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="rounded-xl overflow-hidden shadow-sm">
        <div className="bg-[#1A9494] px-6 py-5 flex items-center gap-4">
          <img src="/lutz.png" alt="lutz" className="h-14 w-14 rounded-lg shadow-md flex-shrink-0" />
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">lutz</h1>
            <p className="text-lutz-100 text-sm mt-0.5">{t('home.subtitle')}</p>
          </div>
        </div>
        {info && (
          <div className="bg-lutz-900 px-6 py-2">
            <p className="text-xs text-lutz-400 font-mono truncate">{info.root}</p>
          </div>
        )}
      </div>

      {/* Metrics */}
      {error ? (
        <div className="text-red-600 text-sm">{error}</div>
      ) : info ? (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          {[
            { label: t('home.metric.articles'), value: info.articles },
            { label: t('home.metric.reports'),  value: info.reports  },
          ].map(({ label, value }) => (
            <div key={label} className="card text-center">
              <div className="text-3xl font-bold text-lutz-600">{value}</div>
              <div className="text-xs text-slate-500 uppercase tracking-wide mt-1">{label}</div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-slate-400 text-sm animate-pulse">{t('home.loading')}</div>
      )}

      {/* Nav cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {CARDS.map(({ to, n, titleKey, descKey, color }) => (
          <Link
            key={to}
            to={to}
            className={`card border-l-4 ${color} hover:shadow-md transition-all group hover:border-lutz-500`}
          >
            <div className="flex items-center gap-3 mb-2">
              <span className="text-lg font-bold text-lutz-300 group-hover:text-lutz-500 transition-colors">
                {n}
              </span>
              <span className="font-semibold text-slate-800">{t(titleKey)}</span>
            </div>
            <p className="text-sm text-slate-500">{t(descKey)}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
