import { useEffect, useState } from 'react'
import {
  Folder, FlaskConical, Star, Bookmark, Microscope, Brain,
  FileText, Layers, Database, Heart, Globe, Zap,
  Pencil, Trash2, Plus, X, Check,
  type LucideIcon,
} from 'lucide-react'
import {
  listProjects, createProject, updateProject, deleteProject,
  type Project,
} from '../api/client'

// ── Icon map ──────────────────────────────────────────────────────────────────

const ICON_MAP: Record<string, LucideIcon> = {
  'folder': Folder,
  'flask-conical': FlaskConical,
  'star': Star,
  'bookmark': Bookmark,
  'microscope': Microscope,
  'brain': Brain,
  'file-text': FileText,
  'layers': Layers,
  'database': Database,
  'heart': Heart,
  'globe': Globe,
  'zap': Zap,
}

const ICON_KEYS = Object.keys(ICON_MAP)

const COLOR_PALETTE = [
  '#6366f1', '#8b5cf6', '#ec4899', '#ef4444', '#f97316', '#eab308',
  '#22c55e', '#10b981', '#06b6d4', '#3b82f6', '#64748b', '#1e293b',
]

// ── Project icon renderer ─────────────────────────────────────────────────────

function ProjectIcon({ icon, color, size = 20 }: { icon: string; color: string; size?: number }) {
  const IconComp: LucideIcon = ICON_MAP[icon] ?? Folder
  return <IconComp size={size} color={color} />
}

// ── Project modal (create / edit) ─────────────────────────────────────────────

interface ProjectModalProps {
  initial?: Project | null
  onClose: () => void
  onSave: (data: { name: string; color: string; icon: string }) => Promise<void>
}

function ProjectModal({ initial, onClose, onSave }: ProjectModalProps) {
  const [name, setName] = useState(initial?.name ?? '')
  const [color, setColor] = useState(initial?.color ?? COLOR_PALETTE[0])
  const [icon, setIcon] = useState(initial?.icon ?? 'folder')
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) { setError('Nome é obrigatório'); return }
    setSaving(true)
    try {
      await onSave({ name: name.trim(), color, icon })
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Erro ao salvar')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-md mx-4 space-y-5">
        <div className="flex items-center justify-between">
          <h3 className="text-base font-semibold text-slate-800">
            {initial ? 'Editar projeto' : 'Novo projeto'}
          </h3>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-600 transition-colors">
            <X size={16} />
          </button>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Name */}
          <div className="space-y-1">
            <label className="text-xs font-medium text-slate-600">Nome</label>
            <input
              type="text"
              value={name}
              onChange={(e) => { setName(e.target.value); setError('') }}
              placeholder="Ex: Revisão sobre NLP"
              className="w-full border border-slate-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-300"
              autoFocus
            />
            {error && <p className="text-xs text-red-500">{error}</p>}
          </div>

          {/* Color */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-600">Cor</label>
            <div className="flex flex-wrap gap-2">
              {COLOR_PALETTE.map((c) => (
                <button
                  key={c}
                  type="button"
                  onClick={() => setColor(c)}
                  className="w-7 h-7 rounded-full transition-transform hover:scale-110 flex items-center justify-center"
                  style={{ backgroundColor: c }}
                  title={c}
                >
                  {color === c && <Check size={12} className="text-white drop-shadow" />}
                </button>
              ))}
            </div>
          </div>

          {/* Icon */}
          <div className="space-y-2">
            <label className="text-xs font-medium text-slate-600">Ícone</label>
            <div className="flex flex-wrap gap-2">
              {ICON_KEYS.map((key) => {
                const IconComp = ICON_MAP[key]!
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setIcon(key)}
                    title={key}
                    className={`w-9 h-9 rounded-lg flex items-center justify-center transition-colors border ${
                      icon === key
                        ? 'border-transparent ring-2 ring-offset-1'
                        : 'border-slate-200 bg-slate-50 hover:bg-slate-100 text-slate-500'
                    }`}
                    style={icon === key ? { backgroundColor: color + '22' } : undefined}
                  >
                    <IconComp size={16} color={icon === key ? color : undefined} />
                  </button>
                )
              })}
            </div>
          </div>

          {/* Preview */}
          <div className="flex items-center gap-3 p-3 rounded-xl border border-slate-100 bg-slate-50">
            <div
              className="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0"
              style={{ backgroundColor: color + '22' }}
            >
              <ProjectIcon icon={icon} color={color} size={20} />
            </div>
            <span className="text-sm font-medium text-slate-700">{name || 'Nome do projeto'}</span>
          </div>

          {/* Actions */}
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={onClose} className="btn-ghost text-sm px-4">
              Cancelar
            </button>
            <button
              type="submit"
              disabled={saving}
              className="text-sm px-4 py-1.5 rounded-lg font-medium bg-indigo-500 hover:bg-indigo-600 text-white transition-colors disabled:opacity-60"
            >
              {saving ? 'Salvando...' : 'Salvar'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Confirm delete dialog ─────────────────────────────────────────────────────

function ConfirmDeleteDialog({ name, onCancel, onConfirm }: { name: string; onCancel: () => void; onConfirm: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4">
        <h3 className="text-base font-semibold text-slate-800">Excluir projeto</h3>
        <p className="text-sm text-slate-500">
          O projeto <strong>"{name}"</strong> será excluído permanentemente. Datasets associados não serão removidos.
        </p>
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost text-sm px-4" onClick={onCancel}>Cancelar</button>
          <button
            className="text-sm px-4 py-1.5 rounded-lg font-medium bg-red-500 hover:bg-red-600 text-white transition-colors"
            onClick={onConfirm}
          >
            Excluir
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Project card ──────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  onEdit,
  onDelete,
}: {
  project: Project
  onEdit: (p: Project) => void
  onDelete: (p: Project) => void
}) {
  const createdAt = new Date(project.created_at).toLocaleDateString('pt-BR', {
    day: '2-digit', month: 'short', year: 'numeric',
  })

  return (
    <div className="card group relative hover:shadow-md transition-shadow">
      <div className="flex items-start gap-3">
        <div
          className="w-11 h-11 rounded-xl flex items-center justify-center flex-shrink-0 mt-0.5"
          style={{ backgroundColor: project.color + '22' }}
        >
          <ProjectIcon icon={project.icon} color={project.color} size={22} />
        </div>
        <div className="flex-1 min-w-0">
          <p className="font-semibold text-slate-800 text-sm truncate">{project.name}</p>
          <div className="flex items-center gap-3 mt-1 text-xs text-slate-400">
            <span>{project.article_count} artigos</span>
            <span>{project.dataset_count} datasets</span>
            <span>{createdAt}</span>
          </div>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0">
          <button
            onClick={() => onEdit(project)}
            title="Editar"
            className="p-1.5 rounded-lg hover:bg-slate-100 text-slate-400 hover:text-slate-700 transition-colors"
          >
            <Pencil size={14} />
          </button>
          <button
            onClick={() => onDelete(project)}
            title="Excluir"
            className="p-1.5 rounded-lg hover:bg-red-50 text-slate-400 hover:text-red-500 transition-colors"
          >
            <Trash2 size={14} />
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onCreate }: { onCreate: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-20 gap-4 text-center">
      <div className="w-16 h-16 rounded-2xl bg-indigo-50 flex items-center justify-center">
        <Folder size={32} className="text-indigo-400" />
      </div>
      <div>
        <p className="text-slate-700 font-medium">Nenhum projeto ainda</p>
        <p className="text-slate-400 text-sm mt-1">Crie um projeto para organizar suas análises e datasets.</p>
      </div>
      <button
        onClick={onCreate}
        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors"
      >
        <Plus size={16} />
        Novo projeto
      </button>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function Projects() {
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState<Project | null>(null)
  const [deleting, setDeleting] = useState<Project | null>(null)

  const load = () => {
    setLoading(true)
    listProjects().then((r) => setProjects(r.projects ?? [])).finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  async function handleSave(data: { name: string; color: string; icon: string }) {
    if (editing) {
      await updateProject(editing.id, data)
    } else {
      await createProject(data)
    }
    load()
  }

  async function handleDelete() {
    if (!deleting) return
    await deleteProject(deleting.id)
    setDeleting(null)
    load()
  }

  function openCreate() {
    setEditing(null)
    setShowModal(true)
  }

  function openEdit(p: Project) {
    setEditing(p)
    setShowModal(true)
  }

  return (
    <div className="space-y-6">
      {showModal && (
        <ProjectModal
          initial={editing}
          onClose={() => { setShowModal(false); setEditing(null) }}
          onSave={handleSave}
        />
      )}
      {deleting && (
        <ConfirmDeleteDialog
          name={deleting.name}
          onCancel={() => setDeleting(null)}
          onConfirm={handleDelete}
        />
      )}

      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-xl font-bold text-slate-800">Projetos</h2>
        <div className="flex items-center gap-2">
          <button className="btn-ghost text-xs" onClick={load}>↺ atualizar</button>
          <button
            onClick={openCreate}
            className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500 hover:bg-indigo-600 text-white text-sm font-medium transition-colors"
          >
            <Plus size={14} />
            Novo projeto
          </button>
        </div>
      </div>

      {loading && <div className="text-slate-400 animate-pulse text-sm">Carregando...</div>}

      {!loading && projects.length === 0 && (
        <EmptyState onCreate={openCreate} />
      )}

      {!loading && projects.length > 0 && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {projects.map((p) => (
            <ProjectCard
              key={p.id}
              project={p}
              onEdit={openEdit}
              onDelete={setDeleting}
            />
          ))}
        </div>
      )}
    </div>
  )
}
