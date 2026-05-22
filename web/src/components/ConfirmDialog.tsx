import { useLanguage } from '../contexts/LanguageContext'

export default function ConfirmDialog({
  title, body, confirmLabel, onConfirm, onCancel, danger = false,
}: {
  title: string
  body?: string
  confirmLabel: string
  onConfirm: () => void
  onCancel: () => void
  danger?: boolean
}) {
  const { t } = useLanguage()
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onCancel} />
      <div className="relative bg-white rounded-2xl shadow-xl p-6 w-full max-w-sm mx-4 space-y-4">
        <h3 className="text-base font-semibold text-slate-800">{title}</h3>
        {body && <p className="text-sm text-slate-500">{body}</p>}
        <div className="flex justify-end gap-2 pt-1">
          <button className="btn-ghost text-sm px-4" onClick={onCancel}>
            {t('dialog.cancel')}
          </button>
          <button
            className={`text-sm px-4 py-1.5 rounded-lg font-medium transition-colors ${
              danger
                ? 'bg-red-500 hover:bg-red-600 text-white'
                : 'bg-lutz-500 hover:bg-lutz-600 text-white'
            }`}
            onClick={onConfirm}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
