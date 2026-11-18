"""Synthetic PDFs for tests. Each builder returns the path of a PDF written in *pasta*."""

from __future__ import annotations

from pathlib import Path

import pymupdf

METODOS = (
    "We conducted a randomized controlled trial in three public schools. "
    "A total of 212 participants completed the protocol. "
    "Students were assigned to the intervention group (n = 106) or the control group (n = 106). "
    "Data were collected with a validated questionnaire and classroom observation."
)
RESULTADOS = (
    "The intervention improved engagement scores by 12 points. "
    "Effects were larger among first-year students. "
    "No adverse events were reported."
)
LIMITACOES = "The main limitation is the short follow-up of eight weeks."


def _texto(page: pymupdf.Page, rect, texto: str, tamanho: float = 10, **kw) -> None:
    x0, y0, x1, y1 = rect
    y1 = max(y1, y0 + tamanho * 1.6)
    while page.insert_textbox(pymupdf.Rect(x0, y0, x1, y1), texto, fontsize=tamanho,
                              fontname="helv", **kw) < 0:
        y1 += tamanho
        assert y1 < page.rect.height, f"texto não coube: {texto[:40]}"


def artigo_simples(
    pasta: Path,
    nome: str = "silva2021.pdf",
    autor: str = "Ana Silva",
    titulo: str = "LLM tutors in public schools",
    ano: int = 2021,
    metodos: str = METODOS,
    resultados: str = RESULTADOS,
    oculto: str | None = None,
    paginas_extra: int = 0,
) -> Path:
    doc = pymupdf.open()
    doc.set_metadata({"title": titulo, "author": autor})
    p1 = doc.new_page()
    _texto(p1, (72, 60, 540, 100), titulo, 16)
    _texto(p1, (72, 100, 540, 130), f"{autor} - Journal of Education Research, {ano}", 9)
    _texto(p1, (72, 150, 540, 170), "Abstract", 12)
    _texto(p1, (72, 175, 540, 260), "This study evaluates large language model tutors in schools. "
           "Engagement improved in the intervention group.")
    _texto(p1, (72, 280, 540, 300), "1. Introduction", 12)
    _texto(p1, (72, 305, 540, 400), "Tutoring is costly. Language models may reduce costs. "
           "Prior studies relied on convenience samples.")
    if oculto:
        _texto(p1, (72, 420, 540, 460), oculto, 10, color=(1, 1, 1))
    p2 = doc.new_page()
    _texto(p2, (72, 60, 540, 80), "2. Methods", 12)
    _texto(p2, (72, 85, 540, 220), metodos)
    _texto(p2, (72, 240, 540, 260), "3. Results", 12)
    _texto(p2, (72, 265, 540, 360), resultados)
    _texto(p2, (72, 380, 540, 400), "4. Limitations", 12)
    _texto(p2, (72, 405, 540, 460), LIMITACOES)
    _texto(p2, (290, 760, 320, 780), "212", 8)
    for i in range(paginas_extra):
        p = doc.new_page()
        _texto(p, (72, 60, 540, 700), f"Additional discussion paragraph number {i}. " * 20)
    destino = Path(pasta) / nome
    doc.save(destino)
    doc.close()
    return destino


def artigo_duas_colunas(pasta: Path, nome: str = "lu2023.pdf") -> Path:
    doc = pymupdf.open()
    doc.set_metadata({"title": "Quiz generation with language models", "author": "Lu Wang"})
    p = doc.new_page()
    _texto(p, (50, 40, 560, 70), "Quiz generation with language models", 16)
    esquerda = ("Methods. We ran a quasi-experimental study with 48 instructors. "
                "Each instructor designed quizzes with and without the tool. ") * 4
    direita = ("Results. Instructors rated tool quizzes higher on clarity. "
               "The average rating rose from 3.1 to 4.2 on a five point scale. ") * 4
    _texto(p, (50, 90, 295, 700), esquerda)
    _texto(p, (315, 90, 560, 700), direita)
    destino = Path(pasta) / nome
    doc.save(destino)
    doc.close()
    return destino


def artigo_com_tabela(pasta: Path, nome: str = "hill2008.pdf") -> Path:
    doc = pymupdf.open()
    doc.set_metadata({"title": "Teacher knowledge survey", "author": "Heather Hill"})
    p = doc.new_page()
    _texto(p, (72, 50, 540, 80), "Teacher knowledge survey", 16)
    _texto(p, (72, 90, 540, 110), "Methods", 12)
    _texto(p, (72, 115, 540, 170), "The sample characteristics are shown in Table 1. "
           "Teachers were drawn from 15 districts. 2008.")
    linhas = [["Group", "n", "Mean age"], ["Elementary", "400", "41"], ["Middle", "240", "39"],
              ["Total", "640", "40"]]
    x0, y0, w, h = 72, 200, 150, 22
    for i, linha in enumerate(linhas):
        for j, cel in enumerate(linha):
            r = pymupdf.Rect(x0 + j * w, y0 + i * h, x0 + (j + 1) * w, y0 + (i + 1) * h)
            p.draw_rect(r, color=(0, 0, 0), width=0.8)
            p.insert_textbox(r + (4, 5, -4, 0), cel, fontsize=9, fontname="helv")
    _texto(p, (72, 320, 540, 420), "A sample of teachers drawn from the study completed the survey. "
           "Response rate was high across districts and the instrument showed good reliability.")
    destino = Path(pasta) / nome
    doc.save(destino)
    doc.close()
    return destino


def artigo_escaneado(pasta: Path, nome: str = "scan1999.pdf") -> Path:
    """An image-only PDF (no text layer)."""
    src = pymupdf.open()
    sp = src.new_page()
    _texto(sp, (72, 72, 540, 400), METODOS * 3, 11)
    pix = sp.get_pixmap(dpi=60)
    src.close()
    doc = pymupdf.open()
    p = doc.new_page()
    p.insert_image(p.rect, pixmap=pix)
    destino = Path(pasta) / nome
    doc.save(destino)
    doc.close()
    return destino
