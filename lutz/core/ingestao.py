"""PDF ingestion: page text, reading order, addressable units, sections and quality signals.

Decisions (see docs/spec-1.0.md, "Ingestão"):

* Only VISIBLE text is kept. A span is hidden when its render mode is invisible (3) and it is
  not an OCR layer over an image, when its opacity is 0, its size is below 4 pt, its colour
  is near white, or it lies outside the page. Hidden text is stored apart for the report and
  never reaches the extractors nor the evidence check.
* Reading order: text blocks are ordered by column when a page has two columns. The original
  block order is stored too; the evidence check accepts a match in either order.
* Units: every sentence and every table row gets a stable id (``p4.s17``, ``p4.t1.r3``) that the
  extractors cite. Table rows carry the column headers, so numbers in tables have context.
* Pages are numbered physically (1..N). The printed page label is stored when available.
* A PDF without a text layer becomes ``sem_texto`` and is blocked from extraction (no OCR).
"""

from __future__ import annotations

import hashlib
import re
import shutil
import sqlite3
import unicodedata
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

import pymupdf

from lutz.core.db import agora, jdump, transacao
from lutz.core.project import Projeto
from lutz.core.texto import estimar_tokens

MIN_CHARS_ARTIGO = 300
MIN_CHARS_POR_PAGINA = 80

_SECOES = {
    "resumo": r"abstract|resumo|resumen|summary",
    "introducao": r"introduction|introdu[cç][aã]o|introducci[oó]n|background|contexto",
    "metodos": r"methods?|methodology|materials?\s+and\s+methods?|m[eé]todos?|metodologia|"
               r"materiais\s+e\s+m[eé]todos|materiales\s+y\s+m[eé]todos|study\s+design|"
               r"participants|procedures?|experimental\s+(?:setup|design|settings?)|data\s+collection|"
               r"approach|proposed\s+method",
    "resultados": r"results?|resultados?|findings|experiments?|evaluation(?:\s+results)?|"
                  r"experimental\s+results|avalia[cç][aã]o",
    "discussao": r"discussion|discuss[aã]o|discusi[oó]n",
    "conclusao": r"conclusions?|conclus[aã]o|conclus[oõ]es|conclusiones?|concluding\s+remarks",
    "limitacoes": r"limitations?|limita[cç][oõ]es|limitaciones",
    "referencias": r"references|refer[eê]ncias|bibliography|bibliograf[ií]a|referencias",
    "agradecimentos": r"acknowledg(e)?ments?|agradecimentos|agradecimientos",
    "apendice": r"appendix|appendices|ap[eê]ndices?|supplementary(?:\s+materials?)?|material\s+suplementar",
}


def secao_canonica(nome: str) -> str | None:
    """Map a heading ('2. Materials and Methods', 'Métodos') to a canonical section id."""
    s = nome.strip()
    for canon, padrao in _SECOES.items():
        if re.fullmatch(r"(?:(?:\d+|[ivxlc]+)[.)]?\s*)?(?:" + padrao + r")\s*[:.]?", s, re.IGNORECASE):
            return canon
    return None


_FRASE = re.compile(r"(?<=[.!?])\s+(?=[\"'“(\[]?[A-ZÀ-Ý0-9])")


@dataclass
class _Bloco:
    bbox: tuple[float, float, float, float]
    texto: str
    tamanho: float = 0.0


@dataclass
class _Pagina:
    numero: int
    rotulo: str
    texto: str
    texto_bruto: str
    oculto: str
    frac_oculto: float
    duas_colunas: bool
    unidades: list[dict] = field(default_factory=list)


@dataclass
class ResultadoImportacao:
    caminho: str
    status: str  # importado | duplicado | sem_texto | erro
    chave: str | None = None
    mensagem: str = ""


def sha256_arquivo(caminho: Path) -> str:
    h = hashlib.sha256()
    with open(caminho, "rb") as fh:
        for bloco in iter(lambda: fh.read(1 << 20), b""):
            h.update(bloco)
    return h.hexdigest()


def _slug(txt: str) -> str:
    t = unicodedata.normalize("NFKD", txt)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", t)


def _juntar_hifen(linhas: list[str]) -> str:
    texto = ""
    for linha in linhas:
        linha = linha.strip()
        if not linha:
            continue
        if texto.endswith(("-", "­")) and linha[:1].islower():
            texto = texto.rstrip("-­") + linha
        elif texto:
            texto += " " + linha
        else:
            texto = linha
    return texto


def _bbox_dentro(a, b, folga: float = 1.5) -> bool:
    cx, cy = (a[0] + a[2]) / 2, (a[1] + a[3]) / 2
    return b[0] - folga <= cx <= b[2] + folga and b[1] - folga <= cy <= b[3] + folga


def _quase_branco(cor) -> bool:
    if cor is None:
        return False
    if isinstance(cor, (int, float)):
        r, g, b = ((int(cor) >> 16) & 255) / 255, ((int(cor) >> 8) & 255) / 255, (int(cor) & 255) / 255
    else:
        vals = list(cor)
        if len(vals) == 1:
            r = g = b = vals[0]
        elif len(vals) == 4:  # CMYK
            c, m, y, k = vals
            r, g, b = (1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k)
        else:
            r, g, b = vals[:3]
    return min(r, g, b) >= 0.94


def _areas_ocultas(page: pymupdf.Page) -> tuple[list[tuple], int, int]:
    """Bounding boxes of hidden text, plus visible and hidden character counts."""
    imagens = [tuple(i["bbox"]) for i in page.get_image_info()]
    rect = page.rect
    ocultas: list[tuple] = []
    vis = ocu = 0
    for s in page.get_texttrace():
        n = len(s.get("chars", ()))
        bbox = tuple(s["bbox"])
        sobre_imagem = any(_bbox_dentro(bbox, im, folga=2) for im in imagens)
        invisivel = s.get("type") == 3 and not sobre_imagem
        fora = not _bbox_dentro(bbox, tuple(rect), folga=0)
        escondido = (
            invisivel
            or s.get("opacity", 1.0) == 0
            or s.get("size", 12) < 4
            or (_quase_branco(s.get("color")) and not sobre_imagem)
            or fora
        )
        if escondido:
            ocultas.append(bbox)
            ocu += n
        else:
            vis += n
    return ocultas, vis, ocu


def _blocos_visiveis(page: pymupdf.Page, ocultas: list[tuple]) -> tuple[list[_Bloco], str]:
    # flags=0: ligatures expanded, text outside the page kept (it is then marked hidden).
    d = page.get_text("dict", flags=0)
    blocos: list[_Bloco] = []
    texto_oculto: list[str] = []
    for b in d.get("blocks", []):
        if b.get("type") != 0:
            continue
        linhas = []
        tamanhos = []
        for ln in b.get("lines", []):
            partes = []
            for sp in ln.get("spans", []):
                t = sp.get("text", "")
                if not t.strip():
                    partes.append(t)
                    continue
                bb = tuple(sp["bbox"])
                if any(_bbox_dentro(bb, o, folga=0.5) for o in ocultas):
                    texto_oculto.append(t)
                    continue
                partes.append(t)
                tamanhos.append(sp.get("size", 0))
            linha = "".join(partes).strip()
            if linha:
                linhas.append(linha)
        if linhas:
            blocos.append(
                _Bloco(
                    bbox=tuple(b["bbox"]),
                    texto=_juntar_hifen(linhas),
                    tamanho=max(tamanhos) if tamanhos else 0,
                )
            )
    return blocos, " ".join(texto_oculto).strip()


def _ordenar(blocos: list[_Bloco], largura: float) -> tuple[list[_Bloco], bool]:
    """Reading order by columns. Returns (ordered blocks, page has two columns)."""
    if not blocos:
        return [], False
    meio = largura / 2
    margem = 0.04 * largura

    def lado(b: _Bloco) -> str:
        x0, _, x1, _ = b.bbox
        if x1 <= meio + margem:
            return "esq"
        if x0 >= meio - margem:
            return "dir"
        return "cheio"

    total = sum(len(b.texto) for b in blocos) or 1
    esq = sum(len(b.texto) for b in blocos if lado(b) == "esq")
    dir_ = sum(len(b.texto) for b in blocos if lado(b) == "dir")
    duas = esq / total >= 0.2 and dir_ / total >= 0.2
    if not duas:
        return sorted(blocos, key=lambda b: (round(b.bbox[1], 0), b.bbox[0])), False
    ordem: list[_Bloco] = []
    faixa: list[_Bloco] = []
    for b in sorted(blocos, key=lambda b: (b.bbox[1], b.bbox[0])):
        if lado(b) == "cheio":
            ordem += sorted([x for x in faixa if lado(x) == "esq"], key=lambda x: x.bbox[1])
            ordem += sorted([x for x in faixa if lado(x) == "dir"], key=lambda x: x.bbox[1])
            faixa = []
            ordem.append(b)
        else:
            faixa.append(b)
    ordem += sorted([x for x in faixa if lado(x) == "esq"], key=lambda x: x.bbox[1])
    ordem += sorted([x for x in faixa if lado(x) == "dir"], key=lambda x: x.bbox[1])
    return ordem, True


def _linhas_celula(page: pymupdf.Page, rect) -> list[tuple[float, str]]:
    """Horizontal text lines inside a cell, as (vertical centre, text)."""
    out = []
    for b in page.get_text("dict", clip=pymupdf.Rect(rect), flags=0).get("blocks", []):
        for ln in b.get("lines", []):
            d = ln.get("dir", (1, 0))
            if abs(d[0] - 1) > 0.01:
                continue
            t = "".join(sp.get("text", "") for sp in ln.get("spans", [])).strip()
            if t:
                out.append(((ln["bbox"][1] + ln["bbox"][3]) / 2, t))
    return out


def _tabelas(page: pymupdf.Page) -> list[tuple[tuple, list[list[str]]]]:
    """Tables as a header row plus data rows, read cell by cell from the page geometry.

    ``Table.extract()`` loses decimal points in some PDFs and merges every line of a borderless
    table into one row; reading each cell with its own clip and splitting the lines of a row by
    vertical position keeps "9.94%" intact and gives one row per printed line.
    """
    try:
        achadas = page.find_tables()
    except Exception:  # pragma: no cover - table finder is best effort
        return []
    out = []
    for t in getattr(achadas, "tables", []):
        try:
            linhas_tab = t.rows
        except Exception:  # pragma: no cover
            continue
        if len(linhas_tab) < 2:
            continue
        cab = [" ".join(x for _, x in _linhas_celula(page, c)) if c else "" for c in linhas_tab[0].cells]
        dados: list[list[str]] = [cab]
        for row in linhas_tab[1:]:
            pontos = []
            for j, c in enumerate(row.cells):
                if c:
                    pontos += [(y, j, x) for y, x in _linhas_celula(page, c)]
            pontos.sort()
            grupos: list[list[tuple]] = []
            for p in pontos:
                if grupos and abs(grupos[-1][0][0] - p[0]) <= 3.0:
                    grupos[-1].append(p)
                else:
                    grupos.append([p])
            for g in grupos:
                linha = [""] * len(cab)
                for _, j, x in g:
                    if j < len(linha):
                        linha[j] = (linha[j] + " " + x).strip()
                if any(linha):
                    dados.append(linha)
        if len(dados) >= 3 and len(cab) >= 2:
            out.append((tuple(t.bbox), dados))
    return out


def _rotulo_impresso(page: pymupdf.Page, blocos: list[_Bloco]) -> str:
    try:
        rot = page.get_label()
    except Exception:  # pragma: no cover
        rot = ""
    if rot:
        return rot
    altura = page.rect.height
    for b in blocos:
        t = b.texto.strip()
        if re.fullmatch(r"\d{1,4}", t) and (b.bbox[3] < 0.1 * altura or b.bbox[1] > 0.88 * altura):
            return t
    return ""


def _processar_pagina(page: pymupdf.Page, numero: int, secao_atual: list[str]) -> _Pagina:
    ocultas, vis, ocu = _areas_ocultas(page)
    blocos, texto_oculto = _blocos_visiveis(page, ocultas)
    ordenados, duas = _ordenar(blocos, page.rect.width)
    tabelas = _tabelas(page)
    rotulo = _rotulo_impresso(page, blocos)

    unidades: list[dict] = []
    ordem = 0
    k = 0
    for b in ordenados:
        if any(_bbox_dentro(b.bbox, tb) for tb, _ in tabelas):
            continue
        cab = secao_canonica(b.texto) if len(b.texto) <= 60 else None
        if cab:
            secao_atual[0] = cab
        for frase in _FRASE.split(b.texto):
            frase = frase.strip()
            if not frase:
                continue
            k += 1
            unidades.append(
                {"uid": f"p{numero}.s{k}", "pagina": numero, "ordem": ordem, "tipo": "frase",
                 "secao": secao_atual[0], "texto": frase}
            )
            ordem += 1
    for t_idx, (_, dados) in enumerate(tabelas, start=1):
        cab = dados[0]
        for r_idx, linha in enumerate(dados[1:], start=1):
            pares = []
            for j, celula in enumerate(linha):
                if not celula:
                    continue
                nome = cab[j] if j < len(cab) and cab[j] else f"col{j + 1}"
                pares.append(f"{nome}: {celula}")
            if pares:
                unidades.append(
                    {"uid": f"p{numero}.t{t_idx}.r{r_idx}", "pagina": numero, "ordem": ordem,
                     "tipo": "linha_tabela", "secao": secao_atual[0], "texto": " | ".join(pares)}
                )
                ordem += 1

    texto = "\n\n".join(b.texto for b in ordenados)
    texto_bruto = "\n\n".join(b.texto for b in blocos)
    frac = ocu / (vis + ocu) if (vis + ocu) else 0.0
    return _Pagina(numero, rotulo, texto, texto_bruto, texto_oculto, frac, duas, unidades)


def _metadados(doc: pymupdf.Document, primeira: str, nome_arquivo: str) -> dict:
    meta = doc.metadata or {}
    titulo = (meta.get("title") or "").strip()
    if len(titulo) < 6 or titulo.lower().endswith((".pdf", ".doc", ".docx")):
        titulo = ""
    if not titulo and doc.page_count:
        # Largest horizontal font line in the top half of page 1 (skips rotated arXiv stamps).
        melhor = (0.0, "")
        meia = doc[0].rect.height * 0.6
        for b in doc[0].get_text("dict").get("blocks", []):
            for ln in b.get("lines", []):
                d = ln.get("dir", (1, 0))
                if abs(d[0] - 1) > 0.01 or ln["bbox"][1] > meia:
                    continue
                t = "".join(s["text"] for s in ln.get("spans", [])).strip()
                tam = max((s.get("size", 0) for s in ln.get("spans", [])), default=0)
                if len(t) > 8 and not re.match(r"arxiv:", t, re.I) and tam > melhor[0] + 0.1:
                    melhor = (tam, t)
        titulo = melhor[1]
    autores = (meta.get("author") or "").strip()
    limite = date.today().year + 1
    ano = None
    arx = re.search(r"arXiv:(\d{2})(\d{2})\.\d{4,5}", primeira[:6000])
    if arx and 7 <= int(arx.group(1)) <= limite % 100:
        ano = 2000 + int(arx.group(1))
    if ano is None:
        cabecalho = [int(a) for a in re.findall(r"\b(19[5-9]\d|20\d\d)\b", primeira[:600]) if int(a) <= limite]
        if cabecalho:
            ano = cabecalho[0]
    if ano is None:
        anos = [int(a) for a in re.findall(r"\b(19[5-9]\d|20\d\d)\b", primeira[:4000])]
        anos = [a for a in anos if a <= limite]
        if anos:
            ano = max(set(anos), key=anos.count)
    return {"titulo": titulo or Path(nome_arquivo).stem, "autores": autores, "ano": ano}


def _chave(con: sqlite3.Connection, meta: dict, nome_arquivo: str) -> str:
    base = ""
    if meta["autores"]:
        primeiro = re.split(r"[;,&]| and ", meta["autores"])[0].strip()
        if primeiro:
            base = _slug(primeiro.split()[-1])
    if not base:
        base = _slug(Path(nome_arquivo).stem)[:20] or "artigo"
    if meta["ano"] and not base.endswith(str(meta["ano"])):
        base = f"{base}{meta['ano']}"
    chave = base
    sufixo = ord("a")
    while con.execute("SELECT 1 FROM artigo WHERE chave=?", (chave,)).fetchone():
        chave = f"{base}{chr(sufixo)}"
        sufixo += 1
    return chave


def importar_pdf(projeto: Projeto, con: sqlite3.Connection, origem: Path) -> ResultadoImportacao:
    origem = Path(origem)
    if origem.suffix.lower() != ".pdf":
        return ResultadoImportacao(str(origem), "erro", mensagem="não é um arquivo .pdf")
    try:
        with open(origem, "rb") as fh:
            if fh.read(5) != b"%PDF-":
                return ResultadoImportacao(str(origem), "erro", mensagem="arquivo não é um PDF válido")
    except OSError as exc:
        return ResultadoImportacao(str(origem), "erro", mensagem=str(exc))
    h = sha256_arquivo(origem)
    dup = con.execute("SELECT chave FROM artigo WHERE hash_pdf=?", (h,)).fetchone()
    if dup:
        return ResultadoImportacao(str(origem), "duplicado", chave=dup[0],
                                   mensagem=f"mesmo conteúdo que {dup[0]}")
    try:
        doc = pymupdf.open(origem)
    except Exception as exc:
        return ResultadoImportacao(str(origem), "erro", mensagem=f"PDF ilegível: {exc}")
    if doc.needs_pass:
        return ResultadoImportacao(str(origem), "erro", mensagem="PDF protegido por senha")

    secao = [""]
    paginas = [_processar_pagina(doc[i], i + 1, secao) for i in range(doc.page_count)]
    meta = _metadados(doc, paginas[0].texto if paginas else "", origem.name)
    doc.close()

    n_chars = sum(len(p.texto) for p in paginas)
    sem_texto = n_chars < MIN_CHARS_ARTIGO or (paginas and n_chars / len(paginas) < MIN_CHARS_POR_PAGINA)
    vis_total = sum(len(p.texto) for p in paginas)
    oculto_total = sum(len(p.oculto) for p in paginas)
    frac_oculto = oculto_total / (vis_total + oculto_total) if (vis_total + oculto_total) else 0.0
    duas = sum(p.duas_colunas for p in paginas) >= max(1, len(paginas) * 0.3)
    secoes = sorted({u["secao"] for p in paginas for u in p.unidades if u["secao"]})
    n_tabelas = len({u["uid"].split(".r")[0] for p in paginas for u in p.unidades
                     if u["tipo"] == "linha_tabela"})

    with transacao(con):
        chave = _chave(con, meta, origem.name)
        destino = projeto.pdfs / f"{chave}.pdf"
        projeto.pdfs.mkdir(parents=True, exist_ok=True)
        shutil.copy2(origem, destino)
        pasta_txt = projeto.texto / chave
        pasta_txt.mkdir(parents=True, exist_ok=True)
        status = "sem_texto" if sem_texto else "pronto"
        cur = con.execute(
            """INSERT INTO artigo (chave, titulo, autores, ano, hash_pdf, caminho_pdf, nome_original,
               n_paginas, n_chars, tokens_estimados, duas_colunas, frac_oculto, n_tabelas, secoes,
               status, erro, importado_em) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (chave, meta["titulo"], meta["autores"], meta["ano"], h, projeto.rel(destino), origem.name,
             len(paginas), n_chars, estimar_tokens("\n".join(p.texto for p in paginas)), int(duas),
             frac_oculto, n_tabelas, jdump(secoes), status,
             "PDF sem camada de texto (escaneado?). OCR está fora do escopo." if sem_texto else None,
             agora()),
        )
        artigo_id = cur.lastrowid
        for p in paginas:
            arq = pasta_txt / f"p{p.numero:04d}.txt"
            arq_bruto = pasta_txt / f"p{p.numero:04d}.raw.txt"
            arq.write_text(p.texto, encoding="utf-8")
            arq_bruto.write_text(p.texto_bruto, encoding="utf-8")
            secao_pag = next((u["secao"] for u in p.unidades if u["secao"]), "")
            con.execute(
                """INSERT INTO pagina (artigo_id, numero, rotulo, caminho_texto, caminho_texto_bruto,
                   n_chars, frac_oculto, texto_oculto, secao) VALUES (?,?,?,?,?,?,?,?,?)""",
                (artigo_id, p.numero, p.rotulo, projeto.rel(arq), projeto.rel(arq_bruto),
                 len(p.texto), p.frac_oculto, p.oculto[:20000], secao_pag),
            )
            con.executemany(
                """INSERT INTO unidade (artigo_id, uid, pagina, ordem, tipo, secao, texto)
                   VALUES (?,?,?,?,?,?,?)""",
                [(artigo_id, u["uid"], u["pagina"], u["ordem"], u["tipo"], u["secao"], u["texto"])
                 for u in p.unidades],
            )
    msg = "sem camada de texto: bloqueado para extração" if sem_texto else ""
    if frac_oculto >= 0.001:
        msg = (msg + "; " if msg else "") + f"{frac_oculto:.1%} do texto está oculto e foi descartado"
    return ResultadoImportacao(str(origem), "sem_texto" if sem_texto else "importado", chave, msg)


def listar_pdfs(caminhos: list[Path]) -> list[Path]:
    out: list[Path] = []
    for c in caminhos:
        c = Path(c)
        if c.is_dir():
            out += sorted(p for p in c.rglob("*") if p.suffix.lower() == ".pdf" and p.is_file())
        elif c.is_file():
            out.append(c)
    return out


def textos_paginas(projeto: Projeto, con: sqlite3.Connection, artigo_id: int) -> dict[int, tuple[str, str]]:
    """{page number: (ordered visible text, raw-order visible text)}."""
    out = {}
    for r in con.execute(
        "SELECT numero, caminho_texto, caminho_texto_bruto FROM pagina WHERE artigo_id=? ORDER BY numero",
        (artigo_id,),
    ):
        txt = projeto.abs(r["caminho_texto"]).read_text(encoding="utf-8")
        bruto = projeto.abs(r["caminho_texto_bruto"]).read_text(encoding="utf-8")
        out[r["numero"]] = (txt, bruto)
    return out


def legibilidade(artigo: dict) -> float:
    """0..1 score from ingestion signals only (extraction signals are added in the report)."""
    if artigo["status"] != "pronto":
        return 0.0
    por_pag = artigo["n_chars"] / max(1, artigo["n_paginas"])
    s = min(1.0, por_pag / 1500)
    s *= 1.0 - min(1.0, artigo["frac_oculto"] * 5)
    return round(s, 3)
