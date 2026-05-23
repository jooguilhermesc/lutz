import { useState, useEffect, useCallback, KeyboardEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import { useLanguage } from '../contexts/LanguageContext'
import {
  queryVectorStoreAnalytics,
  listUDFs,
  type UDFInfo,
  type QueryResult,
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

// ── Helpers ───────────────────────────────────────────────────────────────────

function parseCell(v: unknown): unknown {
  if (Array.isArray(v)) return v
  if (typeof v === 'string' && v.startsWith('[')) {
    try { return JSON.parse(v) } catch { /* fall through */ }
  }
  return v
}

/** Find the first column whose first row value is a 2-element array. */
function findArrayCol(columns: string[], rows: unknown[][]): number {
  for (let c = 0; c < columns.length; c++) {
    const cell = parseCell(rows[0]?.[c])
    if (Array.isArray(cell) && cell.length >= 2) return c
  }
  return -1
}

/** Find the first column whose name looks like a cluster/label column. */
function findLabelCol(columns: string[]): number {
  const patterns = ['cluster', 'label', 'kmeans', 'dbscan', 'group']
  for (let c = 0; c < columns.length; c++) {
    if (patterns.some(p => columns[c].toLowerCase().includes(p))) return c
  }
  return -1
}

/** Find the first column whose name looks like a file/document identifier. */
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
]

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Analytics() {
  const { t } = useLanguage()
  const navigate = useNavigate()

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

  // ── Derive visualization data ──────────────────────────────────────────────
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
      {/* Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-800">{t('analytics.title')}</h2>
        <p className="text-sm text-slate-500 mt-1">{t('analytics.desc')}</p>
      </div>

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

        {/* Example snippets */}
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
            <>
              <span className="text-xs text-slate-500">
                {result.count} {t('store.sql.rows')} &mdash; {result.elapsed_ms} ms
              </span>
              <button
                className="btn-ghost text-xs text-lutz-600 border-lutz-200 hover:bg-lutz-50"
                onClick={() => {
                  const activeExample = EXAMPLES.find(e => e.sql === sql)
                  const analysisType = activeExample?.label ?? 'Analytics'
                  navigate('/chat', {
                    state: {
                      datasetContext: {
                        name: `Análise: ${analysisType}`,
                        source: 'analytics',
                        columns: result.columns,
                        rows: result.rows,
                        row_count: result.count,
                      },
                    },
                  })
                }}
              >
                Analisar no chat
              </button>
            </>
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
          <div>
            <p className="text-xs text-slate-500 mt-0.5">{t('analytics.viz.scatter.hint')}</p>
          </div>

          <ScatterPlot
            coords={scatterCoords}
            labels={scatterLabels}
            names={scatterNames}
          />

          {/* Colour legend */}
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
