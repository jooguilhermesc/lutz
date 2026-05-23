import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { useLanguage } from '../contexts/LanguageContext'
import { NotificationsPanel } from './NotificationsPanel'

export default function Layout() {
  const { t, showVectorStore, showChat, showAnalytics, showCitations, showRoadmap, showProjects } = useLanguage()
  const location = useLocation()
  const isChatPage = location.pathname === '/chat'

  const NAV = [
    { to: '/',          label: t('nav.home'),      icon: '⌂' },
    ...(showChat      ? [{ to: '/chat',      label: t('nav.chat'),      icon: '💬' }] : []),
    { to: '/vectorize', label: t('nav.vectorize'),  icon: '' },
    ...(showVectorStore ? [{ to: '/store',    label: t('nav.store'),     icon: '' }] : []),
    ...(showAnalytics ? [{ to: '/analytics', label: t('nav.analytics'), icon: '' }] : []),
    { to: '/analysis',  label: t('nav.analysis'),   icon: '' },
    ...(showCitations ? [{ to: '/citations', label: t('nav.citations'), icon: '' }] : []),
    ...(showRoadmap   ? [{ to: '/roadmap',   label: t('nav.roadmap'),   icon: '' }] : []),
    { to: '/reports',   label: t('nav.reports'),    icon: '' },
    ...(showProjects  ? [{ to: '/projects',  label: t('nav.projects'),  icon: '' }] : []),
    { to: '/settings',  label: t('nav.settings'),   icon: '' },
  ]

  return (
    <div className="min-h-screen flex flex-col bg-slate-50">
      {/* ── Top nav ─────────────────────────────────────────────────────── */}
      <header className="bg-[#1A1A1A] text-white shadow-md border-b border-lutz-900/40">
        <div className="max-w-7xl mx-auto px-4 flex items-center gap-5 h-14">
          {/* Logo */}
          <NavLink to="/" className="flex items-center gap-2.5 flex-shrink-0 select-none">
            <img src="/lutz.png" alt="lutz" className="h-8 w-8 rounded-md object-cover" />
            <span className="font-bold text-lutz-400 text-base tracking-tight">lutz</span>
          </NavLink>

          <div className="w-px h-6 bg-white/10 flex-shrink-0" />

          {/* Nav links */}
          <nav className="flex items-center justify-center gap-0.5 overflow-x-auto flex-1">
            {NAV.map(({ to, label, icon }) => (
              <NavLink
                key={to}
                to={to}
                end={to === '/'}
                className={({ isActive }) =>
                  'px-3 py-1.5 rounded-md text-sm font-medium whitespace-nowrap transition-colors ' +
                  (isActive
                    ? 'bg-lutz-500/20 text-lutz-300 ring-1 ring-lutz-500/30'
                    : 'text-slate-400 hover:text-white hover:bg-white/5')
                }
              >
                {icon && <span className="mr-1 opacity-50 text-xs">{icon}</span>}
                {label}
              </NavLink>
            ))}
          </nav>

          {/* Right side: notifications + docs + github */}
          <div className="flex items-center gap-3 flex-shrink-0">
            <NotificationsPanel />
            <a
              href="https://github.com/jooguilhermesc/lutz"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-white transition-colors text-xs flex items-center gap-1"
              title="GitHub"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
              </svg>
              GitHub
            </a>
            <a
              href="https://github.com/jooguilhermesc/lutz/blob/main/README.md"
              target="_blank"
              rel="noopener noreferrer"
              className="text-slate-400 hover:text-white transition-colors text-xs"
              title="Documentação"
            >
              Docs
            </a>
          </div>
        </div>
      </header>

      {/* ── Content ──────────────────────────────────────────────────────── */}
      <main className={isChatPage ? 'flex-1 overflow-hidden' : 'flex-1 max-w-7xl mx-auto w-full px-4 py-8'}>
        <Outlet />
      </main>

      {!isChatPage && (
        <footer className="text-center py-4 text-xs text-slate-400 border-t border-slate-200">
          <span className="text-lutz-500 font-medium">lutz</span>
          {' '}—{' '}triagem de artigos acadêmicos com IA
        </footer>
      )}

      {/* ── Floating chat button (hidden on chat page or when chat is disabled) ── */}
      {!isChatPage && showChat && (
        <NavLink
          to="/chat"
          className="fixed bottom-6 right-6 z-50 flex items-center gap-2 bg-lutz-500 hover:bg-lutz-600 text-white px-4 py-3 rounded-full shadow-lg hover:shadow-xl transition-all group"
          title={t('nav.chat')}
        >
          <span className="text-lg leading-none">💬</span>
          <span className="text-sm font-medium max-w-0 overflow-hidden group-hover:max-w-xs transition-all duration-300 whitespace-nowrap">
            {t('nav.chat')}
          </span>
        </NavLink>
      )}
    </div>
  )
}
