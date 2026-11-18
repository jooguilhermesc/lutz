import { useState } from 'react'
import { api, type ArtigoDetalhe, type Pagina } from '../api'
import { useApp } from '../app-context'
import { PdfViewer } from './PdfViewer'
import { Carregando, Destacar, Modal, Nota, useCarregar } from './ui'

/** Page text (what the extractors and the evidence check read) side by side with the PDF page. */
export function PageViewer({ chave, pagina: inicial = 1, trecho, unidades, onFechar }: {
  chave: string; pagina?: number; trecho?: string | null; unidades?: string[]; onFechar: () => void
}) {
  const { tr } = useApp()
  const [pagina, setPagina] = useState(inicial || 1)
  const [modo, setModo] = useState<'unidades' | 'texto'>('unidades')
  const art = useCarregar(() => api.get<ArtigoDetalhe>(`/artigos/${encodeURIComponent(chave)}`), [chave])
  const pag = useCarregar(() => api.get<Pagina>(`/artigos/${encodeURIComponent(chave)}/paginas/${pagina}`), [chave, pagina])
  const destaque = new Set(unidades ?? [])
  const info = art.dados?.paginas.find((p) => p.numero === pagina)
  return (
    <Modal titulo={art.dados?.titulo || chave} sub={`${chave} · ${tr('página física', 'physical page')} ${pagina}` +
      (info?.rotulo ? ` · ${tr('impressa', 'printed')} ${info.rotulo}` : '') + (info?.secao ? ` · ${info.secao}` : '')}
      onFechar={onFechar} largo>
      <div className="modal-b">
        {art.erro ? <Nota tipo="erro">{art.erro}</Nota> : null}
        <div className="row" style={{ alignItems: 'stretch' }}>
          <div className="grow" style={{ flex: '1 1 420px', display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className={`chipb${modo === 'unidades' ? ' on' : ''}`} onClick={() => setModo('unidades')}>
                {tr('Unidades citáveis', 'Citable units')}
              </button>
              <button className={`chipb${modo === 'texto' ? ' on' : ''}`} onClick={() => setModo('texto')}>
                {tr('Texto da página', 'Page text')}
              </button>
              <span className="faint small">{tr('Só texto visível: o texto oculto do PDF é descartado.', 'Visible text only: hidden PDF text is discarded.')}</span>
            </div>
            {pag.carregando && !pag.dados ? <Carregando /> : pag.erro ? <Nota tipo="erro">{pag.erro}</Nota> : pag.dados ? (
              modo === 'texto' ? (
                <div className="pagetext"><Destacar texto={pag.dados.texto} trecho={trecho} /></div>
              ) : (
                <div className="pagetext" style={{ whiteSpace: 'normal', padding: 6 }}>
                  {pag.dados.unidades.length === 0 ? <div className="faint">{tr('Sem unidades nesta página.', 'No units on this page.')}</div> : null}
                  {pag.dados.unidades.map((u) => (
                    <div key={u.uid} className={`unit${destaque.has(u.uid) ? ' hl' : ''}`}>
                      <span className="mono faint">{u.uid}</span>
                      <span>
                        {u.tipo === 'linha_tabela' ? <span className="tag tag-g" style={{ marginRight: 6 }}>{tr('tabela', 'table')}</span> : null}
                        <Destacar texto={u.texto} trecho={destaque.size ? null : trecho} />
                      </span>
                    </div>
                  ))}
                </div>
              )
            ) : null}
            {pag.dados?.texto_oculto ? (
              <Nota>{tr('Texto oculto descartado nesta página', 'Hidden text discarded on this page')}: <span className="mono small">{pag.dados.texto_oculto.slice(0, 300)}</span></Nota>
            ) : null}
          </div>
          <div style={{ flex: '1 1 420px', minWidth: 0 }}>
            <PdfViewer chave={chave} pagina={pagina} onPagina={setPagina} largura={480} />
          </div>
        </div>
      </div>
    </Modal>
  )
}
