import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { LanguageProvider } from './contexts/LanguageContext.tsx'
import { NotificationsProvider } from './contexts/NotificationsContext.tsx'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
      <NotificationsProvider>
        <App />
      </NotificationsProvider>
    </LanguageProvider>
  </StrictMode>,
)
