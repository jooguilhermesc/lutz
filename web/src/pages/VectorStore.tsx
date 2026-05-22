import { useEffect, useMemo, useRef, useState } from 'react'
import {
  useReactTable, getCoreRowModel, getSortedRowModel, getFilteredRowModel,
  flexRender, type ColumnDef, type SortingState, type ColumnFiltersState,
} from '@tanstack/react-table'
import * as XLSX from 'xlsx'
import { getVectorStore, resetVectorStore, queryVectorStore, type VectorStoreInfo, type QueryResult } from '../api/client'
import { useLanguage } from '../contexts/LanguageContext'
import { LANG_LOCALES } from '../i18n'
import ConfirmDialog from '../components/ConfirmDialog'

function fmtDate(s: string | null, locale: string) {
  if (!s) return '—'
  try { return new Date(s).toLocaleString(locale) } catch { return s }
}

// ── SQL panel ─────────────────────────────────────────────────────────────────

const EXAMPLE_QUERIES = [
  { label: 'Contar chunks por arquivo', sql: 'SELECT filename, COUNT(*) AS chunks\nFROM vectors\nGROUP BY filename\nORDER BY chunks DESC' },
  { label: 'Ver schema', sql: 'DESCRIBE vectors' },
  { label: 'Buscar texto', sql: "SELECT filename, page, text\nFROM vectors\nWHERE text ILIKE '%machine learning%'\nLIMIT 20" },
  { label: 'Arquivos únicos', sql: 'SELECT DISTINCT filename\nFROM vectors\nORDER BY filename' },
  { label: 'Chunks recentes', sql: 'SELECT filename, chunk_index, vectorized_at\nFROM vectors\nORDER BY vectorized_at DESC\nLIMIT 20' },
]

// ── Interactive results table ─────────────────────────────────────────────────

type Row = Record<string, string | number | boolean | null | unknown[]>

function ResultsTable({ columns, rows }: { columns: string[]; rows: (string | number | boolean | null | unknown[])[][] }) {
  const { t } = useLanguage()
  const [sorting, setSorting] = useState<SortingState>([])
  const [columnFilters, setColumnFilters] = useState<ColumnFiltersState>([])
  const [globalFilter, setGlobalFilter] = useState('')

  const data = useMemo<Row[]>(
    () => rows.map((r) => Object.fromEntries(columns.map((c, i) => [c, r[i]]))),
    [rows, columns],
  )

  const colDefs = useMemo<ColumnDef<Row>[]>(
    () => columns.map((col) => ({
      accessorKey: col,
      header: col,
      cell: ({ getValue }) => {
        const v = getValue()
        if (v === null || v === undefined) return <span className="text-slate-300 italic">NULL</span>
        const s = String(v)
        return <span title={s}>{s}</span>
      },
      filterFn: 'includesString',
    })),
    [columns],
  )

  const table = useReactTable({
    data,
    columns: colDefs,
    state: { sorting, columnFilters, globalFilter },
    onSortingChange: setSorting,
    onColumnFiltersChange: setColumnFilters,
    onGlobalFilterChange: setGlobalFilter,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
    getFilteredRowModel: getFilteredRowModel(),
  })

  function exportCsv() {
    const visibleRows = table.getFilteredRowModel().rows
    const lines = [
      columns.join(','),
      ...visibleRows.map((r) =>
        columns.map((c) => {
          const v = r.getValue(c)
          const s = v === null || v === undefined ? '' : String(v)
          return s.includes(',') || s.includes('"') || s.includes('\n')
            ? `"${s.replace(/"/g, '""')}"` : s
        }).join(',')
      ),
    ]
    const blob = new Blob([lines.join('\n')], { type: 'text/csv' })
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob)
    a.download = 'query_result.csv'; a.click()
  }

  function exportXlsx() {
    const visibleRows = table.getFilteredRowModel().rows
    const wsData = [
      columns,
      ...visibleRows.map((r) => columns.map((c) => r.getValue(c) ?? '')),
    ]
    const ws = XLSX.utils.aoa_to_sheet(wsData)
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, 'Resultado')
    XLSX.writeFile(wb, 'query_result.xlsx')
  }

  const filtered = table.getFilteredRowModel().rows.length

  return (
    <div className="space-y-3">
      {/* Toolbar */}
      <div className="flex items-center gap-2 flex-wrap">
        <input
          className="input text-xs flex-1 min-w-[180px]"
          placeholder={t('store.sql.filter.global')}
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
        />
        <span className="text-xs text-slate-400 whitespace-nowrap">
          {filtered} / {rows.length} {t('store.sql.rows')}
        </span>
        <button className="btn-ghost text-xs" onClick={exportCsv}>⬇ CSV</button>
        <button className="btn-ghost text-xs" onClick={exportXlsx}>⬇ XLSX</button>
      </div>

      {/* Table */}
      <div className="overflow-auto max-h-[480px] rounded-xl border border-slate-200">
        <table className="w-full text-xs font-mono border-collapse">
          <thead className="bg-slate-800 text-slate-200 sticky top-0 z-10">
            <tr>
              {table.getHeaderGroups()[0].headers.map((header) => (
                <th key={header.id} className="text-left px-3 py-2 whitespace-nowrap font-semibold select-none">
                  <div
                    className="flex items-center gap-1 cursor-pointer hover:text-white"
                    onClick={header.column.getToggleSortingHandler()}
                    title="Clique para ordenar"
                  >
                    {flexRender(header.column.columnDef.header, header.getContext())}
                    {header.column.getIsSorted() === 'asc' && <span>↑</span>}
                    {header.column.getIsSorted() === 'desc' && <span>↓</span>}
                    {!header.column.getIsSorted() && <span className="opacity-30">↕</span>}
                  </div>
                  {/* Per-column filter */}
                  <input
                    className="mt-1 w-full bg-slate-700 text-slate-200 placeholder-slate-500 rounded px-1.5 py-0.5 text-[10px] focus:outline-none focus:ring-1 focus:ring-lutz-400"
                    placeholder="filtrar…"
                    value={(header.column.getFilterValue() as string) ?? ''}
                    onChange={(e) => header.column.setFilterValue(e.target.value || undefined)}
                    onClick={(e) => e.stopPropagation()}
                  />
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row, i) => (
              <tr key={row.id} className={`border-t border-slate-100 hover:bg-lutz-50 transition-colors ${i % 2 === 0 ? '' : 'bg-slate-50'}`}>
                {row.getVisibleCells().map((cell) => (
                  <td
                    key={cell.id}
                    className="px-3 py-1.5 text-slate-700 max-w-[300px] truncate align-top"
                    title={String(cell.getValue() ?? '')}
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                ))}
              </tr>
            ))}
            {table.getRowModel().rows.length === 0 && (
              <tr><td colSpan={columns.length} className="text-center text-slate-400 py-8">{t('store.sql.noRows')}</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── SQL panel ─────────────────────────────────────────────────────────────────

function SqlPanel() {
  const { t } = useLanguage()
  const [sql, setSql] = useState(EXAMPLE_QUERIES[0].sql)
  const [result, setResult] = useState<QueryResult | null>(null)
  const [running, setRunning] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  async function handleRun() {
    if (!sql.trim() || running) return
    setRunning(true)
    try {
      const r = await queryVectorStore(sql)
      setResult(r)
    } catch (e) {
      setResult({ columns: [], rows: [], count: 0, elapsed_ms: 0, error: (e as Error).message })
    } finally {
      setRunning(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') { e.preventDefault(); handleRun() }
    if (e.key === 'Tab') {
      e.preventDefault()
      const el = textareaRef.current!
      const { selectionStart: s, selectionEnd: end } = el
      const next = sql.slice(0, s) + '  ' + sql.slice(end)
      setSql(next)
      requestAnimationFrame(() => { el.selectionStart = el.selectionEnd = s + 2 })
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-semibold text-slate-700">{t('store.sql.title')}</h3>
        <span className="text-xs text-slate-400">{t('store.sql.table')}</span>
      </div>

      {/* Example queries */}
      <div className="flex flex-wrap gap-2">
        {EXAMPLE_QUERIES.map((q) => (
          <button
            key={q.label}
            className="text-xs px-2.5 py-1 rounded-full border border-slate-200 bg-white text-slate-600 hover:border-lutz-400 hover:text-lutz-600 transition-colors"
            onClick={() => setSql(q.sql)}
          >
            {q.label}
          </button>
        ))}
      </div>

      {/* Editor */}
      <div className="relative">
        <textarea
          ref={textareaRef}
          className="w-full font-mono text-sm rounded-xl border border-slate-200 bg-slate-50 p-4 focus:outline-none focus:ring-2 focus:ring-lutz-400 resize-y min-h-[120px]"
          spellCheck={false}
          value={sql}
          onChange={(e) => setSql(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="SELECT * FROM vectors LIMIT 10"
        />
        <div className="absolute bottom-3 right-3 flex items-center gap-2">
          <span className="text-[10px] text-slate-400">{t('store.sql.shortcut')}</span>
          <button
            className="btn-primary text-xs px-3 py-1"
            onClick={handleRun}
            disabled={running || !sql.trim()}
          >
            {running ? '...' : t('store.sql.run')}
          </button>
        </div>
      </div>

      {/* Results */}
      {result && (
        <div className="space-y-2">
          {result.error ? (
            <div className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-xl px-4 py-3 font-mono">
              {result.error}
            </div>
          ) : (
            <>
              <div className="text-xs text-slate-400">{result.elapsed_ms} ms</div>
              {result.columns.length > 0 && (
                <ResultsTable columns={result.columns} rows={result.rows} />
              )}
              {result.columns.length === 0 && (
                <p className="text-center text-slate-400 py-6 text-xs">{t('store.sql.noRows')}</p>
              )}
            </>
          )}
        </div>
      )}
    </div>
  )
}

export default function VectorStore() {
  const { t, lang } = useLanguage()
  const locale = LANG_LOCALES[lang]
  const [info, setInfo] = useState<VectorStoreInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [resetting, setResetting] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)

  const load = () => {
    setLoading(true)
    getVectorStore().then(setInfo).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleReset() {
    setResetting(true)
    await resetVectorStore()
    await load()
    setResetting(false)
  }

  if (loading) return <div className="text-slate-400 animate-pulse text-sm">{t('store.loading')}</div>
  if (!info) return <div className="text-red-500 text-sm">{t('store.error')}</div>

  const empty = info.total_records === 0

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-bold text-slate-800">{t('store.title')}</h2>

      {confirmReset && (
        <ConfirmDialog
          title={t('store.confirm.reset.title')}
          body={t('store.confirm.reset.body')}
          confirmLabel={t('store.danger.reset')}
          danger
          onCancel={() => setConfirmReset(false)}
          onConfirm={() => { setConfirmReset(false); handleReset() }}
        />
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: t('store.metric.chunks'),   value: info.total_records.toLocaleString(locale) },
          { label: t('store.metric.articles'), value: info.unique_documents },
          { label: t('store.metric.model'),    value: info.embedding_model ?? '—' },
          { label: t('store.metric.updated'),  value: fmtDate(info.last_updated, locale) },
        ].map(({ label, value }) => (
          <div key={label} className="card text-center">
            <div className="text-xl font-bold text-slate-800 break-all">{value}</div>
            <div className="text-xs text-slate-500 uppercase tracking-wide mt-1">{label}</div>
          </div>
        ))}
      </div>

      {empty ? (
        <div className="text-slate-400 text-sm py-8 text-center">{t('store.empty')}</div>
      ) : (
        <div className="card p-0 overflow-hidden">
          <div className="px-4 py-3 border-b border-slate-100 text-sm font-semibold text-slate-700">
            {t('store.table.title')}
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-xs text-slate-500 uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-2">{t('store.col.file')}</th>
                  <th className="text-right px-4 py-2">{t('store.col.chunks')}</th>
                  <th className="text-left px-4 py-2">{t('store.col.vectorized')}</th>
                  <th className="text-left px-4 py-2">{t('store.col.model')}</th>
                </tr>
              </thead>
              <tbody>
                {info.articles.map((a) => (
                  <tr key={a.filename} className="border-t border-slate-100 hover:bg-slate-50">
                    <td className="px-4 py-2 font-medium text-slate-700 break-all">{a.filename}</td>
                    <td className="px-4 py-2 text-right text-slate-500">{a.chunk_count}</td>
                    <td className="px-4 py-2 text-slate-400 whitespace-nowrap text-xs">{fmtDate(a.vectorized_at, locale)}</td>
                    <td className="px-4 py-2 text-slate-400 text-xs">{a.embedding_model}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card space-y-4">
        <SqlPanel />
      </div>

      <div className="border border-red-200 rounded-xl p-4 bg-red-50 space-y-2">
        <p className="text-sm font-semibold text-red-700">{t('store.danger.title')}</p>
        <p className="text-xs text-red-500">{t('store.danger.desc')}</p>
        <button className="btn-danger text-xs" onClick={() => setConfirmReset(true)} disabled={resetting || empty}>
          {resetting ? t('store.danger.resetting') : t('store.danger.reset')}
        </button>
      </div>
    </div>
  )
}
