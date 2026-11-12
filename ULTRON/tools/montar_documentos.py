"""Monta o TCC e o relatório técnico e gera as versões DOCX e PDF.

    python tools/montar_documentos.py            # monta TCC_SAFRA.md e gera DOCX + PDF dos dois documentos
    python tools/montar_documentos.py --so-md    # só monta docs/academic/TCC_SAFRA.md (não precisa de pandoc)

* **TCC:** junta ``docs/academic/NN_*.md`` em ordem, resolvendo as marcas
  ``<!-- incluir: CAMINHO | a partir de: TÍTULO [| nivel: N] [| numerar: X] -->`` (o documento técnico vira
  seção do capítulo, renumerada; fonte única, sem cópia) e corrigindo os caminhos relativos de imagens e links.
* **DOCX:** pandoc com um modelo de estilos gerado aqui (Arial 12, espaço 1,5, margens 3/2 cm, títulos em
  caixa alta, capa centralizada) e sumário automático (o Word atualiza os números de página ao abrir).
* **PDF:** pandoc → HTML com CSS de impressão → Chromium (Playwright), A4, com numeração de páginas.

Requisitos: pandoc 3.x; python-docx (modelo de estilos); Node com Playwright (PDF). A formatação segue as
recomendações gerais da ABNT para trabalhos acadêmicos, mas a conformidade com o manual da instituição precisa
ser conferida pelo autor.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DOCS = RAIZ / "docs"
ACAD = DOCS / "academic"
EXPORT = DOCS / "export"
INCLUIR = re.compile(r"<!--\s*incluir:\s*(?P<arq>[^|]+?)\s*\|\s*a partir de:\s*(?P<tit>[^|]+?)\s*"
                     r"(?:\|\s*nivel:\s*(?P<niv>\d)\s*)?(?:\|\s*numerar:\s*(?P<num>[A-Z0-9]+)\s*)?-->")
LINK = re.compile(r"(!?\[[^\]]*\]\()([^)\s]+)(\))")
TITULO = re.compile(r"^(#{1,6})\s+(.*)$")
NUM = re.compile(r"^(?:\d+(?:\.\d+)*\.?|[A-Z]\.\d+(?:\.\d+)*)\s+")


def _rebase(texto: str, origem: Path, destino: Path) -> str:
    def troca(m):
        alvo = m.group(2)
        if re.match(r"^(https?:|mailto:|#|/)", alvo):
            return m.group(0)
        caminho, _, ancora = alvo.partition("#")
        novo = os.path.relpath((origem / caminho).resolve(), destino.resolve()).replace(os.sep, "/")
        return m.group(1) + novo + (("#" + ancora) if ancora else "") + m.group(3)
    return LINK.sub(troca, texto)


def _renumerar(texto: str, prefixo: str, nivel_base: int) -> str:
    """Títulos do documento incluído viram subseções do capítulo: ## → prefixo.k, ### → prefixo.k.j."""
    saida, c2, c3, em_codigo = [], 0, 0, False
    menor = min((len(m.group(1)) for linha in texto.splitlines() if (m := TITULO.match(linha))), default=2)
    for linha in texto.splitlines():
        if linha.startswith("```"):
            em_codigo = not em_codigo
        m = None if em_codigo else TITULO.match(linha)
        if not m:
            saida.append(linha)
            continue
        nivel = len(m.group(1)) - menor + nivel_base
        titulo = NUM.sub("", m.group(2)).strip()
        if nivel == nivel_base:
            c2, c3 = c2 + 1, 0
            saida.append("#" * nivel + f" {prefixo}.{c2} {titulo}")
        elif nivel == nivel_base + 1:
            c3 += 1
            saida.append("#" * nivel + f" {prefixo}.{c2}.{c3} {titulo}")
        else:
            saida.append("#" * min(6, nivel) + " " + titulo)
    return "\n".join(saida)


def montar_tcc() -> Path:
    partes = []
    for arquivo in sorted(ACAD.glob("[0-9][0-9]_*.md")):
        texto = arquivo.read_text(encoding="utf-8")
        cap = re.search(r"^#\s+(\d+)\s", texto, re.M)

        def incluir(m, cap=cap):
            fonte = (arquivo.parent / m.group("arq").strip()).resolve()
            corpo = fonte.read_text(encoding="utf-8")
            inicio = corpo.find(m.group("tit").strip())
            if inicio < 0:
                raise SystemExit(f"{arquivo.name}: título '{m.group('tit')}' não encontrado em {fonte.name}")
            corpo = _rebase(corpo[inicio:], fonte.parent, ACAD)
            prefixo = m.group("num") or (cap.group(1) if cap else "0")
            return _renumerar(corpo, prefixo, int(m.group("niv") or 2))

        partes.append(INCLUIR.sub(incluir, texto).strip())
    tcc = ACAD / "TCC_SAFRA.md"
    aviso = ("<!-- Arquivo GERADO por tools/montar_documentos.py a partir de docs/academic/NN_*.md e dos documentos "
             "técnicos incluídos. Edite os capítulos, não este arquivo. -->\n\n")
    tcc.write_text(aviso + "\n\n".join(partes) + "\n", encoding="utf-8")
    return tcc


SUMARIO_MARCA = "<!-- sumário -->"


def _sumario_md(md: str) -> str:
    """Sumário em Markdown (títulos de nível 1 e 2 a partir do primeiro capítulo numerado)."""
    linhas, comecou, em_codigo = ["# SUMÁRIO {.unnumbered .sumario}", ""], False, False
    for linha in md.splitlines():
        if linha.startswith("```"):
            em_codigo = not em_codigo
        m = None if em_codigo else re.match(r"^(#{1,2})\s+(.+?)\s*$", linha)
        if not m:
            continue
        nivel, titulo = len(m.group(1)), m.group(2)
        if nivel == 1 and re.match(r"\d+\s", titulo):
            comecou = True
        if comecou and "SUMÁRIO" not in titulo:
            linhas.append(("    " if nivel == 2 else "") + "- " + titulo)
    return "\n".join(linhas) + "\n"


TOC_DOCX = ("\n```{=openxml}\n<w:p><w:pPr><w:pStyle w:val=\"TOCHeading\"/></w:pPr><w:r><w:t>SUMÁRIO</w:t></w:r></w:p>"
            "<w:p><w:r><w:fldChar w:fldCharType=\"begin\" w:dirty=\"true\"/></w:r><w:r><w:instrText xml:space=\"preserve\">"
            " TOC \\o \"1-2\" \\h \\z \\u </w:instrText></w:r><w:r><w:fldChar w:fldCharType=\"separate\"/></w:r>"
            "<w:r><w:t>Clique com o botão direito e escolha Atualizar campo para montar o sumário.</w:t></w:r>"
            "<w:r><w:fldChar w:fldCharType=\"end\"/></w:r></w:p>\n```\n")


# ------------------------------------------------------------------ DOCX
def _modelo_docx(destino: Path) -> Path:
    base = destino / "base.docx"
    subprocess.run(["pandoc", "-o", str(base), "--print-default-data-file", "reference.docx"], check=True)
    if not base.exists() or base.stat().st_size == 0:                 # pandoc antigo: só pela saída padrão
        with open(base, "wb") as f:
            subprocess.run(["pandoc", "--print-default-data-file", "reference.docx"], stdout=f, check=True)
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
    from docx.shared import Cm, Pt, RGBColor
    doc = Document(str(base))
    for secao in doc.sections:
        secao.page_height, secao.page_width = Cm(29.7), Cm(21.0)
        secao.top_margin, secao.left_margin = Cm(3), Cm(3)
        secao.bottom_margin, secao.right_margin = Cm(2), Cm(2)
    estilos = doc.styles
    por_nome = {s.name: s for s in estilos}          # o modelo do pandoc usa "Heading 1" como nome literal
    for nome in ("Normal", "Body Text", "First Paragraph", "Compact"):
        if nome in por_nome:
            st = por_nome[nome]
            st.font.name, st.font.size = "Arial", Pt(12)
            st.paragraph_format.line_spacing_rule = WD_LINE_SPACING.ONE_POINT_FIVE
            if nome in ("Body Text", "First Paragraph"):
                st.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                st.paragraph_format.first_line_indent = Cm(1.25)
    for nivel, tamanho in ((1, 12), (2, 12), (3, 12)):
        st = por_nome[f"Heading {nivel}"]
        st.font.name, st.font.size, st.font.bold = "Arial", Pt(tamanho), True
        st.font.color.rgb = RGBColor(0, 0, 0)
        st.font.all_caps = nivel == 1
    for nome in ("Table", "Compact", "Image Caption", "Table Caption"):
        if nome in por_nome:
            por_nome[nome].font.size = Pt(10)
    from docx.enum.style import WD_STYLE_TYPE
    capa = estilos.add_style("Capa", WD_STYLE_TYPE.PARAGRAPH)
    capa.base_style = por_nome["Normal"]
    capa.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    capa.font.bold = True
    modelo = destino / "modelo_abnt.docx"
    doc.save(str(modelo))
    return modelo


QUEBRA = "\n```{=openxml}\n<w:p><w:r><w:br w:type=\"page\"/></w:r></w:p>\n```\n"


def _para_docx(md: str) -> str:
    md = md.replace(SUMARIO_MARCA, TOC_DOCX)
    md = md.replace("<!-- quebra de página -->", QUEBRA)
    md = re.sub(r'<div class="(capa|folha-de-rosto)">', '::: {custom-style="Capa"}', md)
    md = md.replace("</div>", ":::")
    return md


def gerar_docx(md_path: Path, saida: Path, *, sumario: bool, titulo: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        modelo = _modelo_docx(tmp)
        inter = tmp / "entrada.md"
        inter.write_text(_para_docx(md_path.read_text(encoding="utf-8")), encoding="utf-8")
        cmd = ["pandoc", str(inter), "-f", "markdown+pipe_tables+raw_attribute+fenced_divs", "-o", str(saida),
               "--reference-doc", str(modelo), "--resource-path", f"{md_path.parent}:{DOCS}",
               "-M", f"title={titulo}", "-M", "lang=pt-BR", "--columns=4000"]
        subprocess.run(cmd, check=True)


# ------------------------------------------------------------------ PDF (HTML + Chromium)
CSS = """
@page { size: A4; margin: 3cm 2cm 2cm 3cm; }
body { font-family: Arial, 'Liberation Sans', sans-serif; font-size: 12pt; line-height: 1.5; color: #000; }
p { text-align: justify; text-indent: 1.25cm; margin: 0 0 6pt; }
li p, td p, blockquote p { text-indent: 0; }
.capa p, .folha-de-rosto p { text-indent: 0; text-align: center; }
.folha-de-rosto blockquote { margin: 18pt 0 18pt 8cm; } .folha-de-rosto blockquote p { text-align: justify; }
h1 { font-size: 12pt; text-transform: uppercase; page-break-before: always; margin: 0 0 18pt; }
h2, h3, h4 { font-size: 12pt; margin: 18pt 0 6pt; page-break-after: avoid; }
table { border-collapse: collapse; width: 100%; font-size: 9.5pt; line-height: 1.25; margin: 6pt 0 12pt;
        page-break-inside: auto; }
th, td { border: 1px solid #777; padding: 3pt 4pt; vertical-align: top; text-align: left; }
tr { page-break-inside: avoid; }
img { max-width: 100%; max-height: 19cm; display: block; margin: 6pt auto; }
figure { margin: 6pt 0 12pt; page-break-inside: avoid; } figcaption { font-size: 10pt; text-align: center; }
code, pre { font-family: 'DejaVu Sans Mono', monospace; font-size: 9pt; }
pre { white-space: pre-wrap; background: #f4f4f4; padding: 6pt; }
blockquote { margin: 6pt 0 6pt 4cm; font-size: 10pt; line-height: 1.2; }
.capa, .folha-de-rosto { text-align: center; min-height: 23cm; }
h1.sumario + ul, h1.sumario ~ ul { list-style: none; padding-left: 0; } ul ul { list-style: none; }
.quebra { page-break-after: always; }
nav#TOC { page-break-after: always; } nav#TOC ul { list-style: none; padding-left: 1.2em; }
nav#TOC > ul { padding-left: 0; } nav#TOC a { color: #000; text-decoration: none; }
a { color: #000; }
"""


def gerar_pdf(md_path: Path, saida: Path, *, sumario: bool, titulo: str) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        md = md_path.read_text(encoding="utf-8")
        md = md.replace(SUMARIO_MARCA, _sumario_md(md) if sumario else "")
        md = md.replace("<!-- quebra de página -->", '<div class="quebra"></div>')
        inter = tmp / "entrada.md"
        inter.write_text(md, encoding="utf-8")
        css = tmp / "impressao.css"
        css.write_text(CSS, encoding="utf-8")
        html = tmp / "doc.html"
        cmd = ["pandoc", str(inter), "-f", "markdown+pipe_tables", "-s", "--embed-resources", "-c", str(css),
               "--resource-path", f"{md_path.parent}:{DOCS}", "-M", f"title={titulo}", "-M", "lang=pt-BR", "--columns=4000",
               "--metadata", "pagetitle=" + titulo, "-o", str(html)]
        subprocess.run(cmd, check=True)
        txt = html.read_text(encoding="utf-8")
        txt = re.sub(r'<header id="title-block-header">.*?</header>', "", txt, flags=re.S)   # a capa já tem título
        html.write_text(txt, encoding="utf-8")
        script = tmp / "pdf.js"
        script.write_text("""
const { chromium } = require('playwright');
(async () => {
  const [entrada, saida] = process.argv.slice(2);
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + entrada, { waitUntil: 'load' });
  await p.pdf({ path: saida, format: 'A4', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: '<span></span>',
    footerTemplate: '<div style="width:100%;font-size:9px;text-align:right;padding-right:2cm;font-family:Arial">' +
                    '<span class="pageNumber"></span></div>' });
  await b.close();
})().catch((e) => { console.error(e); process.exit(1); });
""", encoding="utf-8")
        subprocess.run(["node", str(script), str(html), str(saida)], check=True)


def main() -> int:
    tcc = montar_tcc()
    print(f"montado: {tcc.relative_to(RAIZ)}")
    if "--so-md" in sys.argv:
        return 0
    if not shutil.which("pandoc"):
        print("pandoc não encontrado: só o Markdown foi montado")
        return 1
    EXPORT.mkdir(exist_ok=True)
    trabalhos = [(tcc, "TCC_SAFRA", True, "SAFRA — Trabalho de Conclusão de Curso"),
                 (DOCS / "technical" / "RELATORIO_TECNICO.md", "RELATORIO_TECNICO_SAFRA", False,
                  "Relatório técnico de desenvolvimento e evolução do SAFRA")]
    for origem, nome, sumario, titulo in trabalhos:
        gerar_docx(origem, EXPORT / f"{nome}.docx", sumario=sumario, titulo=titulo)
        print(f"gerado: docs/export/{nome}.docx")
        try:
            gerar_pdf(origem, EXPORT / f"{nome}.pdf", sumario=sumario, titulo=titulo)
            print(f"gerado: docs/export/{nome}.pdf")
        except (subprocess.CalledProcessError, FileNotFoundError) as exc:
            print(f"PDF não gerado ({exc}); o DOCX pode ser exportado para PDF pelo Word ou LibreOffice")
    return 0


if __name__ == "__main__":
    sys.exit(main())
