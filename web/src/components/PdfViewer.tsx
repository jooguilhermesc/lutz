import { useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight } from 'lucide-react'
import * as pdfjs from 'pdfjs-dist'
import type { PDFDocumentProxy, RenderTask } from 'pdfjs-dist'
// Worker bundled with the app: the viewer works offline (never loaded from a CDN).
import workerUrl from 'pdfjs-dist/build/pdf.worker.min.mjs?url'
import { url } from '../api'
import { useApp } from '../app-context'

pdfjs.GlobalWorkerOptions.workerSrc = workerUrl

/** Renders one page of an article PDF (physical page numbering, 1..N). */
export function PdfViewer({ chave, pagina, onPagina, largura = 560 }: {
  chave: string; pagina: number; onPagina?: (n: number) => void; largura?: number
}) {
  const { tr } = useApp()
  const canvas = useRef<HTMLCanvasElement>(null)
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null)
  const [erro, setErro] = useState('')

  useEffect(() => {
    let vivo = true
    setDoc(null)
    setErro('')
    const tarefa = pdfjs.getDocument(url(`/artigos/${encodeURIComponent(chave)}/pdf`))
    tarefa.promise.then(
      (d) => vivo && setDoc(d),
      (e: Error) => vivo && setErro(e.message),
    )
    return () => {
      vivo = false
      tarefa.destroy()
    }
  }, [chave])

  useEffect(() => {
    if (!doc || !canvas.current) return
    let render: RenderTask | null = null
    let vivo = true
    const n = Math.min(Math.max(1, pagina), doc.numPages)
    doc.getPage(n).then((p) => {
      if (!vivo || !canvas.current) return
      const base = p.getViewport({ scale: 1 })
      const escala = (largura / base.width) * (window.devicePixelRatio || 1)
      const vp = p.getViewport({ scale: escala })
      const c = canvas.current
      c.width = vp.width
      c.height = vp.height
      c.style.width = `${largura}px`
      const ctx = c.getContext('2d')
      if (!ctx) return
      render = p.render({ canvasContext: ctx, viewport: vp })
      render.promise.catch(() => undefined)
    })
    return () => {
      vivo = false
      render?.cancel()
    }
  }, [doc, pagina, largura])

  if (erro) return <div className="err">{tr('Não foi possível abrir o PDF', 'Could not open the PDF')}: {erro}</div>
  const total = doc?.numPages ?? 0
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, minWidth: 0 }}>
      {onPagina ? (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <button className="btn btn-s btn-icon" disabled={pagina <= 1} onClick={() => onPagina(pagina - 1)}
            aria-label={tr('Página anterior', 'Previous page')}>
            <ChevronLeft size={14} />
          </button>
          <span className="mono small">
            {tr('pág.', 'p.')} {pagina} / {total || '…'}
          </span>
          <button className="btn btn-s btn-icon" disabled={!total || pagina >= total} onClick={() => onPagina(pagina + 1)}
            aria-label={tr('Próxima página', 'Next page')}>
            <ChevronRight size={14} />
          </button>
        </div>
      ) : null}
      <div className="pdfbox">
        <canvas ref={canvas} aria-label={`PDF ${chave} ${tr('página', 'page')} ${pagina}`} />
      </div>
    </div>
  )
}
