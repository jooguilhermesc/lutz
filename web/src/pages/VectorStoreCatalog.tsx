import { useEffect, useState } from 'react'
import { fetchStoreCatalog, type CatalogTable } from '../api/client'
import CollapsibleSection from '../components/CollapsibleSection'

interface VectorStoreCatalogProps {
  onUseInQuery: (sql: string) => void
}

const mockCatalog = {
  tables: [
    {
      name: 'articles',
      description: 'Chunks de artigos científicos vetorizados',
      record_count: 0,
      last_updated: null,
      columns: [
        { name: 'filename', type: 'string', description: 'Nome do arquivo PDF' },
        { name: 'chunk_index', type: 'int32', description: 'Índice do chunk no documento' },
        { name: 'page', type: 'int32', description: 'Página do PDF' },
        { name: 'char_start', type: 'int32', description: 'Posição do caractere inicial' },
        { name: 'section', type: 'string', description: 'Seção do documento' },
        { name: 'text', type: 'string', description: 'Conteúdo textual do chunk' },
        { name: 'embedding', type: 'float32[1536]', description: 'Vetor de embedding' },
        { name: 'vectorized_at', type: 'string', description: 'Timestamp de vetorização' },
        { name: 'embedding_model', type: 'string', description: 'Modelo de embedding usado' },
        { name: 'embedding_provider', type: 'string', description: 'Provedor de embedding' },
        { name: 'extraction_backend', type: 'string', description: 'Backend de extração PDF' },
      ],
    },
  ],
}

function TypeBadge({ type }: { type: string }) {
  const isVector = type.startsWith('float32[')
  const isInt = type.startsWith('int')
  return (
    <span
      className={`text-[10px] px-1.5 py-0.5 rounded font-mono font-medium ${
        isVector
          ? 'bg-violet-100 text-violet-700'
          : isInt
          ? 'bg-blue-100 text-blue-700'
          : 'bg-slate-100 text-slate-600'
      }`}
    >
      {type}
    </span>
  )
}

function TableCard({ table, onUseInQuery }: { table: CatalogTable; onUseInQuery: (sql: string) => void }) {
  const fmtDate = (s: string | null) => {
    if (!s) return '—'
    try { return new Date(s).toLocaleString() } catch { return s }
  }

  return (
    <div className="card space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-mono text-sm font-bold text-slate-800">{table.name}</span>
            <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-lutz-100 text-lutz-700 font-medium">
              {table.record_count.toLocaleString()} registros
            </span>
          </div>
          {table.description && (
            <p className="text-xs text-slate-500 mt-0.5">{table.description}</p>
          )}
          <p className="text-[10px] text-slate-400 mt-1">Atualizado: {fmtDate(table.last_updated)}</p>
        </div>
        <button
          className="btn-ghost text-xs flex-shrink-0"
          onClick={() => onUseInQuery(`SELECT * FROM ${table.name} LIMIT 10`)}
          title="Usar no Query"
        >
          Usar no Query
        </button>
      </div>

      <CollapsibleSection title={`Colunas (${table.columns.length})`} storageKey={`catalog_table_${table.name}`}>
        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-slate-50 text-slate-500 uppercase tracking-wide text-[10px]">
                <th className="text-left px-3 py-2 font-medium">Nome</th>
                <th className="text-left px-3 py-2 font-medium">Tipo</th>
                <th className="text-left px-3 py-2 font-medium">Descrição</th>
              </tr>
            </thead>
            <tbody>
              {table.columns.map((col) => (
                <tr key={col.name} className="border-t border-slate-100 hover:bg-slate-50">
                  <td className="px-3 py-2 font-mono font-medium text-slate-700">{col.name}</td>
                  <td className="px-3 py-2">
                    <TypeBadge type={col.type} />
                  </td>
                  <td className="px-3 py-2 text-slate-400">{col.description ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CollapsibleSection>
    </div>
  )
}

export default function VectorStoreCatalog({ onUseInQuery }: VectorStoreCatalogProps) {
  const [tables, setTables] = useState<CatalogTable[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    fetchStoreCatalog()
      .then((data) => {
        setTables(data.tables)
        setError(null)
      })
      .catch(() => {
        // Fall back to mock data when backend endpoint is not available
        setTables(mockCatalog.tables)
        setError(null)
      })
      .finally(() => setLoading(false))
  }, [])

  if (loading) {
    return <div className="text-slate-400 animate-pulse text-sm py-8 text-center">Carregando catálogo...</div>
  }

  if (error) {
    return <div className="text-red-500 text-sm py-8 text-center">{error}</div>
  }

  if (tables.length === 0) {
    return (
      <div className="text-slate-400 text-sm py-12 text-center">
        <p className="text-base font-medium mb-1">Catálogo vazio</p>
        <p className="text-xs">Nenhuma tabela encontrada no vector store.</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <p className="text-xs text-slate-500">
        {tables.length} tabela{tables.length !== 1 ? 's' : ''} encontrada{tables.length !== 1 ? 's' : ''}
      </p>
      {tables.map((table) => (
        <TableCard key={table.name} table={table} onUseInQuery={onUseInQuery} />
      ))}
    </div>
  )
}
