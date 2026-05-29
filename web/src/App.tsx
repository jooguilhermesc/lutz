import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import Vectorize from './pages/Vectorize'
import VectorStore from './pages/VectorStore'
import Analysis from './pages/Analysis'
import Citations from './pages/Citations'
import Roadmap from './pages/Roadmap'
import Reports from './pages/Reports'
import Settings from './pages/Settings'
import Analytics from './pages/Analytics'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="vectorize" element={<Vectorize />} />
          <Route path="store" element={<VectorStore />} />
          <Route path="analytics" element={<Analytics />} />
          <Route path="analysis" element={<Analysis />} />
          <Route path="citations" element={<Citations />} />
          <Route path="roadmap" element={<Roadmap />} />
          <Route path="reports" element={<Reports />} />
          <Route path="settings" element={<Settings />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}
