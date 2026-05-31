import { useState, useEffect, useCallback, KeyboardEvent } from 'react'
import { useLanguage } from '../contexts/LanguageContext'
import {
  queryVectorStoreAnalytics,
  listUDFs,
  type UDFInfo,
  type QueryResult,
  runDedup,
  type DedupResult,
  runRank,
  type RankResult,
  listModels,
  fitModel,
  exploreKmeans,
  deleteModel,
  clusterReport,
  type FittedModel,
} from '../api/client'
import CollapsibleSection from '../components/CollapsibleSection'

// ── Colour palette for clusters ──────────────────────────────────────────────

const PALETTE = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#8b5cf6',
  '#ec4899', '#14b8a6', '#f97316', '#06b6d4', '#84cc16',
]

// ── Scatter plot (pure SVG, no dependencies) ─────────────────────────────────

interface ScatterProps {
  coords: [number, number][]
  labels: (string | number | null)[]
  names: string[]
}

function ScatterPlot({ coords, labels, names }: ScatterProps) {
  const W = 520, H = 380, PAD = 28
  if (coords.length === 0) return null

  const xs = coords.map(c => c[0])
  const ys = coords.map(c => c[1])
  const minX = Math.min(...xs), maxX = Math.max(...xs)
  const minY = Math.min(...ys), maxY = Math.max(...ys)
  const rangeX = maxX - minX || 1
  const rangeY = maxY - minY || 1

  const sx = (x: number) => PAD + ((x - minX) / rangeX) * (W - 2 * PAD)
  const sy = (y: number) => H - PAD - ((y - minY) / rangeY) * (H - 2 * PAD)

  const uniqueLabels = [...new Set(labels.map(String))]
  const colorOf = (l: string | number | null) => {
    const idx = uniqueLabels.indexOf(String(l))
    return PALETTE[idx % PALETTE.length]
  }

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-2xl border border-slate-200 rounded-lg bg-white"
        style={{ minWidth: 320 }}
      >
        {coords.map((c, i) => (
          <circle
            key={i}
            cx={sx(c[0])}
            cy={sy(c[1])}
            r={3.5}
            fill={colorOf(labels[i])}
            fillOpacity={0.75}
            stroke="white"
            strokeWidth={0.6}
          >
            <title>{names[i] ? `${names[i]}${labels[i] !== null ? ` · cluster ${labels[i]}` : ''}` : ''}</title>
          </circle>
        ))}
      </svg>
    </div>
  )
}

// ── Silhouette bar chart (pure SVG) ───────────────────────────────────────────

interface SilhouetteChartProps {
  metrics: Array<{ k: number; silhouette: number; inertia: number }>
  suggestedK: number
}

function SilhouetteChart({ metrics, suggestedK }: SilhouetteChartProps) {
  if (metrics.length === 0) return null
  const W = 480, H = 160, PAD_L = 36, PAD_R = 12, PAD_T = 12, PAD_B = 24
  const barW = Math.max(8, Math.floor((W - PAD_L - PAD_R) / metrics.length) - 4)
  const maxSil = Math.max(...metrics.map(m => m.silhouette), 0.01)
  const innerH = H - PAD_T - PAD_B

  return (
    <div className="overflow-x-auto">
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full max-w-xl border border-slate-200 rounded-lg bg-white"
        style={{ minWidth: 280 }}
      >
        {metrics.map((m, i) => {
          const x = PAD_L + i * ((W - PAD_L - PAD_R) / metrics.length) + 2
          const barH = (m.silhouette / maxSil) * innerH
          const y = PAD_T + innerH - barH
          const isSelected = m.k === suggestedK
          return (
            <g key={m.k}>
              <rect
                x={x}
                y={y}
                width={barW}
                height={barH}
                fill={isSelected ? '#6366f1' : '#94a3b8'}
                rx={2}
              >
                <title>k={m.k} · silhouette={m.silhouette.toFixed(4)}</title>
              </rect>
              <text
                x={x + barW / 2}
                y={H - PAD_B + 12}
                textAnchor="middle"
                fontSize={9}
                fill={isSelected ? '#6366f1' : '#64748b'}
                fontWeight={isSelected ? 'bold' : 'normal'}
              >
                {m.k}
              </text>
            </g>
          )
        })}
        <text x={PAD_L - 4} y={PAD_T + 4} textAnchor="end" fontSize={8} fill="#94a3b8">
          {maxSil.toFixed(2)}
        </text>
        <text x={PAD_L - 4} y={PAD_T + innerH} textAnchor="end" fontSize={8} fill="#94a3b8">
          0
        </text>
        <line x1={PAD_L} y1={PAD_T} x2={PAD_L} y2={PAD_T + innerH} stroke="#e2e8f0" strokeWidth={1} />
        <line x1={PAD_L} y1={PAD_T + innerH} x2={W - PAD_R} y2={PAD_T + innerH} stroke="#e2e8f0" strokeWidth={1} />
      </svg>
    </div>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseCell(v: unknown): unknown {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.startsWith('[')) {
    try { return JSON.parse(v) } catch { /* fall through */ }
  }
  return v
}

function findArrayCol(columns: string[], rows: unknown[][]): number {
  for (let c = 0; c < columns.length; c++) {
    const cell = parseCell(rows[0]?.[c])
    if (Array.isArray(cell) && cell.length >= 2) return c
  }
  return -1
}

function findLabelCol(columns: string[]): number {
  const patterns = ['cluster', 'label', 'kmeans', 'dbscan', 'group']
  for (let c = 0; c < columns.length; c++) {
    if (patterns.some(p => columns[c].toLowerCase().includes(p))) return c
  }
  return -1
}

function findNameCol(columns: string[]): number {
  const patterns = ['filename', 'file', 'name', 'article', 'doc']
  for (let c = 0; c < columns.length; c++) {
    if (patterns.some(p => columns[c].toLowerCase().includes(p))) return c
  }
  return -1
}

function displayCell(v: unknown): string {
  const parsed = parseCell(v)
  if (parsed === null || parsed === undefined) return '—'
  if (Array.isArray(parsed)) {
    const nums = (parsed as number[]).slice(0, 5)
    const preview = nums.map(n => (typeof n === 'number' ? n.toFixed(4) : String(n))).join(', ')
    return `[${preview}${parsed.length > 5 ? ', …' : ''}]`
  }
  return String(v)
}

// ── Example queries ───────────────────────────────────────────────────────────

const EXAMPLES: { label: string; sql: string }[] = [
  {
    label: 'PCA + clusters',
    sql:
      'SELECT filename, section,\n' +
      '       pca_project(embedding, 2) AS coords,\n' +
      '       kmeans_label(embedding, 5) AS cluster\n' +
      'FROM   vectors',
  },
  {
    label: 'Outliers',
    sql:
      'SELECT filename, section,\n' +
      '       corpus_centroid_distance(embedding) AS outlier_score\n' +
      'FROM   vectors\n' +
      'ORDER  BY outlier_score DESC\n' +
      'LIMIT  20',
  },
  {
    label: 'Norm por artigo',
    sql:
      'SELECT filename,\n' +
      '       ROUND(AVG(embedding_norm(embedding)), 4) AS avg_norm,\n' +
      '       COUNT(*) AS chunks\n' +
      'FROM   vectors\n' +
      'GROUP  BY filename\n' +
      'ORDER  BY avg_norm DESC',
  },
  {
    label: 'Chunks por seção',
    sql:
      'SELECT section, COUNT(*) AS chunks\n' +
      'FROM   vectors\n' +
      'GROUP  BY section\n' +
      'ORDER  BY chunks DESC',
  },
  {
    label: 'predict_cluster',
    sql:
      'SELECT filename, section,\n' +
      "       predict_cluster(embedding, 'kmeans_5') AS cluster\n" +
      'FROM   vectors',
  },
  {
    label: 'predict_centroid_distance',
    sql:
      'SELECT filename,\n' +
      "       AVG(predict_centroid_distance(embedding, 'corpus_centroid')) AS outlier_score\n" +
      'FROM   vectors\n' +
      'GROUP  BY filename\n' +
      'ORDER  BY outlier_score DESC\n' +
      'LIMIT  20',
  },
]

// ── Tab types ─────────────────────────────────────────────────────────────────

type TabId = 'sql' | 'dedup' | 'rank' | 'models'

const STORAGE_KEY = 'analytics_active_tab'

// ── Dedup tab ─────────────────────────────────────────────────────────────────

function DedupTab() {
  const { t } = useLanguage()
  const [threshold, setThreshold] = useState(0.05)
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<DedupResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const r = await runDedup(threshold)
      setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const distanceBadge = (d: number) => {
    if (d < 0.02) return 'bg-green-100 text-green-700'
    if (d < 0.05) return 'bg-yellow-100 text-yellow-700'
    return 'bg-red-100 text-red-700'
  }

  return (
    <div className="space-y-4">
      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-slate-700">{t('analytics.dedup.title')}</h3>
        <div className="flex items-center gap-4 flex-wrap">
          <label className="text-sm text-slate-600 font-medium">
            {t('analytics.dedup.threshold')}
          </label>
          <input
            type="number"
            min={0.01}
            max={0.20}
            step={0.01}
            value={threshold}
            onChange={e => setThreshold(parseFloat(e.target.value))}
            className="input w-28 text-sm"
          />
          <input
            type="range"
            min={0.01}
            max={0.20}
            step={0.01}
            value={threshold}
            onChange={e => setThreshold(parseFloat(e.target.value))}
            className="flex-1 min-w-32 accent-lutz-500"
          />
          <span className="text-sm font-mono text-slate-500 w-12">{threshold.toFixed(2)}</span>
        </div>
        <button
          className="btn btn-primary text-sm"
          onClick={run}
          disabled={running}
        >
          {running ? t('analytics.dedup.running') : t('analytics.dedup.run')}
        </button>
        {error && (
          <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
            {error}
          </pre>
        )}
      </div>

      {result && result.groups.length === 0 && (
        <div className="card border border-green-200 bg-green-50 text-green-700 text-sm font-medium">
          {t('analytics.dedup.clean')}
        </div>
      )}

      {result && result.groups.length > 0 && (
        <div className="space-y-3">
          {result.groups.map(g => (
            <div key={g.group_id} className="card space-y-2">
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-xs font-semibold text-slate-500">Grupo {g.group_id}</span>
                <span className="text-xs text-slate-400">—</span>
                <span className="text-xs font-medium text-slate-600">{t('analytics.dedup.keep')}:</span>
                <span className="font-mono text-xs text-lutz-700 bg-lutz-50 px-1.5 py-0.5 rounded">{g.keep}</span>
              </div>
              <ul className="space-y-1">
                {g.duplicates.map(d => (
                  <li key={d.filename} className="flex items-center gap-2 text-xs text-slate-600">
                    <span className="font-mono truncate max-w-xs">{d.filename}</span>
                    <span className={`px-1.5 py-0.5 rounded text-xs font-mono ${distanceBadge(d.distance)}`}>
                      {d.distance.toFixed(4)}
                    </span>
                  </li>
                ))}
              </ul>
            </div>
          ))}
          <p className="text-xs text-slate-400 italic">{t('analytics.dedup.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}

// ── Rank tab ─────────────────────────────────────────────────────────────────

function RankTab() {
  const { t } = useLanguage()
  const [question, setQuestion] = useState('')
  const [aggregation, setAggregation] = useState<'mean' | 'max'>('mean')
  const [sections, setSections] = useState('')
  const [top, setTop] = useState('')
  const [running, setRunning] = useState(false)
  const [result, setResult] = useState<RankResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async () => {
    if (!question.trim() || running) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const body: Parameters<typeof runRank>[0] = {
        question: question.trim(),
        aggregation,
      }
      if (sections.trim()) {
        body.filter_sections = sections.split(',').map(s => s.trim()).filter(Boolean)
      }
      if (top.trim()) {
        body.top = parseInt(top.trim(), 10)
      }
      const r = await runRank(body)
      setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  const maxScore = result ? Math.max(...result.articles.map(a => a.score), 0.001) : 1

  return (
    <div className="space-y-4">
      <div className="card space-y-4">
        <h3 className="text-sm font-semibold text-slate-700">{t('analytics.rank.title')}</h3>

        <div className="space-y-1">
          <label className="text-xs text-slate-600 font-medium">{t('analytics.rank.question')}</label>
          <textarea
            className="input text-sm h-20 resize-y"
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder={t('analytics.rank.question.placeholder')}
          />
        </div>

        <div className="flex items-center gap-4 flex-wrap">
          <label className="text-xs text-slate-600 font-medium">{t('analytics.rank.aggregation')}</label>
          <div className="flex rounded overflow-hidden border border-slate-200 text-xs">
            <button
              className={`px-3 py-1.5 transition-colors ${aggregation === 'mean' ? 'bg-lutz-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
              onClick={() => setAggregation('mean')}
            >
              Média
            </button>
            <button
              className={`px-3 py-1.5 transition-colors ${aggregation === 'max' ? 'bg-lutz-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-50'}`}
              onClick={() => setAggregation('max')}
            >
              Máxima
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div className="space-y-1">
            <label className="text-xs text-slate-600 font-medium">{t('analytics.rank.sections')}</label>
            <input
              type="text"
              className="input text-sm"
              value={sections}
              onChange={e => setSections(e.target.value)}
              placeholder="abstract, introduction"
            />
          </div>
          <div className="space-y-1">
            <label className="text-xs text-slate-600 font-medium">{t('analytics.rank.top')}</label>
            <input
              type="number"
              className="input text-sm"
              value={top}
              onChange={e => setTop(e.target.value)}
              placeholder="20"
              min={1}
            />
          </div>
        </div>

        <button
          className="btn btn-primary text-sm"
          onClick={run}
          disabled={running || !question.trim()}
        >
          {running ? t('analytics.rank.running') : t('analytics.rank.run')}
        </button>

        {error && (
          <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
            {error}
          </pre>
        )}
      </div>

      {result && result.articles.length > 0 && (
        <div className="card space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-slate-700">{result.articles.length} artigos — {result.elapsed_ms} ms</h4>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-xs">
              <thead>
                <tr className="bg-slate-800 text-white">
                  <th className="px-3 py-2 text-left font-medium">Rank</th>
                  <th className="px-3 py-2 text-left font-medium">Arquivo</th>
                  <th className="px-3 py-2 text-left font-medium w-40">Score</th>
                  <th className="px-3 py-2 text-left font-medium">Chunks</th>
                </tr>
              </thead>
              <tbody>
                {result.articles.map((a, i) => (
                  <tr key={a.filename} className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}>
                    <td className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-500">{a.rank}</td>
                    <td className="px-3 py-1.5 border-b border-slate-100 text-slate-700 max-w-xs truncate font-mono" title={a.filename}>
                      {a.filename}
                    </td>
                    <td className="px-3 py-1.5 border-b border-slate-100">
                      <div className="flex items-center gap-2">
                        <div className="flex-1 bg-slate-100 rounded-full h-2 overflow-hidden">
                          <div
                            className="h-2 rounded-full bg-lutz-500"
                            style={{ width: `${Math.max(2, (a.score / maxScore) * 100)}%` }}
                          />
                        </div>
                        <span className="font-mono text-slate-600 w-14 text-right">{a.score.toFixed(4)}</span>
                      </div>
                    </td>
                    <td className="px-3 py-1.5 border-b border-slate-100 text-slate-500 text-center">{a.chunks_used}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-slate-400 italic">{t('analytics.rank.disclaimer')}</p>
        </div>
      )}
    </div>
  )
}

// ── Models tab ────────────────────────────────────────────────────────────────

interface ClusterReportData {
  model_id: string
  clusters: Array<{
    cluster_id: number
    n_articles: number
    article_filenames: string[]
    representative_chunks: Array<{
      filename: string
      section: string
      text: string
      distance_to_centroid: number
    }>
  }>
}

function ModelsTab() {
  const { t } = useLanguage()

  // Explore k state
  const [kRange, setKRange] = useState('')
  const [exploreSample, setExploreSample] = useState('')
  const [exploreRunning, setExploreRunning] = useState(false)
  const [exploreResult, setExploreResult] = useState<{
    metrics: Array<{ k: number; silhouette: number; inertia: number }>
    suggested_k: number
    elapsed_ms: number
  } | null>(null)
  const [exploreError, setExploreError] = useState<string | null>(null)

  // Fit state
  const [fitAlgorithm, setFitAlgorithm] = useState<'kmeans' | 'pca' | 'centroid'>('kmeans')
  const [fitK, setFitK] = useState('')
  const [fitN, setFitN] = useState('')
  const [fitRunning, setFitRunning] = useState(false)
  const [fitSuccess, setFitSuccess] = useState<string | null>(null)
  const [fitError, setFitError] = useState<string | null>(null)

  // List state
  const [models, setModels] = useState<FittedModel[]>([])
  const [listError, setListError] = useState<string | null>(null)

  // Report state (per model)
  const [reportOpen, setReportOpen] = useState<Record<string, boolean>>({})
  const [reportTopChunks, setReportTopChunks] = useState<Record<string, string>>({})
  const [reportRunning, setReportRunning] = useState<Record<string, boolean>>({})
  const [reportData, setReportData] = useState<Record<string, ClusterReportData>>({})
  const [reportError, setReportError] = useState<Record<string, string>>({})
  const [openClusters, setOpenClusters] = useState<Record<string, Set<number>>>({})

  const loadModels = useCallback(async () => {
    try {
      const r = await listModels()
      setModels(r.models)
      setListError(null)
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e))
    }
  }, [])

  useEffect(() => {
    loadModels()
  }, [loadModels])

  const runExplore = async () => {
    if (!kRange.trim() || exploreRunning) return
    setExploreRunning(true)
    setExploreError(null)
    setExploreResult(null)
    try {
      const body: Parameters<typeof exploreKmeans>[0] = { k_range: kRange.trim() }
      if (exploreSample.trim()) body.sample = parseInt(exploreSample.trim(), 10)
      const r = await exploreKmeans(body)
      setExploreResult(r)
    } catch (e) {
      setExploreError(e instanceof Error ? e.message : String(e))
    } finally {
      setExploreRunning(false)
    }
  }

  const runFit = async () => {
    if (fitRunning) return
    setFitRunning(true)
    setFitError(null)
    setFitSuccess(null)
    try {
      const params: Record<string, unknown> = {}
      if (fitAlgorithm === 'kmeans' && fitK.trim()) params.k = parseInt(fitK.trim(), 10)
      if (fitAlgorithm === 'pca' && fitN.trim()) params.n = parseInt(fitN.trim(), 10)
      const r = await fitModel({ algorithm: fitAlgorithm, params })
      setFitSuccess(r.model_id)
      await loadModels()
    } catch (e) {
      setFitError(e instanceof Error ? e.message : String(e))
    } finally {
      setFitRunning(false)
    }
  }

  const handleDelete = async (model_id: string) => {
    try {
      await deleteModel(model_id)
      setModels(ms => ms.filter(m => m.model_id !== model_id))
    } catch (e) {
      setListError(e instanceof Error ? e.message : String(e))
    }
  }

  const toggleReport = (model_id: string) => {
    setReportOpen(prev => ({ ...prev, [model_id]: !prev[model_id] }))
  }

  const generateReport = async (model_id: string) => {
    const tc = parseInt(reportTopChunks[model_id] ?? '3', 10)
    setReportRunning(prev => ({ ...prev, [model_id]: true }))
    setReportError(prev => ({ ...prev, [model_id]: '' }))
    try {
      const r = await clusterReport(model_id, tc || 3)
      setReportData(prev => ({ ...prev, [model_id]: r }))
    } catch (e) {
      setReportError(prev => ({ ...prev, [model_id]: e instanceof Error ? e.message : String(e) }))
    } finally {
      setReportRunning(prev => ({ ...prev, [model_id]: false }))
    }
  }

  const toggleCluster = (model_id: string, cluster_id: number) => {
    setOpenClusters(prev => {
      const s = new Set(prev[model_id] ?? [])
      if (s.has(cluster_id)) s.delete(cluster_id)
      else s.add(cluster_id)
      return { ...prev, [model_id]: s }
    })
  }

  return (
    <div className="space-y-4">

      {/* Explore k */}
      <CollapsibleSection title={t('analytics.models.explore.title')} storageKey="analytics_models_explore">
        <div className="card space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-slate-600 font-medium">{t('analytics.models.explore.krange')}</label>
              <input
                type="text"
                className="input text-sm"
                value={kRange}
                onChange={e => setKRange(e.target.value)}
                placeholder="2..12"
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-slate-600 font-medium">{t('analytics.models.explore.sample')}</label>
              <input
                type="number"
                className="input text-sm"
                value={exploreSample}
                onChange={e => setExploreSample(e.target.value)}
                placeholder="5000"
                min={100}
              />
            </div>
          </div>
          <button
            className="btn btn-primary text-sm"
            onClick={runExplore}
            disabled={exploreRunning || !kRange.trim()}
          >
            {exploreRunning ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                {t('analytics.models.explore.running')}
              </span>
            ) : t('analytics.models.explore.run')}
          </button>
          {exploreError && (
            <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
              {exploreError}
            </pre>
          )}
          {exploreResult && (
            <div className="space-y-3">
              <p className="text-xs text-slate-500">
                {t('analytics.models.explore.suggested')}: <span className="font-mono font-semibold text-lutz-600">{exploreResult.suggested_k}</span>
                {' '}— {exploreResult.elapsed_ms} ms
              </p>
              <SilhouetteChart metrics={exploreResult.metrics} suggestedK={exploreResult.suggested_k} />
              <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                  <thead>
                    <tr className="bg-slate-800 text-white">
                      <th className="px-3 py-2 text-left font-medium">k</th>
                      <th className="px-3 py-2 text-left font-medium">Silhouette</th>
                      <th className="px-3 py-2 text-left font-medium">Inércia</th>
                    </tr>
                  </thead>
                  <tbody>
                    {exploreResult.metrics.map((m, i) => (
                      <tr
                        key={m.k}
                        className={m.k === exploreResult.suggested_k
                          ? 'bg-indigo-50 font-semibold'
                          : i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}
                      >
                        <td className={`px-3 py-1.5 border-b border-slate-100 font-mono ${m.k === exploreResult.suggested_k ? 'text-indigo-700' : 'text-slate-700'}`}>
                          {m.k}{m.k === exploreResult.suggested_k ? ' ★' : ''}
                        </td>
                        <td className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-700">{m.silhouette.toFixed(4)}</td>
                        <td className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-700">{m.inertia.toFixed(2)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* Fit model */}
      <CollapsibleSection title={t('analytics.models.fit.title')} storageKey="analytics_models_fit">
        <div className="card space-y-4">
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-slate-600 font-medium">{t('analytics.models.fit.algorithm')}</label>
              <select
                className="input text-sm"
                value={fitAlgorithm}
                onChange={e => setFitAlgorithm(e.target.value as 'kmeans' | 'pca' | 'centroid')}
              >
                <option value="kmeans">KMeans</option>
                <option value="pca">PCA</option>
                <option value="centroid">Centroide</option>
              </select>
            </div>
            {fitAlgorithm === 'kmeans' && (
              <div className="space-y-1">
                <label className="text-xs text-slate-600 font-medium">{t('analytics.models.fit.k')}</label>
                <input
                  type="number"
                  className="input text-sm"
                  value={fitK}
                  onChange={e => setFitK(e.target.value)}
                  placeholder="5"
                  min={2}
                />
              </div>
            )}
            {fitAlgorithm === 'pca' && (
              <div className="space-y-1">
                <label className="text-xs text-slate-600 font-medium">{t('analytics.models.fit.n')}</label>
                <input
                  type="number"
                  className="input text-sm"
                  value={fitN}
                  onChange={e => setFitN(e.target.value)}
                  placeholder="2"
                  min={2}
                />
              </div>
            )}
          </div>
          <button
            className="btn btn-primary text-sm"
            onClick={runFit}
            disabled={fitRunning}
          >
            {fitRunning ? (
              <span className="flex items-center gap-2">
                <svg className="animate-spin h-3.5 w-3.5" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                </svg>
                {t('analytics.models.fit.running')}
              </span>
            ) : t('analytics.models.fit.run')}
          </button>
          {fitSuccess && (
            <p className="text-xs text-green-600 bg-green-50 border border-green-200 rounded px-3 py-2">
              Modelo treinado: <span className="font-mono font-semibold">{fitSuccess}</span>
            </p>
          )}
          {fitError && (
            <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
              {fitError}
            </pre>
          )}
        </div>
      </CollapsibleSection>

      {/* Trained models list */}
      <CollapsibleSection title={t('analytics.models.list.title')} storageKey="analytics_models_list">
        <div className="card space-y-4">
          <div className="flex items-center gap-3">
            <button className="btn btn-secondary text-xs" onClick={loadModels}>
              {t('analytics.models.list.refresh')}
            </button>
          </div>
          {listError && (
            <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
              {listError}
            </pre>
          )}
          {models.length === 0 && !listError && (
            <p className="text-sm text-slate-400">{t('analytics.models.list.empty')}</p>
          )}
          {models.length > 0 && (
            <div className="overflow-x-auto space-y-0">
              <table className="min-w-full text-xs">
                <thead>
                  <tr className="bg-slate-800 text-white">
                    <th className="px-3 py-2 text-left font-medium">Model ID</th>
                    <th className="px-3 py-2 text-left font-medium">Algoritmo</th>
                    <th className="px-3 py-2 text-left font-medium">Parâmetros</th>
                    <th className="px-3 py-2 text-left font-medium">Chunks</th>
                    <th className="px-3 py-2 text-left font-medium">Treinado em</th>
                    <th className="px-3 py-2 text-left font-medium">Corpus</th>
                    <th className="px-3 py-2 text-left font-medium">Ações</th>
                  </tr>
                </thead>
                <tbody>
                  {models.map((m, i) => (
                    <>
                      <tr
                        key={m.model_id}
                        className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}
                      >
                        <td className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-700 max-w-xs truncate" title={m.model_id}>
                          {m.model_id}
                        </td>
                        <td className="px-3 py-1.5 border-b border-slate-100 text-slate-600">{m.algorithm}</td>
                        <td className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-500 max-w-xs truncate" title={JSON.stringify(m.params)}>
                          {JSON.stringify(m.params)}
                        </td>
                        <td className="px-3 py-1.5 border-b border-slate-100 text-slate-600 text-center">{m.n_rows}</td>
                        <td className="px-3 py-1.5 border-b border-slate-100 text-slate-500 whitespace-nowrap">
                          {new Date(m.trained_at).toLocaleString()}
                        </td>
                        <td className="px-3 py-1.5 border-b border-slate-100">
                          <span className={m.corpus_valid ? 'text-green-600 font-semibold' : 'text-orange-500'}>
                            {m.corpus_valid ? t('analytics.models.list.valid') : t('analytics.models.list.invalid')}
                          </span>
                        </td>
                        <td className="px-3 py-1.5 border-b border-slate-100">
                          <div className="flex items-center gap-1.5">
                            <button
                              className="text-xs px-2 py-1 rounded bg-lutz-50 text-lutz-700 hover:bg-lutz-100 border border-lutz-200 transition-colors"
                              onClick={() => toggleReport(m.model_id)}
                            >
                              {t('analytics.models.list.report')}
                            </button>
                            <button
                              className="text-xs px-2 py-1 rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200 transition-colors"
                              onClick={() => handleDelete(m.model_id)}
                            >
                              {t('analytics.models.list.remove')}
                            </button>
                          </div>
                        </td>
                      </tr>

                      {/* Inline report row */}
                      {reportOpen[m.model_id] && (
                        <tr key={`report-${m.model_id}`} className="bg-indigo-50">
                          <td colSpan={7} className="px-3 py-3 border-b border-slate-200">
                            <div className="space-y-3">
                              <div className="flex items-center gap-3 flex-wrap">
                                <label className="text-xs text-slate-600 font-medium">
                                  {t('analytics.models.report.topChunks')}
                                </label>
                                <input
                                  type="number"
                                  className="input text-xs w-20"
                                  value={reportTopChunks[m.model_id] ?? '3'}
                                  onChange={e => setReportTopChunks(prev => ({ ...prev, [m.model_id]: e.target.value }))}
                                  min={1}
                                  max={20}
                                />
                                <button
                                  className="btn btn-primary text-xs"
                                  onClick={() => generateReport(m.model_id)}
                                  disabled={reportRunning[m.model_id]}
                                >
                                  {reportRunning[m.model_id] ? (
                                    <span className="flex items-center gap-1.5">
                                      <svg className="animate-spin h-3 w-3" viewBox="0 0 24 24" fill="none">
                                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
                                      </svg>
                                      {t('analytics.models.report.generating')}
                                    </span>
                                  ) : t('analytics.models.report.generate')}
                                </button>
                              </div>

                              {reportError[m.model_id] && (
                                <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-2 whitespace-pre-wrap">
                                  {reportError[m.model_id]}
                                </pre>
                              )}

                              {reportData[m.model_id] && (
                                <div className="space-y-2">
                                  {reportData[m.model_id].clusters.map(cluster => {
                                    const isOpen = openClusters[m.model_id]?.has(cluster.cluster_id) ?? false
                                    return (
                                      <div key={cluster.cluster_id} className="border border-slate-200 rounded bg-white">
                                        <button
                                          className="w-full flex items-center justify-between px-3 py-2 text-xs font-medium text-slate-700 hover:bg-slate-50 transition-colors"
                                          onClick={() => toggleCluster(m.model_id, cluster.cluster_id)}
                                        >
                                          <span>
                                            Cluster {cluster.cluster_id} — {cluster.n_articles} artigos
                                          </span>
                                          <span className="text-slate-400">{isOpen ? '▲' : '▼'}</span>
                                        </button>
                                        {isOpen && (
                                          <div className="px-3 pb-3 space-y-2 border-t border-slate-100">
                                            <p className="text-xs text-slate-500 mt-2">
                                              Artigos: {cluster.article_filenames.join(', ')}
                                            </p>
                                            {cluster.representative_chunks.map((ch, ci) => (
                                              <div key={ci} className="bg-slate-50 border border-slate-100 rounded p-2 space-y-1">
                                                <div className="flex items-center gap-2 text-xs">
                                                  <span className="font-mono text-lutz-700 truncate max-w-xs">{ch.filename}</span>
                                                  <span className="text-slate-400">·</span>
                                                  <span className="text-slate-500">{ch.section}</span>
                                                  <span className="text-slate-400">·</span>
                                                  <span className="font-mono text-slate-500">d={ch.distance_to_centroid.toFixed(4)}</span>
                                                </div>
                                                <p className="text-xs text-slate-600 line-clamp-3 leading-relaxed">{ch.text}</p>
                                              </div>
                                            ))}
                                          </div>
                                        )}
                                      </div>
                                    )
                                  })}
                                </div>
                              )}
                            </div>
                          </td>
                        </tr>
                      )}
                    </>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </CollapsibleSection>
    </div>
  )
}

// ── SQL tab ───────────────────────────────────────────────────────────────────

function SQLTab() {
  const { t } = useLanguage()
  const [udfs, setUdfs] = useState<UDFInfo[]>([])
  const [sql, setSql] = useState(EXAMPLES[0].sql)
  const [includeEmb, setIncludeEmb] = useState(true)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [running, setRunning] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    listUDFs()
      .then(d => setUdfs(d.udfs))
      .catch(() => {/* server may be offline */})
  }, [])

  const run = useCallback(async () => {
    if (!sql.trim() || running) return
    setRunning(true)
    setError(null)
    setResult(null)
    try {
      const r = await queryVectorStoreAnalytics(sql, includeEmb)
      if (r.error) setError(r.error)
      else setResult(r)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }, [sql, includeEmb, running])

  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      run()
    }
  }

  let scatterCoords: [number, number][] | null = null
  let scatterLabels: (string | number | null)[] = []
  let scatterNames: string[] = []

  if (result && result.rows.length > 0) {
    const arrCol = findArrayCol(result.columns, result.rows)
    if (arrCol >= 0) {
      const coords: [number, number][] = []
      for (const row of result.rows) {
        const arr = parseCell(row[arrCol])
        if (Array.isArray(arr) && arr.length >= 2) {
          coords.push([Number(arr[0]), Number(arr[1])])
        }
      }
      if (coords.length > 0) {
        scatterCoords = coords
        const lblCol = findLabelCol(result.columns)
        const nameCol = findNameCol(result.columns)
        scatterLabels = result.rows.map(row =>
          lblCol >= 0 ? (row[lblCol] as string | number | null) : null
        )
        scatterNames = result.rows.map(row =>
          nameCol >= 0 ? String(row[nameCol] ?? '') : ''
        )
      }
    }
  }

  const uniqueClusterLabels = scatterLabels.length > 0
    ? [...new Set(scatterLabels.map(String))]
    : []

  return (
    <div className="space-y-6">
      {/* UDF Palette */}
      {udfs.length > 0 && (
        <div className="card space-y-3">
          <h3 className="text-sm font-semibold text-slate-700">{t('analytics.palette.title')}</h3>
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2">
            {udfs.map(u => (
              <button
                key={u.name}
                onClick={() => setSql(s => s + (s === '' || s.endsWith('\n') ? '' : '\n') + u.name + '()')}
                className="text-left p-2 rounded border border-slate-200 hover:border-lutz-400 hover:bg-lutz-50 transition-colors group"
                title={u.description}
              >
                <div className="font-mono text-xs font-semibold text-lutz-600 group-hover:text-lutz-700 truncate">
                  {u.name}
                </div>
                <div className="text-xs text-slate-500 mt-0.5 line-clamp-2 leading-tight">
                  {u.description}
                </div>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* SQL Editor */}
      <CollapsibleSection title={t('analytics.sql.title')} storageKey="analytics_sql">
        <div className="card space-y-3">
          <div className="flex items-center justify-between gap-3 flex-wrap">
            <h3 className="text-sm font-semibold text-slate-700">{t('analytics.sql.title')}</h3>
            <div className="flex items-center gap-4 text-xs text-slate-500">
              <label className="flex items-center gap-1.5 cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={includeEmb}
                  onChange={e => setIncludeEmb(e.target.checked)}
                  className="rounded accent-lutz-500"
                />
                {t('analytics.sql.embeddings')}
              </label>
              <span className="hidden sm:inline text-slate-400">{t('store.sql.shortcut')}</span>
            </div>
          </div>

          <div className="flex flex-wrap gap-1.5">
            {EXAMPLES.map(ex => (
              <button
                key={ex.label}
                onClick={() => setSql(ex.sql)}
                className="text-xs px-2 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-600 transition-colors"
              >
                {ex.label}
              </button>
            ))}
          </div>

          <textarea
            className="input font-mono text-sm h-36 resize-y leading-relaxed"
            value={sql}
            onChange={e => setSql(e.target.value)}
            onKeyDown={onKeyDown}
            spellCheck={false}
          />

          <div className="flex items-center gap-3 flex-wrap">
            <button
              className="btn btn-primary text-sm"
              onClick={run}
              disabled={running || !sql.trim()}
            >
              {running ? t('analytics.sql.running') : t('store.sql.run')}
            </button>
            {result && !error && (
              <span className="text-xs text-slate-500">
                {result.count} {t('store.sql.rows')} &mdash; {result.elapsed_ms} ms
              </span>
            )}
          </div>

          {error && (
            <pre className="text-xs text-red-600 bg-red-50 border border-red-200 rounded p-3 whitespace-pre-wrap overflow-x-auto">
              {error}
            </pre>
          )}
        </div>
      </CollapsibleSection>

      {/* Scatter plot */}
      {scatterCoords && scatterCoords.length > 0 && (
        <CollapsibleSection title={t('analytics.viz.scatter')} storageKey="analytics_scatter">
          <div className="card space-y-3">
            <p className="text-xs text-slate-500 mt-0.5">{t('analytics.viz.scatter.hint')}</p>
            <ScatterPlot
              coords={scatterCoords}
              labels={scatterLabels}
              names={scatterNames}
            />
            {uniqueClusterLabels.length > 1 && (
              <div className="flex flex-wrap gap-3">
                {uniqueClusterLabels.slice(0, 10).map((l, i) => (
                  <span key={l} className="flex items-center gap-1.5 text-xs text-slate-600">
                    <span
                      className="w-3 h-3 rounded-full inline-block flex-shrink-0"
                      style={{ background: PALETTE[i % PALETTE.length] }}
                    />
                    cluster {l}
                  </span>
                ))}
              </div>
            )}
          </div>
        </CollapsibleSection>
      )}

      {/* Results table */}
      {result && result.rows.length > 0 && (
        <div className="card overflow-x-auto">
          <h3 className="text-sm font-semibold text-slate-700 mb-3">{t('analytics.results.title')}</h3>
          <table className="min-w-full text-xs">
            <thead>
              <tr className="bg-slate-800 text-white">
                {result.columns.map(col => (
                  <th key={col} className="px-3 py-2 text-left font-medium whitespace-nowrap">
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 500).map((row, i) => (
                <tr
                  key={i}
                  className={i % 2 === 0 ? 'bg-white' : 'bg-slate-50'}
                >
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className="px-3 py-1.5 border-b border-slate-100 font-mono text-slate-700 max-w-xs truncate"
                      title={displayCell(cell)}
                    >
                      {displayCell(cell)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          {result.rows.length > 500 && (
            <p className="text-xs text-slate-400 mt-2 px-1">
              Showing first 500 of {result.rows.length} rows.
            </p>
          )}
        </div>
      )}

      {result && result.rows.length === 0 && !error && (
        <div className="card text-slate-400 text-sm">{t('store.sql.noRows')}</div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Analytics() {
  const { t } = useLanguage()

  const [activeTab, setActiveTab] = useState<TabId>(() => {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'sql' || stored === 'dedup' || stored === 'rank' || stored === 'models') {
      return stored as TabId
    }
    return 'sql'
  })

  const switchTab = (tab: TabId) => {
    setActiveTab(tab)
    localStorage.setItem(STORAGE_KEY, tab)
  }

  const tabs: { id: TabId; label: string }[] = [
    { id: 'sql', label: t('analytics.tab.sql') },
    { id: 'dedup', label: t('analytics.tab.dedup') },
    { id: 'rank', label: t('analytics.tab.rank') },
    { id: 'models', label: t('analytics.tab.models') },
  ]

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">{t('analytics.title')}</h2>
        <p className="text-sm text-slate-500 mt-1">{t('analytics.desc')}</p>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-slate-200 gap-0">
        {tabs.map(tab => (
          <button
            key={tab.id}
            onClick={() => switchTab(tab.id)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              activeTab === tab.id
                ? 'border-lutz-600 text-lutz-700'
                : 'border-transparent text-slate-500 hover:text-slate-700 hover:border-slate-300'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {activeTab === 'sql' && <SQLTab />}
      {activeTab === 'dedup' && <DedupTab />}
      {activeTab === 'rank' && <RankTab />}
      {activeTab === 'models' && <ModelsTab />}
    </div>
  )
}
